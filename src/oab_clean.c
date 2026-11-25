/* SPDX-License-Identifier: MIT
 * Open Audio Bridge: adaptive, stereo-linked clean gain and peak protection.
 * The volume law sets a maximum requested gain, while a perceptual peak
 * budget preserves the volume progression of material with little headroom.
 * One broadband gain envelope is applied to delayed, otherwise unchanged PCM.
 * There is no compressor or audio-path EQ here, and no per-band rescaling.
 * All workspaces and 4x interpolator coefficients are created on instantiate.
 */
#include "mini_ladspa.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

#define PI 3.1415926535897932384626433832795
#define TAPS 64
#define CENTER 31
#define PHASES 3

enum { IN_L, IN_R, OUT_L, OUT_R, VOL_L, VOL_R, CURVE, DRIVE, CEILING, PORTS };
typedef struct {
    LADSPA_Data *port[PORTS];
    unsigned long delay, ramp, delay_pos, ramp_pos, hold_samples, hold, silence_samples, silent;
    unsigned history_pos;
    float history[2][2*TAPS];
    float fir[PHASES][TAPS];
    float *audio[2];
    double *gain_window;
    double gain_sum, peak, decay, balance[2], balance_step;
} Clean;

static double clamp(double x, double low, double high, double invalid) {
    if (!isfinite(x)) return invalid;
    return fmax(low, fmin(high, x));
}
static double db_gain(double db) { return pow(10., db/20.); }
static void cleanup(LADSPA_Handle h) {
    Clean *p = h;
    if (!p) return;
    free(p->audio[0]); free(p->audio[1]); free(p->gain_window); free(p);
}
static LADSPA_Handle create(const LADSPA_Descriptor *d, unsigned long rate) {
    (void)d;
    if (rate < 8000 || rate > 768000) return NULL;
    Clean *p = calloc(1, sizeof(*p));
    if (!p) return NULL;
    /* The 4 ms finite gain ramp must complete before its detected peak
     * reaches the output. The interpolator estimates a signal 31 samples in
     * the past: add its delay, plus a further 2 ms of safety/lookahead. */
    p->ramp = (unsigned long)ceil(.004 * rate);
    p->delay = p->ramp + (unsigned long)ceil(.002 * rate) + CENTER + 2;
    /* Hold across rhythm transients, then release over musical phrases rather
     * than restoring gain between individual drums. */
    p->hold_samples = (unsigned long)ceil(.300 * rate);
    p->decay = exp(-1. / (4.0 * rate));
    p->silence_samples = 2 * rate;
    p->balance_step = 1. - exp(-1. / (.010 * rate));
    p->audio[0] = calloc(p->delay, sizeof(float));
    p->audio[1] = calloc(p->delay, sizeof(float));
    p->gain_window = calloc(p->ramp, sizeof(double));
    if (!p->audio[0] || !p->audio[1] || !p->gain_window) {
        cleanup(p); return NULL;
    }
    /* Estimate 1/4, 1/2 and 3/4 sample phases using a Blackman-windowed
     * bandlimited sinc. Phase zero is already represented by the samples.
     * Normalize DC response independently in each polyphase branch. */
    for (unsigned q=0;q<PHASES;q++) {
        double phase = (q+1.)/4., sum=0.;
        for (unsigned j=0;j<TAPS;j++) {
            double x=(TAPS-1.)-CENTER-j+phase;
            double w=fabs(x)<TAPS/2. ? .42+.5*cos(PI*x/(TAPS/2.))+.08*cos(2.*PI*x/(TAPS/2.)) : 0.;
            double c=fabs(x)<1e-12 ? w : w*sin(PI*x)/(PI*x);
            p->fir[q][j]=(float)c;
            sum+=c;
        }
        for (unsigned j=0;j<TAPS;j++) p->fir[q][j]=(float)(p->fir[q][j]/sum);
    }
    return p;
}
static void connect(LADSPA_Handle h, unsigned long n, LADSPA_Data *data) {
    Clean *p=h;
    if (p && n<PORTS) p->port[n]=data;
}
static void activate(LADSPA_Handle h) {
    Clean *p=h;
    if (!p) return;
    memset(p->history,0,sizeof(p->history));
    memset(p->audio[0],0,p->delay*sizeof(float));
    memset(p->audio[1],0,p->delay*sizeof(float));
    memset(p->gain_window,0,p->ramp*sizeof(double));
    p->delay_pos=p->ramp_pos=p->history_pos=p->hold=p->silent=0;
    p->gain_sum=p->peak=p->balance[0]=p->balance[1]=0.;
}
static double true_peak(Clean *p, float l, float r) {
    const unsigned pos=p->history_pos;
    p->history[0][pos]=p->history[0][pos+TAPS]=l;
    p->history[1][pos]=p->history[1][pos+TAPS]=r;
    p->history_pos=(pos+1)%TAPS;
    const float *left=p->history[0]+pos+1;
    const float *right=p->history[1]+pos+1;
    double peak=fmax(fabs((double)l),fabs((double)r));
    for (unsigned q=0;q<PHASES;q++) {
        double a=0., b=0.;
        for (unsigned j=0;j<TAPS;j++) {
            a+=(double)left[j]*p->fir[q][j];
            b+=(double)right[j]*p->fir[q][j];
        }
        peak=fmax(peak,fmax(fabs(a),fabs(b)));
    }
    return peak;
}
static void process(LADSPA_Handle h, unsigned long count) {
    Clean *p=h;
    if (!p || !p->port[IN_L] || !p->port[IN_R] || !p->port[OUT_L] || !p->port[OUT_R]) return;
    double l=clamp(p->port[VOL_L]?*p->port[VOL_L]:0.,0.,1.5,0.);
    double r=clamp(p->port[VOL_R]?*p->port[VOL_R]:0.,0.,1.5,0.);
    double m=fmax(l,r), mapped=m;
    const int boost=p->port[CURVE] && isfinite(*p->port[CURVE]) && *p->port[CURVE]>=.5f;
    if (boost) mapped=m<=.2?2.*m:m+.2;
    double max_volume=mapped*mapped*mapped;
    const double bal[2]={m>0.?pow(l/m,3.):0.,m>0.?pow(r/m,3.):0.};
    double requested=max_volume*db_gain(clamp(p->port[DRIVE]?*p->port[DRIVE]:0.,0.,18.,0.));
    double ceiling=db_gain(clamp(p->port[CEILING]?*p->port[CEILING]:-1.5,-12.,-1.,-1.5));
    /* Mastered material has little headroom. Instead of driving it into a
     * limiter at every volume, reserve a progressively larger *peak budget*
     * as the slider rises towards 100%. Quiet material receives the full
     * requested cubic gain (up to +18 dB drive) whenever it fits the budget.
     * Above 100%, extra gain remains available for quiet material only. */
    /* A small extra margin for interpolation error and peaks between phases. */
    double budget=ceiling*db_gain(-.4)*pow(fmin(1.,mapped/(boost?1.2:1.)),1.5);
    unsigned long apos=p->delay_pos, gpos=p->ramp_pos;
    double sum=p->gain_sum;
    if (m==0.) {
        /* Mute is exact and immediate, even with delayed audio in the ring. */
        memset(p->gain_window,0,p->ramp*sizeof(double));
        sum=0.;
    }
    for (unsigned long i=0;i<count;i++) {
        float x=p->port[IN_L][i], y=p->port[IN_R][i];
        if (!isfinite(x)) x=0.f;
        if (!isfinite(y)) y=0.f;
        double peak=true_peak(p,x,y);
        /* A new listening session may be quiet after a genuinely silent gap.
         * Never reset on an ordinary quiet phrase: both channels must remain
         * below -140 dBFS for two seconds, including the interpolated peak. */
        if (peak<=1e-7) {
            if (p->silent<p->silence_samples) p->silent++;
            if (p->silent==p->silence_samples) { p->peak=0.; p->hold=0; }
        } else p->silent=0;
        /* A long, held envelope keeps gain stable across bass cycles and
         * avoids the old per-peak flattening of louder music. A new peak caps
         * future output before it is actually emitted thanks to lookahead. */
        if (peak>=p->peak) {
            p->peak=peak; p->hold=p->hold_samples;
        } else if (p->hold) {
            p->hold--;
        } else {
            p->peak=fmax(peak,p->peak*p->decay);
            if (p->peak<1e-20) p->peak=0.;
        }
        double desired=p->peak>0.?fmin(requested,budget/p->peak):requested;
        sum+=desired-p->gain_window[gpos];
        p->gain_window[gpos]=desired;
        if (++gpos==p->ramp) gpos=0;
        double gain=fmax(0.,sum/p->ramp);
        /* Smooth the balance ratio separately so the same common gain is
         * applied to both channels. Zero-valued channels mute immediately. */
        for (unsigned c=0;c<2;c++) {
            if (bal[c]==0.) p->balance[c]=0.;
            else p->balance[c]+=p->balance_step*(bal[c]-p->balance[c]);
        }
        double out_l=(double)p->audio[0][apos]*gain*p->balance[0];
        double out_r=(double)p->audio[1][apos]*gain*p->balance[1];
        p->audio[0][apos]=x; p->audio[1][apos]=y;
        if (++apos==p->delay) apos=0;
        /* Last-resort numerical sample guard, not an ordinary waveform
         * shaper. The lookahead and interpolation margin normally keep it
         * idle. This also protects on extreme/invalid stream transitions. */
        double out_peak=fmax(fabs(out_l),fabs(out_r));
        if (out_peak>ceiling) {
            double protect=ceiling/out_peak;
            out_l*=protect;out_r*=protect;
        }
        p->port[OUT_L][i]=(float)out_l;
        p->port[OUT_R][i]=(float)out_r;
    }
    p->delay_pos=apos; p->ramp_pos=gpos; p->gain_sum=sum;
}
static const LADSPA_PortDescriptor descriptors[PORTS]={9,9,10,10,5,5,5,5,5};
static const char *const names[PORTS]={"Input L","Input R","Output L","Output R",
    "Volume L","Volume R","Curve","Drive (dB)","Ceiling (dB)"};
static const LADSPA_PortRangeHint hints[PORTS]={{0,0,0},{0,0,0},{0,0,0},{0,0,0},
    {3,0,1.5f},{3,0,1.5f},{3,0,1},{3,0,18},{3,-12,-1}};
static const LADSPA_Descriptor descriptor={795417,"oab_clean_gain",LADSPA_PROPERTY_HARD_RT_CAPABLE,
    "Open Audio Bridge adaptive clean gain","Open Audio Bridge project","MIT",PORTS,
    descriptors,names,hints,NULL,create,connect,activate,process,NULL,NULL,NULL,cleanup};
const LADSPA_Descriptor *ladspa_descriptor(unsigned long i) {
    return i==0?&descriptor:NULL;
}

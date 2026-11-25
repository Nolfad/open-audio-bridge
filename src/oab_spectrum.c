/* SPDX-License-Identifier: MIT
 * Open Audio Bridge spectrum meter. Reads only an anonymous pipe of stereo
 * float32 PCM at 48 kHz. Outputs ten octave-band RMS dBFS energy values as a
 * JSON array per 2048 frames, never a recording. Channel powers are averaged,
 * not samples summed, so opposite stereo phases do not disappear.
 */
#include <math.h>
#include <stdio.h>
#include <string.h>

#define PI 3.1415926535897932384626433832795
#define N 4096
#define HOP (N / 2)
#define BINS (N / 2 + 1)
#define BANDS 10
#define RATE 48000.
#define FLOOR_DB (-80.)

static const double centers[BANDS]={31.5,63.,125.,250.,500.,1000.,2000.,4000.,8000.,16000.};
static float frames[N][2];
static double window[N], real[N], imag[N], twiddle_re[N/2], twiddle_im[N/2];
static double power[BINS], weights[BANDS][BINS];
static unsigned reverse[N];
static double normalization;

_Static_assert(sizeof(float)==4, "float32 PCM required");

static void prepare(void) {
    double window_power=0.;
    for (unsigned i=0;i<N;i++) {
        window[i]=.5-.5*cos(2.*PI*i/(N-1)); /* Hann; correct its energy below. */
        window_power+=window[i]*window[i];
        unsigned x=i,r=0;
        for (unsigned n=N;n>1;n>>=1) { r=(r<<1)|(x&1); x>>=1; }
        reverse[i]=r;
    }
    for (unsigned k=0;k<N/2;k++) {
        double angle=-2.*PI*k/N;
        twiddle_re[k]=cos(angle);twiddle_im[k]=sin(angle);
    }
    /* Parseval: one-sided FFT energy, corrected for Hann power, divided by
     * two channels. A full-scale sine in both channels measures -3.01 dBFS. */
    normalization=1./(2.*N*window_power);
    const double df=RATE/N;
    for (unsigned b=0;b<BANDS;b++) {
        double lower=b?sqrt(centers[b-1]*centers[b]):centers[b]/sqrt(2.);
        double upper=b+1<BANDS?sqrt(centers[b]*centers[b+1]):centers[b]*sqrt(2.);
        for (unsigned k=0;k<BINS;k++) {
            /* Fractional bin overlap avoids sharp artificial jumps when a
             * frequency crosses an octave edge between two FFT bins. */
            double a=fmax(0.,(k-.5)*df), z=fmin(RATE/2.,(k+.5)*df);
            double overlap=fmin(z,upper)-fmax(a,lower);
            if (overlap>0.) weights[b][k]=overlap/(z-a);
        }
    }
}

static void transform(unsigned channel) {
    /* Put windowed samples directly into bit-reversed order. */
    for (unsigned i=0;i<N;i++) {
        float sample=frames[i][channel];
        real[reverse[i]]=isfinite(sample)?(double)sample*window[i]:0.;
        imag[reverse[i]]=0.;
    }
    for (unsigned length=2;length<=N;length*=2) {
        unsigned half=length/2,stride=N/length;
        for (unsigned start=0;start<N;start+=length) {
            for (unsigned j=0;j<half;j++) {
                unsigned a=start+j,b=a+half,k=j*stride;
                double tr=real[b]*twiddle_re[k]-imag[b]*twiddle_im[k];
                double ti=real[b]*twiddle_im[k]+imag[b]*twiddle_re[k];
                double ar=real[a],ai=imag[a];
                real[a]=ar+tr;imag[a]=ai+ti;
                real[b]=ar-tr;imag[b]=ai-ti;
            }
        }
    }
    for (unsigned k=0;k<BINS;k++) {
        double e=real[k]*real[k]+imag[k]*imag[k];
        power[k]+=(k==0||k==N/2)?e:2.*e;
    }
}

static int emit(void) {
    memset(power,0,sizeof(power));
    transform(0);transform(1);
    if (putchar('[')==EOF) return 0;
    for (unsigned b=0;b<BANDS;b++) {
        double energy=0.;
        for (unsigned k=0;k<BINS;k++) energy+=power[k]*weights[b][k];
        energy*=normalization;
        double db=energy>0.?10.*log10(energy):FLOOR_DB;
        if (!isfinite(db)||db<FLOOR_DB) db=FLOOR_DB;
        if (db>0.) db=0.;
        if (printf("%s%.2f",b?",":"",db)<0) return 0;
    }
    return puts("]")!=EOF && fflush(stdout)==0;
}

int main(void) {
    prepare();
    if (fread(frames,sizeof(frames[0]),N,stdin)!=N) return ferror(stdin)?1:0;
    do {
        if (!emit()) return 0;
        memmove(frames,frames+HOP,HOP*sizeof(frames[0]));
    } while (fread(frames+HOP,sizeof(frames[0]),HOP,stdin)==HOP);
    return ferror(stdin)?1:0;
}

/* SPDX-License-Identifier: MIT
 * Open Audio Bridge: linked stereo compressor + sample-peak limiter.
 * No dynamic allocation, file access or locks in the audio callback.
 * Not an emulation of any proprietary Windows APO.
 */
#include "mini_ladspa.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

#define OAB_MIN(a,b) ((a)<(b)?(a):(b))
#define OAB_MAX(a,b) ((a)>(b)?(a):(b))
enum { IN_L, IN_R, OUT_L, OUT_R, DRIVE, THRESHOLD, RATIO,
       ATTACK, RELEASE, CEILING, PORTS };

typedef struct {
  LADSPA_Data *port[PORTS];
  float sample_rate;
  float detector;
  float limiter_gain;
} OAB;

static float clampf(float x, float low, float high) {
  if (!isfinite(x)) return low;
  return OAB_MAX(low, OAB_MIN(high, x));
}
static float db_to_linear(float db) { return powf(10.0f, db / 20.0f); }
static float coeff(float sample_rate, float ms) {
  float time = OAB_MAX(0.1f, ms) / 1000.0f;
  return 1.0f - expf(-1.0f / (sample_rate * time));
}
static LADSPA_Handle create(const LADSPA_Descriptor *d, unsigned long rate) {
  (void)d;
  if (rate < 8000 || rate > 768000) return NULL;
  OAB *p = (OAB *)calloc(1, sizeof(*p));
  if (p) { p->sample_rate = (float)rate; p->limiter_gain = 1.0f; }
  return p;
}
static void connect(LADSPA_Handle h, unsigned long index, LADSPA_Data *data) {
  OAB *p=(OAB *)h;
  if (p && index < PORTS) p->port[index] = data;
}
static void activate(LADSPA_Handle h) {
  OAB *p=(OAB *)h;
  if (p) { p->detector=0.0f; p->limiter_gain=1.0f; }
}
static void process(LADSPA_Handle h, unsigned long samples) {
  OAB *p=(OAB *)h;
  if (!p || !p->port[IN_L] || !p->port[IN_R] ||
      !p->port[OUT_L] || !p->port[OUT_R]) return;
  const float drive = db_to_linear(clampf(p->port[DRIVE]?*p->port[DRIVE]:0, -12, 18));
  const float threshold = clampf(p->port[THRESHOLD]?*p->port[THRESHOLD]:-16,-48,0);
  const float ratio = clampf(p->port[RATIO]?*p->port[RATIO]:2.0f,1,12);
  const float attack_ms = clampf(p->port[ATTACK]?*p->port[ATTACK]:8,0.2f,100);
  const float release_ms=clampf(p->port[RELEASE]?*p->port[RELEASE]:180,10,2000);
  const float ceiling = db_to_linear(clampf(p->port[CEILING]?*p->port[CEILING]:-1.0f,-12,-0.1f));
  const float a=coeff(p->sample_rate,attack_ms), r=coeff(p->sample_rate,release_ms);
  const float limit_release=coeff(p->sample_rate,65.0f);
  const float knee=6.0f;
  const float slope=1.0f - 1.0f/ratio;
  float detector=p->detector, limit_gain=p->limiter_gain;
  for (unsigned long i=0;i<samples;i++) {
    float il=p->port[IN_L][i], ir=p->port[IN_R][i];
    /* Fail closed for invalid input samples. */
    if (!isfinite(il)) il=0.0f;
    if (!isfinite(ir)) ir=0.0f;
    float x=il*drive, y=ir*drive;
    float peak=OAB_MAX(fabsf(x),fabsf(y));
    detector += (peak>detector?a:r)*(peak-detector);
    float over=20.0f*log10f(OAB_MAX(1.0e-12f,detector))-threshold;
    float compressed_over=0;
    if (over>knee/2) compressed_over=over;
    else if (over>-knee/2) {
      float d=over+knee/2;
      compressed_over=d*d/(2*knee);
    }
    float g=db_to_linear(-slope*compressed_over);
    x*=g; y*=g;
    float amplified=OAB_MAX(fabsf(x),fabsf(y));
    float need=amplified>ceiling?ceiling/amplified:1.0f;
    if (need < limit_gain) limit_gain=need;
    else limit_gain += limit_release*(1.0f-limit_gain);
    limit_gain = OAB_MIN(limit_gain, need);
    /* Both channels share exactly the same gain: no artificial imbalance. */
    p->port[OUT_L][i]=x*limit_gain;
    p->port[OUT_R][i]=y*limit_gain;
  }
  p->detector=detector;
  p->limiter_gain=limit_gain;
}
static void destroy(LADSPA_Handle h){ free(h); }
static const LADSPA_PortDescriptor descriptors[PORTS]={
  9,9,10,10,5,5,5,5,5,5
};
static const char *const names[PORTS]={
  "Input L","Input R","Output L","Output R",
  "Drive (dB)","Threshold (dB)","Ratio","Attack (ms)","Release (ms)","Ceiling (dB)"
};
static const LADSPA_PortRangeHint hints[PORTS]={
  {0,0,0},{0,0,0},{0,0,0},{0,0,0},
  {3,-12,18},{3,-48,0},{3,1,12},{3,0.2f,100},{3,10,2000},{3,-12,-0.1f}
};
static const LADSPA_Descriptor descriptor = {
  795415, "oab_stereo_dynamics",LADSPA_PROPERTY_HARD_RT_CAPABLE,
  "Open Audio Bridge linked stereo dynamics", "Open Audio Bridge project",
  "MIT", PORTS,descriptors,names,hints,NULL,
  create,connect,activate,process,NULL,NULL,NULL,destroy
};
const LADSPA_Descriptor *ladspa_descriptor(unsigned long index) {
  return index==0?&descriptor:NULL;
}

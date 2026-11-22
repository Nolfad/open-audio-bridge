/* SPDX-License-Identifier: MIT
 * Volume law only: no extra drive, no compression, 0..100% unchanged; 100..150% adds gain before the final guard.
 * Capture volume controls are percentages (PipeWire scale=cubic).
 */
#include "mini_ladspa.h"
#include <math.h>
#include <stdlib.h>
enum { IL,IR,OL,OR,VL,VR,CURVE,NPORTS };
typedef struct { float *p[NPORTS]; double gain[2],step; } Volume;
static float unit(float x){return !isfinite(x)||x<0?0:x>1.5f?1.5f:x;}
static LADSPA_Handle create(const LADSPA_Descriptor *d,unsigned long rate){
 (void)d;if(rate<8000||rate>768000)return NULL;
 Volume *v=calloc(1,sizeof(*v));if(v)v->step=1-expf(-1.0f/(.01f*rate));return v;
}
static void connect(LADSPA_Handle h,unsigned long n,float *p){if(n<NPORTS)((Volume*)h)->p[n]=p;}
static void activate(LADSPA_Handle h){Volume *v=h;v->gain[0]=v->gain[1]=0;}
static void run(LADSPA_Handle h,unsigned long n){
 Volume *v=h;if(!v->p[IL]||!v->p[IR]||!v->p[OL]||!v->p[OR])return;
 float l=unit(v->p[VL]?*v->p[VL]:0),r=unit(v->p[VR]?*v->p[VR]:0);
 float m=fmaxf(l,r),mapped=m;
 if(v->p[CURVE]&&*v->p[CURVE]>=.5f)mapped=m<=.4f?2*m:m<=1?.8f+(m-.4f)/3:m;
 float common=m>0?mapped/m:0;
 float target[2]={powf(l*common,3),powf(r*common,3)};
 for(unsigned long i=0;i<n;i++)for(int c=0;c<2;c++){
  /* Zero volume must silence immediately, including residual smoothing. */
  if(target[c]==0)v->gain[c]=0;
  else v->gain[c]+=v->step*(target[c]-v->gain[c]);
  float x=v->p[c][i];v->p[c+2][i]=isfinite(x)?x*v->gain[c]:0;
 }
}
static void cleanup(LADSPA_Handle h){free(h);}
static const LADSPA_PortDescriptor ports[NPORTS]={9,9,10,10,5,5,5};
static const char *const names[NPORTS]={"Input L","Input R","Output L","Output R","Volume L","Volume R","Curve"};
static const LADSPA_PortRangeHint hints[NPORTS]={{0,0,0},{0,0,0},{0,0,0},{0,0,0},{3,0,1.5f},{3,0,1.5f},{3,0,1}};
static const LADSPA_Descriptor d={795416,"oab_volume_curve",LADSPA_PROPERTY_HARD_RT_CAPABLE,"Open Audio Bridge volume curve","Open Audio Bridge","MIT",NPORTS,ports,names,hints,NULL,create,connect,activate,run,NULL,NULL,NULL,cleanup};
const LADSPA_Descriptor *ladspa_descriptor(unsigned long i){return i?NULL:&d;}

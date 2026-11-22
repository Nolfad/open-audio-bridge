import ctypes as ct
import math,subprocess,tempfile,unittest
from pathlib import Path
from test_all import Descriptor,DPtr
ROOT=Path(__file__).resolve().parents[1]
class VolumeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();p=Path(cls.tmp.name)/'volume.so'
  subprocess.run(['gcc','-Wall','-Wextra','-Werror','-O2','-shared','-fPIC',str(ROOT/'src/oab_volume.c'),'-lm','-o',str(p)],check=True,capture_output=True)
  cls.lib=ct.CDLL(str(p));cls.lib.ladspa_descriptor.argtypes=[ct.c_ulong];cls.lib.ladspa_descriptor.restype=DPtr
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def render(self,l=.4,r=.4,curve=1,x=.5):
  d=self.lib.ladspa_descriptor(0);h=d.contents.instantiate(d,48000);n=len(x) if isinstance(x,list) else 48000
  ins=[(ct.c_float*n)(*(x if isinstance(x,list) else [x]*n)) for _ in range(2)];outs=[(ct.c_float*n)() for _ in range(2)]
  controls=[ct.c_float(v) for v in [l,r,curve]]
  for i,p in enumerate(ins+outs+[ct.pointer(v) for v in controls]):d.contents.connect_port(h,i,p)
  d.contents.activate(h);d.contents.run(h,n);result=[list(v) for v in outs];d.contents.cleanup(h);return result
 def test_forty_equals_old_sixty(self):
  l,r=self.render();self.assertAlmostEqual(l[-1],.5*.6**3,places=5);self.assertEqual(l,r)
 def test_curve_does_not_reshape_waveform(self):
  x=[.2*math.sin(2*math.pi*997*i/48000)+.05*math.sin(2*math.pi*113*i/48000) for i in range(96000)]
  left,_=self.render(x=x)
  self.assertLess(max(abs(a-b*.216) for a,b in zip(left[48000:],x[48000:])),1e-7)
 def test_zero_is_exact_silence(self):self.assertEqual(max(map(abs,self.render(0,0)[0])),0)
 def test_boost_continues_through_entire_range(self):
  for percent,original in [(1,2),(10,20),(20,40),(40,60),(50,70),(60,80),(80,100),(100,120),(125,145),(150,170)]:
   with self.subTest(percent=percent):
    self.assertAlmostEqual(self.render(percent/100,percent/100,x=.01)[0][-1],.01*(original/100)**3,places=6)
 def test_eighty_to_hundred_keeps_progression(self):
  low=self.render(.8,.8,x=.01)[0][-1];high=self.render(1,1,x=.01)[0][-1]
  self.assertAlmostEqual(high/low,(120/100)**3,places=5)
 def test_normal_curve(self):self.assertAlmostEqual(self.render(curve=0)[0][-1],.5*.4**3,places=5)
 def test_balance_ratio_preserved(self):
  l,r=self.render(.8,.4);self.assertAlmostEqual(l[-1]/r[-1],8,places=4)
 def test_invalid_control_mutes(self):self.assertEqual(max(map(abs,self.render(float('nan'),float('nan'))[0])),0)
 def test_150_amplifies_before_final_guard(self):self.assertAlmostEqual(self.render(1.5,1.5,x=.1)[0][-1],.4913,places=5)
 def test_above_150_clamped(self):self.assertAlmostEqual(self.render(2,2,x=.1)[0][-1],.4913,places=5)
if __name__=='__main__':unittest.main()

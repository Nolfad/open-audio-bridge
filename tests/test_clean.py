"""Exercise the actual adaptive gain LADSPA, including high-volume fidelity."""
import ctypes as ct
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_all import DPtr

ROOT = Path(__file__).resolve().parents[1]
CEILING = -1.5
PEAK = 10 ** (CEILING / 20)


def delay_samples(rate):
    # 4 ms gain ramp, 2 ms additional lookahead, plus interpolator group delay.
    return math.ceil(.004 * rate) + math.ceil(.002 * rate) + 31 + 2


def amplitude(samples, frequency, rate, offset=0):
    a = b = 0.
    for i, x in enumerate(samples):
        angle = 2 * math.pi * frequency * (i + offset) / rate
        a += x * math.cos(angle)
        b += x * math.sin(angle)
    return 2 * math.hypot(a, b) / len(samples)


@unittest.skipUnless(shutil.which('gcc'), 'gcc requerido para testes DSP')
class CleanGainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        binary = Path(cls.tmp.name) / 'clean.so'
        subprocess.run(['gcc', '-O2', '-std=c11', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        str(ROOT / 'src/oab_clean.c'), '-lm', '-o', str(binary)],
                       check=True, capture_output=True, text=True)
        cls.lib = ct.CDLL(str(binary))
        cls.lib.ladspa_descriptor.argtypes = [ct.c_ulong]
        cls.lib.ladspa_descriptor.restype = DPtr

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def render(self, left, right=None, *, rate=48000, volumes=(1,1), curve=1, drive=18,
               ceiling=CEILING, blocks=None, changes=None):
        if right is None:
            right = left
        n = len(left)
        self.assertEqual(n, len(right))
        d = self.lib.ladspa_descriptor(0)
        self.assertEqual(d.contents.Label, b'oab_clean_gain')
        self.assertEqual(d.contents.PortCount, 9)
        self.assertEqual([d.contents.PortNames[i] for i in range(9)], [
            b'Input L', b'Input R', b'Output L', b'Output R', b'Volume L', b'Volume R',
            b'Curve', b'Drive (dB)', b'Ceiling (dB)'])
        h = d.contents.instantiate(d, rate)
        self.assertTrue(h)
        bufs = [(ct.c_float * n)(*left), (ct.c_float * n)(*right),
                (ct.c_float * n)(), (ct.c_float * n)()]
        controls = [ct.c_float(v) for v in (*volumes, curve, drive, ceiling)]
        for i, ctrl in enumerate(controls, 4):
            d.contents.connect_port(h, i, ct.pointer(ctrl))
        d.contents.activate(h)
        try:
            start = 0
            k = 0
            block_sizes = blocks or [n]
            while start < n:
                if changes and start in changes:
                    for port, value in changes[start].items():
                        controls[port].value = value
                count = min(block_sizes[k % len(block_sizes)], n-start)
                for i, buf in enumerate(bufs):
                    ptr = ct.cast(ct.byref(buf, start * ct.sizeof(ct.c_float)), ct.POINTER(ct.c_float))
                    d.contents.connect_port(h, i, ptr)
                d.contents.run(h, count)
                start += count
                k += 1
            return list(bufs[2]), list(bufs[3])
        finally:
            d.contents.cleanup(h)

    def test_quiet_signals_keep_exact_cubic_curve_and_maximum_drive(self):
        x = [.005] * 12000
        for value, equivalent in ((0,0),(.1,.2),(.4,.6),(.8,1.),(1.,1.2),(1.5,1.7)):
            with self.subTest(value=value):
                l,r = self.render(x, volumes=(value,value))
                expected = x[-1] * 10**(18/20) * equivalent**3
                self.assertAlmostEqual(l[-1], expected, places=6)
                self.assertAlmostEqual(r[-1], expected, places=6)
        l,_ = self.render(x, volumes=(.4,.4), curve=0, drive=6)
        self.assertAlmostEqual(l[-1], .005*.4**3*10**(6/20), places=6)

    def test_loud_signal_remains_proportionate_to_slider_below_unity(self):
        x = [.9] * 96000
        l,_ = self.render(x, volumes=(.4,.4))
        high,_ = self.render(x, volumes=(.8,.8))
        self.assertAlmostEqual(l[-1]/high[-1], .6**1.5, places=5)
        full,_ = self.render(x, volumes=(1.,1.))
        self.assertLessEqual(full[-1], PEAK + 1e-6)
        self.assertGreater(full[-1], PEAK * .94)
        self.assertAlmostEqual(high[-1]/full[-1], (1/1.2)**1.5, places=5)

    def test_linked_stereo_preserves_channel_balance_and_mutes_zero_immediately(self):
        x = [.02] * 10000
        l,r = self.render(x, volumes=(.8,.4))
        self.assertAlmostEqual(l[-1]/r[-1], 8, places=4)
        l,r = self.render(x, volumes=(.8,.8), blocks=[2000], changes={6000:{0:0.,1:0.}})
        self.assertGreater(l[5999], 0)
        self.assertEqual(max(map(abs,l[6000:])), 0)
        self.assertEqual(max(map(abs,r[6000:])), 0)
        l,r = self.render(x, volumes=(.8,0.))
        self.assertGreater(l[-1], 0)
        self.assertEqual(max(map(abs,r)), 0)

    def test_multitone_does_not_wash_out_bass_or_treble_at_high_volume(self):
        rate=48000
        bands=(80,1000,8000)
        amps=(.55,.18,.10)
        x=[sum(a*math.sin(2*math.pi*f*i/rate) for f,a in zip(bands,amps)) for i in range(rate*2)]
        l,r=self.render(x, rate=rate, volumes=(1.0,1.0), blocks=[257,511,1024,64])
        self.assertEqual(l,r)
        self.assertLessEqual(max(map(abs,l)),PEAK+1e-6)
        clean=l[rate:]
        ratios=[amplitude(clean,f,rate)/a for f,a in zip(bands,amps)]
        self.assertLess(20*math.log10(max(ratios)/min(ratios)),.05,ratios)
        latency=delay_samples(rate)
        ref=x[rate-latency:len(x)-latency]
        gain=sum(a*b for a,b in zip(ref,clean))/sum(a*a for a in ref)
        err=math.sqrt(sum((b-a*gain)**2 for a,b in zip(ref,clean))/sum(b*b for b in clean))
        self.assertLess(err,.002,err)
        self.assertGreater(max(map(abs,clean)), PEAK*.85)

    def test_recurring_kicks_preserve_voice_dynamics_and_crest_factor(self):
        rate=48000
        n=rate*4
        beat=rate//2  # 120 BPM electronic track
        # Big bass kicks recur every .5 s; the voice has quiet and loud phrases.
        left=[];right=[]
        for i in range(n):
            t=(i%beat)/rate
            kick=.95*math.sin(2*math.pi*60*t)*math.exp(-t/.048) if t<.25 else 0.
            voice=(.025 if t<.25 else .10)*math.sin(2*math.pi*1000*i/rate)
            left.append(kick+voice*.25);right.append(voice)
        l,r=self.render(left,right, rate=rate, volumes=(1.,1.), blocks=[127,512,193])
        self.assertLessEqual(max(map(abs,l+r)),PEAK+1e-6)
        delay=delay_samples(rate)
        def rms(x):return math.sqrt(sum(a*a for a in x)/len(x))
        # Measure both phrases away from the kick attack and lookahead boundary.
        gains=[];contrasts=[]
        for b in range(2,7):
            ref=[];out=[]
            for start,end in ((.075,.20),(.38,.46)):
                a=b*beat+round(start*rate);z=b*beat+round(end*rate)
                ref.append(rms(right[a:z]));out.append(rms(r[a+delay:z+delay]))
                gains.append(out[-1]/ref[-1])
            contrasts.append(20*math.log10((out[1]/out[0])/(ref[1]/ref[0])))
        self.assertLess(20*math.log10(max(gains)/min(gains)),.5,gains)
        self.assertLess(max(map(abs,contrasts)),.5,contrasts)
        ref=left[beat*2:beat*7];out=l[beat*2+delay:beat*7+delay]
        crest_change=20*math.log10((max(map(abs,out))/rms(out))/(max(map(abs,ref))/rms(ref)))
        self.assertLess(abs(crest_change),.5,crest_change)

    def test_only_sustained_digital_silence_resets_peak_memory(self):
        rate=48000
        loud=[.9*math.sin(2*math.pi*1000*i/rate) for i in range(rate//2)]
        quiet=[.003*math.sin(2*math.pi*1000*i/rate) for i in range(rate//2)]
        def quiet_gain(gap):
            x=loud+gap+quiet
            out,_=self.render(x,rate=rate,volumes=(1.,1.))
            d=delay_samples(rate)
            start=len(loud)+len(gap)+rate//4
            stop=len(x)-d
            return max(map(abs,out[start+d:stop+d]))/.003
        brief=quiet_gain([0.]*rate)
        long_quiet=quiet_gain([1e-5]*int(2.1*rate))
        reset=quiet_gain([0.]*int(2.1*rate))
        requested=1.2**3*10**(18/20)
        self.assertLess(brief,requested*.35)
        self.assertLess(long_quiet,requested*.4)
        self.assertAlmostEqual(reset,requested,places=3)

    def test_true_peak_on_phase_offset_high_frequency_sine(self):
        rate=48000
        x=[math.sin(2*math.pi*12000*i/rate+math.pi/4) for i in range(rate)]
        l,_=self.render(x, rate=rate, volumes=(1.5,1.5))
        # At 4 samples/cycle and 45-degree phase, sample peaks underestimate the
        # actual reconstructed sine by 3.01 dB. Verify its reconstructed amplitude.
        true_amplitude=amplitude(l[rate//2:],12000,rate)
        self.assertLessEqual(true_amplitude, PEAK*1.002)
        self.assertGreater(true_amplitude, PEAK*.94)

    def test_lookahead_controls_loud_transients_before_they_are_emitted(self):
        rate=48000
        n=rate
        left=[.01*math.sin(2*math.pi*997*i/rate) if i<rate//2 else
              .9*math.sin(2*math.pi*12000*i/rate+math.pi/4) for i in range(n)]
        right=[.025*math.sin(2*math.pi*997*i/rate) for i in range(n)]
        l,r=self.render(left,right, rate=rate, volumes=(1.2,1.2), blocks=[33,512,17,1023])
        self.assertLessEqual(max(map(abs,l+r)),PEAK+1e-6)
        # Once the loud sine starts, even the very first 4-sample cycle is
        # protected, not hard-clipped at the first peak.
        at=rate//2+delay_samples(rate)
        self.assertLessEqual(max(map(abs,l[at:at+4]))*math.sqrt(2),PEAK*1.005)
        self.assertGreater(max(map(abs,r[rate//4:rate//2-1000])),.05)

    def test_blocks_sample_rates_and_invalid_inputs(self):
        for rate in (8000,44100,96000):
            with self.subTest(rate=rate):
                x=[.24*math.sin(2*math.pi*127*i/rate) for i in range(8000)]
                x[300]=float('nan');x[301]=float('inf');x[2400]=float('-inf');x[3200]=1e30
                one=self.render(x, rate=rate)
                many=self.render(x, rate=rate, blocks=[1,19,128,337])
                self.assertEqual(one,many)
                self.assertTrue(all(math.isfinite(y) for y in one[0]+one[1]))
                self.assertLessEqual(max(map(abs,one[0])),PEAK+1e-6)


if __name__=='__main__':
    unittest.main()

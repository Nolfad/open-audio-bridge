"""Tests for the original, optional adaptive stereo music LADSPA plugin."""
import ctypes as ct
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_all import DPtr

ROOT = Path(__file__).resolve().parents[1]


def tone_mix(rate, seconds, tones):
    return [sum(amplitude * math.sin(2 * math.pi * frequency * i / rate)
                for frequency, amplitude in tones)
            for i in range(round(rate * seconds))]


def amplitude(samples, frequency, rate):
    tail = samples[-rate:]
    a = b = 0.
    for i, value in enumerate(tail):
        angle = 2 * math.pi * frequency * i / rate
        a += value * math.cos(angle)
        b += value * math.sin(angle)
    return 2 * math.hypot(a, b) / len(tail)


@unittest.skipUnless(shutil.which('gcc'), 'gcc required for DSP tests')
class MusicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        binary = Path(cls.tmp.name) / 'music.so'
        subprocess.run(['gcc', '-O2', '-std=c11', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                        str(ROOT / 'src/oab_music.c'), '-lm', '-o', str(binary)],
                       check=True, capture_output=True, text=True)
        cls.lib = ct.CDLL(str(binary))
        cls.lib.ladspa_descriptor.argtypes = [ct.c_ulong]
        cls.lib.ladspa_descriptor.restype = DPtr

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def render(self, left, right=None, mode=0, width=0, rate=24000, blocks=None, changes=None):
        right = left if right is None else right
        n = len(left)
        self.assertEqual(len(right), n)
        d = self.lib.ladspa_descriptor(0)
        self.assertEqual(d.contents.Label, b'oab_music_enhance')
        self.assertEqual([d.contents.PortNames[i].decode() for i in range(6)],
                         ['Input L', 'Input R', 'Output L', 'Output R', 'Mode', 'Width (%)'])
        h = d.contents.instantiate(d, rate)
        self.assertTrue(h)
        buffers = [(ct.c_float*n)(*left), (ct.c_float*n)(*right),
                   (ct.c_float*n)(), (ct.c_float*n)()]
        controls = [ct.c_float(mode), ct.c_float(width)]
        for i, ctrl in enumerate(controls, 4):
            d.contents.connect_port(h, i, ct.pointer(ctrl))
        d.contents.activate(h)
        try:
            start = k = 0
            sizes = blocks or [n]
            while start < n:
                if changes and start in changes:
                    for port, value in changes[start].items():
                        controls[port].value = value
                count = min(sizes[k % len(sizes)], n-start)
                for i, buf in enumerate(buffers):
                    ptr = ct.cast(ct.byref(buf, start * ct.sizeof(ct.c_float)), ct.POINTER(ct.c_float))
                    d.contents.connect_port(h, i, ptr)
                d.contents.run(h, count)
                start += count
                k += 1
            return list(buffers[2]), list(buffers[3])
        finally:
            d.contents.cleanup(h)

    def test_off_is_exact_bypass_not_an_eq(self):
        x = tone_mix(24000, .2, [(63, .21), (997, .13), (8000, .17)])
        y = [v * .37 for v in reversed(x)]
        l, r = self.render(x, y, blocks=[31, 997, 123])
        self.assertEqual(l, [ct.c_float(v).value for v in x])
        self.assertEqual(r, [ct.c_float(v).value for v in y])

    def test_modes_make_gentle_enhancement_without_band_cuts(self):
        rate = 24000
        tones = [(63, .02), (997, .25), (6000, .025)]
        x = tone_mix(rate, 5, tones)
        w,_ = self.render(x, mode=1, rate=rate)
        e,_ = self.render(x, mode=2, rate=rate)
        gains = [[amplitude(samples, f, rate) / a for f,a in tones] for samples in (w,e)]
        for g in gains:
            self.assertGreater(g[0], 1.12)  # weak bass is enhanced
            self.assertGreater(g[2], 1.02)  # sparkle, not high-frequency cut
            self.assertGreaterEqual(g[1], .995)
            self.assertLess(max(g), 10**(3.5/20))
        self.assertGreater(gains[1][0], gains[0][0])
        self.assertGreater(gains[1][2], gains[0][2])

    def test_source_already_bass_rich_gets_less_boost_but_no_cut(self):
        rate = 24000
        gains = []
        for bass, middle in ((.015, .25), (.35, .03)):
            x = tone_mix(rate, 6, [(63, bass), (997, middle), (6000, .025)])
            l,_ = self.render(x, mode=2, rate=rate)
            gains.append(amplitude(l, 63, rate) / bass)
        self.assertGreater(gains[1], 1.0)
        self.assertGreater(gains[0], gains[1] * 1.08)

    def test_treble_rich_material_keeps_treble_and_quiet_material_keeps_same_curve(self):
        rate = 24000
        sparse = tone_mix(rate, 5, [(63, .02), (997, .25), (6000, .025)])
        rich = tone_mix(rate, 5, [(63, .02), (997, .03), (6000, .35)])
        boosted,_ = self.render(sparse, mode=2, rate=rate)
        quiet,_ = self.render([x*.02 for x in sparse], mode=2, rate=rate)
        bright,_ = self.render(rich, mode=2, rate=rate)
        high_gain = amplitude(boosted,6000,rate)/.025
        bright_gain = amplitude(bright,6000,rate)/.35
        self.assertGreater(bright_gain,1.)
        self.assertGreater(high_gain,bright_gain*1.06)
        for f in (63,997,6000):
            self.assertAlmostEqual(amplitude(quiet,f,rate)/amplitude(boosted,f,rate),.02,places=6)

    def test_width_preserves_mono_and_does_not_sum_or_create_channels(self):
        rate = 24000
        x = tone_mix(rate, 1, [(63, .1), (3000, .1)])
        l,r = self.render(x, mode=0, width=25, rate=rate)
        self.assertEqual(l, [ct.c_float(v).value for v in x])
        self.assertEqual(l, r)
        l,r = self.render(x, [0.]*len(x), mode=1, width=0, rate=rate)
        self.assertTrue(any(l))
        self.assertEqual(max(map(abs,r)), 0)

    def test_width_preserves_center_and_most_bass_while_widening_upper_side(self):
        rate = 24000
        center = tone_mix(rate, 2, [(997, .12)])
        side = tone_mix(rate, 2, [(63, .08),(6000,.08)])
        x,y = [a+b for a,b in zip(center,side)], [a-b for a,b in zip(center,side)]
        l,r = self.render(x,y,width=25,rate=rate)
        result_center = [(a+b)*.5 for a,b in zip(l,r)]
        result_side = [(a-b)*.5 for a,b in zip(l,r)]
        self.assertLess(max(abs(a-b) for a,b in zip(result_center,center)), 4e-8)
        self.assertAlmostEqual(amplitude(result_side,63,rate)/.08,1.,delta=.01)
        self.assertGreater(amplitude(result_side,6000,rate)/.08,1.18)
        self.assertLess(amplitude(result_side,6000,rate)/.08,1.26)

    def test_transitions_are_smoothed_and_off_settles_to_bypass(self):
        rate = 24000
        n=5*rate
        x=[.1]*n
        l,r=self.render(x,rate=rate,blocks=[rate],changes={rate:{0:2},3*rate:{0:0}})
        self.assertGreater(l[3*rate-1], .1)
        self.assertLess(max(abs(a-b) for a,b in zip(l[1:],l)), .0005)
        self.assertEqual(l[-1], ct.c_float(.1).value)
        self.assertEqual(r,l)

    def test_sample_rate_and_block_size_are_consistent(self):
        rate = 24000
        x=tone_mix(rate, 5, [(63,.015),(997,.2),(6000,.04)])
        whole=self.render(x,mode=2,width=10,rate=rate)[0]
        split=self.render(x,mode=2,width=10,rate=rate,blocks=[29,2048,41,120])[0]
        self.assertEqual(whole,split)
        rate2=48000
        x2=tone_mix(rate2,5,[(63,.015),(997,.2),(6000,.04)])
        high=self.render(x2,mode=2,width=10,rate=rate2)[0]
        for f in (63,997,6000):
            self.assertAlmostEqual(amplitude(whole,f,rate)/amplitude(high,f,rate2),1.,delta=.025)

    def test_nonfinite_audio_and_controls_fail_safe(self):
        x = [0., float('nan'), float('inf'), -float('inf'), .1, 3.4028234e38, -.1] * 300
        l,r=self.render(x,mode=2,width=25)
        self.assertTrue(all(math.isfinite(v) for v in l+r))
        l,r=self.render(x,mode=float('nan'),width=float('inf'))
        self.assertEqual(l[1:4],[0.,0.,0.])
        self.assertEqual(l[4],ct.c_float(.1).value)


if __name__=='__main__':
    unittest.main()

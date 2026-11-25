"""The display measures PCM energy, not equalizer settings or a fake animation."""
import array
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import spectrum

ROOT = Path(__file__).resolve().parents[1]
RATE = 48000
WINDOW = 4096
CENTERS = (31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000)


@unittest.skipUnless(shutil.which('gcc'), 'gcc required to test the spectrum')
class SpectrumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.temp.name) / 'oab_spectrum'
        subprocess.run(['gcc', '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        str(ROOT / 'src/oab_spectrum.c'), '-lm', '-o', str(cls.binary)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def measure(self, left, right=None):
        if right is None:
            right=left
        data=array.array('f', (sample for frame in zip(left,right) for sample in frame))
        self.assertEqual(data.itemsize,4)
        result=subprocess.run([str(self.binary)], input=data.tobytes(), capture_output=True, timeout=5, check=True)
        self.assertEqual(result.stderr,b'')
        values=[json.loads(line) for line in result.stdout.splitlines()]
        for bands in values:
            self.assertEqual(len(bands),10)
            self.assertTrue(all(isinstance(x,(float,int)) and math.isfinite(x) and -80<=x<=0 for x in bands))
        return values

    def tone(self, f, amp=.2, size=WINDOW):
        return [amp*math.sin(2*math.pi*f*i/RATE) for i in range(size)]

    def test_centers_appear_in_the_correct_octave_band(self):
        for j,f in enumerate(CENTERS):
            with self.subTest(frequency=f):
                levels=self.measure(self.tone(f))[0]
                self.assertEqual(max(range(10),key=levels.__getitem__),j,levels)
                # Full-scale sine is -3.01 dBFS RMS. Allow some boundary
                # leakage of the first octaves, where FFT resolution is coarse.
                self.assertAlmostEqual(levels[j],20*math.log10(.2/math.sqrt(2)),delta=1.5)

    def test_stereo_antiphase_does_not_cancel_energy(self):
        x=self.tone(1000,.20)
        mono=self.measure(x)[0]
        opposite=self.measure(x,[-y for y in x])[0]
        one_channel=self.measure(x,[0.]*len(x))[0]
        self.assertEqual(opposite,mono)
        self.assertAlmostEqual(mono[5]-one_channel[5],10*math.log10(2),delta=.05)
        doubled=self.measure(self.tone(1000,.40))[0]
        self.assertAlmostEqual(doubled[5]-mono[5],20*math.log10(2),delta=.05)

    def test_mixed_tones_have_independent_band_energy(self):
        a=self.tone(125,.20);b=self.tone(4000,.10)
        levels=self.measure([x+y for x,y in zip(a,b)])[0]
        self.assertAlmostEqual(levels[2]-levels[7],20*math.log10(2),delta=.2)
        self.assertEqual(set(sorted(range(10),key=levels.__getitem__,reverse=True)[:2]),{2,7})

    def test_periodicity_overlap_and_silence(self):
        self.assertEqual(self.measure([0.]*(WINDOW-1)),[])
        frames=self.measure([0.]*(WINDOW*2))
        self.assertEqual(len(frames),3)
        self.assertEqual(frames,[[-80.]*10]*3)

    def test_invalid_samples_are_discarded_and_levels_bounded(self):
        x=[0.]*WINDOW
        x[100]=float('nan');x[101]=float('inf');x[102]=float('-inf')
        self.assertEqual(self.measure(x),[[-80.]*10])
        x=self.tone(8000,1e30)
        levels=self.measure(x)[0]
        self.assertEqual(levels[8],0.)


class FakeProcess:
    def __init__(self, stdout=None, exit_code=None, resistant=False):
        self.stdout=stdout
        self.exit_code=exit_code
        self.resistant=resistant
        self.terminated=False
        self.killed=False
        self.waited=False

    def poll(self):return self.exit_code

    def terminate(self):
        self.terminated=True
        if not self.resistant:self.exit_code=-15

    def kill(self):
        self.killed=True;self.exit_code=-9

    def wait(self,timeout=None):
        self.waited=True
        if self.exit_code is None:raise subprocess.TimeoutExpired('stub',timeout)
        return self.exit_code


class WorkerTests(unittest.TestCase):
    TARGET='alsa_output.pci-0000_06_00.1.hdmi-stereo'

    def test_exact_target_and_pipewire_sink_only_properties(self):
        args=spectrum.capture_command(self.TARGET)
        self.assertEqual(args[0],'pw-record')
        self.assertEqual(args[args.index('--target')+1],self.TARGET)
        self.assertEqual(args[args.index('--rate')+1],'48000')
        self.assertEqual(args[args.index('--channels')+1],'2')
        self.assertEqual(args[args.index('--format')+1],'f32')
        self.assertEqual(args[-2:],['--raw','-'])
        props=json.loads(args[args.index('-P')+1])
        self.assertIs(props['stream.capture.sink'],True)
        self.assertIs(props['node.dont-fallback'],True)
        self.assertIs(props['node.dont-reconnect'],True)
        self.assertNotEqual(args[args.index('--media-role')+1],'Communication')
        self.assertIn('bluez_output.DE_AD_BE_EF.1',spectrum.capture_command('bluez_output.DE_AD_BE_EF.1'))
        for target in ('auto','0','alsa_input.test','alsa_output.', 'alsa_output.test;rm','alsa_output.x y','--help',''):
            with self.subTest(target=target), self.assertRaises(ValueError):
                spectrum.capture_command(target)

    def test_target_must_exist_as_a_sink(self):
        reply=mock.Mock(returncode=0,stdout=json.dumps([{'name':self.TARGET},{'name':'oab_output'}]))
        with mock.patch.object(spectrum.subprocess,'run',return_value=reply) as run:
            self.assertTrue(spectrum.target_available(self.TARGET))
            self.assertFalse(spectrum.target_available('alsa_output.absent'))
            self.assertFalse(spectrum.target_available('oab_output'))
            self.assertEqual(run.call_args.args[0],['pactl','-f','json','list','sinks'])
        with mock.patch.object(spectrum.subprocess,'run',side_effect=OSError):
            self.assertFalse(spectrum.target_available(self.TARGET))

    def test_worker_stops_and_reaps_both_children(self):
        pipe=mock.Mock();capture=FakeProcess(pipe,resistant=True);analyzer=FakeProcess()
        with mock.patch.object(spectrum,'target_available',return_value=True), \
             mock.patch.object(spectrum.subprocess,'Popen',side_effect=[capture,analyzer]) as popen:
            calls=iter([False,False,True])
            self.assertEqual(spectrum.run_worker(self.TARGET,lambda:next(calls,True)),0)
        self.assertTrue(capture.terminated);self.assertTrue(capture.killed);self.assertTrue(capture.waited)
        self.assertTrue(analyzer.terminated);self.assertTrue(analyzer.waited)
        pipe.close.assert_called_once()
        self.assertEqual(popen.call_args_list[1].kwargs['stdin'],pipe)
        self.assertEqual(popen.call_args_list[1].args[0],[str(ROOT/'lib/oab_spectrum')])

    def test_recorder_cleaned_up_if_analyzer_start_fails(self):
        pipe=mock.Mock();capture=FakeProcess(pipe)
        with mock.patch.object(spectrum,'target_available',return_value=True), \
             mock.patch.object(spectrum.subprocess,'Popen',side_effect=[capture,OSError('missing analyzer')]):
            self.assertNotEqual(spectrum.run_worker(self.TARGET,lambda:False),0)
        self.assertTrue(capture.terminated);self.assertTrue(capture.waited)
        pipe.close.assert_called_once()

    def test_worker_sigterm_reaps_live_pipeline(self):
        # Exercise real subprocess lifecycle without needing a running audio
        # server. Neither stub saves audio: only its PID is recorded for proof
        # that both processes were reaped.
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/'lib').mkdir();(folder/'bin').mkdir()
            shutil.copy(spectrum.__file__,folder/'spectrum.py')
            def script(path,body):
                path.write_text('#!'+sys.executable+'\n'+body)
                path.chmod(0o700)
            script(folder/'bin/pactl','print('+repr(json.dumps([{'name':self.TARGET}]))+')\n')
            script(folder/'bin/pw-record',
                   'import os,time,sys\n'
                   'open(os.environ["TEST_CAPTURE_PID"],"w").write(str(os.getpid()))\n'
                   'while True:\n sys.stdout.buffer.write(b"\\0"*128);sys.stdout.flush();time.sleep(.01)\n')
            script(folder/'lib/oab_spectrum',
                   'import os,sys\n'
                   'open(os.environ["TEST_ANALYZER_PID"],"w").write(str(os.getpid()))\n'
                   'while sys.stdin.buffer.read(128): pass\n')
            capture_pid=folder/'capture.pid';analyzer_pid=folder/'analyzer.pid'
            env=dict(os.environ,PATH=str(folder/'bin')+os.pathsep+os.environ['PATH'],
                     TEST_CAPTURE_PID=str(capture_pid),TEST_ANALYZER_PID=str(analyzer_pid))
            worker=subprocess.Popen([sys.executable,str(folder/'spectrum.py'),self.TARGET],
                                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=env)
            try:
                deadline=time.monotonic()+3
                while not all(p.exists() and p.stat().st_size for p in (capture_pid,analyzer_pid)):
                    if worker.poll() is not None or time.monotonic()>deadline:
                        self.fail('Worker did not start its pipeline')
                    time.sleep(.02)
                pids=[int(p.read_text()) for p in (capture_pid,analyzer_pid)]
                worker.send_signal(signal.SIGTERM)
                self.assertEqual(worker.wait(timeout=3),0)
                for pid in pids:
                    with self.assertRaises(ProcessLookupError):os.kill(pid,0)
            finally:
                if worker.poll() is None:
                    worker.terminate();worker.wait(timeout=3)

    def test_no_capture_on_nonexistent_or_invalid_sink(self):
        with mock.patch.object(spectrum,'target_available',return_value=False), \
             mock.patch.object(spectrum.subprocess,'Popen') as popen:
            self.assertNotEqual(spectrum.run_worker(self.TARGET,lambda:False),0)
        popen.assert_not_called()


if __name__=='__main__':
    unittest.main()

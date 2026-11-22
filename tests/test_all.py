"""Executable tests: the DSP is exercised as an actual LADSPA shared library."""
import ctypes as ct
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import oab

class Descriptor(ct.Structure):
    pass

DPtr=ct.POINTER(Descriptor)
Instantiate=ct.CFUNCTYPE(ct.c_void_p,DPtr,ct.c_ulong)
Connect=ct.CFUNCTYPE(None,ct.c_void_p,ct.c_ulong,ct.POINTER(ct.c_float))
Activate=ct.CFUNCTYPE(None,ct.c_void_p)
Run=ct.CFUNCTYPE(None,ct.c_void_p,ct.c_ulong)
Cleanup=ct.CFUNCTYPE(None,ct.c_void_p)
Descriptor._fields_=[('UniqueID',ct.c_ulong),('Label',ct.c_char_p),('Properties',ct.c_int),
('Name',ct.c_char_p),('Maker',ct.c_char_p),('Copyright',ct.c_char_p),
('PortCount',ct.c_ulong),('PortDescriptors',ct.POINTER(ct.c_int)),
('PortNames',ct.POINTER(ct.c_char_p)),('PortRangeHints',ct.c_void_p),
('ImplementationData',ct.c_void_p),('instantiate',Instantiate),('connect_port',Connect),
('activate',Activate),('run',Run),('run_adding',ct.c_void_p),
('set_run_adding_gain',ct.c_void_p),('deactivate',ct.c_void_p),('cleanup',Cleanup)]

@unittest.skipUnless(shutil.which('gcc'),'gcc requerido para testes DSP')
class TestLadspa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.bin=Path(cls.tmp.name)/'oab.so'
        r=subprocess.run(['gcc','-O2','-shared','-fPIC','-Wall','-Wextra','-Werror',
          str(ROOT/'src/oab_dynamics.c'),'-lm','-o',str(cls.bin)],capture_output=True,text=True)
        if r.returncode: raise RuntimeError(r.stderr)
        cls.lib=ct.CDLL(str(cls.bin))
        cls.lib.ladspa_descriptor.argtypes=[ct.c_ulong]
        cls.lib.ladspa_descriptor.restype=DPtr
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def render(self,left,right,drive=3,threshold=-17,ratio=1.8,atk=8,rel=160,ceiling=-1.0):
        count=len(left)
        self.assertEqual(count,len(right))
        d=self.lib.ladspa_descriptor(0)
        self.assertEqual(d.contents.Label,b'oab_stereo_dynamics')
        self.assertEqual(d.contents.PortCount,10)
        self.assertFalse(bool(self.lib.ladspa_descriptor(1)))
        h=d.contents.instantiate(d,48000)
        self.assertTrue(h)
        l=(ct.c_float*count)(*left)
        r=(ct.c_float*count)(*right)
        ol=(ct.c_float*count)()
        orr=(ct.c_float*count)()
        ctrl=[ct.c_float(x) for x in (drive,threshold,ratio,atk,rel,ceiling)]
        buffers=[l,r,ol,orr]+[ct.pointer(c) for c in ctrl]
        for i,ptr in enumerate(buffers): d.contents.connect_port(h,i,ptr)
        d.contents.activate(h)
        d.contents.run(h,count)
        result=[list(ol),list(orr)]
        d.contents.cleanup(h)
        return result
    def test_silence_stays_silent(self):
        l,r=self.render([0.0]*4096,[0.0]*4096)
        self.assertEqual(max(map(abs,l)),0.0)
        self.assertEqual(max(map(abs,r)),0.0)
    def test_stereo_balance_unchanged(self):
        x=[0.02*math.sin(2*math.pi*i/100) for i in range(8192)]
        l,r=self.render(x,x)
        self.assertLess(max(abs(a-b) for a,b in zip(l,r)),1e-7)
    def test_quiet_material_is_amplified_when_drive_selected(self):
        x=[0.01]*8192
        l,_=self.render(x,x,drive=6,threshold=0,ratio=1)
        self.assertGreater(l[-1],0.018)
    def test_peak_is_limited(self):
        x=[math.sin(2*math.pi*i/53) for i in range(12000)]
        l,r=self.render(x,x,drive=16,threshold=-32,ratio=3,ceiling=-1)
        self.assertLessEqual(max(map(abs,l)),10**(-1/20)+1e-5)
        self.assertLessEqual(max(map(abs,r)),10**(-1/20)+1e-5)
    def test_non_finite_input_does_not_poison_audio(self):
        x=[float('nan'),float('inf'),float('-inf'),0.05]*1000
        l,r=self.render(x,x)
        self.assertTrue(all(math.isfinite(s) for s in l+r))
    def test_non_identical_channels_not_swapped(self):
        x=[0.1]*2048;y=[0.04]*2048
        l,r=self.render(x,y,drive=0,threshold=0,ratio=1)
        self.assertGreater(l[-1],r[-1])
        self.assertLess(abs(l[-1]/r[-1]-2.5),.01)

class TestConfiguration(unittest.TestCase):
    def test_orphan_plugin_requires_matching_recorded_hash(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            plugin=Path(tmp)/'plugin.so';state=Path(tmp)/'state';state.mkdir()
            plugin.write_bytes(b'known plugin')
            with mock.patch.object(oab,'PLUGIN',plugin), mock.patch.object(oab,'STATE',state):
                self.assertFalse(oab.known_plugin())
                (state/'current.json').write_text(json.dumps({'plugin_sha256':hashlib.sha256(plugin.read_bytes()).hexdigest()}))
                self.assertTrue(oab.known_plugin())
                plugin.write_bytes(b'changed')
                self.assertFalse(oab.known_plugin())

    def test_profiles_are_valid(self):
        for name in ('transparent','loudness','voice','loudness-safe'):
            prof=oab.profile_load(name)
            self.assertEqual(prof['name'],name)
    def test_wireplumber_fragment_links(self):
        prof=oab.profile_load('loudness')
        fragment=oab.fragment(prof,['alsa_output.test.stereo'])
        self.assertIn('node.filter-graph.rules',fragment)
        self.assertNotIn('Audio/Source',fragment)
        self.assertNotIn('monitor.alsa.rules',fragment)
        graph_json=json.loads(fragment.split('= ',1)[1])
        g=graph_json[0]['actions']['create-filter-graph'][0]
        self.assertEqual(g['links'][0]['input'],'oab_dyn:Input L')
        self.assertEqual(g['outputs'],['oab_dyn:Output L','oab_dyn:Output R'])
        self.assertTrue(Path(g['nodes'][-1]['plugin']).suffix == '.so')
        self.assertEqual(graph_json[0]['matches'][0]['node.name'],'alsa_output.test.stereo')
    def test_no_graph_over_matching(self):
        fragment=oab.fragment(oab.profile_load('transparent'),['alsa_output.one'])
        self.assertNotIn('~alsa_output',fragment)
        self.assertNotIn('audio.channels',fragment)
    def test_soft_mixer_opt_in_and_alsa_only(self):
        f=oab.fragment(oab.profile_load('voice'),['alsa_output.a','bluez_output.b'],
                       soft_mixer=True,soft_mixer_cards=['alsa_card.example'])
        self.assertEqual(f.count('"api.alsa.soft-mixer"'),1)
        self.assertIn('"device.name": "alsa_card.example"',f)
    @mock.patch('oab.read_sinks')
    def test_select_only_confirmed_stereo(self,read):
        read.return_value=[{'name':'alsa_output.stereo','channels':2},
                           {'name':'alsa_output.surround','channels':6},
                           {'name':'bluez_output.unknown','channels':None}]
        self.assertEqual([x['name'] for x in oab.selected_sinks()],['alsa_output.stereo'])
        with self.assertRaises(oab.BridgeError):oab.selected_sinks(['alsa_output.surround'])
    def test_autoeq_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'my.txt';dst=Path(tmp)/'my.json'
            src.write_text('Preamp: -6.8 dB\nFilter 1: ON PK Fc 200 Hz Gain 2.2 dB Q 0.8\n')
            oab.import_autoeq(src,dst)
            data=json.loads(dst.read_text())
            self.assertEqual(len(data['filters']),1)
            self.assertEqual(data['filters'][0]['freq'],200)
            self.assertEqual(data['drive_db'],-6.8)

if __name__=='__main__': unittest.main(verbosity=2)

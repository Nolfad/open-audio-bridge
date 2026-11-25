import math,unittest
from pathlib import Path
from unittest import mock
import bridge,native,sound

class SoundTests(unittest.TestCase):
 def test_default_keeps_existing_sound(self):
  self.assertEqual(sound.normalize(None),{'drive_db':18.,'eq_enabled':False,'preset':'flat','bands':[0.]*10,'music_mode':'off','width':0.0})
  graph=bridge.make_graph(Path('.'))
  self.assertEqual([n['name'] for n in graph['nodes']],['volume'])
  self.assertEqual(graph['inputs'],['volume:Input L','volume:Input R'])
 def test_invalid_controls_are_rejected(self):
  for value in [{'drive_db':float('nan')},{'drive_db':19},{'bands':[0]*9},{'bands':[7]*10},{'bands':[float('inf')]*10},{'preset':'unknown'},{'eq_enabled':'false'},{'music_mode':'fake'},{'width':26},{'width':float('nan')}]:
   with self.subTest(value=value),self.assertRaises(ValueError):sound.normalize(value)
 def test_presets_do_not_change_drive(self):
  for preset in sound.PRESETS:
   state=sound.normalize({'drive_db':5,'eq_enabled':True,'preset':preset})
   self.assertEqual(state['drive_db'],5)
   self.assertEqual(len(state['bands']),10)
 def test_one_clean_gain_after_user_equalizer(self):
  g=bridge.make_graph(Path('.'),'boost',{'drive_db':7,'eq_enabled':True,'preset':'rock'})
  byname={n['name']:n for n in g['nodes']}
  self.assertEqual(set(byname),{'tone','volume'})
  self.assertEqual(byname['volume']['label'],'oab_clean_gain')
  self.assertEqual(byname['volume']['control']['Drive (dB)'],7)
  self.assertEqual(byname['volume']['control']['Ceiling (dB)'],-1.2)
  self.assertIn({'output':'tone:Out 1','input':'volume:Input L'},g['links'])
  self.assertIn({'output':'tone:Out 2','input':'volume:Input R'},g['links'])
  self.assertEqual(g['inputs'],['tone:In 1','tone:In 2'])
  self.assertEqual(g['outputs'],['volume:Output L','volume:Output R'])
  self.assertEqual(byname['tone']['config']['filters'],sound.filters({'drive_db':7,'eq_enabled':True,'preset':'rock'}))
 def test_optional_music_and_width_before_manual_eq_and_protection(self):
  settings={'drive_db':18,'eq_enabled':True,'preset':'rock','music_mode':'warm','width':12}
  state=sound.normalize(settings);self.assertEqual(state['music_mode'],'warm');self.assertEqual(state['width'],12)
  g=bridge.make_graph(Path('.'),'boost',settings)
  n={v['name']:v for v in g['nodes']};self.assertEqual(n['music']['control'],{'Mode':1.,'Width (%)':12.})
  self.assertEqual(n['music']['label'],'oab_music_enhance')
  self.assertEqual(g['inputs'],['music:Input L','music:Input R'])
  self.assertIn({'output':'music:Output L','input':'tone:In 1'},g['links'])
  self.assertIn({'output':'tone:Out 2','input':'volume:Input R'},g['links'])
  self.assertEqual(g['outputs'],['volume:Output L','volume:Output R'])
  self.assertEqual(state['bands'],list(sound.PRESETS['rock'][1]))
 def test_custom_curve_and_independent_bypass(self):
  bands=[-2,-1,0,1,2,3,2,1,0,-1]
  state=sound.normalize({'drive_db':9,'eq_enabled':False,'preset':'custom','bands':bands})
  self.assertEqual(state['bands'],bands)
  graph=bridge.make_graph(Path('.'),'normal',state)
  self.assertNotIn('tone',[n['name'] for n in graph['nodes']])
 def test_sound_change_keeps_system_volume_and_mute(self):
  state={'enabled':True,'target':'default','curve':'boost'}
  sink={'name':'alsa_output.a','mute':False,'volume':{'L':{'value':20000},'R':{'value':10000}}}
  with mock.patch.object(native,'settings',return_value=state),mock.patch.object(native.b,'sinks',return_value=[sink]),mock.patch.object(native.b,'save') as save,mock.patch.object(native.b,'run'),mock.patch.object(native,'wait_ready'),mock.patch.object(native,'restore_levels') as restore:
   native.configure('sound',{'drive_db':12,'eq_enabled':True,'preset':'pop'})
  self.assertEqual(save.call_args.args[1]['sound']['drive_db'],12)
  restore.assert_called_once_with({'alsa_output.a':{'volume':[20000,10000],'mute':False}})
 def test_plugin_upgrade_preserves_library_already_mapped_by_audio_server(self):
  import mmap,tempfile
  with tempfile.TemporaryDirectory() as folder:
   old=Path(folder)/'live.so';source=Path(folder)/'new.so';old.write_bytes(b'old library');source.write_bytes(b'new library')
   with old.open('rb') as handle,mmap.mmap(handle.fileno(),0,access=mmap.ACCESS_READ) as loaded:
    native.install_plugin(source,old)
    self.assertEqual(old.read_bytes(),b'new library')
    self.assertEqual(loaded[:],b'old library')

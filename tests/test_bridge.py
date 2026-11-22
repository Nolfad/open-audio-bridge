import unittest,tempfile,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bridge
class BackendTests(unittest.TestCase):
 def test_curve_inverse_preserves_start_level(self):
  self.assertAlmostEqual(bridge.inverse_percent(80,'boost'),60)
  self.assertAlmostEqual(bridge.inverse_percent(60,'boost'),40)
  self.assertAlmostEqual(bridge.inverse_percent(100,'boost'),80)
 def test_amplified_volume_round_trip(self):
  self.assertEqual(bridge.validate_percent(150),150)
  self.assertEqual(bridge.inverse_percent(125,'boost'),105)
  self.assertEqual(bridge.equivalent_percent(125,'boost'),145)
  self.assertEqual(bridge.equivalent_percent(40,'boost'),60)
 def test_full_range_round_trip_and_normal_ceiling(self):
  for p in [0,20,40,60,80,100,125,150]:
   self.assertEqual(bridge.inverse_percent(bridge.equivalent_percent(p,'boost'),'boost'),p)
  self.assertEqual(bridge.inverse_percent(300,'normal'),150)
  for p in [float('nan'),float('inf'),-1]:
   with self.assertRaises(ValueError):bridge.inverse_percent(p,'boost')
 def test_update_preserves_old_listening_level_once(self):
  for old,equivalent in [(0,0),(40,80),(70,90),(100,100),(150,150)]:
   original={'curve':'boost','volume':old,'mute':True,'target':'test'}
   migrated=bridge.migrate_volume_settings(original)
   self.assertAlmostEqual(bridge.equivalent_percent(migrated['volume'],'boost'),equivalent)
   self.assertTrue(migrated['mute']);self.assertEqual(migrated['target'],'test')
   self.assertEqual(bridge.migrate_volume_settings(migrated),migrated)
   self.assertEqual(original['volume'],old)
  self.assertEqual(bridge.migrate_volume_settings({'curve':'normal','volume':125})['volume'],125)
 def test_migrate_doubled_curve_and_cap_unreachable_level(self):
  for p,want in [(10,10),(31,42),(40,60),(80,140),(100,150),(150,150)]:
   result=bridge.migrate_volume_settings({'volume_curve_version':2,'curve':'boost','volume':p})
   self.assertEqual(result['volume'],want)
   self.assertEqual(result['volume_curve_version'],3)
   self.assertEqual(bridge.migrate_volume_settings(result),result)
 def test_snapshot_restores_existing_and_absent(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'present';q=Path(t)/'absent';p.write_bytes(b'original');p.chmod(0o600)
   snap=bridge.snapshot([p,q]);p.write_bytes(b'changed');q.write_text('new')
   bridge.restore(snap)
   self.assertEqual(p.read_bytes(),b'original');self.assertEqual(p.stat().st_mode&0o777,0o600);self.assertFalse(q.exists())
 def test_graph_volume_then_final_guard(self):
  g=bridge.make_graph(Path('/tmp/plugins'),'boost')
  self.assertEqual(g['capture.volumes'][0]['control'],'volume:Volume L')
  self.assertEqual(g['capture.volumes'][0]['scale'],'cubic')
  self.assertIn({'output':'volume:Output L','input':'guard:Input L'},g['links'])
  self.assertEqual(g['outputs'],['guard:Output L','guard:Output R'])
 def test_output_cannot_fallback_or_amplify_again(self):
  c=bridge.make_config(Path('/tmp/plugins'),'alsa_output.example','boost',40)
  a=c['context.modules'][-1]['args'];p=a['playback.props']
  self.assertTrue(p['node.dont-fallback']);self.assertTrue(p['node.linger']);self.assertEqual(p['target.object'],'alsa_output.example');self.assertTrue(p['stream.dont-remix'])
 def test_volume_rejects_nonfinite(self):
  for v in [float('nan'),float('inf'),-1,151]:
   with self.assertRaises(ValueError):bridge.validate_percent(v)
if __name__=='__main__':unittest.main()

from unittest import mock
from contextlib import ExitStack
class LifecycleTests(unittest.TestCase):
 def test_failed_stage_does_not_disrupt_installed_version(self):
  with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
   b=Path(tmp);app=b/'app';app.mkdir();(app/'bridge.py').write_text('old')
   source=b/'source';source.mkdir();(source/'bridge.py').write_text('new')
   names={'APP':app,'STATE':b/'state','SETTINGS':b/'state/settings.json','BASELINE':b/'state/baseline.json','SERVICE':b/'svc','DESKTOP':b/'desktop','AUTOSTART':b/'autostart','LEGACY':b/'legacy'}
   for k,v in names.items():stack.enter_context(mock.patch.object(bridge,k,v))
   bridge.save(bridge.SETTINGS,{'enabled':True,'target':'alsa_output.test'})
   bridge.save(bridge.BASELINE,{'files':{str(bridge.SERVICE):None},'default':'alsa_output.test'})
   bridge.SERVICE.write_text('working service')
   def destructive_disable():bridge.SERVICE.unlink();bridge.save(bridge.SETTINGS,{'enabled':False})
   stack.enter_context(mock.patch.object(bridge,'prerequisites'))
   stack.enter_context(mock.patch.object(bridge,'physical_sinks',return_value=[{'name':'alsa_output.test'}]))
   stack.enter_context(mock.patch.object(bridge,'disable',side_effect=destructive_disable))
   stack.enter_context(mock.patch.object(bridge,'compile_plugins',side_effect=bridge.BridgeError('compiler failed')))
   stack.enter_context(mock.patch.object(bridge,'run'))
   with self.assertRaises(bridge.BridgeError):bridge.install(source)
   self.assertEqual(bridge.SERVICE.read_text(),'working service')
   self.assertTrue(bridge.read(bridge.SETTINGS)['enabled'])
   self.assertEqual((app/'bridge.py').read_text(),'old')
 def test_volume_above_150_cannot_poison_restart(self):
  s={'volume':{'left':{'value':131072},'right':{'value':131072}}}
  self.assertEqual(bridge.percent_of(s),150)
 def test_physical_output_is_muted_until_streams_moved(self):
  state={'muted':False,'volume':40,'moved':False}
  def command(args,**_):
   if args[:3]==['pactl','set-sink-mute','alsa_output.test']:state['muted']=args[3]=='1'
   if args[:3]==['pactl','set-sink-volume','alsa_output.test']:
    self.assertTrue(state['muted']);state['volume']=100
   if args[:3]==['pactl','set-sink-mute','alsa_output.test'] and args[3]=='0':self.assertTrue(state['moved'])
  def move(*_):self.assertTrue(state['muted']);state['moved']=True
  with mock.patch.object(bridge,'run',side_effect=command),mock.patch.object(bridge,'move_streams',side_effect=move),mock.patch.object(bridge,'sink_by_name',return_value=None):
   bridge.activate_route({'volume':40,'mute':True,'balance':[1,1]},'alsa_output.test')
  self.assertTrue(state['moved'])
 def test_stop_failure_does_not_restore_legacy_dsp(self):
  with tempfile.TemporaryDirectory() as t, ExitStack() as stack:
   b=Path(t)
   for key,val in {'STATE':b,'SETTINGS':b/'settings','BASELINE':b/'baseline','LEGACY':b/'legacy'}.items():stack.enter_context(mock.patch.object(bridge,key,val))
   bridge.save(bridge.SETTINGS,{'enabled':True,'volume':40})
   bridge.save(bridge.BASELINE,{'files':{str(bridge.LEGACY):{'data':'b2xk','mode':420}}})
   stack.enter_context(mock.patch.object(bridge,'sink_by_name',return_value=None));stack.enter_context(mock.patch.object(bridge,'recover'))
   def fail(args,**kwargs):
    if 'disable' in args:
     if kwargs.get('check',True):raise bridge.BridgeError('stop failed')
     return __import__('subprocess').CompletedProcess(args,1,'','stop failed')
   stack.enter_context(mock.patch.object(bridge,'run',side_effect=fail))
   with self.assertRaises(bridge.BridgeError):bridge.disable()
   self.assertFalse(bridge.LEGACY.exists())

class DisconnectedUpgradeTests(unittest.TestCase):
 def test_update_without_hardware_preserves_target_and_converts_volume(self):
  with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
   root=Path(tmp);app=root/'app';app.mkdir();(app/'bridge.py').write_text('old')
   source=root/'source';source.mkdir();(source/'bridge.py').write_text('new')
   for name,path in {'APP':app,'STATE':root/'state','SETTINGS':root/'state/settings.json','BASELINE':root/'state/baseline.json','SERVICE':root/'svc','DESKTOP':root/'desktop','AUTOSTART':root/'autostart','LEGACY':root/'legacy'}.items():
    stack.enter_context(mock.patch.object(bridge,name,path))
   bridge.save(bridge.SETTINGS,{'enabled':False,'target':'alsa_output.missing','volume':100,'curve':'boost','mute':True,'balance':[1,.7]})
   bridge.save(bridge.BASELINE,{'files':{},'default':'alsa_output.missing'})
   stack.enter_context(mock.patch.object(bridge,'prerequisites'))
   stack.enter_context(mock.patch.object(bridge,'physical_sinks',return_value=[]))
   stack.enter_context(mock.patch.object(bridge,'sink_by_name',return_value=None))
   stack.enter_context(mock.patch.object(bridge,'compile_plugins'))
   stack.enter_context(mock.patch.object(bridge,'enable'))
   stack.enter_context(mock.patch.object(bridge,'run',return_value=__import__('subprocess').CompletedProcess([],1,'','')))
   bridge.install(source)
   settings=bridge.read(bridge.SETTINGS)
   self.assertEqual(settings['target'],'alsa_output.missing')
   self.assertEqual(settings['volume'],80)
   self.assertEqual(settings['volume_curve_version'],3)
   self.assertTrue(settings['mute']);self.assertEqual(settings['balance'],[1,.7])
   self.assertEqual((app/'bridge.py').read_text(),'new')

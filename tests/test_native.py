import unittest
from unittest import mock
import native

class NativeControlTests(unittest.TestCase):
 def test_default_follows_system_but_fixed_selection_does_not(self):
  self.assertEqual(native.target_name({'target':'default'},'headset'),'headset')
  self.assertEqual(native.target_name({'target':'hdmi'},'headset'),'hdmi')
 def test_only_real_stereo_outputs_are_candidates(self):
  items=[{'name':'alsa_output.a','volume':{'L':{},'R':{}}}, {'name':'oab_output','volume':{'L':{},'R':{}}}, {'name':'alsa_output.surround','volume':{str(i):{} for i in range(6)}}]
  self.assertEqual([x['name'] for x in native.candidates(items)],['alsa_output.a'])
 def test_automatic_mode_prepares_all_outputs_without_changing_default(self):
  items=[{'name':'alsa_output.a'},{'name':'alsa_output.b'}]
  self.assertEqual(native.selected_names({'target':'default'},items),{'alsa_output.a','alsa_output.b'})
  self.assertEqual(native.selected_names({'target':'alsa_output.b'},items),{'alsa_output.b'})
 def test_graph_owns_native_volume_and_final_guard(self):
  graph=native.graph('boost',[.064,.008],False)
  self.assertEqual(graph['capture.volumes'][0]['control'],'oab_native_volume:Volume L')
  self.assertEqual(graph['outputs'],['oab_native_guard:Output L','oab_native_guard:Output R'])
  volume=next(x for x in graph['nodes'] if x['name']=='oab_native_volume')
  self.assertAlmostEqual(volume['control']['Volume L'],.4)
  self.assertAlmostEqual(volume['control']['Volume R'],.2)
 def test_volume_writes_actual_default_device_not_virtual(self):
  with mock.patch.object(native,'settings',return_value={'target':'default'}), mock.patch.object(native.b,'default_sink',return_value='alsa_output.headset'),mock.patch.object(native.b,'sink_by_name',return_value={'name':'alsa_output.headset','volume':{'L':{'value':40000},'R':{'value':20000}}}),mock.patch.object(native.b,'run') as run:
   native.set_volume(40)
  self.assertEqual(run.call_args.args[0],['pactl','set-sink-volume','alsa_output.headset','40.00000%','20.00000%'])
 def test_foreign_graph_is_not_owned(self):
  self.assertFalse(native.owns_node({'info':{'params':{'Props':[{'params':['other:gain',1]}]}}}))
  self.assertTrue(native.owns_node({'info':{'params':{'Props':[{'params':['oab_native_volume:Curve',1]}]}}}))
 def test_volume_can_leave_zero(self):
  with mock.patch.object(native,'settings',return_value={'target':'default'}),mock.patch.object(native.b,'default_sink',return_value='alsa_output.a'),mock.patch.object(native.b,'sink_by_name',return_value={'name':'alsa_output.a','volume':{'L':{'value':0},'R':{'value':0}}}),mock.patch.object(native.b,'run') as run:
   native.set_volume(25)
  self.assertEqual(run.call_args.args[0][-2:],['25.00000%','25.00000%'])
 def test_normal_migration_does_not_apply_boost(self):
  self.assertEqual(native.migration_percent('0.2.1','normal',40),40)
  self.assertEqual(native.migration_percent('0.2.1','boost',32),44)
  self.assertEqual(native.migration_percent('0.2.2','boost',31),42)
 def test_disabled_curve_change_does_not_alter_device_level(self):
  state={'routing':'native','enabled':False,'curve':'boost','target':'default'}
  with mock.patch.object(native,'settings',return_value=state.copy()),mock.patch.object(native.b,'save') as save,mock.patch.object(native.b,'run',side_effect=AssertionError('Disabled curve must not write hardware volume')):
   native.configure('curve','normal')
  self.assertEqual(save.call_args.args[1]['curve'],'normal')
 def test_pipewire_card_lookup_uses_stable_name_not_pulse_index(self):
  sink={'properties':{'device.name':'alsa_card.usb','device.id':'62'}}
  cards=[{'index':42662,'name':'alsa_card.usb','properties':{'object.id':'62','device.name':'alsa_card.usb'}}]
  self.assertEqual(native.card_for_sink(sink,cards),cards[0])

 def test_alsa_properties_are_not_mistaken_for_foreign_effects(self):
  node={'id':42,'info':{'props':{'object.serial':43},'params':{'Props':[{'params':['channelmix.disable',False]},{'params':['audio.channels',2,'api.alsa.period-size',0]}]}}}
  sink={'name':'alsa_output.a','mute':False,'volume':{'L':{'value':20000},'R':{'value':20000}}}
  with mock.patch.object(native.b,'run'),mock.patch.object(native.b,'save'),mock.patch.object(native,'set_props') as setter,mock.patch.object(native,'restore_levels'):
   native.attach(node,sink,'boost',{})
  self.assertEqual(setter.call_count,2)

 def test_curve_failure_restores_mute_even_when_rollback_restart_fails(self):
  state={'routing':'native','enabled':True,'curve':'boost','target':'default'}
  sink={'name':'alsa_output.a','mute':False,'volume':{'L':{'value':20000},'R':{'value':20000}}}
  def run(args,**kwargs):
   if 'restart' in args:raise native.b.BridgeError('restart failed')
  with mock.patch.object(native,'settings',return_value=state),mock.patch.object(native.b,'sinks',return_value=[sink]),mock.patch.object(native.b,'save'),mock.patch.object(native.b,'run',side_effect=run),mock.patch.object(native,'restore_levels') as restore:
   with self.assertRaises(native.b.BridgeError):native.configure('curve','normal')
  restore.assert_called_once_with({'alsa_output.a':{'volume':[20000,20000],'mute':False}})
 def test_mixer_restart_failure_restores_prior_rule_and_settings(self):
  import tempfile
  from pathlib import Path
  previous={'enabled':True,'target':'default','mixer_cards':{}}
  with tempfile.TemporaryDirectory() as directory:
   rule=Path(directory)/'rule.conf';rule.write_text(native.MARKER+' old')
   with mock.patch.object(native,'RULE',rule),mock.patch.object(native,'settings',return_value=previous),mock.patch.object(native.b,'sinks',return_value=[]),mock.patch.object(native.b,'run',return_value=mock.Mock(stdout='[]')),mock.patch.object(native.b,'save') as save,mock.patch.object(native,'level_snapshot',return_value={}),mock.patch.object(native,'restart_policy',side_effect=[native.b.BridgeError('profile failed'),None]) as restart,mock.patch.object(native,'restore_levels'):
    with self.assertRaises(native.b.BridgeError):native.prepare_mixers()
   self.assertEqual(rule.read_text(),native.MARKER+' old')
   self.assertEqual(save.call_args.args[1],previous)
   self.assertEqual(restart.call_count,2)

"""Exercise the installer with real files and simulated audio/service boundaries."""
import contextlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import native
import oab
import audio_routes


class HotUpgradeTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
  self.app=self.root/'app';self.state=self.root/'state';self.source=self.root/'source'
  for path in (self.app,self.state,self.source):path.mkdir()
  for key,value in dict(HOME_DIR=self.root,APP=self.app,STATE=self.state,SETTINGS=self.state/'settings.json',BASELINE=self.state/'baseline.json',SERVICE=self.root/'service',DESKTOP=self.root/'desktop',AUTOSTART=self.root/'autostart',LEGACY=self.root/'legacy').items():
   self.stack.enter_context(mock.patch.object(native.b,key,value))
  for key,value in dict(BASE=self.state/'native-baseline.json',OWNED=self.state/'native-owned.json',READY=self.state/'native-ready.json',RULE=self.root/'rule',DROPIN=self.root/'dropin',ACP_PATHS=self.root/'paths',PLUGINS={'clean':self.root/'.ladspa/clean.so'}).items():
   self.stack.enter_context(mock.patch.object(native,key,value))
  self.profile=self.app/'mixer/card/profile-sets/default.conf'
  self.mixer_path=self.app/'mixer/card/paths/oab-speaker.conf'
  native.b.atomic(self.profile,'[Mapping analog-stereo]\npaths-output = oab-speaker\n')
  native.b.atomic(self.mixer_path,'[Element PCM]\nvolume = zero\n')
  self.mixer_cards={'alsa_card.test':{'profile':str(self.profile),'source':'/usr/share/alsa-card-profile/mixer/profile-sets/default.conf'}}
  self.before=dict(routing='native',target='default',curve='boost',enabled=True,autostart=False,mixer_cards=self.mixer_cards,sound={'mode':'clean'})
  native.b.save(native.b.SETTINGS,self.before)
  native.b.save(native.BASE,{'files':{str(native.RULE):None,str(next(iter(native.PLUGINS.values()))):None}})
  rules=[{'matches':[{'device.name':'alsa_card.test'}],'actions':{'update-props':{'device.profile-set':str(self.profile)}}}]
  self.rule=native.MARKER+'\nmonitor.alsa.rules = '+json.dumps(rules,indent=2)+'\n'
  native.b.atomic(native.RULE,self.rule)
  (self.app/'bridge.py').write_text("VERSION='0.5.2'\n")
  (self.source/'bridge.py').write_text("VERSION='0.6.0'\n")
  self.sink={'name':'alsa_output.test','volume':{'L':{'value':23000},'R':{'value':17000}},'mute':True,'flags':[]}
  self.default=self.sink['name'];self.running=True;self.enabled=False;self.calls=[];self.fail_start=False
  self.original_levels={'volume':[23000,17000],'mute':True}
  self.stack.enter_context(mock.patch.object(native.b,'prerequisites'))
  self.stack.enter_context(mock.patch.object(oab,'version',return_value=(9,9,9)))
  self.stack.enter_context(mock.patch.object(native.shutil,'which',return_value='/usr/bin/stub'))
  self.stack.enter_context(mock.patch.object(native.b,'sinks',side_effect=lambda:[self.sink]))
  self.stack.enter_context(mock.patch.object(native.b,'sink_by_name',side_effect=lambda name:self.sink if name==self.sink['name'] else None))
  self.stack.enter_context(mock.patch.object(native.b,'default_sink',side_effect=lambda:self.default))
  self.stack.enter_context(mock.patch.object(native.b,'run',side_effect=self.run_command))
  self.stack.enter_context(mock.patch.object(native.b,'compile_plugins',side_effect=self.compile_plugins))
  self.stack.enter_context(mock.patch.object(native.updater,'setup'))
  self.stack.enter_context(mock.patch.object(native.updater,'sync_schedule'))
  read_bytes=Path.read_bytes
  self.stack.enter_context(mock.patch.object(Path,'read_bytes',lambda path:b'LADSPA_PATH='+str(self.root/'.ladspa').encode()+b'\0' if path==Path('/proc/123/environ') else read_bytes(path)))

 def compile_plugins(self,stage):
  native.b.atomic(stage/'lib/liboab_clean.so',b'new plugin')

 def run_command(self,args,**kwargs):
  self.calls.append(args)
  code=0;output=''
  if args[0]=='systemctl':
   operation=args[2]
   if operation=='is-active':code=0 if self.running else 3
   elif operation=='is-failed':code=1
   elif operation=='show':output='123'
   elif operation=='disable':
    self.enabled=False
    if '--now' in args:self.running=False
   elif operation=='enable':self.enabled=True
   elif operation=='stop':self.running=False
   elif operation in ('start','restart') and args[3]=='open-audio-bridge':
    self.running=True
    error='DSP start failed' if self.fail_start else ''
    self.fail_start=False
    native.b.save(native.READY,{'ready':True,'pid':123,'error':error})
   elif operation not in ('daemon-reload','restart'):raise AssertionError(args)
  elif args[:4]==['pactl','-f','json','list']:output='[]'
  elif args[:2]==['pactl','set-sink-volume']:
   for value,channel in zip(args[3:],self.sink['volume'].values()):channel['value']=int(value)
  elif args[:2]==['pactl','set-sink-mute']:self.sink['mute']=args[3]=='1'
  elif args[:2]==['pactl','set-default-sink']:self.default=args[2]
  else:raise AssertionError(args)
  return subprocess.CompletedProcess(args,code,stdout=output,stderr='')

 def assert_no_audio_server_restart(self):
  restarts=[cmd for cmd in self.calls if cmd[:3]==['systemctl','--user','restart'] and any(name in cmd[3:] for name in ('wireplumber','pipewire','pipewire-pulse'))]
  self.assertEqual(restarts,[], 'A managed upgrade must not recreate devices or client streams')

 def assert_preserved(self):
  self.assertEqual(native.settings()['mixer_cards'],self.mixer_cards)
  self.assertEqual(self.profile.read_text(),'[Mapping analog-stereo]\npaths-output = oab-speaker\n')
  self.assertEqual(self.mixer_path.read_text(),'[Element PCM]\nvolume = zero\n')
  self.assertEqual(native.RULE.read_text(),self.rule)
  self.assertEqual(native.level_snapshot(),{self.sink['name']:self.original_levels})
  self.assertEqual(self.default,self.sink['name'])
  self.assertFalse(native.settings()['autostart']);self.assertFalse(self.enabled)

 def test_running_native_upgrade_preserves_profiles_without_audio_restart(self):
  native.install(self.source,preserve_enabled=True)
  self.assert_no_audio_server_restart();self.assert_preserved()
  self.assertTrue(self.running);self.assertTrue(native.settings()['enabled'])
  self.assertEqual((self.app/'bridge.py').read_text(),"VERSION='0.6.0'\n")

 def test_managed_upgrade_seeds_live_levels_and_keeps_disconnected_device_history(self):
  path=self.state/'native-volume.json'
  previous=native.native_volume.LevelStore(path,'previous-boot')
  previous.observe(self.sink,{'volume':[65536,65536],'mute':False})
  disconnected={'name':'bluez_output.unplugged','active_port':'headset-output'}
  previous.observe(disconnected,{'volume':[20000,10000],'mute':False})
  with mock.patch.object(native.native_volume,'boot_id',return_value='current-boot'):
   native.install(self.source,preserve_enabled=True)
  saved=native.native_volume.LevelStore(path,'current-boot')
  self.assertEqual(saved.read_level(self.sink),self.original_levels)
  self.assertIsNone(saved.restore_for(self.sink))
  self.assertEqual(saved.restore_for(disconnected),{'volume':[20000,10000],'mute':False})
  self.assert_no_audio_server_restart();self.assert_preserved()

 def test_failed_upgrade_restores_prior_volume_history(self):
  path=self.state/'native-volume.json'
  native.native_volume.LevelStore(path,'previous-boot').observe(self.sink,{'volume':[40000,20000],'mute':False})
  original=path.read_bytes();self.fail_start=True
  with mock.patch.object(native.native_volume,'boot_id',return_value='current-boot'):
   with self.assertRaisesRegex(native.b.BridgeError,'DSP start failed'):native.install(self.source,preserve_enabled=True)
  self.assertEqual(path.read_bytes(),original)
  self.assert_no_audio_server_restart();self.assert_preserved()

 def test_disabled_native_upgrade_keeps_enabled_and_startup_preferences(self):
  self.running=False;self.before['enabled']=False;native.b.save(native.b.SETTINGS,self.before)
  native.install(self.source,preserve_enabled=True)
  self.assert_no_audio_server_restart();self.assert_preserved()
  self.assertFalse(self.running);self.assertFalse(native.settings()['enabled'])

 def test_rollback_after_install_failure_preserves_active_audio_server(self):
  native.updater.setup.side_effect=RuntimeError('scheduler failed')
  with self.assertRaisesRegex(RuntimeError,'scheduler failed'):native.install(self.source,preserve_enabled=True)
  self.assert_no_audio_server_restart();self.assert_preserved()
  self.assertTrue(self.running);self.assertEqual(native.settings(),self.before)
  self.assertEqual((self.app/'bridge.py').read_text(),"VERSION='0.5.2'\n")

 def test_failed_dsp_restart_does_not_restart_policy_on_either_rollback(self):
  self.fail_start=True
  with self.assertRaisesRegex(native.b.BridgeError,'DSP start failed'):native.install(self.source,preserve_enabled=True)
  self.assert_no_audio_server_restart();self.assert_preserved()
  self.assertTrue(self.running);self.assertEqual(native.settings(),self.before)

 def test_unknown_playback_after_compile_cleans_staging_without_stopping_audio(self):
  with mock.patch.object(native.updater,'automatic',return_value=True),mock.patch.object(native.updater,'playback_busy',side_effect=native.updater.DeferredUpdate('playback unknown')):
   with self.assertRaisesRegex(native.updater.DeferredUpdate,'playback unknown'):native.install(self.source,preserve_enabled=True,scheduled=True)
  self.assertFalse(self.app.with_name('app.native-staging').exists())
  self.assertEqual(list((self.state.parent/'open-audio-bridge-upgrades').iterdir()),[])
  self.assertTrue(self.running);self.assert_preserved()
  self.assertFalse(any(cmd[:3]==['systemctl','--user','stop'] for cmd in self.calls))

 def test_missing_managed_profile_aborts_before_stopping_audio(self):
  self.profile.unlink()
  with self.assertRaisesRegex(native.b.BridgeError,'[Pp]erfil.*ausente'):native.install(self.source,preserve_enabled=True)
  self.assertTrue(self.running);self.assertEqual(native.settings(),self.before)
  self.assertEqual(native.RULE.read_text(),self.rule)
  self.assertEqual((self.app/'bridge.py').read_text(),"VERSION='0.5.2'\n")
  self.assertFalse(any(cmd[:3]==['systemctl','--user','stop'] for cmd in self.calls))

 def test_preparation_does_not_reuse_missing_managed_profile(self):
  self.profile.unlink()
  with self.assertRaisesRegex(native.b.BridgeError,'[Pp]erfil.*ausente'):native.prepare_mixers()
  self.assertEqual(native.settings(),self.before);self.assertEqual(native.RULE.read_text(),self.rule)
  self.assert_no_audio_server_restart()


class PolicyRestartTests(unittest.TestCase):
 def test_waits_for_stable_devices_then_restores_application_routes(self):
  levels={'alsa_output.test':{'volume':[23000,17000],'mute':True}}
  saved={'default_source':'alsa_input.test','streams':[{'serial':'912'}]};restored=[]
  with mock.patch.object(native.b,'default_sink',return_value='alsa_output.test'),mock.patch.object(native.b,'sink_by_name',return_value=None),mock.patch.object(native.b,'run',return_value=subprocess.CompletedProcess([],1,stdout='')),mock.patch.object(native,'level_snapshot',side_effect=[levels,{},levels,levels]) as snapshots,mock.patch.object(native,'restore_levels'),mock.patch.object(native.time,'sleep') as sleep,mock.patch.object(audio_routes,'snapshot',return_value=saved),mock.patch.object(audio_routes,'restore',side_effect=restored.append):
   native.restart_policy(levels)
  self.assertEqual(snapshots.call_count,4)
  self.assertEqual([call.args for call in sleep.call_args_list],[(.1,),(.1,),(.1,)])
  self.assertEqual(restored,[saved])

 def test_full_server_restart_keeps_pre_restart_levels_and_default_routes(self):
  levels={'alsa_output.test':{'volume':[23000,17000],'mute':True}};saved={'pid':'123','defaults':{'sink':'a','source':'m'},'streams':{}}
  events=[]
  def record(label):return lambda *args,**kwargs:events.append((label,args))
  with mock.patch.object(audio_routes,'snapshot',return_value=saved),mock.patch.object(native.b,'run',side_effect=record('restart')),mock.patch.object(native,'wait_policy_devices',side_effect=record('wait')),mock.patch.object(native,'restore_levels',side_effect=record('levels')),mock.patch.object(audio_routes,'restore',side_effect=record('routes')):
   native.restart_audio_server(levels)
  self.assertEqual([e[0] for e in events],['restart','wait','levels','routes'])
  self.assertEqual(events[0][1][0],['systemctl','--user','restart','pipewire','pipewire-pulse','wireplumber'])
  self.assertEqual(events[2][1],(levels,));self.assertEqual(events[3][1],(saved,))

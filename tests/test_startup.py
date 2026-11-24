import tempfile,unittest,json,contextlib
from pathlib import Path
from unittest import mock
import native

class StartupTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
  for obj,name,value in [(native.b,'SETTINGS',self.root/'settings.json'),(native.b,'AUTOSTART',self.root/'autostart.desktop'),(native,'BASE',self.root/'baseline.json')]:self.stack.enter_context(mock.patch.object(obj,name,value))
  native.BASE.write_text('{}');self.enabled=True;self.running=True;self.calls=[]
  self.stack.enter_context(mock.patch.object(native.b,'run',side_effect=self.run_command))
  self.save(autostart=True,enabled=True)
 def save(self,**config):native.b.save(native.b.SETTINGS,dict(routing='native',sound={'drive_db':12},**config))
 def run_command(self,args,**kwargs):
  self.calls.append(args)
  if args[2]=='enable':self.enabled=True
  if args[2]=='disable':self.enabled=False
  if '--now' in args or args[2] in ['start','stop','restart']:raise AssertionError('Startup preference must not interrupt audio')
  return mock.Mock(returncode=0 if self.running else 3,stdout='')
 def test_preference_controls_tray_and_service_without_stopping_audio(self):
  native.set_startup(False)
  self.assertFalse(self.enabled);self.assertTrue(self.running)
  self.assertIn('Hidden=true',native.b.AUTOSTART.read_text())
  self.assertFalse(native.settings()['autostart']);self.assertEqual(native.settings()['sound']['drive_db'],12)
  native.set_startup(True)
  self.assertTrue(self.enabled);self.assertNotIn('Hidden=true',native.b.AUTOSTART.read_text())
 def test_disabled_effect_does_not_start_at_login_even_when_tray_does(self):
  self.save(autostart=True,enabled=False);native.sync_startup()
  self.assertFalse(self.enabled);self.assertNotIn('Hidden=true',native.b.AUTOSTART.read_text())
 def test_upgrade_does_not_start_dormant_app_or_reset_preference(self):
  self.save(autostart=False,enabled=False)
  before={'enabled':True,'autostart':False}
  with mock.patch.object(native,'enable',side_effect=AssertionError('Dormant update must not start DSP')):
   native.finish_install(before,running=False,preserve_enabled=True)
  self.assertTrue(native.settings()['enabled']);self.assertFalse(native.settings()['autostart']);self.assertFalse(self.enabled)
 def test_upgrade_resumes_running_app_even_with_startup_off(self):
  self.save(autostart=False,enabled=False)
  with mock.patch.object(native,'enable') as enable:native.finish_install({'enabled':True,'autostart':False},running=True,preserve_enabled=True)
  enable.assert_called_once();self.assertFalse(native.settings()['autostart'])
 def test_manual_launch_resumes_only_previously_enabled_processing(self):
  self.save(autostart=False,enabled=True);self.running=False
  with mock.patch.object(native,'enable') as enable:
   native.resume();enable.assert_called_once();enable.reset_mock()
   self.running=True;native.resume();enable.assert_not_called()
   self.running=False;self.save(autostart=False,enabled=False);native.resume();enable.assert_not_called()
 def test_audio_failure_still_reports_saved_startup_preference(self):
  self.save(autostart=False,enabled=True)
  with mock.patch.object(native.b,'sinks',side_effect=native.b.BridgeError('offline')):
   self.assertIs(native.status().get('autostart'),False)
 def test_failed_preference_write_restores_previous_settings(self):
  previous=native.settings();native.b.AUTOSTART.write_text('old desktop')
  with mock.patch.object(native,'sync_startup',side_effect=[RuntimeError('failed'),None]):
   with self.assertRaises(RuntimeError):native.set_startup(False)
  self.assertEqual(native.settings(),previous);self.assertEqual(native.b.AUTOSTART.read_text(),'old desktop')

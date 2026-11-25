import os,sys,tempfile,unittest,json,time
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt5 import QtCore,QtGui,QtWidgets as W
from unittest import mock
import gui,install
app=W.QApplication.instance() or W.QApplication([])
def wait(seconds):
 until=time.monotonic()+seconds
 while time.monotonic()<until:app.processEvents();time.sleep(.005)
class GuiTests(unittest.TestCase):
 def native_window(self,**changes):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);root=Path(tmp.name)
  status=dict(active=True,enabled=True,connected=True,volume=37,mute=False,curve='boost',target='default',resolved_target='alsa_output.speakers',resolved_description='Alto-falantes',routing='native',devices=[dict(name='alsa_output.speakers',description='Alto-falantes')])
  status.update(changes);state=root/'state.json';state.write_text(json.dumps(status))
  (root/'bridge.py').write_text('''import sys,json\nfrom pathlib import Path\np=Path(__file__).with_name('state.json')\ns=json.loads(p.read_text())\nif sys.argv[1]=='status':print(json.dumps(s))\nelif sys.argv[1]=='set-device':\n s['target']=sys.argv[2];p.write_text(json.dumps(s))\nelif sys.argv[1]=='volume':\n s['volume']=int(sys.argv[2]);p.write_text(json.dumps(s))\nelif sys.argv[1]=='set-sound':\n s['sound']=json.loads(sys.argv[2]);p.write_text(json.dumps(s))\nelif sys.argv[1]=='set-startup':\n s['autostart']=sys.argv[2]=='1';p.write_text(json.dumps(s))\nelif sys.argv[1]=='update-auto':\n s.setdefault('updates',{})['automatic']=sys.argv[2]=='1';p.write_text(json.dumps(s))\nelif sys.argv[1]=='update':\n s['manual_update']=True;s.setdefault('updates',{}).update(message='Atualização aplicada.',state='updated',last_checked=1700000000);p.write_text(json.dumps(s))\nelse:raise SystemExit(2)\n''')
  script=root/'bridge.py'
  script.write_text(script.read_text().replace('import sys,json\n','import sys,json,time\n').replace("if sys.argv[1]=='status':print(json.dumps(s))","if sys.argv[1]=='status':time.sleep(s.get('status_delay',0));print(json.dumps(s))").replace("elif sys.argv[1]=='set-sound':\n", "elif sys.argv[1]=='set-sound':\n with p.with_name('sound_calls.jsonl').open('a') as log:log.write(sys.argv[2]+'\\n')\n time.sleep(s.get('sound_delay',0))\n s=json.loads(p.read_text())\n"))
  patch=mock.patch.object(gui,'ROOT',root);patch.start();self.addCleanup(patch.stop)
  window=gui.Window();window.timer.stop()
  def cleanup():
   window.timer.stop();window.volume_timer.stop();window.sound_timer.stop();window.meter.shutdown();window.tray.hide()
   for process in (window.action,window.reader):
    if process.state()!=QtCore.QProcess.NotRunning:process.waitForFinished(2000)
   window.deleteLater();app.processEvents()
  self.addCleanup(cleanup);wait(.15)
  return window,state
 def test_sound_controls_remain_editable_and_only_latest_snapshot_is_queued(self):
  window,state=self.native_window(sound_delay=.65,sound={'eq_enabled':True})
  window.drive.setValue(15);wait(.43)
  self.assertTrue(window.busy)
  for control in [window.drive,window.eq_enabled,window.eq_preset,window.music_mode,window.width,*window.eq_sliders]:self.assertTrue(control.isEnabled())
  self.assertFalse(window.update_button.isEnabled())
  window.drive.setValue(11);window.width.setValue(7);window.eq_sliders[0].setValue(-4)
  index=window.music_mode.findData('warm');window.music_mode.setCurrentIndex(index);window.music_mode.activated.emit(index)
  window.drive.setValue(9);window.width.setValue(12);wait(.75)
  self.assertEqual(window.drive.value(),9);self.assertEqual(window.eq_sliders[0].value(),-4)
  wait(.8)
  calls=[json.loads(line) for line in state.with_name('sound_calls.jsonl').read_text().splitlines()]
  self.assertEqual(len(calls),2)
  self.assertEqual(calls[-1]['drive_db'],9);self.assertEqual(calls[-1]['width'],12)
  self.assertEqual(calls[-1]['music_mode'],'warm');self.assertEqual(calls[-1]['bands'][0],-2)
  self.assertEqual(json.loads(state.read_text())['sound'],calls[-1])
 def test_preset_animates_intermediate_bars_without_extra_sound_commands(self):
  window,state=self.native_window()
  index=window.eq_preset.findData('rock');signals=[];window.eq_sliders[0].valueChanged.connect(signals.append)
  window.eq_preset.setCurrentIndex(index);window.eq_preset.activated.emit(index)
  self.assertEqual(window.eq_sliders[0].value(),0)
  wait(.23);middle=window.eq_sliders[0].value()
  self.assertGreater(middle,0);self.assertLess(middle,4)
  wait(.32);self.assertEqual(window.eq_sliders[0].value(),4)
  self.assertEqual(signals,[])
  wait(.35)
  calls=state.with_name('sound_calls.jsonl').read_text().splitlines()
  self.assertEqual(len(calls),1);self.assertEqual(json.loads(calls[0])['preset'],'rock')
 def test_equalizer_layout_remains_stationary_while_applying(self):
  window,state=self.native_window(sound_delay=.6,sound={'eq_enabled':True})
  window.show();window.tabs.setCurrentWidget(window.eq_page);wait(.1)
  widgets=[window.tabs,window.eq_enabled,window.eq_preset,*window.eq_sliders,window.toggle,window.refresh_button]
  def geometry():return [(widget.mapTo(window,QtCore.QPoint(0,0)),widget.size()) for widget in widgets]
  for edit in (lambda:window.eq_preset.activated.emit(window.eq_preset.findData('rock')),lambda:window.eq_enabled.setChecked(False),lambda:window.eq_enabled.setChecked(True)):
   before=geometry();destination=window.destination_label.text();edit();wait(.45)
   self.assertTrue(window.busy)
   self.assertIn('Aplicando',window.status_label.text());self.assertEqual(window.destination_label.text(),destination)
   self.assertEqual(geometry(),before,'Changing to Applying must not shift any control')
   wait(.7)
   self.assertFalse(window.busy)
   self.assertIn('Ativo',window.status_label.text());self.assertEqual(window.destination_label.text(),destination)
   self.assertEqual(geometry(),before,'Returning to Active must not shift any control')
 def test_header_long_output_name_is_elided_without_shifting_tabs(self):
  window,state=self.native_window()
  window.show();window.tabs.setCurrentWidget(window.eq_page);wait(.1)
  before=window.tabs.geometry();before_size=window.size()
  data=json.loads(state.read_text());data['resolved_description']='Saída de áudio '+('nome extremamente longo '*40);state.write_text(json.dumps(data));window.refresh();wait(.2)
  self.assertEqual(window.tabs.geometry(),before);self.assertEqual(window.size(),before_size)
  self.assertIn(data['resolved_description'],window.destination_label.toolTip())
  self.assertTrue(window.destination_label.text().endswith('…'))
 def test_manual_edit_interrupts_animation_and_rapid_presets_keep_latest_target(self):
  window,state=self.native_window()
  for name in ['rock','funk','voice']:
   index=window.eq_preset.findData(name)
   self.assertGreaterEqual(index,0)
   window.eq_preset.setCurrentIndex(index);window.eq_preset.activated.emit(index);wait(.04)
  window.eq_sliders[0].setValue(-5);wait(.4)
  self.assertEqual(window.eq_sliders[0].value(),-5)
  self.assertEqual(window.eq_preset.currentData(),'custom')
  wait(.3);calls=state.with_name('sound_calls.jsonl').read_text().splitlines()
  self.assertEqual(len(calls),1);self.assertEqual(json.loads(calls[0])['bands'][0],-2.5)
 def test_rapid_presets_finish_at_latest_curve_with_one_application(self):
  window,state=self.native_window()
  for name in ['rock','funk','voice']:
   index=window.eq_preset.findData(name);window.eq_preset.setCurrentIndex(index);window.eq_preset.activated.emit(index);wait(.04)
  wait(.65)
  self.assertEqual([slider.value() for slider in window.eq_sliders],[-6,-6,-4,-2,0,4,6,4,0,-2])
  self.assertEqual(window.eq_preset.currentData(),'voice')
  calls=state.with_name('sound_calls.jsonl').read_text().splitlines()
  self.assertEqual(len(calls),1);self.assertEqual(json.loads(calls[0])['preset'],'voice')
 def test_delayed_status_cannot_overwrite_new_sound_after_application(self):
  window,state=self.native_window()
  data=json.loads(state.read_text());data['status_delay']=.65;state.write_text(json.dumps(data))
  window.refresh();wait(.05)
  window.drive.setValue(7);wait(.8)
  self.assertEqual(json.loads(state.read_text())['sound']['drive_db'],7)
  self.assertEqual(window.drive.value(),7)
  self.assertEqual(window.sound_state['drive_db'],7)
 def test_visible_equalizer_monitors_selected_output_and_hide_releases_it(self):
  window,state=self.native_window(playing=True)
  (state.parent/'spectrum.py').write_text('import json,time\nwhile True:\n print(json.dumps([-20]*10),flush=True);time.sleep(.04)\n')
  window.show_window();window.tabs.setCurrentWidget(window.eq_page);wait(.4)
  self.assertEqual(window.meter.running_target,'alsa_output.speakers')
  self.assertGreater(window.eq_sliders[0].level,-45)
  window.tabs.setCurrentIndex(0);wait(.3);self.assertFalse(window.meter.running)
  self.assertEqual(window.eq_sliders[0].level,-80)
  window.tabs.setCurrentWidget(window.eq_page);wait(.4);self.assertTrue(window.meter.running)
  window.hide();wait(.3);self.assertFalse(window.meter.running)
 def test_settings_keep_uninstall_out_of_main_page_and_persist_startup(self):
  window,state=self.native_window(autostart=True)
  labels=[window.tabs.tabText(i) for i in range(window.tabs.count())]
  self.assertIn('Configurações',labels)
  self.assertIs(window.remove.parentWidget(),window.settings_page)
  window.startup.setChecked(False);wait(.3)
  saved=json.loads(state.read_text())
  self.assertFalse(saved['autostart']);self.assertTrue(saved['active']);self.assertEqual(saved['volume'],37)
  window.refresh();wait(.2);self.assertFalse(window.startup.isChecked())
  window.startup.setChecked(True);wait(.3);self.assertTrue(json.loads(state.read_text())['autostart'])
 def test_startup_status_sync_does_not_reset_disabled_preference(self):
  window,state=self.native_window(autostart=False)
  self.assertFalse(window.startup.isChecked());self.assertFalse(json.loads(state.read_text())['autostart'])

 def test_system_default_stays_selectable_and_follows_native_device(self):
  window,state=self.native_window()
  self.assertEqual(window.device.itemData(0),'default')
  self.assertEqual(window.device.currentData(),'default')
  self.assertIn('Alto-falantes',window.destination_label.toolTip())
  window.device.setCurrentIndex(1);window.device.activated.emit(1);wait(.2)
  self.assertEqual(json.loads(state.read_text())['target'],'alsa_output.speakers')
  window.device.setCurrentIndex(0);window.device.activated.emit(0);wait(.2)
  self.assertEqual(json.loads(state.read_text())['target'],'default')
 def test_default_available_without_devices(self):
  window,_=self.native_window(active=False,connected=False,devices=[],resolved_target=None,resolved_description=None)
  self.assertEqual(window.device.currentData(),'default')
  self.assertEqual(window.device.count(),1)
  self.assertIn('indisponível',window.destination_label.toolTip().lower())
 def test_disconnected_fixed_device_keeps_selection(self):
  window,_=self.native_window(active=False,connected=False,target='bluez_output.missing',resolved_target=None,resolved_description=None)
  self.assertEqual(window.device.currentData(),'bluez_output.missing')
  self.assertIn('desconectad',window.device.currentText().lower())
  self.assertEqual(window.device.itemData(0),'default')
 def test_tray_remains_available_when_window_closes(self):
  window,_=self.native_window()
  self.assertTrue(window.tray.isVisible())
  event=QtGui.QCloseEvent()
  with mock.patch.object(W.QSystemTrayIcon,'isSystemTrayAvailable',return_value=True):window.closeEvent(event)
  self.assertFalse(event.isAccepted())
  self.assertTrue(window.tray.isVisible())
  window.show_window();self.assertTrue(window.isVisible())
 def test_volume_reads_external_changes_and_writes_same_backend_value(self):
  window,state=self.native_window()
  self.assertEqual(window.slider.value(),37)
  status=json.loads(state.read_text());status['volume']=62;state.write_text(json.dumps(status));window.refresh();wait(.15)
  self.assertEqual(window.slider.value(),62)
  window.slider.setValue(48);wait(.4)
  self.assertEqual(json.loads(state.read_text())['volume'],48)
 def test_pending_volume_survives_mute_action(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);state=root/'state.json';state.write_text(json.dumps({'volume':25,'mute':False}))
   (root/'bridge.py').write_text('''import sys,json,time\nfrom pathlib import Path\np=Path(__file__).with_name('state.json')\ns=json.loads(p.read_text());c=sys.argv[1]\nif c!='status':\n time.sleep(.3)\n if c=='volume':s['volume']=float(sys.argv[2])\n if c=='mute':s['mute']=sys.argv[2]=='1'\n p.write_text(json.dumps(s))\nelse:print(json.dumps(dict(s,active=True,enabled=True,connected=True,devices=[],curve='boost')))\n''')
   with mock.patch.object(gui,'ROOT',root):
    window=gui.Window();window.timer.stop();wait(.15)
    window.slider.setValue(40);window.mute.setChecked(True);wait(1.2)
    result=json.loads(state.read_text());self.assertEqual(result,{'volume':40.0,'mute':True})
    window.tray.hide();window.deleteLater();app.processEvents()
 def test_installer_cannot_close_mid_operation(self):
  window=install.Installer();window.show();window.process.start(sys.executable,['-c','import time;time.sleep(.4)']);window.process.waitForStarted(1000)
  window.close();app.processEvents();self.assertTrue(window.isVisible())
  wait(.6);window.close();app.processEvents();self.assertFalse(window.isVisible());window.deleteLater()

 def test_native_window_cannot_close_during_pending_or_running_change(self):
  window,_=self.native_window()
  window.busy=True;event=QtGui.QCloseEvent();window.closeEvent(event)
  self.assertFalse(event.isAccepted())
  window.busy=False;window.volume_timer.start(180);event=QtGui.QCloseEvent();window.closeEvent(event)
  self.assertFalse(event.isAccepted())
  window.volume_timer.stop();event=QtGui.QCloseEvent()
  with mock.patch.object(W.QSystemTrayIcon,'isSystemTrayAvailable',return_value=False):window.closeEvent(event)
  self.assertTrue(event.isAccepted())

 def test_preset_and_manual_bands_keep_gain_and_system_volume(self):
  window,state=self.native_window()
  window.drive.setValue(10);wait(.7)
  index=window.eq_preset.findData('rock');window.eq_preset.setCurrentIndex(index);window.eq_preset.activated.emit(index);wait(.7)
  saved=json.loads(state.read_text())
  self.assertEqual(saved['sound']['drive_db'],10)
  self.assertEqual(saved['sound']['preset'],'rock')
  self.assertTrue(saved['sound']['eq_enabled'])
  self.assertEqual(saved['volume'],37)
  window.eq_sliders[0].setValue(-4);wait(.7)
  saved=json.loads(state.read_text())
  self.assertEqual(saved['sound']['preset'],'custom')
  self.assertEqual(saved['sound']['bands'][0],-2)
  window.eq_enabled.setChecked(False);wait(.7)
  saved=json.loads(state.read_text())
  self.assertFalse(saved['sound']['eq_enabled'])
  self.assertEqual(saved['sound']['drive_db'],10)
  self.assertEqual(saved['sound']['bands'][0],-2)

 def test_music_mode_and_width_preserve_manual_equalizer(self):
  window,state=self.native_window()
  index=window.music_mode.findData('warm');window.music_mode.setCurrentIndex(index);window.music_mode.activated.emit(index);wait(.7)
  window.width.setValue(12);wait(.7)
  saved=json.loads(state.read_text());self.assertEqual(saved['sound']['music_mode'],'warm');self.assertEqual(saved['sound']['width'],12)
  self.assertEqual(saved['sound']['drive_db'],18)
  self.assertEqual(saved['volume'],37)
  self.assertFalse(saved['sound']['eq_enabled'])
 def test_update_controls_persist_preference_and_apply_manually(self):
  window,state=self.native_window(updates=dict(automatic=True,last_checked=0,available_version=None,message='',error='',state='idle'))
  self.assertIn('Atualizações',[window.tabs.tabText(i) for i in range(window.tabs.count())])
  self.assertTrue(window.update_auto.isChecked())
  window.update_auto.setChecked(False);wait(.25)
  self.assertFalse(json.loads(state.read_text())['updates']['automatic'])
  window.update_auto.setChecked(True);wait(.25)
  self.assertTrue(json.loads(state.read_text())['updates']['automatic'])
  window.update_button.click()
  self.assertTrue(window.busy)
  self.assertFalse(window.update_auto.isEnabled())
  for control in [window.drive,window.eq_enabled,window.eq_preset,window.music_mode,window.width,*window.eq_sliders]:self.assertFalse(control.isEnabled())
  event=QtGui.QCloseEvent();window.closeEvent(event);self.assertFalse(event.isAccepted())
  wait(.3)
  self.assertTrue(json.loads(state.read_text())['manual_update'])
  self.assertIn('Atualização aplicada',window.update_status.text())
  self.assertNotIn('Nunca',window.update_checked.text())
  self.assertIn('Ativo',window.status_label.text())

 def test_update_error_preserves_audio_status_and_shows_version(self):
  window,_=self.native_window(version=gui.VERSION,installed=True,updates=dict(automatic=False,last_checked=0,available_version='99.1.0',message='Tente novamente.',error='Sem conexão',state='error'))
  self.assertFalse(window.update_auto.isChecked())
  self.assertIn(gui.VERSION,window.update_version.text())
  self.assertIn('99.1.0',window.update_status.text())
  self.assertIn('Sem conexão',window.update_status.text())
  self.assertIn('Ativo',window.status_label.text())

 def test_reload_waits_for_pending_changes_and_emits_once(self):
  window,state=self.native_window(installed=True,version=gui.VERSION)
  requested=[];window.restart_requested.connect(requested.append)
  data=json.loads(state.read_text());data['version']='99.1.0';state.write_text(json.dumps(data))
  window.sound_timer.start(10000);window.refresh();wait(.15)
  self.assertEqual(requested,[])
  window.sound_timer.stop();window.volume_timer.start(10000);window.refresh();wait(.15)
  self.assertEqual(requested,[])
  window.volume_timer.stop();window.busy=True;window.refresh();wait(.15)
  self.assertEqual(requested,[])
  window.busy=False;window.show();window.refresh();wait(.15)
  self.assertEqual(requested,[True])
  window.refresh();wait(.15);self.assertEqual(requested,[True])

 def test_missing_version_and_uninstalled_source_do_not_restart(self):
  window,state=self.native_window(installed=True)
  requested=[];window.restart_requested.connect(requested.append)
  window.refresh();wait(.15);self.assertEqual(requested,[])
  data=json.loads(state.read_text());data.update(installed=False,version='99.1.0');state.write_text(json.dumps(data))
  window.refresh();wait(.15);self.assertEqual(requested,[])

 def test_restart_releases_singleton_before_spawning_and_preserves_hidden_state(self):
  window,_=self.native_window();window.hide()
  server=gui.QtNetwork.QLocalServer();name='oab-test-restart-'+str(os.getpid());server.listen(name)
  self.addCleanup(lambda:gui.QtNetwork.QLocalServer.removeServer(name))
  def replacement(program,args,directory):
   self.assertFalse(server.isListening())
   self.assertEqual(program,sys.executable)
   self.assertIn('--tray',args)
   self.assertIn('--no-resume',args)
   probe=gui.QtNetwork.QLocalServer();self.assertTrue(probe.listen(name));probe.close();gui.QtNetwork.QLocalServer.removeServer(name)
   return (True,12345)
  with mock.patch.object(QtCore.QProcess,'startDetached',side_effect=replacement),mock.patch.object(app,'quit') as quit_app:
   gui.restart_interface(window,app,server,name,False)
   quit_app.assert_called_once()
  self.assertFalse(window.tray.isVisible())

 def test_failed_restart_restores_singleton_and_keeps_tray(self):
  window,_=self.native_window();window.restart_pending=True
  server=gui.QtNetwork.QLocalServer();name='oab-test-restart-failure-'+str(os.getpid());server.listen(name)
  self.addCleanup(lambda:gui.QtNetwork.QLocalServer.removeServer(name))
  with mock.patch.object(QtCore.QProcess,'startDetached',return_value=(False,0)),mock.patch.object(app,'quit') as quit_app:
   gui.restart_interface(window,app,server,name,True)
   quit_app.assert_not_called()
  self.assertTrue(server.isListening());server.close()
  self.assertFalse(window.restart_pending)
  self.assertTrue(window.tray.isVisible())
  self.assertIn('Feche e abra',window.update_status.text())

 def test_restart_callback_rechecks_new_pending_change(self):
  window,state=self.native_window(installed=True,version=gui.VERSION)
  requested=[];window.restart_requested.connect(requested.append)
  window.last['version']='99.1.0';window.maybe_restart()
  window.volume_timer.start(10000);wait(.03)
  self.assertEqual(requested,[])
  self.assertFalse(window.restart_pending)
  window.volume_timer.stop();window.queue=[('volume','40')];window.maybe_restart();wait(.03)
  self.assertEqual(requested,[])
  window.queue=[];window.maybe_restart();wait(.03)
  self.assertEqual(requested,[False])

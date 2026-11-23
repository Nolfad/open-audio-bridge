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
  (root/'bridge.py').write_text('''import sys,json\nfrom pathlib import Path\np=Path(__file__).with_name('state.json')\ns=json.loads(p.read_text())\nif sys.argv[1]=='status':print(json.dumps(s))\nelif sys.argv[1]=='set-device':\n s['target']=sys.argv[2];p.write_text(json.dumps(s))\nelif sys.argv[1]=='volume':\n s['volume']=int(sys.argv[2]);p.write_text(json.dumps(s))\nelse:raise SystemExit(2)\n''')
  patch=mock.patch.object(gui,'ROOT',root);patch.start();self.addCleanup(patch.stop)
  window=gui.Window();window.timer.stop()
  def cleanup():
   window.timer.stop();window.volume_timer.stop();window.tray.hide()
   for process in (window.action,window.reader):
    if process.state()!=QtCore.QProcess.NotRunning:process.waitForFinished(2000)
   window.deleteLater();app.processEvents()
  self.addCleanup(cleanup);wait(.15)
  return window,state
 def test_system_default_stays_selectable_and_follows_native_device(self):
  window,state=self.native_window()
  self.assertEqual(window.device.itemData(0),'default')
  self.assertEqual(window.device.currentData(),'default')
  self.assertIn('Alto-falantes',window.status_label.text())
  window.device.setCurrentIndex(1);window.device.activated.emit(1);wait(.2)
  self.assertEqual(json.loads(state.read_text())['target'],'alsa_output.speakers')
  window.device.setCurrentIndex(0);window.device.activated.emit(0);wait(.2)
  self.assertEqual(json.loads(state.read_text())['target'],'default')
 def test_default_available_without_devices(self):
  window,_=self.native_window(active=False,connected=False,devices=[],resolved_target=None,resolved_description=None)
  self.assertEqual(window.device.currentData(),'default')
  self.assertEqual(window.device.count(),1)
  self.assertIn('indisponível',window.status_label.text().lower())
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

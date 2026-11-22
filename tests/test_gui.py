import os,sys,tempfile,unittest,json,time
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt5 import QtCore,QtWidgets as W
from unittest import mock
import gui,install
app=W.QApplication.instance() or W.QApplication([])
def wait(seconds):
 until=time.monotonic()+seconds
 while time.monotonic()<until:app.processEvents();time.sleep(.005)
class GuiTests(unittest.TestCase):
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

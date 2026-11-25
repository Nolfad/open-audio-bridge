import os,sys,tempfile,time,unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PyQt5 import QtCore,QtWidgets as W
from meter_ui import MeterSlider,SpectrumController
app=W.QApplication.instance() or W.QApplication([])
def wait_until(condition,seconds=2):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  app.processEvents()
  if condition():return True
  time.sleep(.005)
 return False
class MeterTests(unittest.TestCase):
 def test_meter_never_changes_gain_or_emits_edit(self):
  slider=MeterSlider();slider.setRange(-12,12);slider.setValue(3);slider.resize(48,200)
  calls=[];slider.valueChanged.connect(calls.append)
  slider.set_meter_db(-15,-9);self.assertEqual(slider.value(),3);self.assertEqual(calls,[])
  self.assertEqual(slider.level,-15);self.assertEqual(slider.peak,-9)
  self.assertFalse(slider.grab().isNull())
  slider.clear_meter();self.assertEqual(slider.level,-80)
 def test_animation_paints_distinct_intermediate_frames_in_native_styles(self):
  for name in ('Fusion','Breeze'):
   style=W.QStyleFactory.create(name)
   if style is None:continue
   with self.subTest(style=name):
    slider=MeterSlider();slider.setStyle(style);slider.setRange(-12,12);slider.setTickInterval(4);slider.setValue(0);slider.resize(46,220);slider.show();app.processEvents()
    try:
     frames=[]
     for position in (-10.0,-5.25,0.0,5.25,10.0):
      slider.set_animation_position(position);app.processEvents()
      frames.append(slider.grab().toImage())
     self.assertTrue(all(a!=b for a,b in zip(frames,frames[1:])), 'Animated native slider must render distinct intermediate positions')
     self.assertEqual(slider.value(),0)
    finally:
     slider.hide();slider.deleteLater();app.processEvents()
 def test_worker_only_when_visible_playing_and_target_is_selected(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   (root/'spectrum.py').write_text('import json,sys,time\nwhile True:\n print(json.dumps([-15]+[-60]*9),flush=True);time.sleep(.04)\n')
   sliders=[MeterSlider() for _ in range(10)];controller=SpectrumController(root,sliders)
   try:
    controller.set_context('alsa_output.first',True,False)
    self.assertFalse(controller.running)
    controller.set_context('alsa_output.first',False,True)
    self.assertFalse(controller.running)
    controller.set_context('alsa_output.first',True,True)
    self.assertTrue(wait_until(lambda:sliders[0].level>-30))
    self.assertGreater(sliders[0].level,sliders[1].level)
    self.assertEqual(controller.running_target,'alsa_output.first')
    controller.set_context('alsa_output.second',True,True)
    self.assertTrue(wait_until(lambda:controller.running_target=='alsa_output.second' and controller.running))
    controller.set_context('alsa_output.second',False,True)
    self.assertTrue(wait_until(lambda:not controller.running))
    self.assertTrue(all(s.level==-80 for s in sliders))
    controller.set_context('invalid',True,True)
    self.assertFalse(controller.running)
   finally:controller.shutdown()
 def test_invalid_frames_are_ignored(self):
  sliders=[MeterSlider() for _ in range(10)];controller=SpectrumController(Path('/nonexistent'),sliders)
  for line in (b'[1]',b'not-json',b'[NaN,0,0,0,0,0,0,0,0,0]',b'[true,0,0,0,0,0,0,0,0,0]'):
   controller.accept_frame(line);self.assertEqual(controller.levels,[-80.]*10)
  controller.accept_frame(b'[-30,-20,-10,0,1,-90,-60,-50,-40,-20]')
  self.assertEqual(controller.levels,[-30,-20,-10,0,0,-80,-60,-50,-40,-20])
  controller.shutdown()
if __name__=='__main__':unittest.main()

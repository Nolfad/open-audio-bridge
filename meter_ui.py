"""A display-only, per-band dBFS meter. Gain remains a separate native control."""
import json,math,sys,time
from PyQt5 import QtCore,QtGui,QtWidgets as W
FLOOR=-80.
MAX_DB=0.
def clamp(value):
 return min(MAX_DB,max(FLOOR,float(value))) if math.isfinite(value) else FLOOR

class MeterSlider(W.QSlider):
 def __init__(self,parent=None):
  super().__init__(QtCore.Qt.Vertical,parent)
  self.level=self.peak=FLOOR;self.animation_position=None
  self.setFixedWidth(46)
  self.setTickPosition(W.QSlider.TicksLeft)
 def set_meter_db(self,level,peak=None):
  self.level=clamp(level);self.peak=clamp(level if peak is None else peak);self.update()
 def clear_meter(self):
  self.set_meter_db(FLOOR)
 def set_animation_position(self,position=None):
  self.animation_position=position;self.update()
 def paintEvent(self,event):
  if self.animation_position is None:super().paintEvent(event)
  else:
   # Preserve the normal half-dB interaction/keyboard steps, but draw
   # intermediate handle positions smoothly at sub-step precision.
   option=W.QStyleOptionSlider();self.initStyleOption(option)
   scale=100
   option.minimum*=scale;option.maximum*=scale;option.tickInterval*=scale
   option.singleStep*=scale;option.pageStep*=scale
   option.sliderPosition=option.sliderValue=round(self.animation_position*scale)
   # QSlider.paintEvent normally selects these subcontrols itself. Without
   # them, both Breeze and Fusion draw nothing during our custom frames.
   option.subControls=W.QStyle.SC_SliderGroove|W.QStyle.SC_SliderHandle
   if self.tickPosition()!=W.QSlider.NoTicks:option.subControls|=W.QStyle.SC_SliderTickmarks
   native=W.QStylePainter(self);native.drawComplexControl(W.QStyle.CC_Slider,option);native.end()
  painter=QtGui.QPainter(self);painter.setRenderHint(QtGui.QPainter.Antialiasing)
  track=QtCore.QRectF(self.width()-12,8,8,max(1,self.height()-16))
  painter.setPen(QtCore.Qt.NoPen)
  background=self.palette().color(QtGui.QPalette.Mid)
  background.setAlpha(85);painter.setBrush(background);painter.drawRoundedRect(track,3,3)
  gradient=QtGui.QLinearGradient(track.bottomLeft(),track.topLeft())
  for position,color in ((0.,'#20b897'),(.62,'#49d28d'),(.83,'#e8ca53'),(.95,'#f28a51'),(1.,'#e95f64')):
   gradient.setColorAt(position,QtGui.QColor(color))
  ratio=(self.level-FLOOR)/-FLOOR
  if ratio>0:
   fill=QtCore.QRectF(track.x(),track.bottom()-track.height()*ratio,track.width(),track.height()*ratio)
   painter.setBrush(QtGui.QBrush(gradient));painter.drawRoundedRect(fill,2,2)
  if self.peak>FLOOR:
   y=track.bottom()-track.height()*(self.peak-FLOOR)/-FLOOR
   painter.setPen(QtGui.QPen(self.palette().color(QtGui.QPalette.Text),1.5))
   painter.drawLine(QtCore.QPointF(track.left(),y),QtCore.QPointF(track.right(),y))
  painter.end()

class SpectrumController(QtCore.QObject):
 """Collect nonblocking analyzer frames, stop capture outside the visible EQ."""
 def __init__(self,root,sliders,parent=None):
  super().__init__(parent);self.root=root;self.sliders=sliders
  self.desired=None;self.running_target=None;self.levels=[FLOOR]*10;self.buffer=b''
  self.displayed=[FLOOR]*10;self.peaks=[FLOOR]*10;self.hold=[0.]*10;self.last_frame=0.
  self.process=QtCore.QProcess(self);self.process.readyReadStandardOutput.connect(self.read_frames)
  self.process.readyReadStandardError.connect(lambda:self.process.readAllStandardError())
  self.process.finished.connect(self.finished);self.process.errorOccurred.connect(self.process_error)
  self.timer=QtCore.QTimer(self);self.timer.setInterval(40);self.timer.timeout.connect(self.tick)
  self.retry=QtCore.QTimer(self);self.retry.setSingleShot(True);self.retry.timeout.connect(self.start)
  self.kill_timer=QtCore.QTimer(self);self.kill_timer.setSingleShot(True);self.kill_timer.timeout.connect(self.kill)
 @property
 def running(self):return self.process.state()!=QtCore.QProcess.NotRunning
 def set_context(self,target,visible,playing):
  desired=target if visible and playing and isinstance(target,str) and target.startswith(('alsa_output.','bluez_output.')) and (self.root/'spectrum.py').is_file() else None
  if desired==self.desired:return
  self.desired=desired;self.retry.stop()
  if self.running:
   self.process.terminate();self.kill_timer.start(4500)
  self.clear()
  if desired and not self.running:self.start()
 def start(self):
  if not self.desired or self.running:return
  self.kill_timer.stop();self.running_target=self.desired;self.buffer=b''
  self.process.start(sys.executable,[str(self.root/'spectrum.py'),self.desired])
  self.timer.start()
 def kill(self):
  if self.running:self.process.kill()
 def clear(self):
  self.timer.stop();self.levels=[FLOOR]*10;self.displayed=[FLOOR]*10;self.peaks=[FLOOR]*10;self.hold=[0.]*10;self.last_frame=0.
  for slider in self.sliders:slider.clear_meter()
 def finished(self,*_):
  old=self.running_target;self.running_target=None;self.kill_timer.stop();self.clear()
  if self.desired:self.retry.start(20 if self.desired!=old else 1200)
 def process_error(self,_):
  if not self.running:self.finished()
 def read_frames(self):
  data=bytes(self.process.readAllStandardOutput())
  if self.desired!=self.running_target:return
  self.buffer+=data
  while b'\n' in self.buffer:
   line,self.buffer=self.buffer.split(b'\n',1);self.accept_frame(line)
  if len(self.buffer)>65536:self.buffer=b''
 def accept_frame(self,line):
  try:
   values=json.loads(line)
   if not isinstance(values,list) or len(values)!=10 or any(type(v) not in (int,float) or not math.isfinite(v) for v in values):return
   self.levels=[clamp(v) for v in values];self.last_frame=time.monotonic()
  except (ValueError,TypeError,OverflowError):return
 def tick(self):
  now=time.monotonic()
  levels=self.levels if now-self.last_frame<.3 else [FLOOR]*10
  for i,target in enumerate(levels):
   current=self.displayed[i]
   current+=(target-current)*(.72 if target>current else .21)
   if current<FLOOR+.2:current=FLOOR
   self.displayed[i]=current
   if current>=self.peaks[i]:
    self.peaks[i]=current;self.hold[i]=now+.22
   elif now>=self.hold[i]:self.peaks[i]=max(current,self.peaks[i]-4)
   self.sliders[i].set_meter_db(current,self.peaks[i])
 def shutdown(self):
  self.desired=None;self.retry.stop();self.kill_timer.stop();self.clear()
  if self.running:
   self.process.terminate()
   if not self.process.waitForFinished(4500):
    self.process.kill();self.process.waitForFinished(250)

#!/usr/bin/env python3
"""Small KDE-friendly control panel. Audio continues when its window closes."""
import json,sys
from pathlib import Path
from PyQt5 import QtCore,QtGui,QtNetwork,QtWidgets as W
from bridge import MAX_VOLUME
ROOT=Path(__file__).resolve().parent
class Window(W.QMainWindow):
 def __init__(self,tray=True):
  super().__init__();self.setWindowTitle('Open Audio Bridge');self.resize(560,450);self.busy=False;self.last={};self.queue=[];self.use_tray=tray
  icon=QtGui.QIcon.fromTheme('audio-volume-high')
  self.setWindowIcon(icon if not icon.isNull() else self.style().standardIcon(W.QStyle.SP_MediaVolume))
  body=W.QWidget();self.setCentralWidget(body);layout=W.QVBoxLayout(body);layout.setContentsMargins(28,24,28,24);layout.setSpacing(16)
  title=W.QLabel('Seu volume, do jeito certo');title.setStyleSheet('font-size:23px;font-weight:600');layout.addWidget(title)
  subtitle=W.QLabel('Reforço com proteção de picos na própria saída de áudio do KDE.');subtitle.setWordWrap(True);layout.addWidget(subtitle)
  self.status_label=W.QLabel('Verificando áudio…');layout.addWidget(self.status_label)
  form=W.QFormLayout();self.device=W.QComboBox();self.device.addItem('Padrão do sistema','default');self.device.setMinimumContentsLength(25);self.device.setSizeAdjustPolicy(W.QComboBox.AdjustToMinimumContentsLengthWithIcon);form.addRow('Ouvir em',self.device)
  self.curve=W.QComboBox();self.curve.addItem('Reforçada — com proteção de picos','boost');self.curve.addItem('Padrão — sem reforço','normal');form.addRow('Curva de volume',self.curve);layout.addLayout(form)
  row=W.QHBoxLayout();self.slider=W.QSlider(QtCore.Qt.Horizontal);self.slider.setRange(0,MAX_VOLUME);self.slider.setSingleStep(1);self.slider.setPageStep(5);self.number=W.QLabel('—%');self.number.setMinimumWidth(50);row.addWidget(self.slider);row.addWidget(self.number);layout.addLayout(row)
  self.mute=W.QCheckBox('Silenciar');layout.addWidget(self.mute)
  note=W.QLabel('Este é o mesmo volume da saída no KDE, sem controle ou saída extra.\nPadrão do sistema acompanha a saída escolhida no KDE. Uma saída fixa recebe o efeito sem mudar a saída padrão.\nFechar esta janela mantém o ícone na bandeja e o áudio ativo.');note.setWordWrap(True);note.setStyleSheet('color:#888;');layout.addWidget(note)
  layout.addStretch();buttons=W.QHBoxLayout();self.toggle=W.QPushButton('Ativar');self.refresh_button=W.QPushButton('Atualizar saídas');self.remove=W.QPushButton('Desinstalar');buttons.addWidget(self.toggle);buttons.addWidget(self.refresh_button);buttons.addStretch();buttons.addWidget(self.remove);layout.addLayout(buttons)
  self.action=QtCore.QProcess(self);self.action.finished.connect(self.action_done);self.action.errorOccurred.connect(self.process_error)
  self.reader=QtCore.QProcess(self);self.reader.finished.connect(self.status_done)
  self.timer=QtCore.QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(1500)
  self.volume_timer=QtCore.QTimer(self);self.volume_timer.setSingleShot(True);self.volume_timer.timeout.connect(lambda:self.execute('volume',str(self.slider.value())))
  self.slider.valueChanged.connect(self.volume_changed)
  self.device.activated.connect(lambda i:self.execute('set-device',self.device.itemData(i)))
  self.curve.activated.connect(lambda i:self.execute('set-curve',self.curve.itemData(i)))
  self.mute.toggled.connect(lambda v:self.execute('mute','1' if v else '0'))
  self.toggle.clicked.connect(lambda:self.execute('disable' if self.last.get('enabled') else 'enable'))
  self.refresh_button.clicked.connect(self.refresh);self.remove.clicked.connect(self.uninstall)
  self.tray=W.QSystemTrayIcon(self.windowIcon(),self);menu=W.QMenu();menu.addAction('Abrir controle',self.show_window);menu.addAction('Sair da interface',self.quit_ui);self.tray.setContextMenu(menu);self.tray.activated.connect(lambda reason:self.show_window() if reason==W.QSystemTrayIcon.Trigger else None);self.tray.setToolTip('Open Audio Bridge')
  if self.use_tray:self.tray.show()
  self.refresh()
 def quit_ui(self):
  if self.busy or self.volume_timer.isActive():self.show_window();return
  W.QApplication.instance().quit()
 def show_window(self):self.showNormal();self.raise_();self.activateWindow()
 def controls(self,enabled):
  for x in [self.device,self.curve,self.slider,self.mute,self.toggle,self.remove]:x.setEnabled(enabled)
 def volume_changed(self,value):
  self.number.setText(f'{value}%');self.volume_timer.start(180)
 def execute(self,command,value=None):
  if self.busy:
   self.queue=[item for item in self.queue if item[0]!=command]+[(command,value)];return
  self.busy=True;self.controls(False);self.status_label.setText('Aplicando…');self.pending_command=command
  self.action.start(sys.executable,[str(ROOT/'bridge.py'),command]+([str(value)] if value is not None else []))
 def process_error(self,_):
  if self.action.state()==QtCore.QProcess.NotRunning and self.busy:
   self.busy=False;self.controls(True);W.QMessageBox.warning(self,'Não foi possível executar',self.action.errorString())
 def action_done(self,code,_):
  error=bytes(self.action.readAllStandardError()).decode(errors='replace');self.busy=False;self.controls(True)
  if code:W.QMessageBox.warning(self,'Não foi possível aplicar',error.strip() or 'Confira se o dispositivo de áudio está conectado.')
  elif self.pending_command=='uninstall':W.QMessageBox.information(self,'Desinstalado','A configuração anterior foi restaurada.');W.QApplication.instance().quit();return
  if self.queue:
   command,value=self.queue.pop(0);self.execute(command,value)
  else:self.refresh()
 def refresh(self):
  if not self.busy and self.reader.state()==QtCore.QProcess.NotRunning:self.reader.start(sys.executable,[str(ROOT/'bridge.py'),'status'])
 def status_done(self,code,_):
  if code or self.busy:return
  try:data=json.loads(bytes(self.reader.readAllStandardOutput()))
  except (ValueError,UnicodeError):return
  self.last=data
  if data.get('error'):self.status_label.setText('Áudio indisponível: '+data['error']);return
  target=data.get('target') or 'default';description=data.get('resolved_description') or data.get('resolved_target') or target
  destination=('Padrão do sistema' if target=='default' else 'Saída fixa')+(' — '+description if data.get('connected') else ' — saída indisponível')
  effect='● Ativo' if data.get('active') else 'Aguardando saída' if data.get('enabled') and not data.get('connected') else 'Efeito indisponível' if data.get('enabled') else 'Desativado — áudio original'
  self.status_label.setText(effect+'\n'+destination);self.status_label.setWordWrap(True)
  self.toggle.setText('Desativar' if data.get('enabled') else 'Ativar')
  self.device.blockSignals(True);self.device.clear();self.device.addItem('Padrão do sistema','default')
  for item in data.get('devices',[]):self.device.addItem(item['description'],item['name'])
  index=self.device.findData(target)
  if index<0:self.device.addItem(target+' (desconectada)',target);index=self.device.count()-1
  self.device.setCurrentIndex(index);self.device.blockSignals(False)
  self.curve.blockSignals(True);self.curve.setCurrentIndex(max(0,self.curve.findData(data.get('curve','boost'))));self.curve.blockSignals(False)
  if not self.slider.isSliderDown() and not self.volume_timer.isActive():
   self.slider.blockSignals(True);self.slider.setValue(round(data.get('volume',0)));self.number.setText(f"{round(data.get('volume',0))}%");self.slider.blockSignals(False)
  self.mute.blockSignals(True);self.mute.setChecked(data.get('mute',False));self.mute.blockSignals(False)
 def uninstall(self):
  if W.QMessageBox.question(self,'Desinstalar Open Audio Bridge','Desinstalar e restaurar a configuração de áudio anterior?',W.QMessageBox.Yes|W.QMessageBox.No)==W.QMessageBox.Yes:self.execute('uninstall')
 def closeEvent(self,event):
  if self.busy or self.volume_timer.isActive():
   event.ignore();self.status_label.setText('Aguarde o ajuste terminar antes de fechar.');return
  if self.use_tray and W.QSystemTrayIcon.isSystemTrayAvailable():event.ignore();self.hide()
  else:event.accept()

def main():
 app=W.QApplication(sys.argv);app.setApplicationName('Open Audio Bridge');app.setOrganizationName('Open Audio Bridge')
 server=None
 if '--screenshot' not in sys.argv:
  import os
  socket=QtNetwork.QLocalSocket();socket.connectToServer('open-audio-bridge-'+str(os.getuid()))
  if socket.waitForConnected(200):
   if '--tray' not in sys.argv:socket.write(b'show');socket.waitForBytesWritten(200)
   return 0
  QtNetwork.QLocalServer.removeServer('open-audio-bridge-'+str(os.getuid()))
  server=QtNetwork.QLocalServer();server.listen('open-audio-bridge-'+str(os.getuid()))
 window=Window()
 if server:
  def incoming():
   client=server.nextPendingConnection()
   client.readyRead.connect(lambda:(client.readAll(),window.show_window(),client.disconnectFromServer()))
  server.newConnection.connect(incoming)
 if '--screenshot' in sys.argv:
  path=sys.argv[sys.argv.index('--screenshot')+1];window.show();QtCore.QTimer.singleShot(900,lambda:(window.grab().save(path),app.quit()))
 elif '--tray' not in sys.argv or not W.QSystemTrayIcon.isSystemTrayAvailable():window.show()
 return app.exec_()
if __name__=='__main__':sys.exit(main())

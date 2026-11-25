#!/usr/bin/env python3
"""Small KDE-friendly control panel. Audio continues when its window closes."""
import json,sys
import sound
import meter_ui
from pathlib import Path
from PyQt5 import QtCore,QtGui,QtNetwork,QtWidgets as W
from bridge import MAX_VOLUME,VERSION
ROOT=Path(__file__).resolve().parent
class HeaderLine(W.QLabel):
 # A permanent single-line row: status text and long device names must never
 # change the geometry of the tabs below. Full text remains in the tooltip.
 def __init__(self,text=''):
  super().__init__();self.setTextFormat(QtCore.Qt.PlainText);self.setWordWrap(False)
  self.setAlignment(QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter)
  self.setSizePolicy(W.QSizePolicy.Ignored,W.QSizePolicy.Fixed)
  self.setFixedHeight(self.fontMetrics().height());self.setText(text)
 def setText(self,text):
  self.full_text=' '.join(str(text).splitlines());self.setToolTip(self.full_text);self.setAccessibleName(self.full_text);self.render_text()
 def render_text(self):
  super().setText(self.fontMetrics().elidedText(self.full_text,QtCore.Qt.ElideRight,max(0,self.contentsRect().width())))
 def resizeEvent(self,event):
  super().resizeEvent(event);self.render_text()
 def changeEvent(self,event):
  super().changeEvent(event)
  if event.type()==QtCore.QEvent.FontChange and hasattr(self,'full_text'):
   self.setFixedHeight(self.fontMetrics().height());self.render_text()

class Window(W.QMainWindow):
 restart_requested=QtCore.pyqtSignal(bool)
 def __init__(self,tray=True):
  super().__init__();self.setWindowTitle('Open Audio Bridge');self.resize(810,680);self.busy=False;self.last={};self.queue=[];self.use_tray=tray;self.restart_pending=False;self.sound_revision=0
  icon=QtGui.QIcon.fromTheme('audio-volume-high')
  self.setWindowIcon(icon if not icon.isNull() else self.style().standardIcon(W.QStyle.SP_MediaVolume))
  body=W.QWidget();self.setCentralWidget(body);layout=W.QVBoxLayout(body);layout.setContentsMargins(28,24,28,24);layout.setSpacing(16)
  title=W.QLabel('Seu volume, do jeito certo');title.setStyleSheet('font-size:23px;font-weight:600');layout.addWidget(title)
  subtitle=W.QLabel('Processamento musical e ganho adaptativo na própria saída do KDE.');subtitle.setWordWrap(True);layout.addWidget(subtitle)
  header=W.QVBoxLayout();header.setContentsMargins(0,0,0,0);header.setSpacing(0)
  self.status_label=HeaderLine('Verificando áudio…');self.destination_label=HeaderLine('Verificando saída…')
  header.addWidget(self.status_label);header.addWidget(self.destination_label);layout.addLayout(header)
  outer=layout;self.tabs=W.QTabWidget();outer.addWidget(self.tabs)
  volume_page=W.QWidget();layout=W.QVBoxLayout(volume_page);layout.setSpacing(16);self.tabs.addTab(volume_page,'Volume e ganho')
  form=W.QFormLayout();self.device=W.QComboBox();self.device.addItem('Padrão do sistema','default');self.device.setMinimumContentsLength(25);self.device.setSizeAdjustPolicy(W.QComboBox.AdjustToMinimumContentsLengthWithIcon);form.addRow('Ouvir em',self.device)
  self.curve=W.QComboBox();self.curve.addItem('Reforçada — com proteção de picos','boost');self.curve.addItem('Padrão — escala original','normal');form.addRow('Curva de volume',self.curve);layout.addLayout(form)
  row=W.QHBoxLayout();self.slider=W.QSlider(QtCore.Qt.Horizontal);self.slider.setRange(0,MAX_VOLUME);self.slider.setSingleStep(1);self.slider.setPageStep(5);self.number=W.QLabel('—%');self.number.setMinimumWidth(50);row.addWidget(self.slider);row.addWidget(self.number);layout.addLayout(row)
  self.mute=W.QCheckBox('Silenciar');layout.addWidget(self.mute)
  drive_row=W.QFormLayout();self.drive=W.QDoubleSpinBox();self.drive.setRange(0,18);self.drive.setSuffix(' dB');self.drive.setDecimals(1);self.drive.setValue(18);drive_row.addRow('Reforço máximo adaptativo',self.drive);layout.addLayout(drive_row)
  drive_note=W.QLabel('O reforço usa a margem disponível do áudio. Uma única proteção antecipada de picos preserva a dinâmica e evita esmagar graves e agudos. Fontes já fortes recebem menos ganho.');drive_note.setWordWrap(True);layout.addWidget(drive_note)
  note=W.QLabel('Este é o mesmo volume da saída no KDE, sem controle ou saída extra.\nPadrão do sistema acompanha a saída escolhida no KDE. Uma saída fixa recebe o efeito sem mudar a saída padrão.\nFechar esta janela mantém o ícone na bandeja e o áudio ativo.');note.setWordWrap(True);note.setStyleSheet('color:#888;');layout.addWidget(note)
  layout.addStretch();layout=outer;self.build_music();self.build_equalizer();self.build_updates();self.build_settings();buttons=W.QHBoxLayout();self.toggle=W.QPushButton('Ativar');self.refresh_button=W.QPushButton('Atualizar saídas');buttons.addWidget(self.toggle);buttons.addWidget(self.refresh_button);buttons.addStretch();layout.addLayout(buttons)
  self.action=QtCore.QProcess(self);self.action.finished.connect(self.action_done);self.action.errorOccurred.connect(self.process_error)
  self.reader=QtCore.QProcess(self);self.reader.finished.connect(self.status_done)
  self.timer=QtCore.QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(1500)
  self.sound_timer=QtCore.QTimer(self);self.sound_timer.setSingleShot(True);self.sound_timer.timeout.connect(lambda:self.execute('set-sound',json.dumps(self.sound_state)))
  self.drive.valueChanged.connect(self.drive_changed)
  self.volume_timer=QtCore.QTimer(self);self.volume_timer.setSingleShot(True);self.volume_timer.timeout.connect(lambda:self.execute('volume',str(self.slider.value())))
  self.slider.valueChanged.connect(self.volume_changed)
  self.device.activated.connect(lambda i:self.execute('set-device',self.device.itemData(i)))
  self.curve.activated.connect(lambda i:self.execute('set-curve',self.curve.itemData(i)))
  self.mute.toggled.connect(lambda v:self.execute('mute','1' if v else '0'))
  self.toggle.clicked.connect(lambda:self.execute('disable' if self.last.get('enabled') else 'enable'))
  self.refresh_button.clicked.connect(self.refresh);self.remove.clicked.connect(self.uninstall)
  self.tray=W.QSystemTrayIcon(self.windowIcon(),self);menu=W.QMenu();menu.addAction('Abrir controle',self.show_window);menu.addAction('Sair da interface',self.quit_ui);self.tray.setContextMenu(menu);self.tray.activated.connect(lambda reason:self.show_window() if reason==W.QSystemTrayIcon.Trigger else None);self.tray.setToolTip('Open Audio Bridge')
  if self.use_tray:self.tray.show()
  self.meter=meter_ui.SpectrumController(ROOT,self.eq_sliders,self)
  self.tabs.currentChanged.connect(self.sync_meter)
  W.QApplication.instance().aboutToQuit.connect(self.meter.shutdown)
  self.refresh()
 def sync_meter(self,*_):
  if not hasattr(self,'meter'):return
  self.meter.set_context(self.last.get('resolved_target') or self.last.get('target'),self.isVisible() and not self.isMinimized() and self.tabs.currentWidget() is self.eq_page,bool(self.last.get('connected') and self.last.get('playing')))
 def showEvent(self,event):
  super().showEvent(event);self.sync_meter()
 def hideEvent(self,event):
  super().hideEvent(event)
  if hasattr(self,'meter'):self.meter.set_context(None,False,False)
 def changeEvent(self,event):
  super().changeEvent(event)
  if event.type()==QtCore.QEvent.WindowStateChange:self.sync_meter()
 def build_settings(self):
  self.settings_page=W.QWidget();layout=W.QVBoxLayout(self.settings_page);layout.setSpacing(16)
  self.startup=W.QCheckBox('Iniciar com o sistema');self.startup.setChecked(True);layout.addWidget(self.startup)
  note=W.QLabel('Inicia o ícone na bandeja ao entrar na sua conta e retoma o processamento se ele estiver ativado. Desmarcar vale para a próxima sessão e não interrompe o áudio atual. Você pode abrir o programa pelo menu quando quiser.');note.setWordWrap(True);layout.addWidget(note)
  layout.addStretch()
  remove_note=W.QLabel('Desinstalar remove o Open Audio Bridge da sua conta e restaura a configuração de áudio anterior.');remove_note.setWordWrap(True);layout.addWidget(remove_note)
  self.remove=W.QPushButton('Desinstalar');layout.addWidget(self.remove)
  self.tabs.addTab(self.settings_page,'Configurações')
  self.startup.toggled.connect(lambda enabled:self.execute('set-startup','1' if enabled else '0'))
 def build_updates(self):
  page=W.QWidget();layout=W.QVBoxLayout(page);layout.setSpacing(16)
  self.update_version=W.QLabel('Interface em execução: '+VERSION);layout.addWidget(self.update_version)
  self.update_auto=W.QCheckBox('Buscar e instalar atualizações automaticamente');self.update_auto.setChecked(True);layout.addWidget(self.update_auto)
  note=W.QLabel('A atualização automática aguarda uma pausa na reprodução e na captura de áudio, inclusive chamadas. Buscar e atualizar agora aplica a versão disponível imediatamente e pode interromper o áudio por alguns instantes. Seus ajustes são preservados.');note.setWordWrap(True);layout.addWidget(note)
  self.update_button=W.QPushButton('Buscar e atualizar agora');layout.addWidget(self.update_button)
  self.update_checked=W.QLabel('Última busca: nunca');layout.addWidget(self.update_checked)
  self.update_status=W.QLabel('Aguardando informações de atualização…');self.update_status.setWordWrap(True);self.update_status.setTextFormat(QtCore.Qt.PlainText);layout.addWidget(self.update_status)
  layout.addStretch();self.tabs.addTab(page,'Atualizações')
  self.update_auto.toggled.connect(lambda enabled:self.execute('update-auto','1' if enabled else '0'))
  self.update_button.clicked.connect(lambda:self.execute('update'))
 def sync_updates(self,data):
  updates=data.get('updates') or {};installed=data.get('version')
  self.update_version.setText('Interface em execução: '+VERSION+'\nVersão instalada: '+(str(installed) if data.get('installed') and installed else 'não informada'))
  self.update_auto.blockSignals(True);self.update_auto.setChecked(updates.get('automatic',True));self.update_auto.blockSignals(False)
  checked=updates.get('last_checked',0)
  stamp=QtCore.QDateTime.fromSecsSinceEpoch(int(checked)).toString('dd/MM/yyyy HH:mm:ss') if isinstance(checked,(int,float)) and checked>0 else 'nunca'
  self.update_checked.setText('Última busca: '+stamp)
  states={'idle':'Pronto para buscar atualizações.','checking':'Buscando atualizações…','deferred':'Atualização aguardando reprodução e captura em pausa.','updating':'Instalando atualização…','updated':'Atualização aplicada.','error':'Não foi possível atualizar.'}
  lines=[updates.get('message') or states.get(updates.get('state'),'Pronto para buscar atualizações.')]
  if updates.get('available_version'):lines.append('Versão disponível: '+str(updates['available_version']))
  if updates.get('error'):lines.append('Falha na atualização: '+str(updates['error']))
  self.update_status.setText('\n'.join(lines))
  self.maybe_restart()
 def pending_changes(self):
  return self.busy or bool(self.queue) or self.volume_timer.isActive() or self.sound_timer.isActive() or self.eq_animation.state()==QtCore.QAbstractAnimation.Running or self.slider.isSliderDown() or any(slider.isSliderDown() for slider in self.eq_sliders)
 def maybe_restart(self):
  version=self.last.get('version')
  if self.restart_pending or self.pending_changes() or not self.last.get('installed') or not isinstance(version,str) or not version or version==VERSION:return
  self.restart_pending=True
  QtCore.QTimer.singleShot(0,self.request_restart)
 def request_restart(self):
  if self.pending_changes():self.restart_pending=False;return
  self.restart_requested.emit(self.isVisible())
 def build_music(self):
  page=W.QWidget();layout=W.QVBoxLayout(page);layout.setSpacing(16)
  heading=W.QLabel('Experiência musical');heading.setStyleSheet('font-size:18px;font-weight:600');layout.addWidget(heading)
  form=W.QFormLayout();self.music_mode=W.QComboBox()
  for key,(label,_) in sound.MUSIC_MODES.items():self.music_mode.addItem(label,key)
  form.addRow('Modo de áudio',self.music_mode)
  self.width=W.QSpinBox();self.width.setRange(0,25);self.width.setSuffix('%');self.width.setToolTip('Expande apenas a componente estéreo acima dos graves, sem criar som espacial multicanal.');form.addRow('Amplitude estéreo',self.width);layout.addLayout(form)
  text=W.QLabel('Música — Quente: reforço adaptativo e suave de graves e detalhes.\nEletrônica: mais presença nos graves e definição dos agudos.\nSem processamento musical: mantém o timbre original, além do equalizador manual se estiver habilitado.');text.setWordWrap(True);layout.addWidget(text)
  note=W.QLabel('Os modos analisam o conteúdo e moderam o reforço extra quando a música já possui energia nessa faixa. A amplitude estéreo mantém os graves centrados e não altera gravações mono. Os ajustes de equalização manual continuam independentes.');note.setWordWrap(True);layout.addWidget(note);layout.addStretch();self.tabs.addTab(page,'Experiência musical')
  self.music_mode.activated.connect(self.music_changed);self.width.valueChanged.connect(self.width_changed)
 def music_changed(self,index):
  self.sound_state['music_mode']=self.music_mode.itemData(index);self.sound_edited()
 def width_changed(self,value):
  self.sound_state['width']=value;self.sound_edited()
 def build_equalizer(self):
  self.sound_state=sound.normalize();page=W.QWidget();self.eq_page=page;layout=W.QVBoxLayout(page);layout.setSpacing(16)
  self.eq_enabled=W.QCheckBox('Ativar equalizador de timbre');layout.addWidget(self.eq_enabled)
  row=W.QFormLayout();self.eq_preset=W.QComboBox()
  for key,(label,_) in sound.PRESETS.items():self.eq_preset.addItem(label,key)
  self.eq_preset.addItem('Personalizado','custom');row.addRow('Preset',self.eq_preset);layout.addLayout(row)
  bars=W.QHBoxLayout();self.eq_sliders=[];self.eq_values=[]
  for index,label in enumerate(sound.LABELS):
   column=W.QVBoxLayout();value=W.QLabel('0 dB');value.setAlignment(QtCore.Qt.AlignCenter);value.setMinimumWidth(max(value.fontMetrics().horizontalAdvance(text) for text in ('+5.5 dB','-5.5 dB')));column.addWidget(value)
   slider=meter_ui.MeterSlider();slider.setRange(-12,12);slider.setTickInterval(4);slider.setMinimumHeight(190);slider.setAccessibleName(label+' Hz — ganho');slider.setToolTip(label+' Hz: −6 a +6 dB');column.addWidget(slider,1,QtCore.Qt.AlignHCenter)
   column.addSpacing(16);frequency=W.QLabel(label);frequency.setAlignment(QtCore.Qt.AlignCenter);column.addWidget(frequency);bars.addLayout(column,1)
   self.eq_sliders.append(slider);self.eq_values.append(value)
   slider.valueChanged.connect(lambda value,i=index:self.band_changed(i,value));slider.sliderReleased.connect(self.sound_edited)
   slider.sliderPressed.connect(lambda i=index:self.interrupt_preset(i))
  layout.addLayout(bars)
  meter_note=W.QLabel('Faixas coloridas: energia do áudio (−80 a 0 dBFS) · Cursores: ganho em dB');meter_note.setWordWrap(True);layout.addWidget(meter_note)
  note=W.QLabel('Bandas em Hz · ajuste de −6 a +6 dB.\nO equalizador muda o timbre antes da proteção de picos. Reforços fortes usam mais margem digital; desligar aqui guarda a curva manual e não desativa o modo musical.');note.setWordWrap(True);layout.addWidget(note)
  self.tabs.addTab(page,'Equalizador');self.eq_enabled.toggled.connect(self.eq_toggled);self.eq_preset.activated.connect(self.preset_changed)
  self.eq_animation=QtCore.QVariantAnimation(self);self.eq_animation.setDuration(480);self.eq_animation.setStartValue(0.);self.eq_animation.setEndValue(1.);self.eq_animation.setEasingCurve(QtCore.QEasingCurve.InOutCubic);self.eq_animation.valueChanged.connect(self.animate_bands);self.eq_animation.finished.connect(self.clear_visual_animation)
  self.sync_sound(None)
 def sync_sound(self,value,animate=False):
  self.eq_animation.stop()
  starts=[slider.animation_position if slider.animation_position is not None else slider.value() for slider in self.eq_sliders]
  self.clear_visual_animation()
  self.sound_state=sound.normalize(value)
  self.music_mode.blockSignals(True);self.music_mode.setCurrentIndex(self.music_mode.findData(self.sound_state['music_mode']));self.music_mode.blockSignals(False)
  self.width.blockSignals(True);self.width.setValue(round(self.sound_state['width']));self.width.blockSignals(False)
  for widget,value in [(self.drive,self.sound_state['drive_db']),(self.eq_enabled,self.sound_state['eq_enabled'])]:
   widget.blockSignals(True)
   if widget is self.drive:widget.setValue(value)
   else:widget.setChecked(value)
   widget.blockSignals(False)
  self.eq_preset.blockSignals(True);self.eq_preset.setCurrentIndex(self.eq_preset.findData(self.sound_state['preset']));self.eq_preset.blockSignals(False)
  for slider,label,value in zip(self.eq_sliders,self.eq_values,self.sound_state['bands']):
   slider.setEnabled(self.sound_state['eq_enabled'] and self.sound_editable())
   if not animate:
    slider.blockSignals(True);slider.setValue(round(value*2));slider.blockSignals(False);label.setText(f'{value:+g} dB')
  if animate:
   self.eq_animation_start=starts;self.eq_animation_end=[round(value*2) for value in self.sound_state['bands']];self.eq_animation.start()
 def animate_bands(self,progress):
  for slider,label,start,end in zip(self.eq_sliders,self.eq_values,self.eq_animation_start,self.eq_animation_end):
   position=start+(end-start)*progress;value=round(position);slider.blockSignals(True);slider.setValue(value);slider.blockSignals(False);slider.set_animation_position(position);label.setText(f'{value/2:+g} dB')
 def clear_visual_animation(self):
  for slider in self.eq_sliders:slider.set_animation_position()
 def interrupt_preset(self,index):
  if self.eq_animation.state()==QtCore.QAbstractAnimation.Running:self.band_changed(index,self.eq_sliders[index].value())
 def sound_editable(self):return not self.busy or getattr(self,'pending_command',None)=='set-sound'
 def sound_edited(self):
  self.sound_revision+=1;self.sound_timer.stop()
  if self.busy:
   self.queue=[item for item in self.queue if item[0]!='set-sound']+[('set-sound',json.dumps(self.sound_state))]
  elif not any(slider.isSliderDown() for slider in self.eq_sliders):self.sound_timer.start(350)
 def drive_changed(self,value):
  self.sound_state['drive_db']=value;self.sound_edited()
 def eq_toggled(self,enabled):
  self.sound_state['eq_enabled']=enabled
  for slider in self.eq_sliders:slider.setEnabled(enabled and self.sound_editable())
  self.sound_edited()
 def preset_changed(self,index):
  config=dict(self.sound_state,preset=self.eq_preset.itemData(index),eq_enabled=True);self.sync_sound(config,animate=True);self.sound_edited()
 def band_changed(self,index,value):
  if self.eq_animation.state()==QtCore.QAbstractAnimation.Running:
   self.eq_animation.stop();self.clear_visual_animation();self.sound_state['bands']=[slider.value()/2 for slider in self.eq_sliders]
  self.sound_state['preset']='custom';self.sound_state['bands'][index]=value/2;self.eq_values[index].setText(f'{value/2:+g} dB')
  self.eq_preset.blockSignals(True);self.eq_preset.setCurrentIndex(self.eq_preset.findData('custom'));self.eq_preset.blockSignals(False)
  self.sound_edited()
 def quit_ui(self):
  if self.pending_changes():self.show_window();return
  W.QApplication.instance().quit()
 def show_window(self):self.showNormal();self.raise_();self.activateWindow()
 def controls(self,enabled):
  for x in [self.device,self.curve,self.slider,self.mute,self.toggle,self.remove,self.update_auto,self.update_button,self.startup]:x.setEnabled(enabled)
  editable=enabled or (self.busy and self.sound_editable())
  for x in [self.drive,self.eq_enabled,self.eq_preset,self.music_mode,self.width]:x.setEnabled(editable)
  for slider in self.eq_sliders:slider.setEnabled(editable and self.eq_enabled.isChecked())
 def volume_changed(self,value):
  self.number.setText(f'{value}%');self.volume_timer.start(180)
 def execute(self,command,value=None):
  if self.busy:
   self.queue=[item for item in self.queue if item[0]!=command]+[(command,value)];return
  self.busy=True;self.pending_command=command;self.controls(False)
  if command=='set-sound':self.sound_revision+=1
  if command=='update':self.update_status.setText('Buscando e aplicando atualização…')
  elif command!='update-auto':self.status_label.setText('Aplicando…')
  self.action.start(sys.executable,[str(ROOT/'bridge.py'),command]+([str(value)] if value is not None else []))
 def process_error(self,_):
  if self.action.state()==QtCore.QProcess.NotRunning and self.busy:
   self.busy=False;self.controls(True);W.QMessageBox.warning(self,'Não foi possível executar',self.action.errorString())
 def action_done(self,code,_):
  error=bytes(self.action.readAllStandardError()).decode(errors='replace');self.busy=False;self.controls(True)
  if self.pending_command=='set-sound':self.sound_revision+=1
  if code:W.QMessageBox.warning(self,'Não foi possível aplicar',error.strip() or 'Confira se o dispositivo de áudio está conectado.')
  elif self.pending_command=='uninstall':W.QMessageBox.information(self,'Desinstalado','A configuração anterior foi restaurada.');W.QApplication.instance().quit();return
  if self.queue:
   command,value=self.queue.pop(0);self.execute(command,value)
  else:self.refresh()
 def refresh(self):
  if not self.busy and self.reader.state()==QtCore.QProcess.NotRunning:
   self.status_sound_revision=self.sound_revision;self.reader.start(sys.executable,[str(ROOT/'bridge.py'),'status'])
 def status_done(self,code,_):
  if code or self.busy:return
  try:data=json.loads(bytes(self.reader.readAllStandardOutput()))
  except (ValueError,UnicodeError):return
  self.last=data;self.sync_meter();self.sync_updates(data)
  self.startup.blockSignals(True);self.startup.setChecked(data.get('autostart',True));self.startup.blockSignals(False)
  target=data.get('target') or 'default';description=data.get('resolved_description') or data.get('resolved_target') or target
  destination=('Padrão do sistema' if target=='default' else 'Saída fixa')+(' — '+description if data.get('connected') else ' — saída indisponível')
  self.destination_label.setText(destination)
  if data.get('error'):self.status_label.setText('Áudio indisponível: '+data['error']);return
  effect='● Ativo' if data.get('active') else 'Aguardando saída' if data.get('enabled') and not data.get('connected') else 'Efeito indisponível' if data.get('enabled') else 'Desativado — áudio original'
  self.status_label.setText(effect)
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
  if self.status_sound_revision==self.sound_revision and not self.sound_timer.isActive() and not any(command=='set-sound' for command,_ in self.queue) and self.eq_animation.state()!=QtCore.QAbstractAnimation.Running and not any(slider.isSliderDown() for slider in self.eq_sliders):self.sync_sound(data.get('sound'))
 def uninstall(self):
  if W.QMessageBox.question(self,'Desinstalar Open Audio Bridge','Desinstalar e restaurar a configuração de áudio anterior?',W.QMessageBox.Yes|W.QMessageBox.No)==W.QMessageBox.Yes:self.execute('uninstall')
 def closeEvent(self,event):
  if self.pending_changes():
   event.ignore();self.status_label.setText('Aguarde o ajuste terminar antes de fechar.');return
  if self.use_tray and W.QSystemTrayIcon.isSystemTrayAvailable():event.ignore();self.hide()
  else:event.accept()

def restart_interface(window,app,server,server_name,visible):
 # Release the singleton before launching, or the new process would show this old one.
 if window.pending_changes():window.restart_pending=False;return
 if server:server.close();QtNetwork.QLocalServer.removeServer(server_name)
 arguments=[str(ROOT/'gui.py'),'--no-resume']+([] if visible else ['--tray'])
 started=QtCore.QProcess.startDetached(sys.executable,arguments,str(ROOT))
 if isinstance(started,tuple):started=started[0]
 if not started:
  if server:server.listen(server_name)
  window.restart_pending=False;window.update_status.setText('Atualização instalada. Feche e abra a interface para carregar a nova versão.');return
 window.timer.stop();window.tray.hide();app.quit()

def main():
 app=W.QApplication(sys.argv);app.setApplicationName('Open Audio Bridge');app.setOrganizationName('Open Audio Bridge')
 server=None;server_name=None
 if '--screenshot' not in sys.argv:
  import os
  server_name='open-audio-bridge-'+str(os.getuid())
  socket=QtNetwork.QLocalSocket();socket.connectToServer(server_name)
  if socket.waitForConnected(200):
   if '--tray' not in sys.argv:socket.write(b'show');socket.waitForBytesWritten(200)
   return 0
  QtNetwork.QLocalServer.removeServer(server_name)
  server=QtNetwork.QLocalServer();server.listen(server_name)
 window=Window()
 if '--screenshot' not in sys.argv and '--no-resume' not in sys.argv:window.execute('resume')
 if '--screenshot' not in sys.argv:window.restart_requested.connect(lambda visible:restart_interface(window,app,server,server_name,visible))
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

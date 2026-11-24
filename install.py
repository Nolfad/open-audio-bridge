#!/usr/bin/env python3
import sys,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
try:from PyQt5 import QtCore,QtWidgets as W
except ImportError:
 message='Falta o componente gráfico PyQt5. No Tuxedo/Ubuntu, instale python3-pyqt5 e gcc; no Arch Linux, python-pyqt5 e gcc pelo gerenciador de pacotes.'
 try:subprocess.run(['kdialog','--error',message])
 except OSError:print(message,file=sys.stderr)
 sys.exit(1)
class Installer(W.QWidget):
 def __init__(self):
  super().__init__();self.setWindowTitle('Instalar Open Audio Bridge');self.resize(500,270)
  layout=W.QVBoxLayout(self);layout.setContentsMargins(28,25,28,25);layout.setSpacing(18)
  title=W.QLabel('Open Audio Bridge');title.setStyleSheet('font-size:24px;font-weight:600');layout.addWidget(title)
  self.text=W.QLabel('Reforço de áudio com proteção de picos na própria saída do KDE. Você continua usando os mesmos dispositivos e controles de volume, sem saída ou controle extra.\n\nInstala apenas na sua conta e guarda a configuração anterior para restauração. As atualizações automáticas ficam ativadas; você pode desligá-las na aba Atualizações.');self.text.setWordWrap(True);layout.addWidget(self.text)
  self.button=W.QPushButton('Instalar e ativar');layout.addWidget(self.button);self.button.clicked.connect(self.install)
  self.process=QtCore.QProcess(self);self.process.finished.connect(self.done)
  self.process.errorOccurred.connect(lambda _:self.failed(self.process.errorString()))
 def closeEvent(self,event):
  if self.process.state()!=QtCore.QProcess.NotRunning:
   event.ignore();self.text.setText('Aguarde a instalação terminar para fechar esta janela.');return
  event.accept()
 def install(self):
  self.button.setEnabled(False);self.text.setText('Preparando o áudio… Pode haver uma breve interrupção.');self.process.start(sys.executable,[str(ROOT/'bridge.py'),'install'])
 def failed(self,message):self.text.setText(message);self.button.setEnabled(True)
 def done(self,code,_):
  if code:self.failed(bytes(self.process.readAllStandardError()).decode(errors='replace'));return
  self.text.setText('Instalado! Abra Open Audio Bridge pelo menu de aplicativos ou pelo ícone na bandeja.\nUse o volume do KDE normalmente. Fechar a janela mantém o processamento de áudio ativo.');self.button.setText('Abrir controle');self.button.setEnabled(True);self.button.clicked.disconnect();self.button.clicked.connect(self.open)
 def open(self):
  subprocess.Popen([sys.executable,str(Path.home()/'.local/share/open-audio-bridge/app/gui.py')],start_new_session=True);W.QApplication.instance().quit()
if __name__=='__main__':
 app=W.QApplication(sys.argv);window=Installer();window.show();sys.exit(app.exec_())

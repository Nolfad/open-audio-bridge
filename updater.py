#!/usr/bin/env python3
"""User-scoped updates from stable releases in the project's fixed GitHub repo."""
import ast,fcntl,hashlib,json,os,re,stat,subprocess,sys,tempfile,time,urllib.request,zipfile
from pathlib import Path,PurePosixPath
import bridge as b

REPO='Nolfad/open-audio-bridge'
API='https://api.github.com/repos/'+REPO+'/releases/latest'
PREFS=b.STATE/'updates.json'
STATUS=b.STATE/'update-status.json'
LOCK=b.STATE/'update.lock'
SERVICE=b.HOME_DIR/'.config/systemd/user/open-audio-bridge-update.service'
TIMER=SERVICE.with_suffix('.timer')
UNIT='open-audio-bridge-update'
MARKER='# Managed by Open Audio Bridge updater'
MAX_DOWNLOAD=25*1024*1024
MAX_UNPACKED=50*1024*1024
CHECK_INTERVAL=6*60*60

def version_tuple(value):
 if not isinstance(value,str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)',value):raise ValueError('Versão estável inválida.')
 return tuple(map(int,value.split('.')))

def file_version(path):
 for node in ast.parse(Path(path).read_text()).body:
  if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in node.targets):
   value=ast.literal_eval(node.value);version_tuple(value);return value
 raise ValueError('O pacote não informa sua versão.')

def installed():return (b.APP/'bridge.py').is_file() and (b.STATE/'native-baseline.json').is_file() and b.read(b.SETTINGS,{}).get('routing')=='native'
def automatic():return b.read(PREFS,{}).get('automatic',False) is True
def notifications():return b.read(PREFS,{}).get('notifications',True) is True

def status():
 result={'automatic':automatic(),'last_checked':0,'available_version':None,'message':'Ainda não houve verificação.','error':'','state':'idle'}
 result.update(b.read(STATUS,{}));result['automatic']=automatic();result['notifications']=notifications();return result

def record(**changes):
 result=b.read(STATUS,{});result.update(changes);b.save(STATUS,result);return result

def validate_url(url):
 parsed=urllib.parse.urlsplit(url)
 if parsed.scheme!='https' or parsed.hostname not in {'api.github.com','github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'} or parsed.username or parsed.password or parsed.port not in (None,443):raise ValueError('Destino de download não autorizado.')

class SafeRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,request,fp,code,msg,headers,newurl):
  validate_url(newurl);return super().redirect_request(request,fp,code,msg,headers,newurl)

def download(url,limit=MAX_DOWNLOAD):
 validate_url(url)
 request=urllib.request.Request(url,headers={'User-Agent':'Open-Audio-Bridge/'+b.VERSION,'Accept':'application/vnd.github+json' if url==API else 'application/octet-stream'})
 with urllib.request.build_opener(SafeRedirect()).open(request,timeout=20) as response:
  validate_url(response.geturl());data=response.read(limit+1)
 if len(data)>limit:raise ValueError('Download excede o tamanho permitido.')
 return data

def release_version(release):
 if release.get('draft') is not False or release.get('prerelease') is not False:raise ValueError('Apenas releases estáveis são aceitas.')
 tag=release.get('tag_name','')
 if not isinstance(tag,str) or not tag.startswith('v'):raise ValueError('Tag de release inválida.')
 version=tag[1:];version_tuple(version)
 names={asset.get('name') for asset in release.get('assets',[]) if isinstance(asset,dict)}
 if not {'open-audio-bridge-'+version+'.zip','SHA256SUMS'}<=names:raise ValueError('A release ainda não contém o instalador e seu checksum.')
 return version

def asset_url(version,name):
 version_tuple(version)
 if name not in ('SHA256SUMS','open-audio-bridge-'+version+'.zip'):raise ValueError('Arquivo de release inválido.')
 return 'https://github.com/'+REPO+'/releases/download/v'+version+'/'+name

def verify_checksum(blob,checksum,name):
 matches=[]
 for line in checksum.decode('utf-8').splitlines():
  parts=line.split()
  if len(parts)==2 and parts[1].lstrip('*')==name:matches.append(parts[0])
 if len(matches)!=1 or not re.fullmatch('[a-fA-F0-9]{64}',matches[0]) or hashlib.sha256(blob).hexdigest()!=matches[0].lower():raise ValueError('O pacote não corresponde ao checksum publicado. Nada foi instalado.')

def extract_release(package,destination,version):
 version_tuple(version);root_name='open-audio-bridge-'+version;destination=Path(destination);seen=set();total=0
 with zipfile.ZipFile(package) as archive:
  infos=archive.infolist()
  if len(infos)>512:raise ValueError('Pacote contém arquivos demais.')
  for info in infos:
   name=info.filename.rstrip('/');parts=name.split('/');mode=(info.external_attr>>16)&0o170000
   if not name or '\\' in name or any(part in ('','.','..') for part in parts) or parts[0]!=root_name or name in seen or mode not in (0,stat.S_IFREG,stat.S_IFDIR):raise ValueError('Caminho ou tipo de arquivo inseguro no pacote.')
   seen.add(name);total+=info.file_size
   if total>MAX_UNPACKED or info.file_size>MAX_DOWNLOAD:raise ValueError('Pacote descompactado excede o limite.')
  for info in infos:
   path=destination/PurePosixPath(info.filename)
   if info.is_dir():path.mkdir(parents=True,exist_ok=True);continue
   path.parent.mkdir(parents=True,exist_ok=True)
   with archive.open(info) as source:data=source.read(MAX_DOWNLOAD+1)
   if len(data)!=info.file_size:raise ValueError('Tamanho inválido no pacote.')
   path.write_bytes(data);path.chmod(0o755 if path.suffix=='.py' or path.name=='Instalar.desktop' else 0o644)
 root=destination/root_name
 required=['bridge.py','native.py','updater.py','gui.py','sound.py','oab.py','install.py']
 if version_tuple(version)>=(1,0,1):required.append('native_volume.py')
 for name in required:
  if not (root/name).is_file():raise ValueError('Pacote incompleto: '+name)
 if file_version(root/'bridge.py')!=version:raise ValueError('Versão interna diferente da release.')
 return root

def playback_busy():
 # Keep this entry point for installed/candidate installers; capture also
 # matters, and a muted or zero-volume stream still owns a live connection.
 try:
  for kind in ('sink-inputs','source-outputs'):
   streams=json.loads(b.run(['pactl','-f','json','list',kind]).stdout)
   if not isinstance(streams,list):raise ValueError('Lista de fluxos inválida.')
   for item in streams:
    if not isinstance(item,dict) or type(item.get('corked')) is not bool:raise ValueError('Estado do fluxo desconhecido.')
    if not item['corked']:return True
 except (b.BridgeError,ValueError,TypeError,OSError) as error:
  raise DeferredUpdate('Atualização adiada: não foi possível confirmar se a reprodução e a captura estão em pausa.') from error
 return False

class DeferredUpdate(Exception):pass

def apply_release(version,manual=False):
 name='open-audio-bridge-'+version+'.zip'
 checksum=download(asset_url(version,'SHA256SUMS'),64*1024);blob=download(asset_url(version,name));verify_checksum(blob,checksum,name)
 with tempfile.TemporaryDirectory(prefix='oab-update-') as directory:
  package=Path(directory)/name;package.write_bytes(blob);root=extract_release(package,Path(directory)/'source',version)
  if not installed():return False
  if not manual and (not automatic() or playback_busy()):raise DeferredUpdate('Atualização adiada até a próxima pausa na reprodução e na captura.')
  if version_tuple(file_version(b.APP/'bridge.py'))>=version_tuple(version):return False
  # Candidate installer repeats the version/ownership check under native.lock.
  process=subprocess.run([sys.executable,str(root/'bridge.py'),'install-update','manual' if manual else 'scheduled'],capture_output=True,text=True)
  if process.returncode==75:raise DeferredUpdate(process.stdout.strip() or 'Atualização adiada.')
  if process.returncode:raise b.BridgeError((process.stderr or process.stdout or 'Falha ao instalar a atualização.').strip())
  current=version_tuple(file_version(b.APP/'bridge.py'));wanted=version_tuple(version)
  if current<wanted:raise b.BridgeError('A versão instalada não corresponde à atualização.')
  return current==wanted

def notification_message(version,auto):
 version_tuple(version)
 return ('Atualização disponível — Open Audio Bridge',
  ('Versão '+version+' disponível. A instalação automática aguarda uma pausa no áudio. Abra Atualizações para acompanhar ou instalar agora.' if auto else 'Versão '+version+' disponível. Abra o Open Audio Bridge, na aba Atualizações, para instalar quando quiser.'))

def notify_running_gui(version,auto):
 # Use the existing user-scoped singleton; an acknowledgement means the
 # running interface could actually display a clickable tray notification.
 try:
  from PyQt5 import QtCore,QtNetwork
  app=QtCore.QCoreApplication.instance() or QtCore.QCoreApplication(['oab-update'])
  socket=QtNetwork.QLocalSocket()
  socket.connectToServer('open-audio-bridge-'+str(os.getuid()))
  try:
   if not socket.waitForConnected(250):return False
   payload=('notify:'+version+':'+('1' if auto else '0')+'\n').encode()
   if socket.write(payload)!=len(payload):return False
   socket.flush()
   if socket.bytesToWrite() and not socket.waitForBytesWritten(250):return False
   return bool((socket.bytesAvailable() or socket.waitForReadyRead(1000)) and bytes(socket.readAll()).strip()==b'ok')
  finally:socket.abort()
 except (ImportError,OSError,RuntimeError):return False

def send_notification(version,auto):
 title,body=notification_message(version,auto)
 if notify_running_gui(version,auto):return True
 # The tray may be closed or disabled. The desktop can still notify using
 # the standard freedesktop service (no GUI or extra required dependency).
 for command in (
  ['notify-send','--app-name=Open Audio Bridge','--icon=software-update-available','--hint=string:desktop-entry:open-audio-bridge',title,body],
  ['gdbus','call','--session','--dest','org.freedesktop.Notifications','--object-path','/org/freedesktop/Notifications','--method','org.freedesktop.Notifications.Notify','Open Audio Bridge','0','software-update-available',title,body,'[]','{}','10000']):
  try:
   if b.run(command,check=False,timeout=3).returncode==0:return True
  except (b.BridgeError,OSError):pass
 return False

def notify_once(version):
 if not notifications() or status().get('notified_version')==version:return
 try:
  if send_notification(version,automatic()):record(notified_version=version)
 except Exception:
  # A missing notification daemon or session must never interrupt updates.
  pass

def check_apply(manual=False):
 b.STATE.mkdir(parents=True,exist_ok=True)
 with LOCK.open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:return {'message':'Uma atualização já está em andamento.'}
  if not installed():return {'message':'Instale o programa antes de atualizar.'}
  if not manual and not (automatic() or notifications()):return {'message':'Buscas e atualizações automáticas desativadas.'}
  try:
   prior=status();now=time.time();version=prior.get('available_version');current=file_version(b.APP/'bridge.py')
   if manual or not prior.get('last_checked') or now-prior['last_checked']>=CHECK_INTERVAL:
    record(state='checking',error='',message='Verificando releases estáveis…')
    version=release_version(json.loads(download(API,1024*1024)))
    record(last_checked=now,available_version=version)
   if not version or version_tuple(version)<=version_tuple(current):return record(state='idle',available_version=None,error='',message='Você está na versão mais recente disponível.')
   if not manual:
    notify_once(version)
    if not automatic():return record(state='available',error='',message='Versão '+version+' disponível. Instale quando quiser na aba Atualizações.')
    if playback_busy():return record(state='deferred',error='',message='Versão '+version+' disponível. Aguardando uma pausa na reprodução e na captura.')
   record(state='updating',error='',message='Baixando e instalando a versão '+version+'…')
   changed=apply_release(version,manual=manual)
   return record(state='updated' if changed else 'idle',available_version=None,error='',message='Atualizado para '+version+'.' if changed else 'A instalação já foi atualizada ou removida.')
  except DeferredUpdate as error:return record(state='deferred',error='',message=str(error))
  except Exception as error:
   record(state='error',error=str(error),message='Não foi possível concluir a atualização.')
   raise

def sync_schedule():
 if TIMER.exists() and (automatic() or notifications()):b.run(['systemctl','--user','enable','--now',UNIT+'.timer'])
 else:b.run(['systemctl','--user','disable','--now',UNIT+'.timer'],check=False)

def set_preference(key,enabled):
 if type(enabled) is not bool:raise ValueError('Preferência inválida.')
 b.STATE.mkdir(parents=True,exist_ok=True)
 with (b.STATE/'native.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  prefs=b.read(PREFS,{});prefs[key]=enabled;b.save(PREFS,prefs);sync_schedule()

def set_auto(enabled):set_preference('automatic',enabled)
def set_notifications(enabled):set_preference('notifications',enabled)

def setup():
 base_path=b.STATE/'native-baseline.json';base=b.read(base_path,{})
 for path in [SERVICE,TIMER,PREFS]:
  if str(path) not in base.get('files',{}):
   if path in [SERVICE,TIMER] and path.exists() and not path.read_text().startswith(MARKER):raise b.BridgeError('Serviço desconhecido preservado: '+str(path))
   base.setdefault('files',{}).update(b.snapshot([path]))
 b.save(base_path,base)
 if not PREFS.exists():b.save(PREFS,{'automatic':True,'notifications':True})
 command=json.dumps(sys.executable)+' '+json.dumps(str(b.APP/'updater.py').replace('%','%%'))+' --scheduled'
 b.atomic(SERVICE,MARKER+'\n[Unit]\nDescription=Open Audio Bridge stable release updater\n\n[Service]\nType=oneshot\nExecStart='+command+'\nTimeoutStartSec=0\n')
 b.atomic(TIMER,MARKER+'\n[Unit]\nDescription=Open Audio Bridge update checks\n\n[Timer]\nOnActiveSec=5min\nOnUnitInactiveSec=15min\nRandomizedDelaySec=60\nUnit='+UNIT+'.service\n\n[Install]\nWantedBy=timers.target\n')
 b.run(['systemctl','--user','daemon-reload']);sync_schedule()

def remove_schedule():b.run(['systemctl','--user','disable','--now',UNIT+'.timer'],check=False)

def main():
 try:print(json.dumps(check_apply(manual='--scheduled' not in sys.argv),ensure_ascii=False))
 except Exception as error:print('ERRO: '+str(error),file=sys.stderr);sys.exit(1)
if __name__=='__main__':main()

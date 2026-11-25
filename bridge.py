#!/usr/bin/env python3
"""Open Audio Bridge desktop lifecycle and PipeWire graph. No root required."""
from pathlib import Path
import argparse,base64,fcntl,json,math,os,shutil,signal,subprocess,sys,time,tempfile
VERSION='1.0.0'
MAX_VOLUME=150
ROOT=Path(__file__).resolve().parent
HOME_DIR=Path.home()
APP=HOME_DIR/'.local/share/open-audio-bridge/app'
STATE=HOME_DIR/'.local/state/open-audio-bridge-desktop'
SETTINGS=STATE/'settings.json'
BASELINE=STATE/'baseline.json'
SERVICE=HOME_DIR/'.config/systemd/user/open-audio-bridge.service'
DESKTOP=HOME_DIR/'.local/share/applications/open-audio-bridge.desktop'
AUTOSTART=HOME_DIR/'.config/autostart/open-audio-bridge.desktop'
LEGACY=HOME_DIR/'.config/wireplumber/wireplumber.conf.d/92-open-audio-bridge.conf'
SINK='oab_output'
class BridgeError(RuntimeError):pass

def run(args,check=True,timeout=15):
 try:r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired) as e:raise BridgeError(str(e)) from e
 if check and r.returncode:raise BridgeError((r.stderr or r.stdout or 'Falha no comando').strip())
 return r

def atomic(path,data,mode=None):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile(mode='wb' if isinstance(data,bytes) else 'w',dir=path.parent,prefix='.'+path.name+'-',delete=False) as f:
  f.write(data);temp=Path(f.name)
 try:
  if mode is not None:temp.chmod(mode)
  os.replace(temp,path)
 finally:temp.unlink(missing_ok=True)

def save(path,data):atomic(path,json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def read(path,default=None):
 try:return json.loads(Path(path).read_text())
 except FileNotFoundError:return default

def snapshot(paths):
 out={}
 for path in paths:
  p=Path(path)
  if p.is_symlink():raise BridgeError(f'Arquivo vinculado não será alterado: {p}')
  out[str(p)]={'data':base64.b64encode(p.read_bytes()).decode(),'mode':p.stat().st_mode&0o777} if p.exists() else None
 return out

def restore(snap):
 for name,value in snap.items():
  p=Path(name)
  if value is None:p.unlink(missing_ok=True)
  else:
   atomic(p,base64.b64decode(value['data']),value['mode'])

def validate_percent(value):
 value=float(value)
 if not math.isfinite(value) or not 0<=value<=MAX_VOLUME:raise ValueError(f'Volume deve estar entre 0 e {MAX_VOLUME}%.')
 return value

def inverse_percent(old,curve):
 # Equivalent levels may exceed the slider's 150% range (boost reaches 170%).
 p=float(old)
 if not math.isfinite(p) or p<0:raise ValueError('Nível equivalente inválido.')
 return min(MAX_VOLUME,(p/2 if p<=40 else p-20) if curve=='boost' else p)

def equivalent_percent(value,curve):
 p=validate_percent(value)
 return (2*p if p<=20 else p+20) if curve=='boost' else p

def migrate_volume_settings(settings):
 # Preserve the prior gain once, capped at the new curve's reachable maximum.
 result=dict(settings)
 revision=result.get('volume_curve_version',1)
 if revision<3:
  p=validate_percent(result.get('volume',25))
  if result.get('curve','boost')=='boost':
   old_equivalent=2*p if revision==2 or p<=40 else 80+(p-40)/3 if p<=100 else p
   result['volume']=inverse_percent(old_equivalent,'boost')
  result['volume_curve_version']=3
 return result

def make_graph(lib,curve='boost',sound_config=None):
 import sound
 controls=sound.normalize(sound_config)
 # Linear timbre changes and optional adaptive stereo enhancement are made
 # in float before the single, volume-aware, lookahead protection stage.
 nodes=[];links=[];inputs=None;previous=None
 def append(node,ins,outs):
  nonlocal inputs,previous
  nodes.append(node)
  if previous is None:inputs=ins
  else:links.extend({'output':a,'input':b} for a,b in zip(previous,ins))
  previous=outs
 if controls['music_mode']!='off' or controls['width']>0:
  append({'type':'ladspa','name':'music','plugin':str(lib/'liboab_music.so'),'label':'oab_music_enhance','control':{'Mode':float(sound.MUSIC_MODES[controls['music_mode']][1]),'Width (%)':controls['width']}},['music:Input L','music:Input R'],['music:Output L','music:Output R'])
 tone_filters=sound.filters(controls)
 if tone_filters:
  append({'type':'builtin','name':'tone','label':'param_eq','config':{'filters':tone_filters}},['tone:In 1','tone:In 2'],['tone:Out 1','tone:Out 2'])
 append({'type':'ladspa','name':'volume','plugin':str(lib/'liboab_clean.so'),'label':'oab_clean_gain','control':{'Volume L':0.,'Volume R':0.,'Curve':1. if curve=='boost' else 0.,'Drive (dB)':controls['drive_db'],'Ceiling (dB)':-1.2}},['volume:Input L','volume:Input R'],['volume:Output L','volume:Output R'])
 return {'nodes':nodes,'links':links,'inputs':inputs,'outputs':previous,'capture.volumes':[{'control':'volume:Volume '+c,'min':0.,'max':1.,'scale':'cubic'} for c in ['L','R']]}

def make_config(lib,target,curve,percent):
 validate_percent(percent)
 return {'context.properties':{'log.level':2},'context.spa-libs':{'audio.convert.*':'audioconvert/libspa-audioconvert','support.*':'support/libspa-support'},'context.modules':[
 {'name':'libpipewire-module-protocol-native'},{'name':'libpipewire-module-client-node'},{'name':'libpipewire-module-adapter'},
 {'name':'libpipewire-module-filter-chain','args':{'node.description':'Open Audio Bridge','audio.rate':48000,'audio.channels':2,'audio.position':['FL','FR'],'filter.graph':make_graph(lib,curve),
 'capture.props':{'node.name':SINK,'node.description':'Open Audio Bridge','media.class':'Audio/Sink','node.virtual':True,'node.autoconnect':False,'priority.session':0},
 'playback.props':{'node.name':'oab_playback','node.description':'Open Audio Bridge — saída','target.object':target,'node.autoconnect':True,'node.dont-fallback':True,'node.linger':True,'node.passive':True,'stream.dont-remix':True}}}]}

def sinks():return json.loads(run(['pactl','-f','json','list','sinks']).stdout)
def playback_present(sink):
 # A source-output (including the optional spectrum recorder) is not playback.
 if not sink or 'index' not in sink:return False
 try:
  streams=json.loads(run(['pactl','-f','json','list','sink-inputs'],timeout=3).stdout)
  return any(str(stream.get('sink'))==str(sink['index']) and stream.get('corked') is False for stream in streams if isinstance(stream,dict))
 except (BridgeError,TypeError,ValueError):return False
def device_description(s):
 description=s.get('description')
 if description and description!='(null)':return description
 props=s.get('properties',{});label=props.get('node.nick') or props.get('device.description') or s['name']
 return label+(' · HDMI' if 'hdmi' in s['name'] else '')

def physical_sinks():
 return [s for s in sinks() if s['name'].startswith(('alsa_output.','bluez_output.')) and len(s.get('volume',{}))==2]
def sink_by_name(name):return next((s for s in sinks() if s['name']==name),None)
def percent_of(s):
 return min(float(MAX_VOLUME),max(0.,max((v['value']/65536*100 for v in s.get('volume',{}).values()),default=0)))
def default_sink():return run(['pactl','get-default-sink']).stdout.strip()
def set_volume(name,p):run(['pactl','set-sink-volume',name,f'{validate_percent(p):.5f}%'])
def remember_device(s):
 settings=read(SETTINGS,{})
 devices=settings.setdefault('original_devices',{})
 if s['name'] not in devices:
  devices[s['name']]={'volume':[v['value'] for v in s['volume'].values()],'mute':s['mute']}
 save(SETTINGS,settings)
def restore_device(name,settings):
 old=settings.get('original_devices',{}).get(name)
 if old and sink_by_name(name):
  run(['pactl','set-sink-volume',name]+[str(v) for v in old['volume']])
  run(['pactl','set-sink-mute',name,'1' if old['mute'] else '0'])
def move_streams(from_name,to_name):
 source=sink_by_name(from_name)
 if not source:return
 for stream in json.loads(run(['pactl','-f','json','list','sink-inputs']).stdout):
  props=stream.get('properties',{})
  if str(stream['sink'])==str(source['index']) and props.get('node.name')!='oab_playback':
   run(['pactl','move-sink-input',str(stream['index']),to_name])

def wait_sink(name,seconds=8):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  s=sink_by_name(name)
  if s:return s
  time.sleep(.15)
 raise BridgeError('A saída de áudio não apareceu. As configurações anteriores serão restauradas.')

def status():
 settings=read(SETTINGS,{})
 try:
  all_sinks=sinks();s=next((s for s in all_sinks if s['name']==SINK),None)
  devices=[{'name':x['name'],'description':device_description(x)} for x in all_sinks if x['name'].startswith(('alsa_output.','bluez_output.')) and len(x.get('volume',{}))==2]
  connected=any(x['name']==settings.get('target') for x in all_sinks)
  default=default_sink()
  return {'installed':(APP/'bridge.py').is_file(),'active':bool(s) and connected and default==SINK,'sink_present':bool(s),'connected':connected,'enabled':settings.get('enabled',False),'target':settings.get('target'),'curve':settings.get('curve','boost'),'volume':round(percent_of(s),1) if s else settings.get('volume',25),'mute':s['mute'] if s else settings.get('mute',False),'devices':devices,'default':default,'playing':playback_present(next((x for x in all_sinks if x['name']==settings.get('target')),None)),'version':VERSION}
 except BridgeError as e:return {'installed':APP.exists(),'active':False,'devices':[],'error':str(e),'version':VERSION}

def compile_plugins(where):
 lib=where/'lib';lib.mkdir(exist_ok=True)
 for stem in ['dynamics','volume','clean','music']:
  run(['gcc','-O2','-fPIC','-shared','-Wall','-Wextra','-Werror','-std=c11',str(where/f'src/oab_{stem}.c'),'-lm','-o',str(lib/f'liboab_{stem}.so')],timeout=30)

 run(['gcc','-O2','-Wall','-Wextra','-Werror','-std=c11',str(where/'src/oab_spectrum.c'),'-lm','-o',str(lib/'oab_spectrum')],timeout=30)

def prerequisites():
 missing=[x for x in ['gcc','pipewire','pactl','systemctl'] if not shutil.which(x)]
 if missing:raise BridgeError('Faltam componentes: '+', '.join(missing))
 run([sys.executable,'-c','import PyQt5.QtWidgets'])
 if run(['systemctl','--user','is-active','pipewire'],check=False).returncode:raise BridgeError('O serviço PipeWire precisa estar ativo.')

def desktop_text(tray=False):
 return '[Desktop Entry]\nType=Application\nName=Open Audio Bridge\nComment=Volume confortável e proteção de picos\nExec='+json.dumps(sys.executable)+' '+json.dumps(str(APP/'gui.py'))+(' --tray' if tray else '')+'\nIcon=audio-volume-high\nTerminal=false\nCategories=AudioVideo;Audio;\nStartupNotify=true\n'

def install(source=ROOT):
 prerequisites();available=physical_sinks()
 was=read(SETTINGS,{});updating=BASELINE.exists()
 if not available and not (updating and was.get('target')):
  raise BridgeError('Conecte uma saída estéreo antes de instalar.')
 if not updating:
  for p in [SERVICE,DESKTOP,AUTOSTART]:
   if p.exists():raise BridgeError(f'Já existe um arquivo não gerenciado: {p}')
  if APP.exists():raise BridgeError('Existe uma pasta de aplicação sem registro; ela foi preservada.')
  if LEGACY.exists() and not LEGACY.read_text().startswith('# Managed by Open Audio Bridge'):
   raise BridgeError('A regra de áudio existente não pertence ao Open Audio Bridge.')
 # Build completely before interrupting a working version.
 stage=APP.with_name('app.staging');old=APP.with_name('app.previous')
 if stage.exists():shutil.rmtree(stage)
 try:
  shutil.copytree(source,stage,ignore=shutil.ignore_patterns('__pycache__','lib','.git','docs'))
  compile_plugins(stage)
 except Exception:
  if stage.exists():shutil.rmtree(stage)
  raise
 immediate=snapshot([SERVICE,DESKTOP,AUTOSTART,LEGACY,SETTINGS,BASELINE,STATE/'last-volume.json'])
 prior_enabled=run(['systemctl','--user','is-enabled','open-audio-bridge'],check=False).returncode==0
 prior_running=run(['systemctl','--user','is-active','open-audio-bridge'],check=False).returncode==0
 promoted=False
 try:
  if updating:disable();was=migrate_volume_settings(read(SETTINGS,{}))
  else:save(BASELINE,{'files':snapshot([SERVICE,DESKTOP,AUTOSTART,LEGACY]),'default':default_sink()})
  target=was.get('target') or next((x['name'] for x in available if x['name']==default_sink()),available[0]['name'])
  if not updating and target not in [x['name'] for x in available]:target=available[0]['name']
  physical=next((x for x in available if x['name']==target),None)
  raw=[v['value'] for v in physical['volume'].values()] if physical else [1,1];largest=max(raw) or 1
  # A fresh migration may have no legacy processor at all: start conservatively.
  initial=min(25.,inverse_percent(percent_of(physical),'boost')) if physical else 25.
  if old.exists():shutil.rmtree(old)
  if APP.exists():APP.rename(old)
  stage.rename(APP);promoted=True
  save(SETTINGS,dict(was,target=target,curve=was.get('curve','boost'),volume_curve_version=3,volume=was.get('volume',initial),mute=was.get('mute',physical['mute'] if physical else False),balance=was.get('balance',[v/largest for v in raw]),enabled=False))
  executable=json.dumps(sys.executable);backend=json.dumps(str(APP/'bridge.py').replace('%','%%'))
  atomic(SERVICE,'[Unit]\nDescription=Open Audio Bridge\nAfter=pipewire.service pipewire-pulse.service wireplumber.service\nRequires=pipewire.service\n\n[Service]\nType=simple\nExecStart='+executable+' '+backend+' daemon\nExecStopPost='+executable+' '+backend+' recover\nRestart=on-failure\nRestartSec=2\nTimeoutStopSec=5\n\n[Install]\nWantedBy=default.target\n')
  atomic(DESKTOP,desktop_text());atomic(AUTOSTART,desktop_text(True))
  run(['systemctl','--user','daemon-reload']);enable()
  if old.exists():shutil.rmtree(old)
 except Exception:
  run(['systemctl','--user','disable','--now','open-audio-bridge'],check=False,timeout=20)
  if run(['systemctl','--user','is-active','open-audio-bridge'],check=False).returncode==0:
   raise BridgeError('Não consegui parar o serviço para restaurar. Os backups foram preservados.')
  if promoted and APP.exists():shutil.rmtree(APP)
  if old.exists():old.rename(APP)
  restore(immediate)
  run(['systemctl','--user','daemon-reload'])
  if LEGACY.exists():run(['systemctl','--user','restart','wireplumber'])
  if prior_enabled:run(['systemctl','--user','enable','open-audio-bridge'])
  if prior_running:enable()
  raise
 finally:
  if stage.exists():shutil.rmtree(stage)

def enable():
 settings=read(SETTINGS)
 if not settings:raise BridgeError('Instale o Open Audio Bridge primeiro.')
 if run(['systemctl','--user','is-active','open-audio-bridge'],check=False).returncode==0:return
 target=settings['target'];physical=sink_by_name(target)
 if physical:remember_device(physical);settings=read(SETTINGS)
 original=snapshot([LEGACY,SETTINGS,STATE/'last-volume.json'])
 try:
  if LEGACY.exists():
   if not LEGACY.read_text().startswith('# Managed by Open Audio Bridge'):raise BridgeError('Regra de áudio não gerenciada foi preservada.')
   LEGACY.unlink();run(['systemctl','--user','restart','wireplumber'])
   if physical:wait_sink(target)
  settings['enabled']=True;save(SETTINGS,settings)
  settings['volume']=validate_percent(min(MAX_VOLUME,max(0,settings.get('volume',25))))
  save(STATE/'last-volume.json',{'volume':settings['volume'],'mute':settings.get('mute',False)})
  (STATE/'ready.json').unlink(missing_ok=True)
  run(['systemctl','--user','enable','--now','open-audio-bridge'],timeout=20)
  end=time.monotonic()+10
  while time.monotonic()<end:
   ready=read(STATE/'ready.json',{})
   if ready.get('ready') and sink_by_name(SINK):return
   if run(['systemctl','--user','is-active','open-audio-bridge'],check=False).returncode:break
   time.sleep(.15)
  raise BridgeError('Não foi possível ativar o processamento. Restaurando áudio anterior.')
 except Exception:
  run(['systemctl','--user','disable','--now','open-audio-bridge'],check=False,timeout=20)
  if run(['systemctl','--user','is-active','open-audio-bridge'],check=False).returncode==0:
   raise BridgeError('O serviço não parou; a regra anterior não foi reaplicada para evitar processamento duplicado.')
  recover();restore(original)
  if LEGACY.exists():run(['systemctl','--user','restart','wireplumber'])
  raise

def recover():
 # Called on service exit, including crashes. Restore hardware level before rerouting.
 settings=read(SETTINGS,{})
 try:
  for name in settings.get('original_devices',{}):restore_device(name,settings)
  baseline=read(BASELINE,{})
  name=baseline.get('default',settings.get('target'))
  if name and sink_by_name(name):
   if default_sink()==SINK:run(['pactl','set-default-sink',name])
   move_streams(SINK,name)
 except BridgeError:pass

def disable():
 settings=read(SETTINGS,{})
 try:s=sink_by_name(SINK)
 except BridgeError:s=None
 if s:settings.update(volume=percent_of(s),mute=s['mute'])
 settings['enabled']=False;save(SETTINGS,settings)
 if s:run(['pactl','set-sink-mute',SINK,'1'])
 recover()
 run(['systemctl','--user','disable','--now','open-audio-bridge'],timeout=20)
 if run(['systemctl','--user','is-active','open-audio-bridge'],check=False).returncode==0:
  raise BridgeError('O serviço ainda está ativo; não restaurei o processamento antigo.')
 baseline=read(BASELINE,{})
 if str(LEGACY) in baseline.get('files',{}):
  before=LEGACY.read_bytes() if LEGACY.exists() else None
  restore({str(LEGACY):baseline['files'][str(LEGACY)]})
  after=LEGACY.read_bytes() if LEGACY.exists() else None
  if before!=after:run(['systemctl','--user','restart','wireplumber'])

def uninstall():
 if not BASELINE.exists():return
 disable();settings=read(SETTINGS,{})
 missing=[n for n in settings.get('original_devices',{}) if not sink_by_name(n)]
 if missing:raise BridgeError('Áudio desativado. Reconecte as saídas usadas para restaurar seus volumes antes de concluir a desinstalação: '+', '.join(missing))
 baseline=read(BASELINE);restore(baseline['files'])
 run(['systemctl','--user','daemon-reload']);run(['systemctl','--user','reset-failed','open-audio-bridge'],check=False)
 # Keep user backups as an uninstall record, but do not treat them as an installed baseline.
 archived=STATE/('uninstalled-'+time.strftime('%Y%m%d-%H%M%S')+'.json');BASELINE.rename(archived)
 SETTINGS.unlink(missing_ok=True)
 if APP.exists():shutil.rmtree(APP)

def configure(key,value):
 settings=read(SETTINGS,{})
 if key=='target' and value not in [s['name'] for s in physical_sinks()]:raise BridgeError('Saída estéreo indisponível.')
 if key=='curve' and value not in ['normal','boost']:raise BridgeError('Curva inválida.')
 active=settings.get('enabled',False)
 if active:disable()
 settings=read(SETTINGS,settings)
 if key=='curve':
  equivalent=equivalent_percent(settings.get('volume',25),settings.get('curve','boost'))
  settings['volume']=inverse_percent(equivalent,value)
 settings[key]=value;save(SETTINGS,settings)
 if active:enable()

def set_virtual_volume(percent,balance=None):
 p=validate_percent(percent)
 if balance is None:
  current=sink_by_name(SINK)
  values=[v['value'] for v in current['volume'].values()] if current else [1,1]
  maximum=max(values) or 1;balance=[v/maximum for v in values]
 run(['pactl','set-sink-volume',SINK]+[f'{p*max(0,min(1,v)):.5f}%' for v in balance])

def activate_route(settings,target):
 # Never raise hardware gain while a direct stream can still be audible.
 run(['pactl','set-sink-mute',target,'1'])
 run(['pactl','set-sink-mute',SINK,'1'])
 set_virtual_volume(settings['volume'],settings.get('balance',[1,1]))
 set_volume(target,100)
 run(['pactl','set-default-sink',SINK]);move_streams(target,SINK)
 run(['pactl','set-sink-mute',SINK,'1' if settings.get('mute') else '0'])
 run(['pactl','set-sink-mute',target,'0'])

def volume(value):
 p=validate_percent(value);s=sink_by_name(SINK)
 if s:set_virtual_volume(p)
 settings=read(SETTINGS,{});settings['volume']=p;save(SETTINGS,settings)
def mute(value):
 flag=bool(value);s=sink_by_name(SINK)
 if s:run(['pactl','set-sink-mute',SINK,'1' if flag else '0'])
 settings=read(SETTINGS,{});settings['mute']=flag;save(SETTINGS,settings)

def daemon():
 stop=False
 def quit_signal(*_):
  nonlocal stop;stop=True
 signal.signal(signal.SIGTERM,quit_signal);signal.signal(signal.SIGINT,quit_signal)
 settings=read(SETTINGS);settings.update(read(STATE/'last-volume.json',{}))
 settings['volume']=min(MAX_VOLUME,max(0,settings.get('volume',25)))
 target=settings['target'];child=None;last_saved=None
 try:
  cfg=STATE/'runtime.conf';save(cfg,make_config(APP/'lib',target,settings['curve'],settings['volume']))
  env=dict(os.environ);env['LADSPA_PATH']=str(APP/'lib')+':'+env.get('LADSPA_PATH','/usr/lib/ladspa:/usr/lib/x86_64-linux-gnu')
  child=subprocess.Popen(['pipewire','-c',str(cfg)],env=env)
  wait_sink(SINK);run(['pactl','set-sink-mute',SINK,'1']);set_virtual_volume(settings['volume'],settings.get('balance',[1,1]))
  # Keep this sink, even if its selected hardware is absent. No fallback playback.
  run(['pactl','set-default-sink',SINK]);present=False
  if not sink_by_name(target):run(['pactl','set-sink-mute',SINK,'1' if settings.get('mute') else '0'])
  while not stop:
   if child.poll() is not None:raise BridgeError('O processamento de áudio encerrou inesperadamente.')
   physical=sink_by_name(target)
   if physical and not present:
    remember_device(physical);activate_route(settings,target)
   present=bool(physical)
   ready=read(STATE/'ready.json',{})
   if not ready.get('ready') or ready.get('connected')!=present:
    save(STATE/'ready.json',{'ready':True,'connected':present,'pid':os.getpid()})
   virtual=sink_by_name(SINK)
   if virtual:
    raw_max=max(v['value'] for v in virtual['volume'].values())
    if raw_max>65536*MAX_VOLUME/100:set_virtual_volume(MAX_VOLUME)
    values={'volume':percent_of(virtual),'mute':virtual['mute']}
    settings.update(values)
    if values!=last_saved:save(STATE/'last-volume.json',values);last_saved=values.copy()
   time.sleep(.5)
 finally:
  (STATE/'ready.json').unlink(missing_ok=True)
  recover()
  if child and child.poll() is None:child.terminate();child.wait(timeout=5)

def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=['install','enable','disable','uninstall','status','set-device','set-curve','volume','mute','daemon','recover']);p.add_argument('value',nargs='?');args=p.parse_args()
 try:
  if args.command=='status':print(json.dumps(status(),ensure_ascii=False));return 0
  if args.command=='daemon':daemon();return 0
  if args.command=='recover':recover();return 0
  STATE.mkdir(parents=True,exist_ok=True)
  with (STATE/'operation.lock').open('w') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX)
   if args.command=='set-device':configure('target',args.value)
   elif args.command=='set-curve':configure('curve',args.value)
   elif args.command=='volume':volume(args.value)
   elif args.command=='mute':mute(args.value=='1')
   else:globals()[args.command]()
  print('Concluído.');return 0
 except Exception as e:print(str(e),file=sys.stderr);return 1
if __name__=='__main__':
 import native
 native.main()

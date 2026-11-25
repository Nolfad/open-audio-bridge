#!/usr/bin/env python3
"""DSP inside real output nodes; KDE remains the owner of routing and volume."""
from pathlib import Path
import argparse,ast,hashlib,json,os,shutil,signal,subprocess,sys,tempfile,time
import bridge as b
import sound
import updater
import audio_routes

RULE=b.HOME_DIR/'.config/wireplumber/wireplumber.conf.d/93-open-audio-bridge-native.conf'
DROPIN=b.HOME_DIR/'.config/systemd/user/pipewire.service.d/91-open-audio-bridge-native.conf'
BASE=b.STATE/'native-baseline.json'
OWNED=b.STATE/'native-owned.json'
READY=b.STATE/'native-ready.json'
KEY='audioconvert.filter-graph.77'
PLUGINS={s:b.HOME_DIR/f'.ladspa/liboab_native_03_{s}.so' for s in ['dynamics','volume']}
PLUGINS.update({s:b.HOME_DIR/f'.ladspa/liboab_native_06_{s}.so' for s in ['clean','music']})
MARKER='# Managed by Open Audio Bridge native'
ACP_PATHS=Path(os.environ.get('XDG_CONFIG_HOME',str(b.HOME_DIR/'.config')))/'alsa-card-profile/mixer/paths'

def settings():return b.read(b.SETTINGS,{})
def sync_startup():
 config=settings();startup=config.get('autostart',True)
 b.atomic(b.AUTOSTART,b.desktop_text(True)+('' if startup else 'Hidden=true\n'))
 b.run(['systemctl','--user','enable' if startup and config.get('enabled',False) else 'disable','open-audio-bridge'],timeout=20)

def set_startup(enabled):
 if type(enabled) is not bool:raise ValueError('Preferência de inicialização inválida.')
 if not BASE.exists():raise b.BridgeError('Instale o Open Audio Bridge primeiro.')
 previous=settings();desktop=b.snapshot([b.AUTOSTART])
 try:
  b.save(b.SETTINGS,dict(previous,autostart=enabled));sync_startup()
 except Exception:
  b.save(b.SETTINGS,previous)
  try:sync_startup()
  finally:b.restore(desktop)
  raise

def resume():
 if BASE.exists() and settings().get('enabled',False) and b.run(['systemctl','--user','is-active','open-audio-bridge'],check=False).returncode:enable()

def finish_install(before,running,preserve_enabled):
 desired=before.get('enabled',True) if preserve_enabled else True
 b.save(b.SETTINGS,dict(settings(),enabled=desired))
 if desired and (not preserve_enabled or running):enable()
 else:sync_startup()

def target_name(config,default):return default if config.get('target','default')=='default' else config['target']
def candidates(items):return [s for s in items if s['name'].startswith(('alsa_output.','bluez_output.')) and len(s.get('volume',{}))==2]
def selected_names(config,items):return {s['name'] for s in items if config.get('target','default')=='default' or config['target']==s['name']}
def nodes():
 return {o['info']['props']['node.name']:o for o in json.loads(b.run(['pw-dump']).stdout) if o.get('type')=='PipeWire:Interface:Node' and 'node.name' in o.get('info',{}).get('props',{})}
def params(node):
 return {k:v for obj in node.get('info',{}).get('params',{}).get('Props',[]) for k,v in zip(obj.get('params',[])[::2],obj.get('params',[])[1::2])}
def owns_node(node):return 'oab_native_volume:Curve' in params(node)
def serial(node):return str(node['info']['props'].get('object.serial',node['id']))
def raw_levels(sink):return [v['value'] for v in sink['volume'].values()]
def graph(curve,levels,mute,sound_config=None):
 g=b.make_graph(Path('.'),curve,sound_config)
 for node in g['nodes']:
  node['name']='oab_native_'+node['name']
  if node.get('type')=='ladspa':node['plugin']=str(PLUGINS[{'oab_clean_gain':'clean','oab_music_enhance':'music'}[node['label']]])
  if node['name']=='oab_native_volume':
   node['control'].update({'Volume L':0 if mute else levels[0]**(1/3),'Volume R':0 if mute else levels[1]**(1/3)})
 for link in g['links']:
  for end in ['input','output']:link[end]='oab_native_'+link[end]
 for direction in ['inputs','outputs']:g[direction]=['oab_native_'+x for x in g[direction]]
 for volume in g['capture.volumes']:volume['control']='oab_native_'+volume['control']
 return g

def set_props(node,value):b.run(['pw-cli','set-param',str(node['id']),'Props',json.dumps(value)])
def level_snapshot():
 return {s['name']:{'volume':raw_levels(s),'mute':s['mute']} for s in candidates(b.sinks())}
def restore_levels(levels):
 for name,level in levels.items():
  if b.sink_by_name(name):
   b.run(['pactl','set-sink-volume',name]+[str(v) for v in level['volume']])
   b.run(['pactl','set-sink-mute',name,'1' if level['mute'] else '0'])
def resolved_sink():
 name=target_name(settings(),b.default_sink());s=b.sink_by_name(name)
 if not s or not candidates([s]):raise b.BridgeError('A saída selecionada não está disponível em estéreo.')
 return s

def set_volume(value):
 p=b.validate_percent(value);s=resolved_sink();values=raw_levels(s);values=values if any(values) else [1]*len(values);largest=max(values)
 b.run(['pactl','set-sink-volume',s['name']]+[f'{p*v/largest:.5f}%' for v in values])
def set_mute(flag):b.run(['pactl','set-sink-mute',resolved_sink()['name'],'1' if flag else '0'])

def status():
 try:
  config=settings();items=candidates(b.sinks());default=b.default_sink();target=target_name(config,default)
  sink=next((s for s in items if s['name']==target),None);ready=b.read(READY,{})
  return {'installed':config.get('routing')=='native','routing':'native','version':b.VERSION,'sound':sound.normalize(config.get('sound')),'updates':updater.status(),'autostart':config.get('autostart',True),'curve':config.get('curve','boost'),'enabled':config.get('enabled',False),'target':config.get('target','default'),'resolved_target':target,'resolved_description':b.device_description(sink) if sink else target,'default':default,'connected':sink is not None,'playing':b.playback_present(sink),'active':bool(config.get('enabled') and target in ready.get('attached',[])),'volume':round(b.percent_of(sink),1) if sink else 0,'mute':sink['mute'] if sink else False,'devices':[{'name':s['name'],'description':b.device_description(s)} for s in items],'error':ready.get('error','')}
 except b.BridgeError as e:return {'routing':'native','installed':BASE.exists(),'autostart':settings().get('autostart',True),'enabled':False,'active':False,'devices':[],'error':str(e),'version':b.VERSION}

def attach(node,sink,curve,owned,sound_config=None):
 name=sink['name']
 if 'HW_VOLUME_CTRL' in sink.get('flags',[]):raise b.BridgeError('A saída '+b.device_description(sink)+' ainda exige preparação do controle nativo.')
 extra=[key for key,value in params(node).items() if (':' in key and not key.startswith('oab_native_')) or (key.startswith('audioconvert.filter-graph') and key!='audioconvert.filter-graph.disable' and bool(value))]
 if extra:raise b.BridgeError('Existe outro processamento nesta saída; ele foi preservado: '+name)
 prior={'volume':raw_levels(sink),'mute':sink['mute']}
 # Persist ownership before touching a node, so ExecStopPost can recover failures.
 owned[name]={'id':node['id'],'serial':serial(node),'curve':curve,'sound':sound.normalize(sound_config)};b.save(OWNED,owned)
 b.run(['pactl','set-sink-mute',name,'1'])
 try:
  set_props(node,{'params':[KEY,json.dumps(graph(curve,[(v/65536)**3 for v in prior['volume']],prior['mute'],sound_config))]})
  set_props(node,{'channelVolumes':[(v/65536)**3 for v in prior['volume']],'mute':prior['mute']})
 finally:restore_levels({name:prior})

def detach(node,sink):
 prior={'volume':raw_levels(sink),'mute':sink['mute']}
 b.run(['pactl','set-sink-mute',sink['name'],'1'])
 try:
  set_props(node,{'params':[KEY,'']})
  # The graph previously consumed channelVolumes; return volume ownership to channelmix.
  set_props(node,{'channelVolumes':[(v/65536)**3 for v in prior['volume']],'softVolumes':[(v/65536)**3 for v in prior['volume']],'mute':prior['mute'],'softMute':prior['mute']})
 finally:restore_levels({sink['name']:prior})

def recover():
 owned=b.read(OWNED,{})
 if not owned:return
 current=nodes();sinks={s['name']:s for s in candidates(b.sinks())}
 for name,record in list(owned.items()):
  node=current.get(name)
  if node and serial(node)==record['serial'] and name in sinks:detach(node,sinks[name])
  owned.pop(name,None);b.save(OWNED,owned)
 READY.unlink(missing_ok=True)

def restore_rule():
 baseline=b.read(BASE,{})
 if str(RULE) in baseline.get('files',{}):b.restore({str(RULE):baseline['files'][str(RULE)]})
def wait_policy_devices(levels):
 deadline=time.monotonic()+8;stable=0
 while time.monotonic()<deadline:
  if b.run(['systemctl','--user','is-failed','wireplumber'],check=False).returncode==0:raise b.BridgeError('O gerenciador de áudio não iniciou; restaurando a configuração anterior.')
  try:stable=stable+1 if set(levels)<=set(level_snapshot()) else 0
  except (b.BridgeError,ValueError,OSError):stable=0
  if stable>=2:break
  time.sleep(.1)

def restart_policy(levels):
 default=b.default_sink();routes=audio_routes.snapshot()
 b.run(['systemctl','--user','restart','wireplumber'],timeout=20)
 wait_policy_devices(levels)
 restore_levels(levels)
 if b.sink_by_name(default):b.run(['pactl','set-default-sink',default])
 audio_routes.restore(routes)

def restart_audio_server(levels):
 # Only needed if the running server lacks the required LADSPA search path.
 # Preserve levels and default microphone before it destroys the old IDs.
 routes=audio_routes.snapshot()
 b.run(['systemctl','--user','restart','pipewire','pipewire-pulse','wireplumber'],timeout=25)
 wait_policy_devices(levels);restore_levels(levels);audio_routes.restore(routes)

def card_for_sink(sink,cards):
 props=sink.get('properties',{})
 return next((card for card in cards if card.get('name')==props.get('device.name') or (props.get('device.id') is not None and str(card.get('properties',{}).get('object.id'))==str(props['device.id']))),None)

def publish_paths(prepared):
 import native_mixer
 baseline=b.read(BASE,{})
 if 'files' not in baseline:raise b.BridgeError('Registro de restauração ausente.')
 for filename,source in native_mixer.prepared_paths(prepared).items():
  target=ACP_PATHS/filename
  if str(target) not in baseline['files']:
   if target.exists() or target.is_symlink():raise b.BridgeError('Perfil de áudio desconhecido preservado: '+str(target))
   baseline['files'].update(b.snapshot([target]));b.save(BASE,baseline)
  b.atomic(target,source.read_text())

def validate_mixers(config):
 for item in config.get('mixer_cards',{}).values():
  profile=Path(item.get('profile',''))
  if not profile.is_file() or not profile.resolve().is_relative_to((b.APP/'mixer').resolve()):raise b.BridgeError('Perfil de áudio preparado ausente ou fora da instalação; operação cancelada: '+str(profile))


def prepare_mixers():
 """Replace only playback mixer paths; microphones keep their original profiles."""
 import native_mixer
 config=settings();previous=json.loads(json.dumps(config));rule_before=b.snapshot([RULE]);known=config.get('mixer_cards',{})
 validate_mixers(config)
 cards=json.loads(b.run(['pactl','-f','json','list','cards']).stdout)
 for sink in candidates(b.sinks()):
  if 'HW_VOLUME_CTRL' not in sink.get('flags',[]):continue
  if not sink['name'].startswith('alsa_output.'):continue
  card=card_for_sink(sink,cards)
  if not card:raise b.BridgeError('Não consegui identificar a placa de '+b.device_description(sink))
  props=card['properties'];name=props.get('device.name')
  if not name:raise b.BridgeError('A placa não informa um identificador estável.')
  if name in known:continue
  profile_name=props.get('device.profile-set','default.conf')
  profile=native_mixer.find_profile(profile_name)
  folder=b.APP/'mixer'/hashlib.sha256(name.encode()).hexdigest()[:16]
  prepared=native_mixer.prepare_profile(profile,folder,Path('/usr/share/alsa-card-profile/mixer/paths'))
  publish_paths(prepared)
  known[name]={'profile':str(prepared),'source':str(profile)}
 config['mixer_cards']=known;b.save(b.SETTINGS,config)
 rules=[{'matches':[{'device.name':name}],'actions':{'update-props':{'device.profile-set':item['profile']}}} for name,item in known.items()]
 content=MARKER+'\nmonitor.alsa.rules = '+json.dumps(rules,indent=2)+'\n'
 if RULE.exists() and RULE.read_text()==content:return False
 if RULE.exists() and not RULE.read_text().startswith(MARKER):raise b.BridgeError('Regra nativa desconhecida foi preservada.')
 levels=level_snapshot()
 # Mute outputs before the profile switches their hardware controls to fixed 0 dB.
 try:
  for name in levels:b.run(['pactl','set-sink-mute',name,'1'])
  b.atomic(RULE,content)
  restart_policy(levels)
 except Exception:
  b.restore(rule_before);b.save(b.SETTINGS,previous)
  restart_policy(levels)
  raise
 finally:restore_levels(levels)
 return True

def daemon():
 stopping=False
 def stop(*_):
  nonlocal stopping;stopping=True
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 recover();owned={};last=None;last_owned=None;prepared=set(settings().get('mixer_cards',{}))
 try:
  while not stopping:
   config=settings();items=candidates(b.sinks())
   hardware=[s for s in items if 'HW_VOLUME_CTRL' in s.get('flags',[])]
   if hardware:
    # New hardware gets an output-only mixer once; existing native cards are unchanged.
    signature=tuple(sorted(s['name'] for s in hardware))
    if signature not in prepared:
     prepared.add(signature)
     try:prepare_mixers();items=candidates(b.sinks())
     except (b.BridgeError,ValueError,OSError) as e:
      b.save(READY,{'ready':True,'pid':os.getpid(),'attached':sorted(owned),'error':str(e)})
   current=nodes();wanted=selected_names(config,items) if config.get('enabled') else set()
   errors=[]
   for name,record in list(owned.items()):
    node=current.get(name);sink=next((s for s in items if s['name']==name),None)
    if not node or serial(node)!=record['serial']:owned.pop(name,None)
    elif name not in wanted or record['curve']!=config.get('curve','boost') or record.get('sound')!=sound.normalize(config.get('sound')):
     if sink:detach(node,sink)
     owned.pop(name,None)
   for sink in items:
    name=sink['name'];node=current.get(name)
    if name not in wanted or name in owned or not node:continue
    try:attach(node,sink,config.get('curve','boost'),owned,config.get('sound'))
    except b.BridgeError as e:
     errors.append(str(e))
     # Keep ownership after a partial attachment until removal succeeds.
     if name in owned:
      detach(node,sink);owned.pop(name,None)
   if owned!=last_owned:b.save(OWNED,owned);last_owned=dict(owned)
   result={'ready':True,'pid':os.getpid(),'attached':sorted(owned),'error':'\n'.join(errors)}
   if result!=last:b.save(READY,result);last=result
   time.sleep(.2)
 finally:recover()

def wait_ready():
 pid=int(b.run(['systemctl','--user','show','open-audio-bridge','--property=MainPID','--value']).stdout.strip() or 0)
 deadline=time.monotonic()+10
 while time.monotonic()<deadline:
  ready=b.read(READY,{})
  if ready.get('ready') and ready.get('pid')==pid:
   if ready.get('error'):raise b.BridgeError(ready['error'])
   return
  if b.run(['systemctl','--user','is-active','open-audio-bridge'],check=False).returncode:break
  time.sleep(.1)
 raise b.BridgeError('O processamento nativo não iniciou.')

def enable():
 if not BASE.exists():raise b.BridgeError('Instale o Open Audio Bridge primeiro.')
 previous=settings();levels=level_snapshot();rule=b.snapshot([RULE])
 try:
  config=dict(previous,enabled=True);b.save(b.SETTINGS,config)
  prepare_mixers();READY.unlink(missing_ok=True)
  sync_startup()
  b.run(['systemctl','--user','restart','open-audio-bridge'],timeout=20);wait_ready()
 except Exception:
  b.run(['systemctl','--user','disable','--now','open-audio-bridge'],check=False,timeout=20)
  if b.run(['systemctl','--user','is-active','open-audio-bridge'],check=False).returncode==0:raise b.BridgeError('Não consegui parar o serviço; backups e estado foram preservados.')
  recover();policy_changed=b.snapshot([RULE])!=rule
  b.restore(rule);b.save(b.SETTINGS,dict(previous,enabled=False))
  if policy_changed:restart_policy(levels)
  else:restore_levels(levels)
  raise


def suspend():
 """Detach DSP for an upgrade without unloading profiles or changing preferences."""
 b.run(['systemctl','--user','stop','open-audio-bridge'],timeout=20)
 if b.run(['systemctl','--user','is-active','open-audio-bridge'],check=False).returncode==0:raise b.BridgeError('Não consegui parar o processamento; configurações foram preservadas.')
 recover()


def disable():
 config=settings();config['enabled']=False;b.save(b.SETTINGS,config)
 b.run(['systemctl','--user','disable','--now','open-audio-bridge'],timeout=20)
 if b.run(['systemctl','--user','is-active','open-audio-bridge'],check=False).returncode==0:raise b.BridgeError('Não consegui parar o processamento; configurações foram preservadas.')
 recover();levels=level_snapshot();restore_rule();restart_policy(levels)

def configure(key,value):
 config=settings()
 if key=='target' and value!='default' and value not in {s['name'] for s in candidates(b.sinks())}:raise b.BridgeError('Saída estéreo indisponível.')
 if key=='curve' and value not in ['normal','boost']:raise b.BridgeError('Curva inválida.')
 if key=='sound':value=sound.normalize(value)
 previous=config.copy();levels={};converted={}
 if key in ['curve','sound'] and config.get('enabled'):
  items=candidates(b.sinks())
  for sink in items:
   if sink['name'] not in selected_names(config,items):continue
   levels[sink['name']]={'volume':raw_levels(sink),'mute':sink['mute']}
   if key=='sound':
    converted[sink['name']]=levels[sink['name']].copy();continue
   p=b.inverse_percent(b.equivalent_percent(b.percent_of(sink),config.get('curve','boost')),value)
   values=raw_levels(sink);largest=max(values) or 1
   converted[sink['name']]={'volume':[round(p*65536/100*v/largest) for v in values],'mute':sink['mute']}
 try:
  for name in levels:b.run(['pactl','set-sink-mute',name,'1'])
  config[key]=value;b.save(b.SETTINGS,config)
  if config.get('enabled'):
   b.run(['systemctl','--user','restart','open-audio-bridge'],timeout=20);wait_ready()
  restore_levels(converted)
 except Exception:
  b.save(b.SETTINGS,previous)
  try:
   if previous.get('enabled'):b.run(['systemctl','--user','restart','open-audio-bridge'],timeout=20);wait_ready()
  finally:restore_levels(levels)
  raise


def uninstall():
 if not BASE.exists():return
 updater.remove_schedule();disable();base=b.read(BASE);b.restore(base['files'])
 b.run(['systemctl','--user','daemon-reload']);restart_policy(base.get('volumes',{}))
 if base.get('default') and b.sink_by_name(base['default']):b.run(['pactl','set-default-sink',base['default']])
 if b.APP.exists():shutil.rmtree(b.APP)
 b.SETTINGS.unlink(missing_ok=True);OWNED.unlink(missing_ok=True);READY.unlink(missing_ok=True);updater.STATUS.unlink(missing_ok=True)
 BASE.rename(BASE.with_name('native-uninstalled-'+str(time.time_ns())+'.json'))
 if b.BASELINE.exists():b.BASELINE.rename(b.BASELINE.with_name('legacy-retired-'+str(time.time_ns())+'.json'))

def migration_percent(version,curve,value):
 if curve=='normal':equivalent=value
 elif version in ['0.2.0','0.2.1']:equivalent=2*value if value<=40 else 80+(value-40)/3 if value<=100 else value
 elif version=='0.2.2':equivalent=2*value
 else:equivalent=b.equivalent_percent(value,curve)
 return b.inverse_percent(equivalent,curve)

def install_plugin(source,target):
 # Never truncate a library that the audio server may still have mapped.
 b.atomic(target,source.read_bytes(),source.stat().st_mode&0o777)

def restore_state(source):
 # Keep advisory lock inodes alive while restoring all other application state.
 b.STATE.mkdir(parents=True,exist_ok=True)
 for entry in b.STATE.iterdir():
  if entry.name.endswith('.lock'):continue
  if entry.is_dir() and not entry.is_symlink():shutil.rmtree(entry)
  else:entry.unlink()
 if source.exists():
  for entry in source.iterdir():
   if entry.name.endswith('.lock'):continue
   if entry.is_dir():shutil.copytree(entry,b.STATE/entry.name)
   else:shutil.copy2(entry,b.STATE/entry.name)

def install(source,preserve_enabled=False,scheduled=False):
 b.prerequisites()
 import oab
 if oab.version('pipewire')<(1,6,0) or oab.version('wireplumber')<(0,5,15):raise b.BridgeError('A integração nativa exige PipeWire 1.6+ e WirePlumber 0.5.15+.')
 for command in ['pw-cli','pw-dump']:
  if not shutil.which(command):raise b.BridgeError('Falta '+command)
 before=settings();is_native=before.get('routing')=='native';legacy=bool(b.read(b.BASELINE)) and not is_native
 if b.APP.exists() and not is_native and not legacy:raise b.BridgeError('Aplicação existente sem registro gerenciado; arquivos preservados.')
 if not candidates(b.sinks()):raise b.BridgeError('Conecte uma saída estéreo para preparar a integração nativa.')
 baseline=b.read(BASE,{})
 for path in [RULE,*PLUGINS.values()]:
  if path.exists() and (not BASE.exists() or (path in PLUGINS.values() and str(path) not in baseline.get('files',{}))):raise b.BridgeError('Arquivo não gerenciado preservado: '+str(path))
 if is_native:validate_mixers(before)
 stage=b.APP.with_name('app.native-staging');shutil.rmtree(stage,ignore_errors=True)
 shutil.copytree(source,stage,ignore=shutil.ignore_patterns('.git','dist','lib','__pycache__','mixer','docs'))
 b.compile_plugins(stage)
 backup=b.STATE.parent/'open-audio-bridge-upgrades'/str(time.time_ns());backup.mkdir(parents=True)
 if b.APP.exists():shutil.copytree(b.APP,backup/'app')
 if b.STATE.exists():shutil.copytree(b.STATE,backup/'state')
 files=list(dict.fromkeys([b.SERVICE,b.DESKTOP,b.AUTOSTART,b.LEGACY,RULE,DROPIN,*PLUGINS.values(),*[Path(p) for p in b.read(BASE,{}).get('files',{})]]))
 snap=b.snapshot(files);b.save(backup/'files.json',snap)
 legacy_sink=b.sink_by_name(b.SINK)
 streams=[x['index'] for x in json.loads(b.run(['pactl','-f','json','list','sink-inputs']).stdout) if legacy_sink and x['sink']==legacy_sink['index']]
 levels=level_snapshot();default=b.default_sink();running=b.run(['systemctl','--user','is-active','open-audio-bridge'],check=False).returncode==0
 try:
  if scheduled and (not updater.automatic() or updater.playback_busy()):raise updater.DeferredUpdate('Atualização adiada até uma pausa na reprodução.')
 except updater.DeferredUpdate:
  shutil.rmtree(stage,ignore_errors=True);shutil.rmtree(backup,ignore_errors=True)
  raise
 try:
  if is_native:suspend()
  elif legacy:b.disable();before=settings()
  if b.LEGACY.exists():
   if not b.LEGACY.read_text().startswith('# Managed by Open Audio Bridge'):raise b.BridgeError('Regra antiga não gerenciada foi preservada.')
   b.LEGACY.unlink()
  if not BASE.exists():
   original=b.read(b.BASELINE,{}) if legacy else {}
   snapshots=dict(snap);snapshots.update(original.get('files',{}))
   # The original virtual service must not be restored by native uninstall.
   b.save(BASE,{'files':snapshots,'volumes':level_snapshot(),'default':default if default!=b.SINK else original.get('default')})
  else:
   baseline=b.read(BASE);baseline['files'].update({str(path):snap[str(path)] for path in PLUGINS.values() if str(path) not in baseline['files']});b.save(BASE,baseline)
  # These files are still referenced by live WirePlumber cards. Keep their exact
  # contents and stable installed paths when replacing application code.
  if is_native and (b.APP/'mixer').exists():shutil.copytree(b.APP/'mixer',stage/'mixer')
  if b.APP.exists():shutil.rmtree(b.APP)
  stage.rename(b.APP)
  for stem,path in PLUGINS.items():install_plugin(b.APP/f'lib/liboab_{stem}.so',path)
  paths=f'{b.HOME_DIR}/.ladspa:/usr/lib64/ladspa:/usr/lib/ladspa:/usr/lib/x86_64-linux-gnu'
  b.atomic(DROPIN,'# Managed by Open Audio Bridge native\n[Service]\nEnvironment="LADSPA_PATH='+paths+'"\n')
  selected=before.get('target','default') if is_native else 'default'
  config={'routing':'native','target':selected,'curve':before.get('curve','boost'),'enabled':False,'autostart':before.get('autostart',True),'volume_curve_version':3,'mixer_cards':before.get('mixer_cards',{}) if is_native else {},'sound':sound.normalize(before.get('sound'))}
  b.save(b.SETTINGS,config)
  executable=json.dumps(sys.executable);backend=json.dumps(str(b.APP/'native.py').replace('%','%%'))
  b.atomic(b.SERVICE,'[Unit]\nDescription=Open Audio Bridge native DSP\nAfter=pipewire.service pipewire-pulse.service wireplumber.service\nRequires=pipewire.service\n\n[Service]\nType=simple\nExecStart='+executable+' '+backend+' daemon\nExecStopPost='+executable+' '+backend+' recover\nRestart=on-failure\nRestartSec=1\nTimeoutStopSec=10\n\n[Install]\nWantedBy=default.target\n')
  b.atomic(b.DESKTOP,b.desktop_text());b.atomic(b.AUTOSTART,b.desktop_text(True))
  b.run(['systemctl','--user','daemon-reload'])
  pid=b.run(['systemctl','--user','show','pipewire','--property=MainPID','--value']).stdout.strip()
  environment=Path('/proc')/pid/'environ'
  if str(b.HOME_DIR/'.ladspa').encode() not in environment.read_bytes():
   restart_audio_server(level_snapshot())
  # Migration starts from the previous processed listening level; cap other outputs once.
  current=level_snapshot()
  if not is_native:
   for level in current.values():level['volume']=[min(v,int(.35*65536)) for v in level['volume']]
   old=before.get('volume',25)
   # The installed 0.2.1 may carry newer settings after a manual reinstall.
   installed=(backup/'app/bridge.py').read_text() if (backup/'app/bridge.py').exists() else ''
   version=next((ast.literal_eval(n.value) for n in ast.parse(installed).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in n.targets)),'0.2.3')
   target=before.get('target')
   if target in current:
    p=min(50,migration_percent(version,config['curve'],old));current[target]={'volume':[round(p*65536/100*x) for x in before.get('balance',[1,1])],'mute':before.get('mute',False)}
  restore_levels(current)
  finish_install(before,running,preserve_enabled)
  updater.setup()
  destination=default if default!=b.SINK else before.get('target',b.default_sink())
  if b.sink_by_name(destination):
   b.run(['pactl','set-default-sink',destination])
   for stream in streams:b.run(['pactl','move-sink-input',str(stream),destination],check=False)
 except Exception:
  b.run(['systemctl','--user','disable','--now','open-audio-bridge'],check=False,timeout=20)
  if b.run(['systemctl','--user','is-active','open-audio-bridge'],check=False).returncode==0:raise b.BridgeError('Não consegui parar o serviço para reverter. Backup preservado em '+str(backup))
  recover()
  policy_changed=b.snapshot([RULE])!={str(RULE):snap.get(str(RULE))}
  # Include helper files created during this attempt in the rollback.
  created={name:value for name,value in b.read(BASE,{}).get('files',{}).items() if name not in snap}
  b.restore(created);b.restore(snap)
  if b.APP.exists():shutil.rmtree(b.APP)
  if (backup/'app').exists():shutil.copytree(backup/'app',b.APP)
  restore_state(backup/'state')
  b.run(['systemctl','--user','daemon-reload']);updater.sync_schedule()
  if not is_native or policy_changed:restart_policy(levels)
  else:restore_levels(levels)
  if is_native:sync_startup()
  if running:
   b.run(['systemctl','--user','start','open-audio-bridge'],timeout=20)
   if not is_native:b.run(['systemctl','--user','enable','open-audio-bridge'],timeout=20)
   pid=int(b.run(['systemctl','--user','show','open-audio-bridge','--property=MainPID','--value']).stdout.strip())
   for _ in range(100):
    ready=b.read(READY if is_native else b.STATE/'ready.json',{})
    if ready.get('ready') and ready.get('pid')==pid:break
    time.sleep(.1)
  if b.sink_by_name(default):b.run(['pactl','set-default-sink',default])
  raise
 finally:shutil.rmtree(stage,ignore_errors=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=['install','install-update','update','update-auto','set-startup','resume','enable','disable','uninstall','status','set-device','set-curve','set-sound','volume','mute','daemon','recover']);p.add_argument('value',nargs='?');a=p.parse_args()
 try:
  if a.command=='status':print(json.dumps(status(),ensure_ascii=False));return
  if a.command=='update':print(json.dumps(updater.check_apply(manual=True),ensure_ascii=False));return
  if a.command=='update-auto':updater.set_auto(a.value=='1');print('Concluído.');return
  b.STATE.mkdir(parents=True,exist_ok=True)
  with (b.STATE/'native.lock').open('w') as lock:
   if a.command not in ['daemon','recover']:b.fcntl.flock(lock,b.fcntl.LOCK_EX)
   if a.command=='install':install(Path(__file__).resolve().parent)
   elif a.command=='install-update':
    if not updater.installed():raise b.BridgeError('A instalação foi removida; atualização cancelada.')
    if updater.version_tuple(b.VERSION)<=updater.version_tuple(updater.file_version(b.APP/'bridge.py')):print('A instalação já está atualizada.');return
    if a.value=='scheduled' and (not updater.automatic() or updater.playback_busy()):print('Atualização adiada até uma pausa na reprodução.');sys.exit(75)
    install(Path(__file__).resolve().parent,preserve_enabled=True,scheduled=a.value=='scheduled')
   elif a.command=='set-startup':
    if a.value not in ['0','1']:raise ValueError('Use 0 ou 1 para a inicialização automática.')
    set_startup(a.value=='1')
   elif a.command=='set-device':configure('target',a.value)
   elif a.command=='set-curve':configure('curve',a.value)
   elif a.command=='set-sound':configure('sound',json.loads(a.value))
   elif a.command=='volume':set_volume(a.value)
   elif a.command=='mute':set_mute(a.value=='1')
   else:globals()[a.command]()
  print('Concluído.')
 except updater.DeferredUpdate as e:print(str(e));sys.exit(75)
 except (b.BridgeError,ValueError,OSError) as e:print('ERRO: '+str(e),file=sys.stderr);sys.exit(1)
if __name__=='__main__':main()

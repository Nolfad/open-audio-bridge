#!/usr/bin/env python3
"""Open Audio Bridge CLI: offline building, safe WirePlumber configuration and rollback.

Only runs on Linux with PipeWire + WirePlumber >= 0.5.13.
Only touches its own fragment under ~/.config/wireplumber and ~/.ladspa.
"""
from __future__ import annotations

import argparse
import hashlib
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
MARKER = '# Managed by Open Audio Bridge v0.1.0; remove with ./oab.py uninstall'
FRAGMENT = Path.home() / '.config/wireplumber/wireplumber.conf.d/92-open-audio-bridge.conf'
PLUGIN = Path.home() / '.ladspa/liboab_dynamics.so'
STATE = Path.home() / '.local/state/open-audio-bridge'
LABEL = 'oab_stereo_dynamics'
FIELDS = {'drive_db':(-12,18), 'threshold_db':(-48,0), 'ratio':(1,12),
          'attack_ms':(0.2,100), 'release_ms':(10,2000), 'ceiling_db':(-12,-0.1)}
DSP_PARAMS = {'drive_db':'Drive (dB)', 'threshold_db':'Threshold (dB)',
              'ratio':'Ratio', 'attack_ms':'Attack (ms)',
              'release_ms':'Release (ms)', 'ceiling_db':'Ceiling (dB)'}
VALID_FILTERS = {'bq_lowshelf', 'bq_highshelf', 'bq_peaking',
                 'bq_lowpass', 'bq_highpass', 'bq_notch'}

class BridgeError(RuntimeError):
    pass


def run(cmd, timeout=10, check=False):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              check=check)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise BridgeError(f"Não foi possível executar {' '.join(map(str,cmd))}: {exc}") from exc


def version(tool):
    process = run([tool, '--version'])
    if process.returncode:
        raise BridgeError(f'{tool} --version retornou erro: {process.stderr.strip()}')
    m = re.search(r'(\d+)\.(\d+)\.(\d+)', process.stdout + process.stderr)
    if not m:
        raise BridgeError(f'Não identifiquei a versão de {tool}: {process.stdout[:180]}')
    return tuple(map(int, m.groups()))


def platform_check():
    if sys.platform != 'linux':
        raise BridgeError('A instalação requer Linux. preview e testes podem ser usados em outro sistema.')
    wp = version('wireplumber')
    pw = version('pipewire')
    if wp < (0,5,13):
        raise BridgeError(f'WirePlumber {wp} não suporta filtros internos; requer >= 0.5.13. Não há fallback para saída virtual.')
    if pw < (1,0,0):
        raise BridgeError('Este protótipo foi preparado para PipeWire >= 1.0.')
    if not shutil.which('gcc'):
        raise BridgeError('Compilador gcc ausente. Instale gcc antes de ativar o protótipo.')
    return pw,wp


def compile_plugin(path: Path):
    if not shutil.which('gcc'):
        raise BridgeError('gcc indisponível para compilar o plugin LADSPA')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix='.oab-', suffix='.so',dir=str(path.parent))
    os.close(fd)
    try:
        result = run(['gcc','-O2','-fPIC','-shared','-Wall','-Wextra','-Werror',
                      '-std=c11',str(ROOT/'src/oab_dynamics.c'),'-lm','-o',temp_name],timeout=30)
        if result.returncode:
            raise BridgeError('Compilação falhou:\n'+result.stderr)
        os.chmod(temp_name,0o755)
        os.replace(temp_name,path)
    finally:
        if os.path.exists(temp_name): os.unlink(temp_name)


def profile_load(name):
    if not re.fullmatch('[a-zA-Z0-9_-]+', name):
        raise BridgeError('Nome de perfil inválido')
    p = ROOT/'profiles'/f'{name}.json'
    if not p.is_file():
        raise BridgeError(f'Perfil não encontrado: {name}')
    data = json.loads(p.read_text(encoding='utf-8'))
    for field, (lo,hi) in FIELDS.items():
        number = data.get(field)
        if not isinstance(number,(int,float)) or isinstance(number,bool) or not lo <= number <= hi:
            raise BridgeError(f'{field} deve estar entre {lo} e {hi}')
    filters = data.get('filters',[])
    if not isinstance(filters,list) or len(filters)>24:
        raise BridgeError('O perfil suporta até 24 filtros')
    for f in filters:
        if f.get('type') not in VALID_FILTERS:
            raise BridgeError('Tipo de filtro inválido')
        if not 15 <= f.get('freq',-1) <= 22000:
            raise BridgeError('Frequência de filtro inválida')
        if not -12 <= f.get('gain',0) <= 12 or not 0.2 <= f.get('q',-1) <= 6:
            raise BridgeError('Ganhos ou Q de filtro fora da faixa segura')
    return data


def read_sinks():
    proc = run(['pw-dump'],timeout=15)
    if proc.returncode:
        raise BridgeError(f'pw-dump falhou: {proc.stderr[:250]}')
    try:
        objects=json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise BridgeError('pw-dump retornou dados inválidos') from exc
    device_names={str(ob.get('id')): ((ob.get('info') or {}).get('props') or {}).get('device.name')
                  for ob in objects if ob.get('type')=='PipeWire:Interface:Device'}
    sinks=[]
    for ob in objects:
        if ob.get('type')!='PipeWire:Interface:Node': continue
        props=ob.get('info',{}).get('props',{}) or {}
        if props.get('media.class')!='Audio/Sink': continue
        name=props.get('node.name')
        if not isinstance(name,str) or not name: continue
        chans=props.get('audio.channels')
        if chans is None:
            pos=props.get('audio.position')
            if isinstance(pos,list): chans=len(pos)
            elif isinstance(pos,str):
                tokens=re.findall(r'\b(?:FL|FR|FC|LFE|RL|RR|SL|SR|MONO|AUX\d+)\b',pos)
                if tokens: chans=len(tokens)
        try: chans=int(chans) if chans is not None else None
        except (ValueError,TypeError): chans=None
        sinks.append({'name':name,'description':props.get('node.description',name),
                      'channels':chans,'id':ob.get('id'),
                      'card':device_names.get(str(props.get('device.id')))})
    return sorted(sinks,key=lambda x:x['name'])


def selected_sinks(names=None):
    sinks=read_sinks()
    if names:
        selected=[]
        for name in names:
            hit=next((s for s in sinks if s['name']==name),None)
            if hit is None: raise BridgeError(f'Saída não encontrada em pw-dump: {name}')
            if hit['channels'] != 2:
                raise BridgeError(f'Não ativo DSP estéreo em {name}; canais detectados: {hit["channels"]}')
            selected.append(hit)
    else:
        selected=[s for s in sinks if s['channels']==2 and
                  s['name'].startswith(('alsa_output.','bluez_output.'))]
    if not selected:
        raise BridgeError('Nenhuma saída física estéreo confirmada. Use list e confira os canais. Nada será instalado.')
    return selected


def graph(profile, plugin:Path):
    nodes=[]; links=[]
    if profile['filters']:
        nodes.append({'type':'builtin','name':'oab_eq','label':'param_eq',
                      'config':{'filters':profile['filters']}})
    nodes.append({'type':'ladspa','name':'oab_dyn',
                  'plugin':str(plugin),
                  'label':LABEL,'control':{name:float(profile[field]) for field,name in DSP_PARAMS.items()}})
    if profile['filters']:
        links=[{'output':'oab_eq:Out 1','input':'oab_dyn:Input L'},
               {'output':'oab_eq:Out 2','input':'oab_dyn:Input R'}]
        inputs=['oab_eq:In 1','oab_eq:In 2']
    else:
        inputs=['oab_dyn:Input L','oab_dyn:Input R']
    return {'nodes':nodes, 'links':links, 'inputs':inputs,
            'outputs':['oab_dyn:Output L','oab_dyn:Output R']}


def fragment(profile, names, plugin=PLUGIN, soft_mixer=False, soft_mixer_cards=None):
    if not names: raise BridgeError('Lista de saídas vazia')
    # Exact name match, not a catch-all rule. Avoids accidental 5.1/7.1 processing.
    matches=[{'media.class':'Audio/Sink','node.name':name} for name in names]
    cfg={'matches':matches, 'actions':{'create-filter-graph':[graph(profile,plugin)]}}
    result=MARKER+'\n# Somente nos dispositivos estéreo selecionados; entrada/microfone não é afetado.\n'
    result+='node.filter-graph.rules = '+json.dumps([cfg],indent=2,ensure_ascii=False)+'\n'
    if soft_mixer:
        # api.alsa.soft-mixer is a *device* property, NOT a sink-node property.
        cards=sorted(set(soft_mixer_cards or []))
        if any(n.startswith('alsa_output.') for n in names) and not cards:
            raise BridgeError('Não consegui identificar as placas ALSA necessárias ao soft-mixer; nenhuma regra foi gerada.')
        alsa=[{'matches':[{'device.name':card}],
               'actions':{'update-props':{'api.alsa.soft-mixer':True}}}
              for card in cards]
        if alsa:
            result+='\n# Opt-in: não altera ganhos do hardware; força volume por software em dispositivos escolhidos.\n'
            result+='monitor.alsa.rules = '+json.dumps(alsa,indent=2)+'\n'
    return result


def status():
    print('Open Audio Bridge 0.1.0 (experimental)')
    for cmd in ('pipewire','wireplumber','pw-dump','systemctl','gcc'):
        print(f'  {cmd}: {shutil.which(cmd) or "não encontrado"}')
    for cmd in ('pipewire','wireplumber'):
        if shutil.which(cmd):
            try: print(f'  versão {cmd}: {".".join(map(str,version(cmd)))}')
            except BridgeError as e: print('  AVISO:',e)
    if shutil.which('systemctl'):
        result=run(['systemctl','--user','is-active','wireplumber'],timeout=5)
        print('  serviço WirePlumber:',result.stdout.strip() or result.stderr.strip())
    print('  configuração deste programa:', 'instalada' if FRAGMENT.is_file() and FRAGMENT.read_text().startswith(MARKER) else 'não instalada')
    if shutil.which('pw-dump'):
        try:
            for sink in read_sinks():
                print('  saída:',sink['name'],'| canais:',sink['channels'])
        except BridgeError as exc: print('  AVISO:',exc)
    print('  observação: este diagnóstico não julga qualidade sonora ou emula APOs do Windows.')


def backup_file(path:Path,backup_dir:Path):
    if path.exists():
        backup_dir.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,backup_dir/path.name)
        return str(backup_dir/path.name)
    return None


def known_plugin():
    try:
        state=json.loads((STATE/'current.json').read_text())
        return state.get('plugin_sha256') == hashlib.sha256(PLUGIN.read_bytes()).hexdigest()
    except (OSError, ValueError, AttributeError):
        return False


def apply(profile,names,soft_mixer=False,soft_mixer_cards=None):
    desktop_state=STATE.parent/'open-audio-bridge-desktop/settings.json'
    if desktop_state.exists() and json.loads(desktop_state.read_text()).get('enabled'):
        raise BridgeError('Open Audio Bridge Desktop está ativo. Use a janela do programa; instalar a regra antiga duplicaria o processamento.')
    platform_check()
    if FRAGMENT.exists() and not FRAGMENT.read_text(encoding='utf-8').startswith(MARKER):
        raise BridgeError('O destino já existe e não pertence ao OAB. Não será sobrescrito.')
    if PLUGIN.exists() and not FRAGMENT.exists() and not known_plugin():
        raise BridgeError('Plugin OAB existente sem configuração gerenciada. Não sobrescrevo arquivo desconhecido.')
    service=run(['systemctl','--user','is-active','wireplumber'])
    if service.returncode or service.stdout.strip()!='active':
        raise BridgeError('Serviço wireplumber não está ativo. Abortado sem mudanças.')
    now=dt.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_dir=STATE/'backups'/now
    old_fragment=backup_file(FRAGMENT,backup_dir)
    old_plugin=backup_file(PLUGIN,backup_dir)
    old_frag_data=FRAGMENT.read_bytes() if FRAGMENT.exists() else None
    old_plugin_data=PLUGIN.read_bytes() if PLUGIN.exists() else None
    modified=False
    try:
        compile_plugin(PLUGIN)
        data=fragment(profile,names,PLUGIN,soft_mixer,soft_mixer_cards)
        FRAGMENT.parent.mkdir(parents=True,exist_ok=True)
        tmp=FRAGMENT.with_suffix('.conf.tmp')
        tmp.write_text(data,encoding='utf-8')
        os.replace(tmp,FRAGMENT)
        modified=True
        restarted=run(['systemctl','--user','restart','wireplumber'],timeout=18)
        up=run(['systemctl','--user','is-active','wireplumber'],timeout=6)
        if restarted.returncode or up.returncode or up.stdout.strip()!='active':
            raise BridgeError('WirePlumber não reiniciou corretamente. Revertendo a alteração.')
    except Exception:
        if modified or PLUGIN.exists():
            if old_frag_data is None: FRAGMENT.unlink(missing_ok=True)
            else: FRAGMENT.write_bytes(old_frag_data)
            if old_plugin_data is None: PLUGIN.unlink(missing_ok=True)
            else: PLUGIN.write_bytes(old_plugin_data)
            run(['systemctl','--user','restart','wireplumber'],timeout=18)
        raise
    STATE.mkdir(parents=True,exist_ok=True)
    (STATE/'current.json').write_text(json.dumps({'date':now,'profile':profile['name'],
        'names':names,'soft_mixer':soft_mixer,'soft_mixer_cards':soft_mixer_cards,
        'fragment_backup':old_fragment,
        'plugin_backup':old_plugin, 'plugin_sha256':hashlib.sha256(PLUGIN.read_bytes()).hexdigest()},indent=2),encoding='utf-8')
    print('Instalado: ',FRAGMENT)
    print('Plugin:    ',PLUGIN)
    print('Saídas selecionadas:',', '.join(names))
    print('WirePlumber ativo. Isto verifica o serviço, NÃO a qualidade do som nem o DSP em execução.')
    print('Se o som falhar: python3 oab.py uninstall')


def uninstall():
    if not FRAGMENT.exists():
        print('Não há fragmento OAB instalado. Nada foi alterado.')
        return
    if not FRAGMENT.read_text(encoding='utf-8').startswith(MARKER):
        raise BridgeError('Arquivo não gerenciado; não será excluído.')
    FRAGMENT.unlink()
    if shutil.which('systemctl'):
        run(['systemctl','--user','restart','wireplumber'],timeout=18)
    print('Regra OAB desinstalada e roteamento original restaurado no próximo ciclo de áudio.')
    print('O plugin em ~/.ladspa foi preservado para não apagar um binário ainda em uso.')


def import_autoeq(src:Path,dst:Path):
    if dst.exists(): raise BridgeError('O arquivo de destino já existe; não será sobrescrito.')
    original=src.read_text(encoding='utf-8')
    filt=[]; preamp=0.0
    for line in original.splitlines():
        line=line.strip()
        m=re.match(r'Preamp:\s*([+-]?[\d.]+)\s*dB',line,re.I)
        if m:
            preamp=float(m.group(1))
            continue
        m=re.match(r'Filter\s+\d+:\s*ON\s+(PK|LSC|HSC)\s+Fc\s+([\d.]+)\s*Hz\s+Gain\s+([+-]?[\d.]+)\s*dB\s+Q\s+([\d.]+)',line,re.I)
        if m:
            label={'PK':'bq_peaking','LSC':'bq_lowshelf','HSC':'bq_highshelf'}[m.group(1).upper()]
            filt.append({'type':label,'freq':float(m.group(2)),
                         'gain':float(m.group(3)),'q':float(m.group(4))})
    if not filt: raise BridgeError('Nenhum filtro AutoEQ compatível identificado')
    template=profile_load('transparent')
    template.update(name=dst.stem, description=f'Imported from {src.name}; not a Windows APO',
                    drive_db=max(-12.0,min(18.0,preamp)),filters=filt)
    # Validate before saving, using a standalone profile validator.
    if len(filt)>24: raise BridgeError('Número máximo de filtros suportados é 24')
    for f in filt:
        if f['type'] not in VALID_FILTERS or not 15 <= f['freq'] <= 22000 or not -12 <= f['gain'] <= 12 or not 0.2 <= f['q'] <= 6:
            raise BridgeError('Filtro AutoEQ fora das faixas permitidas; nada foi escrito')
    dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_text(json.dumps(template,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('Perfil importado:',dst,'(importação AutoEQ, não importação de APO Windows)')


def main():
    p=argparse.ArgumentParser(description='Open Audio Bridge - protótipo PipeWire/WirePlumber com reversão')
    subs=p.add_subparsers(dest='cmd',required=True)
    for name in ('doctor','list','build','uninstall'):
        subs.add_parser(name)
    for name in ('preview','install'):
        q=subs.add_parser(name)
        q.add_argument('--profile',default='transparent',help='transparent, loudness ou voice')
        q.add_argument('--target',action='append',help='Nome exato de uma saída (obtido em list); pode repetir')
        q.add_argument('--soft-mixer',action='store_true',help='Opt-in ALSA soft-mixer para saídas selecionadas')
    q=subs.add_parser('import-autoeq')
    q.add_argument('source',type=Path); q.add_argument('destination',type=Path)
    args=p.parse_args()
    try:
        if args.cmd=='doctor': status()
        elif args.cmd=='list':
            for s in read_sinks(): print(f"{s['name']}\t{s['channels']} canal(is)\t{s['description']}")
        elif args.cmd=='build':
            compile_plugin(PLUGIN)
            print('Plugin compilado em:',PLUGIN,'(não alterou o roteamento)')
        elif args.cmd=='uninstall': uninstall()
        elif args.cmd=='import-autoeq': import_autoeq(args.source,args.destination)
        else:
            prof=profile_load(args.profile)
            selected=selected_sinks(args.target)
            names=[s['name'] for s in selected]
            cards=[s.get('card') for s in selected if s['name'].startswith('alsa_output.')]
            if args.soft_mixer and any(not card or not card.startswith('alsa_card.') for card in cards):
                raise BridgeError('Não foi possível mapear todas as saídas ALSA para suas placas; desative --soft-mixer ou confira pw-dump.')
            cards=[c for c in cards if c]
            if args.cmd=='preview':
                print(fragment(prof,names,soft_mixer=args.soft_mixer,soft_mixer_cards=cards))
            elif args.cmd=='install': apply(prof,names,args.soft_mixer,cards)
    except BridgeError as exc:
        print('ERRO:',exc,file=sys.stderr)
        return 2
    return 0

if __name__=='__main__': sys.exit(main())

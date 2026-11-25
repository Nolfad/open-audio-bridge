"""Best-effort preservation of routes of living audio streams across policy reloads.

Only device names, numeric IDs and PipeWire object serials are inspected; no
application content or recording is involved. Never guess a stream identity
across a PipeWire server restart (numeric IDs may then be reused).
"""
import json
import bridge as b

_KINDS={'sink':('sinks','sink-inputs','move-sink-input'),'source':('sources','source-outputs','move-source-output')}


def _output(args):
 try:
  result=b.run(args,check=False)
  return result.stdout.strip() if result.returncode==0 else None
 except (b.BridgeError,OSError,ValueError,TypeError,AttributeError):return None


def _list(kind):
 raw=_output(['pactl','-f','json','list',kind])
 if raw is None:return []
 try:
  data=json.loads(raw)
  return [x for x in data if isinstance(x,dict)] if isinstance(data,list) else []
 except (ValueError,TypeError):return []


def _server_pid():
 value=_output(['systemctl','--user','show','pipewire','--property=MainPID','--value'])
 return value if value and value.isdigit() and int(value)>0 else None


def _devices(kind):
 return {str(x['index']):x['name'] for x in _list(_KINDS[kind][0])
         if 'index'in x and isinstance(x.get('name'),str) and x['name']}


def _identity(stream):
 props=stream.get('properties')
 value=props.get('object.serial') if isinstance(props,dict) else None
 return str(value) if isinstance(value,(str,int)) and str(value).isdigit() else None


def snapshot():
 """Capture stable target names before a necessary WirePlumber restart."""
 saved={'pid':_server_pid(),'defaults':{},'streams':{'sink':{},'source':{}}}
 for kind,(_,listing,_) in _KINDS.items():
  saved['defaults'][kind]=_output(['pactl','get-default-'+kind]);devices=_devices(kind)
  for stream in _list(listing):
   serial=_identity(stream);target=devices.get(str(stream.get(kind)))
   if serial and target:saved['streams'][kind][serial]=target
 return saved


def restore(saved):
 """Restore only still-existing devices and streams from the same server.

 An application that actually disconnected cannot be revived by moving another
 stream. A missing device is left to WirePlumber's fallback policy.
 """
 if not isinstance(saved,dict):return
 pid=saved.get('pid');same_server=bool(pid and pid==_server_pid())
 for kind,(_,listing,move) in _KINDS.items():
  devices=_devices(kind);names=set(devices.values());target=saved.get('defaults',{}).get(kind)
  if target in names and target!=_output(['pactl','get-default-'+kind]):
   _output(['pactl','set-default-'+kind,target])
  if not same_server:continue
  old=saved.get('streams',{}).get(kind,{})
  for stream in _list(listing):
   serial=_identity(stream);target=old.get(serial);index=stream.get('index')
   if target in names and target!=devices.get(str(stream.get(kind))) and isinstance(index,(str,int)) and str(index).isdigit():
    _output(['pactl',move,str(index),target])

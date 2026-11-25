import json,unittest
from unittest.mock import patch
from types import SimpleNamespace
import audio_routes as routes

class RouteTests(unittest.TestCase):
 def fixture(self,after=False,pid='123'):
  # Numeric device IDs change, but stable names and living stream serials do not.
  sinks=[{'index':22 if after else 2,'name':'hdmi'},{'index':33 if after else 3,'name':'usb'}]
  sources=[{'index':44 if after else 4,'name':'mic'},{'index':55 if after else 5,'name':'webcam'}]
  playback=[{'index':71 if after else 7,'sink':33 if after else 2,'properties':{'object.serial':'1001'}},
            {'index':72 if after else 8,'sink':22 if after else 3,'properties':{'object.serial':'9999' if after else '1002'}}]
  capture=[{'index':91 if after else 9,'source':55 if after else 4,'properties':{'object.serial':'1003'}}]
  return {'sinks':sinks,'sources':sources,'sink-inputs':playback,'source-outputs':capture,'default-sink':'usb' if after else 'hdmi','default-source':'webcam' if after else 'mic','pid':pid}
 def runner(self,state,commands,failed=()):
  def run(args,**kwargs):
   commands.append(args)
   if args[0]=='systemctl':return SimpleNamespace(returncode=0,stdout=state['pid']+'\n')
   if args[1:4]==['-f','json','list']:
    if args[-1] in failed:return SimpleNamespace(returncode=1,stdout='')
    return SimpleNamespace(returncode=0,stdout=json.dumps(state[args[-1]]))
   if args[1].startswith('get-default-'):return SimpleNamespace(returncode=0,stdout=state[args[1][4:]]+'\n')
   return SimpleNamespace(returncode=0,stdout='')
  return run
 def test_restore_living_playback_and_capture_after_device_recreation(self):
  commands=[]
  with patch.object(routes.b,'run',side_effect=self.runner(self.fixture(),commands)):saved=routes.snapshot()
  commands=[]
  with patch.object(routes.b,'run',side_effect=self.runner(self.fixture(True),commands)):routes.restore(saved)
  self.assertIn(['pactl','set-default-sink','hdmi'],commands)
  self.assertIn(['pactl','set-default-source','mic'],commands)
  self.assertIn(['pactl','move-sink-input','71','hdmi'],commands)
  self.assertIn(['pactl','move-source-output','91','mic'],commands)
  self.assertNotIn(['pactl','move-sink-input','72','usb'],commands) # new unrelated stream
 def test_never_move_streams_across_pipewire_server_restart(self):
  with patch.object(routes.b,'run',side_effect=self.runner(self.fixture(),[])):saved=routes.snapshot()
  commands=[]
  with patch.object(routes.b,'run',side_effect=self.runner(self.fixture(True,pid='456'),commands)):routes.restore(saved)
  self.assertIn(['pactl','set-default-sink','hdmi'],commands)
  self.assertFalse(any('move-sink-input'in c or 'move-source-output'in c for c in commands))
 def test_missing_device_and_missing_serial_do_not_move_streams(self):
  state=self.fixture();state['sink-inputs'][1]['properties']={}
  with patch.object(routes.b,'run',side_effect=self.runner(state,[])):saved=routes.snapshot()
  now=self.fixture(True);now['sinks']=[now['sinks'][1]];commands=[]
  with patch.object(routes.b,'run',side_effect=self.runner(now,commands)):routes.restore(saved)
  self.assertNotIn(['pactl','set-default-sink','hdmi'],commands)
  self.assertFalse(any('move-sink-input'in c for c in commands))
  self.assertIn(['pactl','move-source-output','91','mic'],commands)
 def test_unavailable_server_is_best_effort_without_guessing(self):
  with patch.object(routes.b,'run',side_effect=routes.b.BridgeError('server unavailable')):saved=routes.snapshot();routes.restore(saved)
  self.assertEqual(saved['streams'],{'sink':{},'source':{}})
 def test_no_writes_when_routes_already_correct(self):
  state=self.fixture();commands=[]
  with patch.object(routes.b,'run',side_effect=self.runner(state,commands)):saved=routes.snapshot();routes.restore(saved)
  self.assertFalse(any(len(c)>1 and (c[1].startswith('move-') or c[1].startswith('set-default-')) for c in commands))

import io,json,tempfile,unittest,zipfile,stat,hashlib
from pathlib import Path
from unittest import mock
import updater

class UpdaterTests(unittest.TestCase):
 def test_numeric_versions_and_only_stable(self):
  self.assertGreater(updater.version_tuple('0.10.0'),updater.version_tuple('0.9.9'))
  for value in ['v0.5.0','0.5.0-rc1','0.5','1.2.3/evil']:
   with self.assertRaises(ValueError):updater.version_tuple(value)
 def archive(self,version='0.6.0',extras=None):
  data=io.BytesIO();root='open-audio-bridge-'+version+'/'
  with zipfile.ZipFile(data,'w') as archive:
   for name in ['bridge.py','native.py','updater.py','gui.py','sound.py','oab.py','install.py']:
    archive.writestr(root+name,"VERSION='"+version+"'\n" if name=='bridge.py' else '# fixture\n')
   for name,body in (extras or {}).items():archive.writestr(name,body)
  return data.getvalue()
 def test_safe_release_and_version_match(self):
  with tempfile.TemporaryDirectory() as folder:
   package=Path(folder)/'release.zip';package.write_bytes(self.archive())
   root=updater.extract_release(package,Path(folder)/'out','0.6.0')
   self.assertEqual(root.name,'open-audio-bridge-0.6.0')
   self.assertTrue((root/'native.py').is_file())
 def test_traversal_wrong_root_and_embedded_version_rejected(self):
  for extra in ['../escape','open-audio-bridge-0.6.0/../../escape','wrong/bridge.py','/absolute','open-audio-bridge-0.6.0/dir\\evil']:
   with self.subTest(extra=extra),tempfile.TemporaryDirectory() as folder:
    package=Path(folder)/'x.zip';package.write_bytes(self.archive(extras={extra:'bad'}))
    with self.assertRaises(ValueError):updater.extract_release(package,Path(folder)/'out','0.6.0')
  with tempfile.TemporaryDirectory() as folder:
   package=Path(folder)/'x.zip';package.write_bytes(self.archive('0.7.0'))
   with self.assertRaises(ValueError):updater.extract_release(package,Path(folder)/'out','0.6.0')
 def test_symlink_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   package=Path(folder)/'x.zip';package.write_bytes(self.archive())
   with zipfile.ZipFile(package,'a') as archive:
    link=zipfile.ZipInfo('open-audio-bridge-0.6.0/link');link.external_attr=(stat.S_IFLNK|0o777)<<16;archive.writestr(link,'../../escape')
   with self.assertRaises(ValueError):updater.extract_release(package,Path(folder)/'out','0.6.0')
 def test_checksum_must_match_exact_asset(self):
  blob=b'fixture';digest=hashlib.sha256(blob).hexdigest()
  updater.verify_checksum(blob,(digest+'  expected.zip\n').encode(),'expected.zip')
  for checksum in [digest+'  other.zip','0'*64+'  expected.zip',digest+'  ../expected.zip']:
   with self.assertRaises(ValueError):updater.verify_checksum(blob,checksum.encode(),'expected.zip')
 def test_release_url_does_not_come_from_remote_metadata(self):
  release={'tag_name':'v0.6.0','draft':False,'prerelease':False,'assets':[{'name':'open-audio-bridge-0.6.0.zip','browser_download_url':'https://evil.invalid/payload'},{'name':'SHA256SUMS'}]}
  self.assertEqual(updater.release_version(release),'0.6.0')
  self.assertTrue(updater.asset_url('0.6.0','SHA256SUMS').startswith('https://github.com/Nolfad/open-audio-bridge/releases/'))
  release['prerelease']=True
  with self.assertRaises(ValueError):updater.release_version(release)
 def test_redirect_rejects_non_https_and_unrelated_hosts(self):
  for url in ['http://github.com/x','https://evil.invalid/x','file:///etc/passwd','https://github.com.evil.invalid/x']:
   with self.assertRaises(ValueError):updater.validate_url(url)
  updater.validate_url('https://release-assets.githubusercontent.com/file')

class UpdateFlowTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.app=self.root/'app';self.state=self.root/'state';self.app.mkdir();self.state.mkdir()
  self.installed=self.app/'bridge.py';self.installed.write_text("VERSION='0.5.0'\n")
  (self.state/'native-baseline.json').write_text('{}');(self.state/'settings.json').write_text('{"routing":"native","enabled":false}')
  for obj,name,value in [(updater.b,'APP',self.app),(updater.b,'STATE',self.state),(updater.b,'SETTINGS',self.state/'settings.json'),(updater,'PREFS',self.state/'updates.json'),(updater,'STATUS',self.state/'status.json'),(updater,'LOCK',self.state/'update.lock')]:
   patch=mock.patch.object(obj,name,value);patch.start();self.addCleanup(patch.stop)
  updater.b.save(updater.PREFS,{'automatic':True})
  self.release={'tag_name':'v0.6.0','draft':False,'prerelease':False,'assets':[{'name':'open-audio-bridge-0.6.0.zip'},{'name':'SHA256SUMS'}]}
  self.blob=UpdaterTests().archive();self.calls=[]
 def fetch(self,url,limit=None):
  self.calls.append(url)
  if url==updater.API:return json.dumps(self.release).encode()
  if url.endswith('SHA256SUMS'):return (hashlib.sha256(self.blob).hexdigest()+'  open-audio-bridge-0.6.0.zip\n').encode()
  return self.blob
 def test_opt_out_does_not_connect(self):
  updater.b.save(updater.PREFS,{'automatic':False})
  with mock.patch.object(updater,'download',side_effect=AssertionError('must not connect')):updater.check_apply()
 def test_busy_playback_defers_before_download(self):
  with mock.patch.object(updater,'download',side_effect=self.fetch),mock.patch.object(updater,'playback_busy',return_value=True),mock.patch.object(updater,'apply_release',side_effect=AssertionError('must not install')):
   result=updater.check_apply()
  self.assertEqual(result['state'],'deferred');self.assertEqual(self.calls,[updater.API])
 def test_idle_retry_uses_cached_release_and_verified_package(self):
  updater.record(last_checked=updater.time.time(),available_version='0.6.0',state='deferred')
  def install(args,**kwargs):
   self.assertEqual(args[-2:],['install-update','scheduled']);self.installed.write_text("VERSION='0.6.0'\n");return mock.Mock(returncode=0)
  with mock.patch.object(updater,'download',side_effect=self.fetch),mock.patch.object(updater,'playback_busy',return_value=False),mock.patch.object(updater.subprocess,'run',side_effect=install):result=updater.check_apply()
  self.assertEqual(result['state'],'updated');self.assertNotIn(updater.API,self.calls)
 def test_manual_can_update_with_auto_off_and_audio_playing(self):
  updater.b.save(updater.PREFS,{'automatic':False})
  def install(args,**kwargs):
   self.assertEqual(args[-1],'manual');self.installed.write_text("VERSION='0.6.0'\n");return mock.Mock(returncode=0)
  with mock.patch.object(updater,'download',side_effect=self.fetch),mock.patch.object(updater,'playback_busy',side_effect=AssertionError('manual request is explicit')),mock.patch.object(updater.subprocess,'run',side_effect=install):result=updater.check_apply(manual=True)
  self.assertEqual(result['state'],'updated');self.assertFalse(updater.automatic())
 def test_new_playback_during_download_defers(self):
  with mock.patch.object(updater,'download',side_effect=self.fetch),mock.patch.object(updater,'playback_busy',side_effect=[False,True]),mock.patch.object(updater.subprocess,'run',side_effect=AssertionError('must not install')):result=updater.check_apply()
  self.assertEqual(result['state'],'deferred');self.assertEqual(updater.file_version(self.installed),'0.5.0')
 def test_checksum_failure_never_runs_installer(self):
  def fetch(url,limit=None):return b'0'*64+b'  open-audio-bridge-0.6.0.zip' if url.endswith('SHA256SUMS') else self.fetch(url,limit)
  with mock.patch.object(updater,'download',side_effect=fetch),mock.patch.object(updater.subprocess,'run',side_effect=AssertionError('must not execute')):
   with self.assertRaises(ValueError):updater.check_apply(manual=True)
  self.assertEqual(updater.status()['state'],'error');self.assertEqual(updater.file_version(self.installed),'0.5.0')
 def test_older_remote_release_never_downgrades(self):
  self.installed.write_text("VERSION='0.7.0'\n")
  with mock.patch.object(updater,'download',side_effect=self.fetch),mock.patch.object(updater,'apply_release',side_effect=AssertionError('must not downgrade')):result=updater.check_apply(manual=True)
  self.assertEqual(result['state'],'idle')
 def test_concurrent_check_keeps_first_job_state(self):
  with updater.LOCK.open('a') as held:
   updater.fcntl.flock(held,updater.fcntl.LOCK_EX|updater.fcntl.LOCK_NB)
   with mock.patch.object(updater,'download',side_effect=AssertionError('already running')):result=updater.check_apply(manual=True)
   self.assertIn('andamento',result['message'])
 def test_installer_rechecks_playback_after_lock(self):
  with mock.patch.object(updater,'download',side_effect=self.fetch),mock.patch.object(updater,'playback_busy',return_value=False),mock.patch.object(updater.subprocess,'run',return_value=mock.Mock(returncode=75,stdout='Aguardando áudio.')):result=updater.check_apply()
  self.assertEqual(result['state'],'deferred');self.assertEqual(updater.file_version(self.installed),'0.5.0')
 def test_failed_installer_reports_error_without_success_marker(self):
  with mock.patch.object(updater,'download',side_effect=self.fetch),mock.patch.object(updater.subprocess,'run',return_value=mock.Mock(returncode=1,stderr='rollback completed',stdout='')):
   with self.assertRaises(updater.b.BridgeError):updater.check_apply(manual=True)
  self.assertEqual(updater.status()['state'],'error')
  self.assertEqual(updater.file_version(self.installed),'0.5.0')

class InstallerLockTests(unittest.TestCase):
 def test_rollback_preserves_lock_inode_and_exclusion(self):
  import native
  with tempfile.TemporaryDirectory() as folder:
   state=Path(folder)/'state';backup=Path(folder)/'backup';state.mkdir();backup.mkdir();lock_path=state/'native.lock'
   (state/'settings.json').write_text('new');(backup/'settings.json').write_text('old');(backup/'native.lock').write_text('backup lock')
   with lock_path.open('a') as held,mock.patch.object(native.b,'STATE',state):
    updater.fcntl.flock(held,updater.fcntl.LOCK_EX|updater.fcntl.LOCK_NB);inode=lock_path.stat().st_ino
    native.restore_state(backup)
    self.assertEqual(lock_path.stat().st_ino,inode)
    with lock_path.open('a') as other:
     with self.assertRaises(BlockingIOError):updater.fcntl.flock(other,updater.fcntl.LOCK_EX|updater.fcntl.LOCK_NB)
   self.assertEqual((state/'settings.json').read_text(),'old')

class PreferenceConcurrencyTests(unittest.TestCase):
 setUp=UpdateFlowTests.setUp
 def test_opt_out_waits_for_installer_and_wins_over_rollback(self):
  import concurrent.futures,threading
  started=threading.Event()
  def disable():started.set();updater.set_auto(False)
  with mock.patch.object(updater,'sync_schedule'),concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
   with (self.state/'native.lock').open('a') as held:
    updater.fcntl.flock(held,updater.fcntl.LOCK_EX)
    future=executor.submit(disable);self.assertTrue(started.wait(1))
    updater.time.sleep(.05);self.assertFalse(future.done())
    updater.b.save(updater.PREFS,{'automatic':True})
   future.result(timeout=2)
  self.assertFalse(updater.automatic())

class LatePlaybackTests(unittest.TestCase):
 def test_audio_started_during_compile_defers_before_stopping_processing(self):
  import native,oab,contextlib
  with tempfile.TemporaryDirectory() as folder,contextlib.ExitStack() as stack:
   root=Path(folder);state=root/'state';state.mkdir();app=root/'app';app.mkdir();source=root/'source';source.mkdir()
   (app/'bridge.py').write_text("VERSION='0.4.0'\n");(source/'bridge.py').write_text("VERSION='0.5.0'\n")
   (state/'settings.json').write_text('{"routing":"native","enabled":true}')
   (state/'native-baseline.json').write_text('{"files":{}}')
   sink={'name':'alsa_output.test','volume':{'L':{'value':20000},'R':{'value':20000}},'mute':False}
   patches=[mock.patch.object(native.b,'STATE',state),mock.patch.object(native.b,'APP',app),mock.patch.object(native.b,'SETTINGS',state/'settings.json'),mock.patch.object(native.b,'BASELINE',state/'legacy.json'),mock.patch.object(native,'BASE',state/'native-baseline.json'),mock.patch.object(native,'RULE',root/'rule'),mock.patch.object(native,'PLUGINS',{}),mock.patch.object(native.b,'prerequisites'),mock.patch.object(oab,'version',return_value=(9,9,9)),mock.patch.object(native.shutil,'which',return_value='/usr/bin/stub'),mock.patch.object(native.b,'sinks',return_value=[sink]),mock.patch.object(native.b,'snapshot',return_value={}),mock.patch.object(native.b,'sink_by_name',return_value=None),mock.patch.object(native.b,'default_sink',return_value=sink['name']),mock.patch.object(native.b,'run',return_value=mock.Mock(stdout='[]',returncode=0)),mock.patch.object(native,'level_snapshot',return_value={sink['name']:{'volume':[20000,20000],'mute':False}}),mock.patch.object(updater,'automatic',return_value=True)]
   for patch in patches:stack.enter_context(patch)
   audio={'busy':False}
   def compile_plugins(_):audio['busy']=True
   stack.enter_context(mock.patch.object(native.b,'compile_plugins',side_effect=compile_plugins));stack.enter_context(mock.patch.object(updater,'playback_busy',side_effect=lambda:audio['busy']))
   stop=stack.enter_context(mock.patch.object(native,'disable',side_effect=AssertionError('Must not stop processing')))
   with self.assertRaises(updater.DeferredUpdate):native.install(source,preserve_enabled=True,scheduled=True)
   stop.assert_not_called();self.assertEqual(updater.file_version(app/'bridge.py'),'0.4.0')
   self.assertFalse(app.with_name('app.native-staging').exists())

"""ACP output profiles must never rewrite the microphone's mixer configuration."""
import os
import resource
import shutil
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_mixer import find_profile, prepare_profile, prepared_paths


class NativeMixerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = self.root / 'paths'
        self.paths.mkdir()
        self.profile = self.root / 'default.conf'
        self.profile.write_text('[General]\nauto-profiles = yes\n.include mappings.conf\n')
        (self.root / 'mappings.conf').write_text(
            '[Mapping analog-stereo]\ndevice-strings = front:%f\n'
            'paths-output = analog-output\npaths-input = analog-input-mic\n')
        (self.paths / 'analog-output.conf').write_text(
            '[General]\npriority = 99\n[Jack Headphone]\nstate.plugged = yes\n'
            '.include analog-output.conf.common\n')
        (self.paths / 'analog-output.conf.common').write_text(
            '[Element PCM]\nvolume = merge\nswitch = mute\n'
            '[Element Master]\nvolume = merge # keep this comment\n')
        (self.paths / 'analog-input-mic.conf').write_text('[Element Mic]\nvolume = merge\n')
        self.out = self.root / 'generated'

    def test_preserves_input_ports_and_recursive_output_includes(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = prepare_profile(self.profile, self.out, self.paths)
        self.assertEqual(result, self.out / 'profile-sets/default.conf')
        self.assertIn('paths-input = analog-input-mic', result.read_text())
        published = prepared_paths(result)
        token = next(n[:-5] for n in published if n.endswith('-analog-output.conf'))
        self.assertIn('paths-output = ' + token, result.read_text())
        self.assertNotIn('/', token)
        output = published[token + '.conf'].read_text()
        self.assertIn('[Jack Headphone]\nstate.plugged = yes', output)
        common = next(p for n, p in published.items() if n.endswith('-analog-output.conf.common')).read_text()
        self.assertIn('volume = zero', common)
        self.assertIn('switch = mute', common)
        self.assertNotIn('volume = merge', common)
        self.assertFalse((self.out / 'paths/analog-input-mic.conf').exists())
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_fixed_pcm_does_not_apply_to_other_elements(self):
        prepare_profile(self.profile, self.out, self.paths, fixed_pcm=61)
        common = next(self.out.glob('paths/*-analog-output.conf.common')).read_text()
        self.assertIn('[Element PCM]\nvolume = 61', common)
        self.assertIn('[Element Master]\nvolume = zero', common)

    def test_missing_output_fails_without_publishing_profile(self):
        (self.paths / 'analog-output.conf.common').unlink()
        with self.assertRaises(FileNotFoundError):
            prepare_profile(self.profile, self.out, self.paths)
        self.assertFalse((self.out / 'profile-sets/default.conf').exists())

    def test_traversal_rejected(self):
        (self.root / 'mappings.conf').write_text('[Mapping a]\npaths-output = ../escape\n')
        with self.assertRaises(ValueError):
            prepare_profile(self.profile, self.out, self.paths)

    def test_duplicate_basenames_rejected(self):
        (self.paths / 'nested').mkdir()
        (self.paths / 'nested/analog-output.conf').write_text('[Element PCM]\nvolume = merge\n')
        (self.root / 'mappings.conf').write_text('[Mapping a]\npaths-output = analog-output nested/analog-output\n')
        with self.assertRaises(ValueError):
            prepare_profile(self.profile, self.out, self.paths)

    def test_recursive_include_cycle_rejected(self):
        (self.paths / 'analog-output.conf.common').write_text('.include analog-output.conf\n')
        with self.assertRaises(ValueError):
            prepare_profile(self.profile, self.out, self.paths)

    def test_nested_include_preserves_parent_section(self):
        self.profile.write_text('[General]\n.include mappings.conf\nauto-profiles = yes\n')
        (self.paths / 'analog-output.conf.common').write_text('.include pcm.conf\n')
        (self.paths / 'pcm.conf').write_text('[Element PCM]\nvolume = merge\nswitch = mute\n')
        result = prepare_profile(self.profile, self.out, self.paths)
        self.assertTrue(result.read_text().endswith('[General]\nauto-profiles = yes\n'))
        self.assertIn('volume = zero', next(self.out.glob('paths/*-pcm.conf')).read_text())

    def test_include_symlink_cannot_escape_source_root(self):
        (self.paths / 'analog-output.conf.common').unlink()
        (self.paths / 'analog-output.conf.common').symlink_to(self.profile)
        with self.assertRaises(ValueError):
            prepare_profile(self.profile, self.out, self.paths)

    def test_destination_symlink_cannot_overwrite_input(self):
        prepared = prepare_profile(self.profile, self.out, self.paths)
        original = self.paths / 'analog-input-mic.conf'
        before = original.read_bytes()
        output = next(p for n, p in prepared_paths(prepared).items() if n.endswith('-analog-output.conf'))
        output.unlink()
        output.symlink_to(original)
        with self.assertRaises(ValueError):
            prepare_profile(self.profile, self.out, self.paths)
        self.assertEqual(original.read_bytes(), before)

    def test_repeated_mappings_use_same_basename_lookup_key(self):
        mappings = self.root / 'mappings.conf'
        mappings.write_text(mappings.read_text() + '[Mapping second]\npaths-output = analog-output\n')
        result = prepare_profile(self.profile, self.out, self.paths)
        tokens = [line.split('=', 1)[1].strip() for line in result.read_text().splitlines()
                  if line.startswith('paths-output')]
        self.assertEqual(tokens[0], tokens[1])
        self.assertEqual(tokens[0], Path(tokens[0]).name)
        self.assertTrue((self.out / 'paths' / (tokens[0] + '.conf')).is_file())

    def test_private_profiles_get_distinct_output_names(self):
        first = prepare_profile(self.profile, self.out, self.paths)
        second = prepare_profile(self.profile, self.root / 'second', self.paths)
        self.assertFalse(set(prepared_paths(first)) & set(prepared_paths(second)))

    @unittest.skipUnless(os.environ.get('OAB_TEST_ACP_CARD') and shutil.which('spa-acp-tool'),
                         'Set OAB_TEST_ACP_CARD for the read-only native ACP regression test')
    def test_actual_acp_reuses_paths_across_null_pcm_mappings(self):
        # Null PCMs exercise ACP's actual path hashmaps even while real audio is busy.
        # No profile is activated, and mixer path selection is explicitly disabled.
        self.profile.write_text('[General]\nauto-profiles = yes\n' + ''.join(
            f'[Mapping output-{i}]\ndirection = output\ndevice-strings = null\n'
            'channel-map = left,right\npaths-output = analog-output\n' for i in range(2)))
        prepared = prepare_profile(self.profile, self.out, self.paths)
        env = dict(os.environ, ACP_PATHS_DIR=str(self.out / 'paths'))

        def probe(profile):
            props = (f'device.profile-set={profile} api.acp.auto-profile=false '
                     'api.acp.auto-port=false api.alsa.disable-mixer-path=true '
                     'api.acp.disable-pro-audio=true')
            return subprocess.run(['spa-acp-tool', '-c', os.environ['OAB_TEST_ACP_CARD'],
                                   '-p', props, 'list-profiles'], env=env,
                                  capture_output=True, text=True, timeout=20,
                                  preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))

        good = probe(prepared)
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertIn('output:output-0', good.stderr)
        self.assertIn('output:output-1', good.stderr)
        token = next(line.split('=', 1)[1].strip() for line in prepared.read_text().splitlines()
                     if line.startswith('paths-output'))
        old = self.root / 'absolute-path-regression.conf'
        old.write_text(prepared.read_text().replace('paths-output = ' + token,
                       'paths-output = ' + str(self.out / 'paths' / token)))
        broken = probe(old)
        self.assertEqual(broken.returncode, -6, broken.stderr)
        self.assertIn('profile_set_add_path', broken.stderr)

    def test_profile_search_environment_and_absolute_paths(self):
        with patch.dict(os.environ, {'ACP_PROFILES_DIR': str(self.root)}, clear=False):
            self.assertEqual(find_profile(), self.profile)
            self.assertEqual(find_profile(str(self.profile)), self.profile)
        with self.assertRaises(FileNotFoundError):
            find_profile(str(self.root / 'absent.conf'))

    def test_user_profile_search_before_system(self):
        preferred = self.root / 'alsa-card-profile/mixer/profile-sets/default.conf'
        preferred.parent.mkdir(parents=True)
        preferred.write_text('[General]\nauto-profiles = yes\n')
        with patch.dict(os.environ, {'ACP_PROFILES_DIR': '', 'XDG_CONFIG_HOME': str(self.root)}):
            self.assertEqual(find_profile(), preferred)


if __name__ == '__main__':
    unittest.main()

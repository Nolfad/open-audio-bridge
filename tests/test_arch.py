"""Arch recipes pin the validated ZIP and package only enumerated sources."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.build_arch import prepare_arch

ROOT = Path(__file__).resolve().parents[1]


class ArchPackageTests(unittest.TestCase):
    def test_recipe_pins_source_and_packages_clean_payload(self):
        with tempfile.TemporaryDirectory(prefix='oab arch ') as directory:
            root = Path(directory)
            archive = root / 'open-audio-bridge-0.5.2.zip'
            archive.write_bytes(b'validated source archive')
            recipe = prepare_arch(archive, '0.5.2', root / 'recipe')
            content = recipe.read_text()
            self.assertIn(hashlib.sha256(archive.read_bytes()).hexdigest(), content)
            self.assertNotIn('SKIP', content)
            for dependency in ('python>=3.10', 'python-pyqt5', 'gcc', 'glibc',
                               'pipewire>=1:1.6', 'pipewire-audio>=1:1.6',
                               'wireplumber>=0.5.15', 'pipewire-pulse', 'libpulse', 'systemd'):
                self.assertIn("'" + dependency + "'", content)
            # Exercise the real package() function, without makepkg or privileges.
            sources = root / 'source with spaces'
            sources.mkdir()
            (sources / 'open-audio-bridge-0.5.2').symlink_to(ROOT, target_is_directory=True)
            destination = root / 'package root'
            subprocess.run(['bash', '-euc', 'source "$1"; package', 'test', str(recipe)],
                           env=dict(os.environ, srcdir=str(sources), pkgdir=str(destination)), check=True)
            payload = destination / 'usr/share/open-audio-bridge-installer'
            self.assertEqual((payload / 'bridge.py').read_bytes(), (ROOT / 'bridge.py').read_bytes())
            self.assertFalse((payload / 'lib').exists())
            self.assertFalse((payload / '.git').exists())
            self.assertFalse(list(payload.rglob('*.pyc')))
            self.assertEqual((destination / 'usr/bin/open-audio-bridge').stat().st_mode & 0o777, 0o755)
            self.assertTrue((destination / 'usr/share/licenses/open-audio-bridge-installer/LICENSE').is_file())
            self.assertTrue((destination / 'usr/share/applications/open-audio-bridge-installer.desktop').is_file())

    def test_invalid_version_and_mismatched_archive_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for version in ('../escape', '0.5.2;false', '0.5.2'):
                with self.assertRaises(ValueError):
                    prepare_arch(root / 'other.zip', version, root / 'output')
            self.assertFalse((root / 'output').exists())

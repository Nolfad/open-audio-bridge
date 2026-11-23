"""The Debian artifact bootstraps a user install without maintainer scripts."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from tools.build_deb import build_deb

ROOT = Path(__file__).resolve().parents[1]


def launcher_module():
    loader = importlib.machinery.SourceFileLoader('oab_deb_launcher', str(ROOT / 'packaging/open-audio-bridge'))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class LauncherTests(unittest.TestCase):
    def test_new_or_orphan_install_uses_packaged_installer(self):
        launcher = launcher_module()
        with tempfile.TemporaryDirectory(prefix='oab home ') as directory:
            home = Path(directory)
            app = home / '.local/share/open-audio-bridge/app'
            self.assertEqual(launcher.entrypoint(home), launcher.PACKAGE / 'install.py')
            app.mkdir(parents=True)
            (app / 'gui.py').write_text('orphan')
            self.assertEqual(launcher.entrypoint(home), launcher.PACKAGE / 'install.py')
            self.assertEqual((app / 'gui.py').read_text(), 'orphan')

    def test_managed_install_with_spaces_opens_user_gui(self):
        launcher = launcher_module()
        with tempfile.TemporaryDirectory(prefix='oab home ') as directory:
            home = Path(directory)
            app = home / '.local/share/open-audio-bridge/app'
            app.mkdir(parents=True)
            for name in launcher.REQUIRED:
                (app / name).write_text('# managed source')
            (app / 'bridge.py').write_text("VERSION='0.5.0'\n")
            package = home / 'packaged installer'
            package.mkdir()
            (package / 'bridge.py').write_text("VERSION='0.5.0'\n")
            launcher.PACKAGE = package
            state = home / '.local/state/open-audio-bridge-desktop'
            state.mkdir(parents=True)
            (state / 'settings.json').write_text(json.dumps({'routing': 'native'}))
            (state / 'native-baseline.json').write_text(json.dumps({'files': {}}))
            self.assertEqual(launcher.entrypoint(home), app / 'gui.py')
            self.assertEqual(launcher.command(home, ['--tray']), ['/usr/bin/python3', str(app / 'gui.py'), '--tray'])
            (app / 'bridge.py').write_text("VERSION='0.6.0'\n")
            self.assertEqual(launcher.entrypoint(home), app / 'gui.py')
            (app / 'bridge.py').write_text("VERSION='0.4.0'\nraise RuntimeError('must not execute')\n")
            self.assertEqual(launcher.entrypoint(home), package / 'install.py')
            (app / 'bridge.py').write_text("VERSION='0.5.0'\n")
            (state / 'native-baseline.json').write_text('broken json')
            self.assertEqual(launcher.entrypoint(home), launcher.PACKAGE / 'install.py')


@unittest.skipUnless(shutil.which('dpkg-deb'), 'dpkg-deb is required')
class DebianPackageTests(unittest.TestCase):
    def test_contents_dependencies_no_scripts_and_reproducible(self):
        from tools.build import sources
        paths = [path.relative_to(ROOT) for path in sources()]
        with tempfile.TemporaryDirectory(prefix='oab deb ') as directory:
            root = Path(directory)
            stage = root / 'source stage'
            for relative in paths:
                destination = stage / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, destination)
            (stage / 'lib').mkdir()
            (stage / 'lib/compiled.so').write_bytes(b'not packaged')
            (stage / '.git').mkdir()
            (stage / '.git/config').write_text('not packaged')
            extras = [Path('lib/compiled.so'), Path('.git/config')]
            archive = build_deb(stage, paths + extras, '0.5.0', root / 'output one')
            again = build_deb(stage, paths + extras, '0.5.0', root / 'output two')
            self.assertEqual(archive.read_bytes(), again.read_bytes())
            metadata = subprocess.check_output(['dpkg-deb', '--field', str(archive)], text=True)
            for field in ['Package: open-audio-bridge-installer', 'Version: 0.5.0', 'Architecture: all',
                          'python3 (>= 3.10)', 'python3-pyqt5', 'gcc', 'libc6-dev | libc-dev', 'pipewire (>= 1.6)',
                          'wireplumber (>= 0.5.15)', 'pipewire-pulse', 'pipewire-bin', 'pulseaudio-utils', 'systemd']:
                self.assertIn(field, metadata)
            control = root / 'control'
            subprocess.run(['dpkg-deb', '--control', str(archive), str(control)], check=True)
            self.assertEqual({p.name for p in control.iterdir()}, {'control'})
            extracted = root / 'extract'
            subprocess.run(['dpkg-deb', '--extract', str(archive), str(extracted)], check=True)
            packaged = extracted / 'usr/share/open-audio-bridge-installer'
            self.assertEqual((packaged / 'bridge.py').read_bytes(), (stage / 'bridge.py').read_bytes())
            self.assertFalse((packaged / 'lib').exists())
            self.assertFalse((packaged / '.git').exists())
            self.assertEqual((extracted / 'usr/bin/open-audio-bridge').stat().st_mode & 0o777, 0o755)
            self.assertIn('Exec=/usr/bin/open-audio-bridge', (extracted / 'usr/share/applications/open-audio-bridge-installer.desktop').read_text())
            self.assertIn('MIT', (extracted / 'usr/share/doc/open-audio-bridge-installer/copyright').read_text())
            self.assertIn('dpkg', (extracted / 'usr/share/doc/open-audio-bridge-installer/README').read_text())

    def test_source_path_cannot_escape_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                build_deb(root, [Path('../outside')], '0.5.0', root / 'output')

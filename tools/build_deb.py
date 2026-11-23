#!/usr/bin/env python3
"""Build a deterministic Debian bootstrap installer from validated source files."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

PACKAGE = 'open-audio-bridge-installer'
EPOCH = 1577836800
EXCLUDED = {'.git', '__pycache__', '.pytest_cache', 'dist', 'lib'}


def build_deb(stage, source_paths, version, output):
    """Return a .deb in output; source_paths must be relative to validated stage.

    Only enumerated sources are shipped. Test-generated libraries and caches in
    stage are never collected. Neither source files nor the live user install
    are modified, and there are no package lifecycle scripts.
    """
    stage, output = Path(stage), Path(output)
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid installer version')
    paths = []
    for item in source_paths:
        path = Path(item)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError(f'Source must be relative to stage: {path}')
        if EXCLUDED.intersection(path.parts) or path.suffix in {'.so', '.o', '.pyc', '.pyo'}:
            continue
        source = stage / path
        if not source.is_file() or any((stage / Path(*path.parts[:i])).is_symlink() for i in range(1, len(path.parts) + 1)):
            raise ValueError(f'Invalid source: {path}')
        paths.append(path)
    with tempfile.TemporaryDirectory(prefix='oab-deb-') as directory:
        root = Path(directory) / PACKAGE
        payload = root / 'usr/share' / PACKAGE
        for relative in sorted(set(paths)):
            target = payload / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / relative, target)
            target.chmod(0o644)
        for source, destination, mode in (
            ('packaging/open-audio-bridge', 'usr/bin/open-audio-bridge', 0o755),
            ('packaging/open-audio-bridge-installer.desktop', 'usr/share/applications/open-audio-bridge-installer.desktop', 0o644),
            ('packaging/README', f'usr/share/doc/{PACKAGE}/README', 0o644),
            ('LICENSE', f'usr/share/doc/{PACKAGE}/copyright', 0o644),
        ):
            target = root / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / source, target)
            target.chmod(mode)
        control = root / 'DEBIAN/control'
        control.parent.mkdir(parents=True)
        size = sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
        control.write_text(
            f'Package: {PACKAGE}\nVersion: {version}\nArchitecture: all\n'
            'Maintainer: Nolfad <30302179+Nolfad@users.noreply.github.com>\n'
            'Section: sound\nPriority: optional\n'
            'Depends: python3 (>= 3.10), python3-pyqt5, gcc, libc6-dev | libc-dev, pipewire (>= 1.6), '
            'wireplumber (>= 0.5.15), pipewire-pulse, pipewire-bin, pulseaudio-utils, systemd\n'
            f'Installed-Size: {(size + 1023) // 1024}\n'
            'Description: Bootstrap installer for Open Audio Bridge\n'
            ' Installs source and a launcher for a separate per-user audio application.\n'
            ' Run Open Audio Bridge from the desktop menu to install in your account.\n'
            ' Runtime updates are managed by the application, independently of dpkg.\n'
            ' Removing this package does not remove per-user applications or settings.\n',
            encoding='utf-8',
        )
        control.chmod(0o644)
        for path in [root, *root.rglob('*')]:
            if path.is_dir():
                path.chmod(0o755)
            os.utime(path, (EPOCH, EPOCH))
        archive = Path(directory) / f'{PACKAGE}_{version}_all.deb'
        subprocess.run(
            ['dpkg-deb', '--build', '--root-owner-group', '-Zxz', '-z9', str(root), str(archive)],
            env=dict(os.environ, SOURCE_DATE_EPOCH=str(EPOCH)), check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        output.mkdir(parents=True, exist_ok=True)
        destination = output / archive.name
        shutil.copyfile(archive, destination)
    return destination

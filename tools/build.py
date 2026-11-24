#!/usr/bin/env python3
"""Compile and test an isolated copy, then create a reproducible source installer."""
import argparse
import ast
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'bridge.py', 'gui.py', 'install.py', 'oab.py', 'Instalar.desktop',
    'README.md', 'CHANGELOG.md', 'LICENSE', 'tools/build.py', 'native.py', 'native_mixer.py', 'sound.py', 'updater.py', 'tools/build_deb.py', 'tools/build_arch.py',
)


def version():
    for node in ast.parse((ROOT / 'bridge.py').read_text(encoding='utf-8')).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == 'VERSION'
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str) and re.fullmatch(r'\d+\.\d+\.\d+', value):
                return value
    raise RuntimeError('VERSION inválida em bridge.py')


def sources():
    paths = [ROOT / name for name in FILES]
    paths.extend(p for p in (ROOT / 'packaging').iterdir() if p.is_file())
    for directory, suffixes in (
        ('src', {'.c', '.h'}), ('profiles', {'.json'}), ('tests', {'.py'}),
    ):
        paths.extend(p for p in (ROOT / directory).iterdir() if p.suffix in suffixes)
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f'Fonte inválida: {path.relative_to(ROOT)}')
    return sorted(paths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    if not shutil.which('gcc'):
        raise SystemExit('gcc é obrigatório para validar o build.')
    package = f'open-audio-bridge-{version()}'
    paths = sources()
    # No installation, service restart or access to the live audio graph.
    with tempfile.TemporaryDirectory(prefix='oab-build-') as temp:
        stage = Path(temp) / package
        stage.mkdir()
        for source in paths:
            target = stage / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1')
        subprocess.run(
            [sys.executable, '-c', 'import bridge; bridge.compile_plugins(bridge.ROOT)'],
            cwd=stage, env=env, check=True,
        )
        subprocess.run(
            [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
            cwd=stage, env=env, check=True,
        )
        archive = Path(temp) / f'{package}.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as out:
            for source in paths:
                relative = source.relative_to(ROOT)
                info = zipfile.ZipInfo(f'{package}/{relative.as_posix()}', (2020, 1, 1, 0, 0, 0))
                info.create_system = 3
                executable = relative.as_posix() == 'Instalar.desktop' or source.suffix == '.py'
                info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                out.writestr(info, (stage / relative).read_bytes())
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        args.output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(archive, args.output / archive.name)
        from build_deb import build_deb
        deb = build_deb(stage, [p.relative_to(ROOT) for p in paths], version(), args.output)
        deb_digest = hashlib.sha256(deb.read_bytes()).hexdigest()
        (args.output / 'SHA256SUMS').write_text(f'{digest}  {archive.name}\n{deb_digest}  {deb.name}\n', encoding='utf-8')
        from build_arch import prepare_arch
        prepare_arch(args.output / archive.name, version(), args.output / 'arch')
    print(f'Build validado: {args.output / archive.name}')


if __name__ == '__main__':
    main()

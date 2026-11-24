#!/usr/bin/env python3
"""Prepare a makepkg recipe pinned to the already validated release ZIP."""
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def prepare_arch(archive, version, output):
    archive, output = Path(archive), Path(output)
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid installer version')
    if archive.name != f'open-audio-bridge-{version}.zip':
        raise ValueError('Source archive name does not match version')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    template = (ROOT / 'packaging/PKGBUILD.in').read_text(encoding='utf-8')
    output.mkdir(parents=True, exist_ok=True)
    recipe = output / 'PKGBUILD'
    recipe.write_text(template.replace('@VERSION@', version).replace('@SHA256@', digest), encoding='utf-8')
    return recipe

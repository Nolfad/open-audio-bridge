"""Prepare private ACP output mixer paths without changing input mixer behavior.

This module only prepares files. Loading the profile and changing audio devices
are deliberately left to the caller.
"""
import os
import hashlib
from pathlib import Path
import re


def find_profile(name: str = 'default.conf') -> Path:
    """Resolve an ACP profile using PipeWire's configuration search order."""
    requested = Path(name)
    if requested.is_absolute():
        if not requested.is_file():
            raise FileNotFoundError(requested)
        return requested.resolve()
    if '..' in requested.parts:
        raise ValueError('Profile path traversal is not allowed')
    config = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    roots = []
    if os.environ.get('ACP_PROFILES_DIR'):
        roots.append(Path(os.environ['ACP_PROFILES_DIR']))
    roots.extend(base / suffix / 'profile-sets'
                 for base in (config, Path('/etc'))
                 for suffix in ('alsa-card-profile/mixer', 'alsa-card-profile'))
    roots.append(Path('/usr/share/alsa-card-profile/mixer/profile-sets'))
    for root in roots:
        candidate = root / requested
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f'ACP profile not found: {name}')


def _body(line: str) -> str:
    return re.split(r'[;#]', line, maxsplit=1)[0].strip()


def _prefix(folder: Path) -> str:
    return 'oab-' + hashlib.sha256(str(folder.resolve()).encode()).hexdigest()[:16] + '-'


def prepared_paths(profile: Path) -> dict[str, Path]:
    """Files the caller must expose in its user ACP ``paths`` directory.

    Publish these unique basenames (files or symlinks) before loading the profile.
    ACP requires lookup tokens to equal the loaded path basename; absolute path
    tokens cause duplicate-key assertions when multiple mappings share a path.
    """
    folder = Path(profile).parent.parent
    return {p.name: p for p in sorted((folder / 'paths').glob(_prefix(folder) + '*')) if p.is_file()}


def prepare_profile(source_profile: Path, output_dir: Path, paths_dir: Path,
                    fixed_pcm: int | None = None) -> Path:
    """Clone a profile and its output paths, keeping input paths untouched.

    Profile/mapping names are preserved; output ports get private basename tokens.
    The caller must publish ``prepared_paths(result)`` in a user ACP paths folder.
    The default
    ``zero`` volume asks ALSA for its nearest 0 dB step. ``fixed_pcm`` optionally
    supplies a device-specific raw step for the PCM playback element only.
    No source file is rewritten, and all inputs are validated before publishing.
    """
    source_profile = Path(source_profile).resolve(strict=True)
    paths_dir = Path(paths_dir).resolve(strict=True)
    output_dir = Path(output_dir).resolve()
    if fixed_pcm is not None and (type(fixed_pcm) is not int or fixed_pcm < 0):
        raise ValueError('fixed_pcm must be a nonnegative integer')
    if any(c.isspace() or c in '#;' for c in str(output_dir)):
        raise ValueError('ACP output directory must not contain whitespace or comment delimiters')
    pending: dict[Path, str] = {}
    sources: set[Path] = set()
    basenames: dict[str, Path] = {}
    active: set[Path] = set()
    root_paths: dict[Path, str] = {}
    prefix = _prefix(output_dir)

    def resolve_reference(value: str, parent: Path, root: Path) -> Path:
        reference = Path(value)
        if '..' in reference.parts:
            raise ValueError(f'ACP path traversal is not allowed: {value}')
        candidate = reference if reference.is_absolute() else parent / reference
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError(f'ACP reference escapes its source directory: {value}')
        if not resolved.is_file():
            raise ValueError(f'ACP reference is not a file: {value}')
        return resolved

    def enter(source: Path) -> list[str]:
        if source in active:
            raise ValueError(f'ACP include cycle: {source}')
        active.add(source)
        sources.add(source)
        return source.read_text().splitlines(keepends=True)

    def clone_output(source: Path) -> Path:
        previous = basenames.setdefault(source.name, source)
        if previous != source:
            raise ValueError(f'Ambiguous ACP output basename: {source.name}')
        target = output_dir / 'paths' / (prefix + source.name)
        if target in pending:
            return target
        result = []
        section = ''
        for line in enter(source):
            body = _body(line)
            if body.startswith('.include '):
                included = resolve_reference(body[9:].strip(), source.parent, paths_dir)
                result.append(f'.include {clone_output(included)}\n')
            else:
                if body.startswith('[') and body.endswith(']'):
                    section = body[1:-1].strip()
                if re.fullmatch(r'volume\s*=\s*merge', body):
                    value = str(fixed_pcm) if fixed_pcm is not None and section in (
                        'Element PCM', 'Element PCM,0') else 'zero'
                    line = re.sub(r'(?<=\=)(\s*)merge\b', lambda m: m[1] + value, line, count=1)
                result.append(line)
        active.remove(source)
        pending[target] = ''.join(result)
        return target

    def expand_profile(source: Path) -> str:
        result = []
        section = ''
        for line in enter(source):
            body = _body(line)
            if body.startswith('.include '):
                included = resolve_reference(body[9:].strip(), source.parent, source_profile.parent)
                expanded = expand_profile(included)
                result.append(expanded + ('' if expanded.endswith('\n') else '\n'))
                # ACP's recursive parser restores the caller's section on return.
                if section:
                    result.append(f'[{section}]\n')
            elif re.match(r'paths-output\s*=', body):
                values = body.split('=', 1)[1].split()
                rewritten = []
                for value in values:
                    original = resolve_reference(value + '.conf', paths_dir, paths_dir)
                    copied = clone_output(original)
                    root_paths[copied] = original.stem
                    rewritten.append(copied.name[:-5])
                result.append('paths-output = ' + ' '.join(rewritten) + '\n')
            else:
                if body.startswith('[') and body.endswith(']'):
                    section = body[1:-1].strip()
                result.append(line)
        active.remove(source)
        return ''.join(result)

    result = output_dir / 'profile-sets' / source_profile.name
    pending[result] = expand_profile(source_profile)
    for path, original_name in root_paths.items():
        # Keep translated stock labels even though ACP's internal port key changes.
        # An explicit description-key in the source still takes precedence.
        pending[path] = f'[General]\ndescription-key = {original_name}\n' + pending[path]
    for target in pending:
        resolved = target.resolve()
        if not resolved.is_relative_to(output_dir) or resolved in sources:
            raise ValueError(f'Unsafe ACP output destination: {target}')
    for target, content in pending.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    return result

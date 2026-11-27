"""Remember real output levels without taking ownership of the desktop mixer."""
from pathlib import Path
import json
import bridge as b


def boot_id():
    try:
        return Path('/proc/sys/kernel/random/boot_id').read_text().strip() or None
    except OSError:
        return None


def device_key(sink):
    name, port = sink.get('name'), sink.get('active_port')
    if not isinstance(name, str) or not name.startswith(('alsa_output.', 'bluez_output.')):
        return None
    if isinstance(port, dict):
        port = port.get('name')
    if not isinstance(port, str):
        port = ''
    return json.dumps([name, port], ensure_ascii=False, separators=(',', ':'))


def validated_level(level):
    if not isinstance(level, dict) or type(level.get('mute')) is not bool:
        return None
    values = level.get('volume')
    if not isinstance(values, list) or len(values) != 2:
        return None
    # Do not replay corrupt or extreme values outside the supported mixer range.
    if any(type(v) is not int or not 0 <= v <= b.MAX_VOLUME * 65536 // 100 for v in values):
        return None
    return {'volume': list(values), 'mute': level['mute']}


def snapshot(sink):
    try:
        return validated_level({'volume': [v['value'] for v in sink['volume'].values()], 'mute': sink['mute']})
    except (AttributeError, KeyError, TypeError):
        return None


class LevelStore:
    def __init__(self, path, boot):
        self.path, self.boot = Path(path), boot
        try:
            state = b.read(self.path, {})
        except (OSError, ValueError):
            state = {}
        entries = state.get('devices', {}) if isinstance(state, dict) else {}
        self.entries = entries if isinstance(entries, dict) else {}

    def read_level(self, sink):
        return validated_level(self.entries.get(device_key(sink)))

    def restore_for(self, sink, allow_restore=True):
        entry = self.entries.get(device_key(sink))
        if not allow_restore or not self.boot or not isinstance(entry, dict):
            return None
        previous = entry.get('boot')
        if not isinstance(previous, str) or not previous or previous == self.boot:
            return None
        return validated_level(entry)

    def observe(self, sink, level=None):
        key = device_key(sink)
        level = snapshot(sink) if level is None else validated_level(level)
        if key is None or level is None or not self.boot:
            return
        entry = dict(level, boot=self.boot)
        if self.entries.get(key) == entry:
            return
        entries = dict(self.entries, **{key: entry})
        b.save(self.path, {'version': 1, 'devices': entries})
        self.entries = entries


class ArrivalTracker:
    """Allow asynchronous WirePlumber route restoration before attachment."""
    def __init__(self, settle=0.6, maximum=2.0):
        self.settle, self.maximum, self.pending = settle, maximum, {}

    def ready(self, sink, incarnation, now):
        key = (device_key(sink), incarnation)
        value = snapshot(sink)
        first, changed, last = self.pending.get(key, (now, now, value))
        if value != last:
            changed = now
        self.pending[key] = (first, changed, value)
        # The policy manager can publish the node before its route/volume is ready.
        return now - changed >= self.settle or now - first >= self.maximum

    def retain(self, keys):
        self.pending = {key: value for key, value in self.pending.items() if key in keys}

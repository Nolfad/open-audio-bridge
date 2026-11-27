"""Native volume survives a session restart without taking volume ownership from KDE."""
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import native


def make_sink(name='alsa_output.test', port='analog-output-lineout', values=(26214, 13107), mute=True):
    return {
        'name': name, 'active_port': port, 'mute': mute,
        'volume': {k: {'value': v} for k, v in zip(('front-left', 'front-right'), values)},
    }


def level(values=(26214, 13107), mute=True):
    return {'volume': list(values), 'mute': mute}


class NativeVolumeStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'native-volume.json'
        self.Store = importlib.import_module('native_volume').LevelStore

    def test_reboot_restores_exact_channel_levels_and_mute_before_first_observation(self):
        previous = self.Store(self.path, 'old-boot')
        previous.observe(make_sink())
        restarted = self.Store(self.path, 'new-boot')
        startup = make_sink(values=(65536, 65536), mute=False)
        self.assertEqual(restarted.restore_for(startup), level())
        self.assertEqual(restarted.read_level(startup), level())

    def test_same_boot_uses_live_volume_instead_of_replaying_persisted_volume(self):
        self.Store(self.path, 'same-boot').observe(make_sink())
        restarted = self.Store(self.path, 'same-boot')
        changed = make_sink(values=(42598, 42598), mute=False)
        self.assertIsNone(restarted.restore_for(changed))
        restarted.observe(changed)
        self.assertEqual(restarted.read_level(changed), level((42598, 42598), False))

    def test_restore_is_not_repeated_once_sink_observed_in_current_boot(self):
        self.Store(self.path, 'old-boot').observe(make_sink())
        current = self.Store(self.path, 'new-boot')
        self.assertEqual(current.restore_for(make_sink(values=(65536, 65536), mute=False)), level())
        current.observe(make_sink())
        self.assertIsNone(current.restore_for(make_sink(values=(50000, 40000), mute=False)))
        self.assertIsNone(self.Store(self.path, 'new-boot').restore_for(make_sink()))

    def test_unknown_sink_is_not_treated_as_saved_device(self):
        self.Store(self.path, 'old-boot').observe(make_sink())
        current = self.Store(self.path, 'new-boot')
        unknown = make_sink(name='alsa_output.other', values=(65536, 65536), mute=False)
        self.assertIsNone(current.restore_for(unknown))
        self.assertIsNone(current.read_level(unknown))

    def test_later_connected_device_retains_previous_boot_level_until_seen(self):
        previous = self.Store(self.path, 'old-boot')
        previous.observe(make_sink(name='alsa_output.headset', values=(17600, 11000), mute=False))
        previous.observe(make_sink(name='alsa_output.hdmi'))
        current = self.Store(self.path, 'new-boot')
        current.observe(make_sink(name='alsa_output.hdmi', values=(31000, 31000), mute=False))
        # The headset was not present when the HDMI sink appeared at login.
        late = make_sink(name='alsa_output.headset', values=(65536, 65536), mute=False)
        self.assertEqual(current.restore_for(late), level((17600, 11000), False))
        # Device record survives an independent daemon restart in this boot.
        self.assertEqual(self.Store(self.path, 'new-boot').restore_for(late), level((17600, 11000), False))

    def test_shared_sink_name_has_independent_output_ports(self):
        previous = self.Store(self.path, 'old-boot')
        previous.observe(make_sink(port='analog-output-lineout', values=(26214, 13107), mute=True))
        previous.observe(make_sink(port='analog-output-headphones', values=(40000, 30000), mute=False))
        current = self.Store(self.path, 'new-boot')
        self.assertEqual(current.restore_for(make_sink(port='analog-output-lineout')), level())
        self.assertEqual(current.restore_for(make_sink(port='analog-output-headphones')), level((40000, 30000), False))
        self.assertIsNone(current.restore_for(make_sink(port='hdmi-output-0')))

    def test_manual_start_can_suppress_previous_boot_restore(self):
        self.Store(self.path, 'old-boot').observe(make_sink())
        current = self.Store(self.path, 'new-boot')
        live = make_sink(values=(50000, 40000), mute=False)
        self.assertIsNone(current.restore_for(live, allow_restore=False))
        current.observe(live)
        self.assertEqual(current.read_level(live), level((50000, 40000), False))
        self.assertIsNone(current.restore_for(live))

    def test_missing_or_invalid_file_is_safe_and_can_capture_new_level(self):
        for data in (None, '{garbage', '[]', '{"junk":true}'):
            with self.subTest(data=data):
                self.path.unlink(missing_ok=True)
                if data is not None:
                    self.path.write_text(data)
                current = self.Store(self.path, 'new-boot')
                self.assertIsNone(current.restore_for(make_sink()))
                self.assertIsNone(current.read_level(make_sink()))
                current.observe(make_sink())
                self.assertEqual(current.read_level(make_sink()), level())

    def test_zero_and_above_unity_channel_levels_roundtrip_without_rescaling(self):
        previous = self.Store(self.path, 'old-boot')
        previous.observe(make_sink(values=(0, 81920), mute=False))
        current = self.Store(self.path, 'new-boot')
        self.assertEqual(current.restore_for(make_sink()), level((0, 81920), False))


    def test_invalid_level_record_is_not_restored(self):
        import json
        from native_volume import device_key
        for invalid in ({'volume': [65536], 'mute': False},
                        {'volume': [-1, 20000], 'mute': False},
                        {'volume': [1000000, 0], 'mute': False},
                        {'volume': [True, 20000], 'mute': False},
                        {'volume': [20000, 20000], 'mute': 'false'}):
            with self.subTest(invalid=invalid):
                self.path.write_text(json.dumps({'version': 1, 'devices': {
                    device_key(make_sink()): dict(invalid, boot='old-boot'),
                }}))
                current = self.Store(self.path, 'new-boot')
                self.assertIsNone(current.read_level(make_sink()))
                self.assertIsNone(current.restore_for(make_sink()))

    def test_unavailable_boot_id_disables_replay_and_preserves_saved_record(self):
        self.Store(self.path, 'old-boot').observe(make_sink())
        current = self.Store(self.path, None)
        self.assertIsNone(current.restore_for(make_sink()))
        current.observe(make_sink(values=(65536, 65536), mute=False))
        self.assertEqual(self.Store(self.path, 'new-boot').restore_for(make_sink()), level())


class NativeArrivalTrackerTests(unittest.TestCase):
    def setUp(self):
        self.native_volume = importlib.import_module('native_volume')
        self.tracker = self.native_volume.ArrivalTracker(settle=0.5, maximum=2.0)

    def test_waits_for_route_volume_to_settle_before_attachment(self):
        initial = make_sink(values=(65536, 65536), mute=False)
        restored = make_sink()
        self.assertFalse(self.tracker.ready(initial, 'first', 0.0))
        self.assertFalse(self.tracker.ready(initial, 'first', 0.25))
        self.assertFalse(self.tracker.ready(restored, 'first', 0.5))
        self.assertFalse(self.tracker.ready(restored, 'first', 0.75))
        self.assertTrue(self.tracker.ready(restored, 'first', 1.0))

    def test_maximum_wait_does_not_starve_continuously_changing_output(self):
        for step in range(8):
            self.assertFalse(self.tracker.ready(make_sink(values=(10000 + step, 20000)), 'first', step / 4))
        self.assertTrue(self.tracker.ready(make_sink(values=(10008, 20000)), 'first', 2.0))

    def test_recreated_node_or_new_port_must_settle_independently(self):
        lineout = make_sink()
        headphones = make_sink(port='analog-output-headphones')
        self.assertFalse(self.tracker.ready(lineout, 'first', 0.0))
        self.assertTrue(self.tracker.ready(lineout, 'first', 0.5))
        self.assertFalse(self.tracker.ready(lineout, 'new-node', 0.5))
        self.assertFalse(self.tracker.ready(headphones, 'first', 0.5))
        self.tracker.retain({(self.native_volume.device_key(lineout), 'new-node')})
        self.assertFalse(self.tracker.ready(lineout, 'first', 1.0))
        self.assertTrue(self.tracker.ready(lineout, 'new-node', 1.0))


class NativeAttachmentLevelTests(unittest.TestCase):
    def test_saved_level_is_applied_while_output_is_muted_before_dsp_attach(self):
        sink = make_sink(values=(65536, 65536), mute=False)
        prior = level()
        node = {'id': 42, 'info': {'props': {'object.serial': 43}, 'params': {'Props': []}}}
        events = []
        with mock.patch.object(native.b, 'run', side_effect=lambda args: events.append(('run', args))), \
                mock.patch.object(native.b, 'save'), \
                mock.patch.object(native, 'set_props', side_effect=lambda n, props: events.append(('props', props))), \
                mock.patch.object(native, 'restore_levels', side_effect=lambda levels: events.append(('restore', levels))):
            native.attach(node, sink, 'boost', {}, prior=prior)
        self.assertEqual(events[0], ('run', ['pactl', 'set-sink-mute', sink['name'], '1']))
        self.assertEqual(events[1][0], 'props')  # graph initialized while muted
        self.assertEqual(events[2], ('props', {'channelVolumes': [(v / 65536) ** 3 for v in prior['volume']], 'mute': True}))
        self.assertEqual(events[3], ('restore', {sink['name']: prior}))


class NativeDaemonVolumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.Store = importlib.import_module('native_volume').LevelStore
        self.path = self.state / 'native-volume.json'
        self.config = {'routing': 'native', 'enabled': True, 'autostart': True,
                       'target': 'default', 'curve': 'boost'}
        self.primary = make_sink(name='alsa_output.hdmi', port='hdmi-output-0')
        self.late = make_sink(name='bluez_output.headset', port='headset-output', values=(17000, 16000), mute=False)
        self.Store(self.path, 'old-boot').observe(self.primary)
        self.Store(self.path, 'old-boot').observe(self.late)
        self.patches = [mock.patch.object(native.b, 'STATE', self.state),
                        mock.patch.object(native, 'OWNED', self.state / 'owned.json'),
                        mock.patch.object(native, 'READY', self.state / 'ready.json'),
                        mock.patch.object(native.native_volume, 'boot_id', return_value='new-boot')]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    @staticmethod
    def set_levels(sink, values, mute):
        for channel, value in zip(sink['volume'].values(), values):
            channel['value'] = value
        sink['mute'] = mute

    def run_session(self, items, event, duration=2.75, restores=None):
        clock = [0.0]
        handlers = {}
        calls = []

        def fake_nodes():
            return {s['name']: {'id': i + 10, 'info': {'props': {'object.serial': i + 100}}}
                    for i, s in enumerate(items)}

        def fake_attach(node, sink, curve, owned, sound_config=None, prior=None):
            calls.append((sink['name'], prior))
            owned[sink['name']] = {'id': node['id'], 'serial': native.serial(node),
                                   'curve': curve, 'sound': native.sound.normalize(sound_config),
                                   'device_key': native.native_volume.device_key(sink)}
            if prior is not None:
                self.set_levels(sink, prior['volume'], prior['mute'])

        def fake_restore(levels):
            if restores is not None:
                restores.append(levels)
            for sink in items:
                if sink['name'] in levels:
                    saved = levels[sink['name']]
                    self.set_levels(sink, saved['volume'], saved['mute'])

        def fake_run(args, **kwargs):
            # Isolate all system mixer operations, including potential route-only mute.
            if args[:2] == ['pactl', 'set-sink-mute']:
                next(s for s in items if s['name'] == args[2])['mute'] = args[3] == '1'
            else:
                raise AssertionError(f'Unexpected live audio command in daemon test: {args}')

        def sleep(_):
            clock[0] += 0.25
            event(clock[0])
            if clock[0] >= duration:
                handlers[native.signal.SIGTERM]()

        with mock.patch.object(native, 'settings', return_value=self.config), \
                mock.patch.object(native, 'recover'), \
                mock.patch.object(native, 'nodes', side_effect=fake_nodes), \
                mock.patch.object(native.b, 'sinks', side_effect=lambda: items.copy()), \
                mock.patch.object(native.b, 'run', side_effect=fake_run), \
                mock.patch.object(native, 'restore_levels', side_effect=fake_restore), \
                mock.patch.object(native, 'attach', side_effect=fake_attach), \
                mock.patch.object(native.signal, 'signal', side_effect=lambda sig, callback: handlers.update({sig: callback})), \
                mock.patch.object(native.time, 'monotonic', side_effect=lambda: clock[0]), \
                mock.patch.object(native.time, 'sleep', side_effect=sleep):
            native.daemon()
        return calls

    def test_reboot_restore_late_device_current_kde_change_and_same_boot_restart(self):
        self.set_levels(self.primary, (65536, 65536), False)
        self.set_levels(self.late, (65536, 65536), False)
        items = [self.primary]

        def event(now):
            if now == 1.0:  # KDE change after initial restoration/attachment
                self.set_levels(self.primary, (42598, 22000), False)
            if now == 1.25:
                items.append(self.late)

        calls = self.run_session(items, event)
        self.assertEqual(calls, [(self.primary['name'], level()),
                                 (self.late['name'], level((17000, 16000), False))])
        saved = self.Store(self.path, 'new-boot')
        self.assertEqual(saved.read_level(self.primary), level((42598, 22000), False))
        self.assertEqual(saved.read_level(self.late), level((17000, 16000), False))

        # Restart OAB in the same boot after another system mixer change.
        self.set_levels(self.primary, (51000, 31000), True)
        self.assertEqual(self.run_session(items, lambda _: None, duration=1.5),
                         [(self.primary['name'], None), (self.late['name'], None)])
        self.assertEqual(self.Store(self.path, 'new-boot').read_level(self.primary),
                         level((51000, 31000), True))

    def test_same_node_port_switch_restores_previous_route_without_rebuilding_graph(self):
        original_port = self.primary['active_port']
        alternate = make_sink(name=self.primary['name'], port='hdmi-output-1',
                              values=(18000, 15000), mute=True)
        self.Store(self.path, 'old-boot').observe(alternate)
        self.set_levels(self.primary, (65536, 65536), False)
        restores = []

        def event(now):
            if now == 1.0:
                # PipeWire keeps the same node and serial, changing only the port.
                self.primary['active_port'] = alternate['active_port']
                self.set_levels(self.primary, (65536, 65536), False)
            if now == 1.25:
                self.assertEqual(self.Store(self.path, 'new-boot').restore_for(alternate),
                                 level((18000, 15000), True),
                                 'Do not persist the new port at 100% while it is still settling')
            if now == 2.25:
                self.set_levels(self.primary, (30000, 25000), False)

        calls = self.run_session([self.primary], event, restores=restores)
        self.assertEqual(calls, [(self.primary['name'], level())],
                         'Changing a port on the same node must not rebuild the DSP graph')
        self.assertEqual(restores, [{self.primary['name']: level((18000, 15000), True)}])
        saved = self.Store(self.path, 'new-boot')
        self.assertEqual(saved.read_level(make_sink(name=self.primary['name'], port=original_port)), level())
        self.assertEqual(saved.read_level(alternate), level((30000, 25000), False))

    def test_seed_levels_only_updates_selected_sinks_without_overriding_live_volume(self):
        self.set_levels(self.primary, (41500, 25000), False)
        self.set_levels(self.late, (65536, 65536), False)
        with mock.patch.object(native.b, 'sinks', return_value=[self.primary, self.late]), \
                mock.patch.object(native.b, 'run', side_effect=AssertionError('Seeding must not modify live levels')):
            native.seed_levels(dict(self.config, target=self.primary['name']))
        saved = self.Store(self.path, 'new-boot')
        self.assertEqual(saved.read_level(self.primary), level((41500, 25000), False))
        self.assertIsNone(saved.restore_for(self.primary))
        self.assertEqual(saved.restore_for(self.late), level((17000, 16000), False))

    def test_managed_transition_lock_prevents_recording_temporary_volume_mute(self):
        saved = self.Store(self.path, 'new-boot')
        self.set_levels(self.primary, (65536, 65536), True)
        with (self.state / 'native.lock').open('a') as lock:
            native.b.fcntl.flock(lock, native.b.fcntl.LOCK_EX)
            native.observe_levels(saved, [self.primary], {self.primary['name']: {}})
        self.assertEqual(self.Store(self.path, 'new-boot').restore_for(self.primary), level())

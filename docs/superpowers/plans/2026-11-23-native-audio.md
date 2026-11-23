# Native audio implementation plan

Use executing-plans task by task; GUI and output mixer research are delegated independent units.
Goal: one KDE device/volume control, automatic system target and optional fixed target.
Architecture: internal PipeWire graph with native volume binding, output-only ACP mixer paths, reversible migration and service recovery.
Spec: docs/superpowers/specs/2026-11-23-native-audio.md

- [x] Inspect native graph support; prove controls bind and post-filter samples are processed in an isolated null sink.
- [x] Implement native backend: target selection, graph ownership, hotplug, volume/mute, failures and restoration. Add focused behavioral tests first.
- [x] Integrate output-only mixer setup without changing capture paths; test generated configuration and actual HyperX microphone control.
- [x] Update GUI/default/tray/installer copy and tests.
- [x] Validate automatic and fixed routing, silence, level equivalence, peak ceiling and recovery. Save prior local state, migrate actual install and verify hardware controls/default switching.
- [x] Review, build/test, update README/changelog and repository.


Verification (2026-11-23): 72 automated tests, one actual ACP probe opt-in (also passed locally). Native null-sink post-processing captured via debug.wav-path: 0% silence, progressive 40/80/100/150 gains, hot 150% sample peak 0.630957 (-4 dBFS), detach restored ordinary cubic volume. Real HyperX/HDMI default switching, fixed target, shared volume, disable/enable, upgrade and full uninstall/fresh install passed. All owned helper files removed on uninstall; HyperX microphone mixer unchanged throughout. Earlier failed profile migrations restored the prior installation; repeated path tokens are now tested against actual ACP parser with null PCMs.

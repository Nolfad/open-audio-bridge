# Native system audio

The user's requested behavior is the specification: choose output and volume in KDE once; processing follows the system without another output/volume or mandatory tray icon. Keep an optional fixed processing target. Preserve EQ/dynamics/peak guard and +20-point law; no microphone DSP or volume behavior change.

Use PipeWire's internal audioconvert filter graph on eligible real stereo outputs. In automatic mode, prepare each eligible output so KDE switches are immediate; each output retains its own native level/mute. Fixed mode processes only the named output, without overriding the system default. Bind native channel volume directly to the existing volume plugin, followed by the final limiter. For hardware mixer outputs, use an output-only ACP mixer configuration; input paths remain unchanged. Never attach over an unknown existing graph.

Keep the user service for hotplug/recovery. The GUI is optional and controls the same native output; no extra tray by default. Migration stages compilation, saves the existing state/files and retains rollback before removing the virtual route. Enable/disable and uninstall must remove only owned graphs/configuration, restore native mixing, preserve current mute/volume, and leave microphones untouched. Tests must capture post-processing output (sink monitors are pre-filter on this PipeWire).

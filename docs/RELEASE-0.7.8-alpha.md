# v0.7.8-alpha (Windows)

Reduce default diagnostic sampling and reuse immutable native-GL capture views
when coherent texture/palette contents are unchanged. Guest CPU/device timing,
geometry execution and integer-rendered guest readbacks keep their contracts.

The final matched older i5-4670 / GTX 760 sample used 5.08% less process CPU
time, 2.22% fewer process cycles and 1.31% less elapsed time. Private committed
memory was about 65 MiB lower. This is targeted uncapped simulation evidence,
not sustained interactive 60-FPS, all-game or real-peer Wiimmfi qualification.
CPU span and periodic-deadline probes were measured and rejected.

Focused graphics/save-state checks and state/pixel/audio/event comparisons pass;
the owner accepted the desktop visual playtest and authorized release without
a new Wiimmfi match or additional performance runs. Native saves are preserved.
The existing required bank inventory, compatible native shards and portable
toolchain remain included. Software rendering, LLE build choices and original
diagnostic/capture paths remain available. Linux delivery is unchanged.

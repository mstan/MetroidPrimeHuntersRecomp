# Host Adaptive Off comparison build

This branch is a temporary diagnostic build only.

When the launcher requests Adaptive Widescreen for an executable-compatible MPH ROM:

- guest-side MPH 21:9 projection/culling patch: **enabled**
- ndsrecomp host 448px adaptive framebuffer: **disabled**
- ndsrecomp adaptive HUD band anchoring/splitting: **disabled**
- host presentation falls back to the native 256x192 compositor path

The runner prints this marker when the comparison path is active:

```text
[mph-test] guest 21:9 projection/culling ON; host 448px adaptive framebuffer/HUD anchoring OFF
```

This experiment is intended to determine whether the current visual corruption is caused by combining the game-side melonPrimeDS/mphCodex aspect-ratio patch with ndsrecomp's host-side Adaptive Widescreen renderer.

# Host Adaptive Off comparison build

This branch is a temporary diagnostic build only.

When the launcher requests Adaptive Widescreen for an executable-compatible MPH ROM:

- guest-side MPH 21:9 projection/culling patch: **enabled**
- ndsrecomp host 448px adaptive GPU3D/render-width path: **disabled**
- ndsrecomp adaptive 448px GPU2D framebuffer/compositor path: **disabled**
- ndsrecomp adaptive HUD band anchoring/splitting: **disabled**
- emulated top-screen source remains **native 256x192**
- only the completed top-screen image is stretched by SDL from **256x192 to 448x192** for final display

The last point is required for a meaningful test. The MPH game-side patch changes the projection/culling for a 21:9 target, but the DS still produces a native 256x192 image. Displaying that image unchanged as 4:3 would make the game look horizontally compressed. This branch therefore restores the intended display shape with a simple final stretch while deliberately avoiding ndsrecomp's host-side widescreen renderer.

The runner prints this marker when the comparison path is active:

```text
[mph-test] guest 21:9 projection/culling ON; host adaptive renderer/HUD OFF; native 256x192 -> 448x192 present stretch ON
```

## What this isolates

Normal current Adaptive Widescreen combines two mechanisms:

1. MPH guest code/data patches derived from melonPrimeDS/mphCodex, which change projection/culling.
2. ndsrecomp host adaptive rendering, which widens the actual host render/composition path to 448 pixels and can separately anchor/split HUD content.

This comparison keeps (1), removes (2), and replaces (2) only with a dumb final 256-to-448 stretch. If the visual corruption disappears, that strongly indicates the current problem comes from combining the guest aspect-ratio patch with the host adaptive renderer rather than from the guest patch alone.

This is not automatically expected to be the final implementation. The original ndsrecomp host-wide path can provide higher-quality wide rendering because it actually renders extra horizontal pixels rather than stretching a native DS image. The purpose of this branch is A/B diagnosis of the suspected double application.

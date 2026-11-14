# v0.7.14-alpha

This update provides an exact fixed 16:9 display choice and matching adventure
geometry, corrects native OpenGL depth comparisons, and associates the touch
window with its game window without making it modal or globally topmost.
Current-build checkpoints rebind complete frustum groups to the selected width;
native aspect and explicit widescreen Off restore the original guest geometry.

Fresh profiles retain adaptive Fit to screen. Explicit saved aspect, rendering
and control choices are preserved, as are native cartridge saves. Execution
snapshots remain specific to their game and engine build.

Windows retains the native OpenGL/HLE execution profile and complete native
bank inventory. Linux retains its portable faithful profile. Both desktop
packages include the supported overlay toolchain, compatible published native
shards, matching font/component notices and exact source/build information.

Supply your own supported ROM. ROMs, BIOS, firmware, saves and captured guest
memory are not included.

# Prime Hunters bring-up ledger

## Target and references

- Cartridge: USA revision 0 (`AMHE`, `MP HUNTERS`)
- ROM SHA-1: `90164d1ac127ee5f9815ea4ae7de798c7b5fc629`
- Framework main integration: `778e74385aa223179a5d9534c2201ed1096a3df7`
- MphRead reference: `26cd8a6fe93dc5e525d1a1bb304fe96001111e55`
- Public matching disassembly: none found

The ARM9 ROM image is 517,828 bytes and expands to 907,736 bytes. The ARM7
image is 164,964 bytes. Prime Hunters has 18 compressed ARM9 overlays whose
overlay table contains 576 bytes (18 records), not 576 separate overlays.

## Evidence so far

1. The pre-existing SM64DS-native runner failed around the Prime Hunters game
   handoff with ARM7 PC `0xE590100C` and a corrupt stack.
2. The failure was caused by unconditional SM64DS bank registration, not by a
   Prime Hunters instruction or device requirement. Both titles load ARM7 at
   `0x02380000`, so address-only dispatch selected SM64DS code.
3. A clean BIOS-bank-only runner reaches 700,000,000 ARM9 cycles with both
   CPUs alive and no terminal dispatch miss.
4. Visual checkpoints:
   - VBlank 300: ActImagine splash
   - VBlank 900-1200: opening logo animation
   - VBlank 2400: opening cinematic
   - VBlank 3000: hunter cinematic
   - VBlank 3600: Weavel introduction
5. The initial generated main banks contained 4,335 ARM9 functions and 16
   ARM7 functions. Exact-ROM-gated registration produced the same 700,000,000
   cycle machine state as the clean interpreter runner.
6. AMHE uses melonDS SaveMemType 5: 256 KiB flash. Save type/capacity are now
   game-owned configuration instead of an SM64DS runner constant.
7. Native and ndsref event/cycle counts agree through the no-input return to
   the hunter reel and onward to VBlank 12000.
8. The title split exposed a cold-boot screen-routing defect hidden by the
   mirrored intro video: ndsrecomp reset POWCNT1 to `0x0001` instead of the
   retail/melonDS `0x820F`. The reset and 3D power defaults are corrected.
9. A second routing defect appeared only when Prime Hunters changed the LCD
   assignment during VBlank. The native renderer stored engine-relative
   frames and applied the current POWCNT1 only when the completed frame was
   read, which could retroactively swap it. Routing is now applied while each
   scanline is produced, matching melonDS framebuffer assignment.
10. The no-input title/loop checkpoints are:
    - VBlank 7800: title logo and `TOUCH TO START`
    - VBlank 8400: title animation
    - VBlank 9000: return to the hunter reel
    Native top/bottom captures are byte-identical to ndsref at all three.
11. The checkpoint helper now names screens explicitly and continues after a
    server safety-round exhaustion. It refuses to label or save a frame unless
    the requested absolute VBlank was actually reached.
12. A seeded, trace-preserving input search discovered the first campaign
    path. Its minimized replay is:
    - tap the title and Adventure Mode
    - create and confirm mission file A
    - select file A again to start the campaign
    - skip the mission briefing
    - wait for the Celestial Archives gunship screen and confirm landing
    The native and reference runs reach the live first-person HUD at VBlank
    10859.
13. `tools/fuzz_mph_gameplay.py` records every action, absolute VBlank,
    screenshot, perceptual signature, RGB hash, and event-count snapshot.
    `scenarios/adventure_start.json` is the replayable minimized result.
14. All 15 matching native/oracle checkpoints in the minimized route are
    byte-identical across both physical screens: zero differing pixels and
    zero maximum channel delta, including the first gameplay frame.
15. Tier-3 coverage captured from that route yielded 567 unique ARM9
    call/indirect targets inside the immutable main image. Slice-resume roots,
    runtime RAM, and all reused overlay ranges were excluded. Adding those
    seeds expands the ARM9 bank to 7,115 functions; the identical replay cuts
    ARM9 Tier-3 entries from 64,619,845 to 57,525,780 (10.98%) and interpreted
    instructions from 3,866,962,843 to 3,638,379,652 (5.91%). All 13 action
    checkpoints retain identical event counts and RGB hashes. This does not
    yet establish a wall-clock speedup while generated code remains `-O0`.
16. The opening FMV slowdown was isolated with
    `tools/benchmark_mph_fmv.py`. Static-only FMV windows ran at 26-28 FPS:
    presentation stayed below 1 ms/frame while emulation rose to 34-37
    ms/frame and ARM9 executed roughly 620,000 Tier-3 instructions per frame.
    The hot code is the runtime ITCM mirror plus the active overlay near
    `0x02102D74`.
17. A deterministic VBlank-3000 ITCM+main-RAM capture is pinned by SHA-1
    `2f4a2ba36886fb9152781f5829dedfd4b836a73b`. The separate
    `mph_arm9_fmv_runtime` bank uses only call/indirect roots observed in the
    VBlank 2400-3000 delta and validates live guest bytes before dispatch.
    Seeding scheduler-resume PCs was rejected because it split hot loops into
    one-instruction functions and generated about 589,000 fallthrough
    dispatches/frame; the retained bank records about 5,400/frame.
18. The retained interactive run sustains 59.73-59.84 FPS from VBlank
    2400-4800 at 8.37-9.31 ms emulation/frame with zero audio underruns.
    Static-only and optimized runners have identical event, instruction, and
    cycle counts and zero differing pixels at VBlanks 2400, 3000, 3600, 4200,
    and 4800.

## Bring-up gates

- [x] Isolated framework worktree from latest `origin/main`
- [x] Exact AMHE0 ROM identity and header inventory
- [x] Independent game repository/scaffold
- [x] Public reverse-engineering resource audit and pinned MphRead checkout
- [x] Safe interpreter boot through the opening cinematic
- [x] Remove the cross-title SM64DS bank-registration assumption
- [x] Reach and capture the title screen
- [x] Observe one complete no-input attract loop
- [x] Compare the same attract checkpoints against the ndsref oracle
- [x] Compile and register AMHE0 main ARM9/ARM7 banks by ROM capability
- [ ] Capture remaining runtime ARM7 code and ARM9 overlay generations (the
      opening-FMV ARM9 generation is complete)
- [x] Generalize cartridge save type/size beyond SM64DS's 8 KiB EEPROM
- [x] Add deterministic Prime Hunters navigation and gameplay-entry scenario
- [ ] Add sustained traversal, combat, pause, death, and reload scenarios
- [x] Enable an exact-ROM upper-screen adaptive-wide bring-up baseline
- [x] Latch adaptive/direct presentation state to the published frame so
      boot logos and capture transitions do not flicker at high host scaling
- [ ] Audit Prime Hunters projection/culling/HUD across sustained gameplay
- [x] Add an MPH recomp-ui development launcher and enhancement toggle
- [x] Add top-window relative mouse aim, Mouse 1 fire, and persisted controls
- [x] Add portable Windows release launcher/mod packaging with a baked,
      content-validated FMV runtime bank

## Design constraints

- A title bank must never be selected by address alone. Registration is gated
  by exact cartridge identity, and mutable/overlay banks also validate live
  bytes.
- The runner also validates `[game].sha1` before applying title-owned config,
  so a Prime Hunters save-device declaration cannot silently affect another
  cartridge.
- Each overlay generation remains a separate content-validated bank. Prime
  Hunters reuses virtual ranges, so combining entry points from different
  overlay images would be unsound.
- The interpreter is the correctness oracle for uncompiled code within the
  native runtime; ndsref remains the independent machine oracle.
- Widescreen is a title-owned capability. Separate windows are safe as a host
  layout, but field-of-view, culling, HUD anchors, movies, and touch routing
  require Prime Hunters-specific proof.
- MphRead's recreation uses a 78-degree camera FOV and derives projection and
  frustum planes from the live output aspect ratio. That is a useful semantic
  reference, but it does not prove which AMHE0 guest structures and GX command
  sites must be patched. The host adaptive viewport is enabled as an explicit
  bring-up baseline, but it is not considered visually complete until those
  title-side behaviors pass sustained gameplay review.

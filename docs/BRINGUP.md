# Prime Hunters bring-up ledger

## Target and references

- Cartridge: USA revision 0 (`AMHE`, `MP HUNTERS`)
- ROM SHA-1: `90164d1ac127ee5f9815ea4ae7de798c7b5fc629`
- Framework base: `8c587032f602f07fde3540b05748df83ac355275`
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
5. The generated main banks contain 4,335 ARM9 functions and 16 ARM7
   functions. Exact-ROM-gated registration produces the same 700,000,000
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
- [ ] Capture content-validated runtime ARM7 code and ARM9 overlay generations
- [x] Generalize cartridge save type/size beyond SM64DS's 8 KiB EEPROM
- [ ] Add deterministic Prime Hunters navigation and attract scenarios
- [ ] Audit Prime Hunters projection/culling/HUD before enabling adaptive wide
- [ ] Add launcher/mod packaging after the runtime path is stable

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
  sites must be patched; adaptive output therefore remains disabled.

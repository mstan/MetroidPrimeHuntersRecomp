# Issue 44: campaign coverage and Gorea investigation

Investigation date: 2026-10-03. Beads: `beads-lqa.53`, framework
`beads-yjp.90`. Local work is on `issue44-coverage` in both repositories.

## Findings

[Issue 44](https://github.com/mstan/MetroidPrimeHuntersRecomp/issues/44)
contains three distinct observations. The graphics change and Omega loss
should not be treated as a single interpreter bug.

* **Missing campaign code is confirmed.** Native visits to Gorea exposed
  overlays 12 and 13, neither of which was declared in the build. Other
  campaign rooms also reached uncompiled code. The Arcterra Fault Line visit
  alone recorded 7,234,610 interpreted ARM9 instructions before this ingest.
* **Omega loss is a host shortcut bug.** In campaign mode, the native weapon
  menu locks the special slot when it contains Omega (weapon 8). PC hunter
  weapon shortcuts bypassed that guard. Live requests reproduced current
  weapon/special slot/ownership changing from `8/8/1` to `7/7/0`.
  Power Beam instead produced `0/8/1`, and requesting the locked slot again
  returned to `8/8/1`. The framework fix redirects campaign special-weapon
  shortcuts to Omega while that slot is locked. Beam and missiles keep their
  usual behavior, as does multiplayer. It does not restore an already-lost
  Omega slot. Native AMHE0 guard: `0x02026F58`; swap path: `0x0200C81C`.
* **The governor is a plausible graphics explanation, not a confirmed
  diagnosis of the reporter's machine.** Stage 2 sets internal and sample
  scale to 1 and disables HD 2D emission. Repeated engagement can set
  `stage2_held`, preventing automatic restoration. Extra interpreter work
  could trigger that policy. The issue has no governor history or renderer
  logs, so an Arc-specific problem cannot be inferred. A useful diagnostic
  is `--performance-governor off` (or `NDS_PERFORMANCE_GOVERNOR=off`) plus
  `governor_history` and `frontend_stats` around a transition.

The screen-layout comparison is a separate frontend request. This work does
not change layouts or the governor policy.

## Harvest scope and evidence

ROM: USA AMHE revision 0, SHA-1
`90164d1ac127ee5f9815ea4ae7de798c7b5fc629`.

All **66 campaign room IDs, 27 through 92**, were entered through the native
ship-landing path and reviewed in screenshots. The landing modifier came
from the [libretro DS cheat corpus](https://github.com/libretro/libretro-database/blob/master/cht/Nintendo%20-%20Nintendo%20DS/Metroid%20Prime%20-%20Hunters%20(USA).cht).
The harness writes the destination byte during landing, then stops doing so.
It grants health/ammunition and weapon ownership through bounded, logged data
writes, and uses native controls for shooting, charged shots, morph, scanning,
movement and jumping. It does not patch executable code. Rival hunters occupy
additional player slots; the arrival check accepts the native 1..4 range.

All eight ordinary weapon indices were observed across the sweep. Room 27's
initial visit only selected 0..3; room 92 received a dedicated Omega session
after its transmission was dismissed. Input attempts are not proof that each
action succeeded in every room. Dialogs and scan-complete states remain in
some evidence frames. Room entry also does not prove every exit, puzzle,
pickup, escape timer, enemy variant or multiplayer combination was covered.

Additional verified boss paths:

* Gorea 1 first form and transformation into the seal-sphere form. Setting
  the two native arm-severed flags let the game's own transition run.
* The bad-ending movie path, by setting the active second form's remaining
  phases to zero.
* Gorea 2 active combat, Omega equip/fire, the shortcut-loss reproduction,
  and the good-ending movie path through the native defeated predicate.

The attempted direct player-health-zero edit did not establish a verified
death/respawn path and is not counted as one.

Every process used `--no-save`; the original battery save was not changed.
Snapshots retain the normal ROM/build identity checks and are private.
The coverage manifest is cumulative across snapshot restores. The pre-build
harvest ended with:

| Measure | Result |
| --- | ---: |
| Captured code-page versions | 94 |
| Dropped / replaced pages | 0 / 0 |
| Captured bytes | 385,024 |
| Pages matching prepared ROM images | 81 |
| Other runtime page versions | 13 |
| ARM9 interpreter entries | 3,117,112 |
| ARM9 interpreted instructions | 49,700,886 |
| ARM7 interpreted instructions | 0 |

These are discovery totals from assisted traversal, not an FPS benchmark or
a percentage of the game's total possible coverage.

## Promotion and reproduction

The ingest preserves every previous `(address, mode)` seed. New content:

| Bank group | Added seeds |
| --- | ---: |
| New overlay 12 | 1,175 |
| New overlay 13 | 258 |
| Existing overlays | 1,208 |
| ARM9 main closure | 115 |

Thirteen content-validated runtime page banks cover captured generations
that the whole-page ROM matcher could not resolve. Their configs contain
addresses and identities; their byte images remain in ignored
`generated/capture/`. They must accompany a future private build-artifact
refresh before another machine can reproduce the complete build. No ROM,
snapshot, screenshot, capture payload or generated game source is committed.
The 13 images are hash-verified and bundled locally in
`scratch/issue44/private-bank-delta.zip`. A focused check added three further
entries to one of those banks and two to overlay 12; the totals above include
the latter two.

`tools/seed_overlay_from_coverage.py --kinds call,indirect --span-starts`
seeds contiguous interpreted-span starts only from pages that byte-match
that exact overlay. It checks both overlay and captured-page SHA-1. This is
essential because several bosses reuse the same virtual addresses.

Do **not** use the generic framework ingest's overlay-split TOMLs for this
capture: its session-wide `(cpu, page address)` target map can combine
different resident generations. The dedicated overlay seeder uses the
generation-bound page observations instead. The generic ingest supplies
the immutable main seeds and content-validated runtime banks here.

Typical local workflow, with a headless runner and real BIOS files:

```powershell
python tools/harvest_campaign_coverage.py --port 19944 `
  --rom 'Metroid Prime Hunters.nds' --out scratch/coverage-harvest `
  --checkpoint scratch/coverage-harvest/ship.state --make-checkpoint
python ../ndsrecomp/tools/ingest_coverage_manifests.py FINAL_MANIFEST `
  --out scratch/ingest --images generated/inputs `
  --rom-sha1 90164d1ac127ee5f9815ea4ae7de798c7b5fc629
python tools/seed_overlay_from_coverage.py --overlay-id 12 `
  --manifest FINAL_MANIFEST --out scratch/overlay-seeds/mph_arm9_ov012.toml `
  --kinds call,indirect --span-starts
# Repeat seeding for each resident overlay; add configs for newly declared ones.
python tools/merge_field_coverage.py --ingest scratch/ingest `
  --overlay-seeds scratch/overlay-seeds
```

The runner needs the new headless `state_save`, `state_load`, and `write_mem`
commands. Snapshot load uses normal core validation, including networking
eligibility. Memory writes go through the real bus/invalidation path and are
limited to 1..4096 bytes of canonical main RAM. Use forward slashes in debug
protocol paths. A `STOP` file in the harvest output stops between rooms.

Private local evidence is under `scratch/issue44/`: per-room visits and
screenshots, three reviewed contact sheets, bounded-write logs, Omega
reproduction records, boss snapshots, the final cumulative manifest, merge
reports and build logs. The sanitized room inventory is committed separately.

## Validation and remaining performance work

The Release build passed, and the bank inventory verified **266 banks**:
4 main/alias, 14 overlay, 4 named runtime and 244 captured-coverage banks.
The shortcut regression test passed, including all local slots, all special
hotkeys, Beam/missile return paths and unchanged multiplayer behavior.
Savestate, network savestate guard, video savestate and dispatch lookup tests
passed. The new debug protocol check passed 13 cases; the seeder regression
checks passed both tests, including same-address foreign pages and bad hashes.

The first post-promotion checks recorded:

| Active segment | VBlanks | ARM9 interpreted instructions | ARM7 |
| --- | ---: | ---: | ---: |
| Gorea first form | 388 | 4,284 | 0 |
| Gorea transformed form | 294 | 1,029 | 0 |
| Gorea 2 / Omega | 4,969 | 4,455 | 0 |

The residuals identified five further entries in known page generations,
which were promoted without adding new byte images. The final coverage-only
check returned **zero ARM9 and ARM7 interpreter entries/instructions** over
388 first-form, 294 transformed-form and 417 Omega VBlanks: **1,099 total**.
Screenshots and native gameplay state remained valid. This is evidence for
those checked states, not every possible boss action. The completed performance
sample remains the one shown above; no repeated performance leg was used.

Forced interpreter execution also stayed in active Gorea 2 gameplay for
42 VBlanks (3,522,579 ARM9 and 1,036,330 ARM7 instructions), with Omega still
equipped. This is a floor smoke check, not exhaustive equivalence testing.

The framework's `docs/mph-issue44-performance.md` contains the full assessment.
In the Omega sample, generated bodies account for about 32% of emulation
thread self samples, cycle helpers 11%, dispatch 9%, GPU3D 11%, and bus/memory
6%. Interpreter work is negligible there. The next candidates are cycle and
resume-dispatch overhead, DMA/GXFIFO batching, then a guarded HLE pilot for
measured fixed-point math routines. HD rendering on the reporter's Arc GPU
remains unmeasured. No new HLE routine or governor behavior was introduced.

No routine gameplay/performance matrix or release publication is part of this
task. The sampled emulation-time estimator overstates wall time by 12.5%; the
assessment states that limitation and does not present the estimate as a gate.

Sanitized counters and artifact identity are in
[`coverage/issue44-validation.json`](../coverage/issue44-validation.json).
The tested executable was built from the working changes with build ID
`f6f1367-dirty`; its SHA-256 is
`8de1f399e1a2c898c50e4078120912fbc104908178daf8b1a535ef47232dcc68`.
No GitHub response, release, or private-artifact upload was performed.

# Handoff: Metroid Prime Hunters Local Play Across Two Systems

## Goal

Implement and validate non-WFC Metroid Prime Hunters local play with two
headless/interactive runner instances. Success is:

1. Instance A hosts a local Multi-Card game.
2. Instance B discovers and joins A through local wireless, not Nintendo WFC.
3. Both advance into a match.
4. Both can move around in-game while still connected.
5. Evidence is captured from screenshots, logs, debug queries, and any local
   wireless counters/captures added during the work.

Treat this as the local-play equivalent of the prior WFC validation: menu
navigation is part of acceptance, not just backend packet smoke tests.

## Repos And Commits To Review

Active title repo:

- `F:\Projects\ndsrecomp\metroidprimehuntersrecomp-live-overlay-provider`
- Current branch: `codex/watchdog-fix-20260817`
- Current HEAD reviewed for this handoff: `e88dc47`

Important MPH commits:

- `ab64ad8` - offline multiplayer route and overlay coverage loop.
- `638f6b3` - documented real MPH bot-match start procedure.
- `8d93cdf` - active combat in the MPH bot route.
- `1932f62` - MPH friend matches across local WFC peer routing.
- `938a5aa` - WFC full P2P payload capture and post-join RAM dumps.
- `e88dc47` - two free-running visible instances for a human-driven WFC match.

Shared framework:

- `F:\Projects\ndsrecomp\ndsrecomp`
- MPH `game.toml` pins framework commit `e9b530a`.
- `e9b530a` contains local wireless support because `9360290` is an ancestor.
- `9360290` is the key framework commit: `Add experimental local wireless transport`.

MKDS local-play reference:

- `F:\Projects\ndsrecomp\mariokartdsrecomp-local-multiplayer`
- `0d4dd0a` documents experimental same-machine local wireless multiplayer.
- `1f0d1d9` documents the prior WFC multiplayer acceptance pattern.

Existing committed handoffs worth reading:

- `Handoff_For_Fable.md`
- `Handoff_For_Fable_Quickstart.md`

Those are WFC-oriented and partly stale on latest commit IDs, but they capture
the validation style and the failure mode that led to free-running instances.

## Current Framework Capability

Local wireless is implemented behind melonDS `Platform::MP_*` hooks in
`ndsrecomp/runner/src/wifi_net.cpp`.

The current implementation is:

- Opt-in with `--local-wireless on`.
- Keyed by `--instance-index N`.
- Bound to localhost UDP at `base_port + instance_index`.
- Default base port: `26710`.
- Valid instance range for local wireless: `0..15`.
- Windows-only in the reviewed commit.
- Same-machine only as written. It binds and sends to `127.0.0.1`.

This matters because the user request says "going over lan". The existing
transport is not a two-host LAN transport yet. Recommended staging:

1. First reproduce two local MPH instances on the same machine using the
   existing localhost transport.
2. Then extend the transport for two machines by making bind/listen address and
   peer target addresses configurable, or by adding an explicit LAN mode.
3. Validate the same menu path and in-game movement on both same-machine and
   two-machine setups before claiming LAN.

Do not confuse this with WFC peer routing. WFC uses infrastructure networking,
Slirp/pcap, WFC provider selection, friend codes, and local WFC peer bridge
ports. Local play should use DS local wireless and should not require Wiimmfi,
friend codes, DNS, TCP, TLS, or Internet reachability.

## Runner Command Shape

Verify the runner first:

```powershell
F:\Projects\ndsrecomp\ndsrecomp\runner\build-mph-release\nds_runner.exe --help
```

The help must include:

```text
--local-wireless on|off
--local-wireless-port 1024..65520
--instance-index 0..255
```

For non-WFC local play, use:

```text
--network off --wfc off --local-wireless on --instance-index N
```

`--network off` is intentional: the Wi-Fi device is still constructed, but no
host Internet/backend is attached. Local wireless is configured independently.

Minimal launch shape per instance:

```powershell
F:\Projects\ndsrecomp\ndsrecomp\runner\build-mph-release\nds_runner.exe `
  F:\Projects\ndsrecomp\ndsrecomp\bios `
  --interactive `
  --port 20710 `
  --rom F:\Projects\ndsrecomp\metroidprimehuntersrecomp-live-overlay-provider\Metroid Prime Hunters.nds `
  --config F:\Projects\ndsrecomp\metroidprimehuntersrecomp-live-overlay-provider\game.toml `
  --save-path F:\Projects\ndsrecomp\metroidprimehuntersrecomp-live-overlay-provider\scratch\local-play\profiles\A.sav `
  --firmware-state-path F:\Projects\ndsrecomp\metroidprimehuntersrecomp-live-overlay-provider\scratch\local-play\profiles\A.firmware.bin `
  --startup-mode automatic `
  --boot direct `
  --screen-layout stacked `
  --mph-prime-controls off `
  --relative-mouse-touch off `
  --network off `
  --wfc off `
  --local-wireless on `
  --local-wireless-port 26710 `
  --instance-index 0
```

Launch B with a different debug port, save, firmware-state path, and
`--instance-index 1`.

Expected stderr evidence:

```text
[local_mp] configured instance=0 base_port=26710
[local_mp] enabled instance=0 port=26710
```

and for B:

```text
[local_mp] configured instance=1 base_port=26710
[local_mp] enabled instance=1 port=26711
```

`--instance-index` also perturbs the guest MAC bytes for multi-instance Wi-Fi
identity. Keep one unique save/firmware-state path per instance.

## Existing Menu Route Baseline

Use the existing local/offline multiplayer scenarios as the route baseline:

- `scenarios/multiplayer_probe.json`
- `scenarios/mp_start_probe.json`
- `scenarios/mp_bots_start.json`
- `scenarios/multiplayer_battle_bots.json`

Known coordinates from those scenarios:

- Main menu `MULTIPLAYER`: touch `(160, 92)`.
- Nickname dialog may require two `A` presses on fresh profiles.
- Mode row:
  - `SINGLE-CARD`: `(50, 80)`
  - `MULTI-CARD`: `(128, 80)`
  - `WI-FI`: `(205, 80)`
- Multi-Card menu:
  - `CREATE GAME`: `(50, 80)`
  - `JOIN GAME`: likely the sibling row/button at `(128, 80)`; verify visually.
- Game mode:
  - `BATTLE`: `(50, 62)`
- Arena/settings confirm: `(212, 172)` or `(222, 173)` depending screen capture.
- Hunter select:
  - Samus portrait: `(27, 132)`.
- Bot route start/control coordinates that may help identify the room screen:
  - slot/bot toggles around `(97, 139)`, `(154, 61)`, `(212, 139)`
  - start disc/button: `(195, 35)` in `multiplayer_battle_bots.json`
  - WFC friend-match host start disc candidate: `(240, 149)`

Do not assume coordinates for guest join/ready are correct until screenshots
prove them. Capture every screen transition and add a local-play screen
classifier rather than relying only on frame delays.

## Important Lesson From WFC Validation

`tools/run_mph_friend_match.py` drove two instances in lockstep and was useful
for deterministic screenshots, but it failed for time-sensitive room windows:
while one debug server was being driven, the other instance was paused and not
answering its peer. `tools/launch_wifi_pair.ps1` fixed that for WFC by launching
both instances in `--interactive` mode so they free-run like real consoles.

For local play, prefer the free-running model:

- Start both processes in `--interactive`.
- Use the play-mode debug surface for live queries and input injection.
- Sample by wall time.
- Avoid `run_to_event`, `run_cycles`, and `run_rounds` in interactive mode; the
  debug server rejects execution-driving commands while the frontend owns
  execution.
- Allowed live commands include `ping`, `event_counts`, `framebuffer`,
  `net_state`, `net_progress`, `net_ring_dump`, `touch`, and `keys`.

If automation needs precise holds, use short timed key/touch injection and
wall-clock sleeps, not long frame-advance commands.

## Implementation Plan For Ox Alpha

1. Create a title-local launcher script, likely
   `tools/launch_local_play_pair.ps1`, based on `tools/launch_wifi_pair.ps1`.
   Differences from WFC launcher:
   - use `--network off`
   - use `--wfc off`
   - add `--local-wireless on`
   - add `--local-wireless-port <base>`
   - keep unique debug ports, saves, firmware state paths, and instance indexes
   - check `base_port + instance_index` UDP ports for conflicts, not WFC bridge
     ports `27610 + index`

2. Create a Python driver/validator, likely `tools/run_mph_local_play.py`.
   Reuse helper patterns from:
   - `tools/capture_mph_checkpoints.py`
   - `tools/fuzz_mph_gameplay.py`
   - `tools/run_mph_friend_match.py`
   - `tools/mph_screens.py`

3. Add local-play screen classifiers to `tools/mph_screens.py` or a separate
   `tools/mph_local_screens.py`.
   Start with fixed-box/color classifiers, as WFC did. Needed states:
   - title/main menu
   - nickname/name confirm if a fresh profile triggers it
   - multiplayer mode select
   - multi-card create/join menu
   - host room published/waiting
   - guest searching/list of games
   - guest selected/connecting
   - select hunter/ready state
   - match loading
   - in-game HUD/combat

4. Drive the host:
   - Multiplayer
   - Multi-Card
   - Create Game
   - Battle
   - Confirm arena/settings
   - Reach the room or hunter-select wait state

5. Drive the guest:
   - Multiplayer
   - Multi-Card
   - Join Game
   - Wait until the host appears
   - Select host row and confirm
   - Pick Samus
   - Ready/confirm

6. Finish host startup:
   - Once the guest is visible/ready, use the host start control.
   - Keep both instances executing while doing this.

7. In-game movement validation:
   - On both instances, take a pre-move screenshot.
   - Inject movement on A, for example hold `up` or `w` depending the debug key
     model being used, then release.
   - Inject movement/turn on B.
   - Take post-move screenshots from both.
   - Record `event_counts` before/after to prove both sessions kept advancing.
   - Save a summary JSON with final screen classifications and screenshot names.

8. If local discovery fails, add observability before guessing menu fixes:
   - Local MP currently does not expose dedicated counters in `net_progress`.
   - Add a small debug-visible counter block for local MP send/recv by type:
     packet, cmd, reply, ack, recv-host, recv-replies.
   - Log sender instance, local port, target port, type, length, and dropped
     queue count.
   - Keep payload bytes out of always-on logs unless an explicit capture option
     is added.

9. For real LAN/two-machine support, extend the transport deliberately:
   - Current code binds `127.0.0.1` and sends to `127.0.0.1`.
   - Add config/CLI for bind address and peers, for example:
     `--local-wireless-bind 0.0.0.0`
     `--local-wireless-peer <ip>:<port>`
   - Keep same-machine defaults unchanged.
   - Validate firewall behavior and make failures explicit in stderr.
   - Do not call it LAN-supported until two physical hosts have completed the
     same menu-to-movement validation.

## Suggested Commands

Build from the title repo if needed:

```powershell
cd F:\Projects\ndsrecomp\metroidprimehuntersrecomp-live-overlay-provider
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools\build-windows.ps1 -Version local-play-dev
```

Launch same-machine local pair manually:

```powershell
cd F:\Projects\ndsrecomp\metroidprimehuntersrecomp-live-overlay-provider
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools\launch_local_play_pair.ps1 `
  -ProfileDir scratch\local-play\profiles `
  -BasePort 20710 `
  -LocalWirelessPort 26710 `
  -BaseInstance 0
```

Run automated validation once the navigator exists:

```powershell
py -3 tools\run_mph_local_play.py `
  --runner F:\Projects\ndsrecomp\ndsrecomp\runner\build-mph-release\nds_runner.exe `
  --bios F:\Projects\ndsrecomp\ndsrecomp\bios `
  --rom "F:\Projects\ndsrecomp\metroidprimehuntersrecomp-live-overlay-provider\Metroid Prime Hunters.nds" `
  --config F:\Projects\ndsrecomp\metroidprimehuntersrecomp-live-overlay-provider\game.toml `
  --out scratch\local-play\run01 `
  --profile-dir scratch\local-play\profiles `
  --base-port 20710 `
  --local-wireless-port 26710 `
  --instances 2
```

## Evidence To Preserve

Keep output under ignored `scratch/local-play/<run>/`.

Each accepted run should contain:

- `summary.json`
- per-instance `runner.stdout.log`
- per-instance `runner.stderr.log`
- per-instance screenshots for every menu milestone
- final in-game screenshots before and after movement
- local MP counter snapshots if added
- optional main RAM dumps only if debugging a stalled connected state

Do not commit ROMs, BIOS files, firmware dumps, saves, generated banks, packet
payload captures, `.gpr`, or `.rep` files.

## Acceptance Criteria

Same-machine acceptance:

- Both logs show local MP configured and bound on distinct ports.
- No WFC path is used:
  - launch args include `--network off --wfc off`
  - no DNS/TCP/TLS success is required or relevant
- Screenshots prove:
  - A hosted a Multi-Card local game
  - B found and joined A
  - both reached hunter/ready flow
  - both reached in-game HUD/combat
  - both moved after match start
- Summary JSON reports both instances still advancing after movement.

Two-machine LAN acceptance:

- Same as above, but across two physical hosts.
- Logs show non-loopback bind/peer configuration.
- Host firewall/NAT assumptions are documented.
- Packet/counter evidence shows bidirectional local MP traffic between host IPs.

Do not close the Beads task until at least same-machine acceptance is complete.
Do not claim LAN acceptance until two-host validation is complete.


# Handoff: Metroid Prime Hunters Wi‑Fi Probe / Connection Stuck Work

## Current state
- Active repo: `F:\Projects\ndsrecomp\metroidprimehuntersrecomp-live-overlay-provider`
- Active branch pushed: `codex/watchdog-fix-20260817`
- Latest commit: `4a63af6`
  - Message: **Harden MPH Wi-Fi probe summary and runner help parsing**
  - Pushed to origin.

## What was done
- Previously implemented scripts in this repo to automate MPH WFC flows:
  - `tools/probe_mph_wfc.py` (setup/search/friends/finding game automation)
  - `tools/probe_nodump_wfc_auth.py`
  - `tools/run_mph_wfc_instances.py`
- In `4a63af6` fixed robustness issues in `probe_mph_wfc.py`:
  - `--help` output parsing in `_runner_help_mentions` now captures `stderr` too.
  - Summary path no longer crashes when `counts` entries are missing.

## Most important files touched
- `tools/probe_mph_wfc.py`

## Latest test outcomes (important)
- Multiple scripted runs of `probe_mph_wfc.py` for:
  - `--flow setup`
  - `--flow search-game`
  - `--flow friends-rivals`
- Runner: `F:\Projects\ndsrecomp\ndsrecomp\runner\build-mph-release\nds_runner.exe`
- Backend: `--network-backend slirp`, `--wfc-provider wiimmfi`

Observed result:
- Runs **complete** through menu flow but report as `*_no_network`:
  - `dhcp = 0`
  - `dns_query = 0`
  - `tcp_open = 0`
  - `tls_record = 0`
  - `backend_error = 0`
  - `backend_drop = 0`
- In all failing scripted runs, `net_state` still reports:
  - `wifi_attached: True`, `network_enabled: True`
  - `backend: slirp`, `live_backend_active: True`, `worker_active: True`
  - `wfc_dns_ip` resolved to `178.62.43.212`.

No successful `authenticated`/network event capture was observed in probe outputs.

## Key evidence files
- Run outputs under:
  - `F:\Projects\ndsrecomp\scratch\wifi-stability\run01`
  - `...\run05`, `run07`, `run08`, `run12`
- Prior successful-looking manual-auth artifacts may still be in:
  - `F:\Projects\ndsrecomp\metroidprimehuntersrecomp\scratch\nodump-wfc-20260814\`

## Commands used
- Test command pattern:
  ```powershell
  py -3 tools/probe_mph_wfc.py `
    --runner F:\Projects\ndsrecomp\ndsrecomp\runner\build-mph-release\nds_runner.exe `
    --rom F:\Projects\ndsrecomp\metroidprimehuntersrecomp\Metroid Prime Hunters.nds `
    --config F:\Projects\ndsrecomp\metroidprimehuntersrecomp\game.toml `
    --out <outdir> `
    --save-path F:\Projects\ndsrecomp\metroidprimehuntersrecomp\scratch\nodump-wfc-20260814\nodump.sav `
    --port 199xx --instance-index 1 `
    --flow <setup|search-game|friends-rivals> `
    --network-backend slirp --wfc-provider wiimmfi `
    --connection-timeout 35 --connection-stall-s 10 --startup-mode automatic
  ```
- `--no-dumps` mode tested too (with default profile path generation).

## Known probable blocker to continue
- The probe automation reaches menus and confirms backend state, but no actual WFC net events are recorded.
- This suggests the game may be blocked before issuing any socket/dns/tcp activity in this scripted input path, likely one of:
  1) missing/incorrect interaction path in automated taps for this specific session state,
  2) stale profile/save/firmware state assumptions differing from manual flow,
  3) no network events emitted until a later in-flow step that automation exits too soon.

## Suggested continuation plan for Fable
1. Replay same session in manual UI and capture exact input deltas with screenshots from a known-working run.
2. Confirm `probe_nodump_wfc_auth.py`/`probe_mph_wfc.py` tap sequence matches that exact flow.
3. Dump `net_state` + `net_progress` + ring every step, especially right when entering test/confirm dialogs.
4. Compare successful manual save/firmware against script-generated ones:
   - try using the exact save/firmware from manual connect as `--save-path` and `--firmware-state-path` inputs
5. Add explicit ring query for `dhcp` before/after each screen transition and fail-fast only if no possible state-change evidence for N+ seconds.
6. If automation still gets no events, validate whether game is waiting in a modal/UI state by adding stronger image-based screen-state checks.

## Note
- There is an untracked `bios/` folder in this worktree from local runs. It is not part of this commit.
- Latest run logs include `runner.stderr.log` showing backend initialized cleanly, no runtime errors.

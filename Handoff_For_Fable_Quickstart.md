# Handoff for Fable (NDsRecomp/MPH Wi-Fi Probe Continuation)

## Branch and commits
- Repo: `F:\Projects\ndsrecomp\metroidprimehuntersrecomp-live-overlay-provider`
- Branch: `codex/watchdog-fix-20260817`
- Pushed to origin: yes (`origin/codex/watchdog-fix-20260817`)
- Commits to review:
  - `c1b6904` Integrate live overlay sharding into MPH launcher
  - `8d93cdf` Enter active combat in MPH bot route
  - `10b0674` checkpoint: pre-connection-watchdog change
  - `50c0aea` Use default profile paths and non-zero instance index for no-dumps probes
  - `8eea99e` Use net_progress telemetry in MPH WFC setup probes
  - `167a160` Handle legacy runner CLI when probing no-dumps WFC setup
  - `4a63af6` Harden MPH Wi-Fi probe summary and runner help parsing
  - `1a33eb0` Add handoff notes for Fable continuation

## Working tree state
- `git status` had only: `?? bios/` (untracked from local runs, not part of commit)

## Current blocking symptom
- MPH scripted flow reaches menus but no backend activity for network handshake.
- Repeated statuses:
  - `F:\Projects\ndsrecomp\scratch\wifi-stability\run08\summary.json` ? `search_game_no_network`
  - `F:\Projects\ndsrecomp\scratch\wifi-stability\run12\summary.json` ? `friends_rivals_no_network`
- `net_state` in logs still shows:
  - `wifi_attached=true`, `network_enabled=true`
  - `backend=slirp`, `wfc_provider=wiimmfi`, `live_backend_active=true`, `worker_active=true`
  - `wfc_dns_ip=178.62.43.212`
- Ring/summary counters remain zero for DHCP/DNS/TCP/TLS/UDP in those runs.

## Where to start next (highest leverage)
1. Reproduce from a clean state with both saves:
   - `F:\Projects\ndsrecomp\metroidprimehuntersrecomp\scratch\nodump-wfc-20260814\nodump.sav`
   - compare with manually successful save path if available.
2. Run probe command from repo with saved `out` and inspect:
   - `summary.json`, `net_state.json`, `net_progress.json`, screenshots + runner stderr/stdout.
3. Verify `probe_mph_wfc.py` transition sequencing at:
   - `nickname-dialog` -> `multiplayer-menu` -> `wfc-menu` -> `friends-rivals` and `friends-rivals` timed waits.
4. Check for any change in UI state that should trigger activity before exit from `friends-rivals`.

## Key command used in this session
```powershell
py -3 tools/probe_mph_wfc.py `
  --runner F:\Projects\ndsrecomp\ndsrecomp\runner\build-mph-release\nds_runner.exe `
  --rom F:\Projects\ndsrecomp\metroidprimehuntersrecomp\Metroid Prime Hunters.nds `
  --config F:\Projects\ndsrecomp\metroidprimehuntersrecomp\game.toml `
  --out <outdir> `
  --save-path F:\Projects\ndsrecomp\metroidprimehuntersrecomp\scratch\nodump-wfc-20260814\nodump.sav `
  --startup-mode automatic `
  --port 199XX --instance-index 1 `
  --flow friends-rivals `
  --network-backend slirp --wfc-provider wiimmfi `
  --connection-timeout 35 --connection-stall-s 10
```

## Notes
- `tools/probe_mph_wfc.py` fix in `4a63af6`:
  - captures runner `--help` stderr path as well as stdout
  - summary parsing no longer throws when keys are missing
- This is a handoff-only request; no new code changes since `4a63af6` in this handoff path.
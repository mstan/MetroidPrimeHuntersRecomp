<#
Launch free-running Metroid Prime Hunters instances for same-machine local
wireless (Multi-Card) play -- the non-WFC path. No slirp, no Wiimmfi, no
friend codes, no DNS/TCP/TLS: the Wi-Fi device exists but no host network
backend is attached (--network off --wfc off), and DS local wireless frames
travel over localhost UDP between the instances.

Why free-running: tools\run_mph_friend_match.py drove two WFC instances in
frame lockstep and each console was paused while the other was driven, so
time-sensitive room windows collapsed (beads-lqa.6). Local play has the same
shape of problem -- a host advertising a Multi-Card game will not answer a
guest that is not executing. These instances FREE-RUN in --interactive mode,
exactly like real consoles; drive them by hand or with
tools\run_mph_local_play.py, which injects input through each instance's own
debug port without ever pausing execution.

Each instance binds 127.0.0.1:<LocalWirelessPort + instance-index> and fans
every MP frame out to the other ports in that block, so the whole block must
be free. Each instance also needs its own cartridge save and its own console
identity (firmware state); fresh profiles are fine, the in-game nickname
prompt just needs confirming on first entry.

Usage:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    tools\launch_local_play_pair.ps1 -ProfileDir scratch\local-play\profiles

Then: instance A hosts (MULTIPLAYER -> MULTI-CARD -> CREATE GAME -> ...),
instance B joins (MULTIPLAYER -> MULTI-CARD -> JOIN GAME).
#>
param(
    [Parameter(Mandatory = $true)][string]$ProfileDir,
    [string]$Runner = 'F:\Projects\ndsrecomp\ndsrecomp\runner\build-mph-release\nds_runner.exe',
    [string]$Bios   = 'F:\Projects\ndsrecomp\ndsrecomp\bios',
    # The ROM lives with the base title checkout, not this tooling branch.
    [string]$Rom    = 'F:\Projects\ndsrecomp\metroidprimehuntersrecomp\Metroid Prime Hunters.nds',
    [string]$Config = 'game.toml',
    # Names of the two profiles; <Name>.sav and <Name>.firmware.bin are
    # created here on first launch if missing.
    [string[]]$Names = @('A', 'B'),
    [int]$BasePort = 20710,
    # Base of the local-wireless UDP block: instance N holds port
    # <LocalWirelessPort> + N. Default matches the runner's built-in default.
    [int]$LocalWirelessPort = 26710,
    # Valid local-wireless instance range is 0..15. The index perturbs the
    # guest MAC bytes for multi-instance identity and offsets the bound port.
    [int]$BaseInstance = 0,
    # Prime mouse-look is off by default: a plain absolute stylus is what the
    # multiplayer menus need. Pass -PrimeControls to validate the shipping
    # control scheme instead.
    [switch]$PrimeControls
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $Runner)) { throw "runner not found: $Runner" }
if (-not (Test-Path $Bios))   { throw "BIOS dir not found: $Bios" }
if (-not (Test-Path $Rom))    { throw "ROM not found: $Rom" }
if (-not (Test-Path $Config)) { throw "config not found: $Config" }
New-Item -ItemType Directory -Force $ProfileDir | Out-Null

$mpPorts = 0..($Names.Count - 1) | ForEach-Object { $LocalWirelessPort + $BaseInstance + $_ }
$busy = Get-NetUDPEndpoint -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in $mpPorts }
if ($busy) {
    throw ("local wireless UDP port(s) {0} already bound by pid(s) {1}; " +
           "close the other session first" -f ($mpPorts -join ','),
           (($busy.OwningProcess | Sort-Object -Unique) -join ','))
}

$procs = @()
for ($i = 0; $i -lt $Names.Count; $i++) {
    $name     = $Names[$i]
    $port     = $BasePort + $i
    $instance = $BaseInstance + $i
    $out      = Join-Path $ProfileDir "session-$name"
    New-Item -ItemType Directory -Force $out | Out-Null

    $a = @(
        "`"$Bios`"", '--interactive',
        '--port', $port,
        '--rom', "`"$((Resolve-Path $Rom).Path)`"",
        '--config', "`"$((Resolve-Path $Config).Path)`"",
        '--save-path', "`"$ProfileDir\$name.sav`"",
        '--firmware-state-path', "`"$ProfileDir\$name.firmware.bin`"",
        '--startup-mode', 'automatic',
        '--boot', 'direct',
        '--screen-layout', 'stacked',
        '--mph-prime-controls', $(if ($PrimeControls) { 'on' } else { 'off' }),
        '--relative-mouse-touch', $(if ($PrimeControls) { 'on' } else { 'off' }),
        # No host network backend at all: local wireless is independent.
        '--network', 'off',
        '--wfc', 'off',
        '--local-wireless', 'on',
        '--local-wireless-port', $LocalWirelessPort,
        '--instance-index', $instance
    ) -join ' '

    $p = Start-Process -FilePath $Runner -ArgumentList $a `
        -WorkingDirectory (Split-Path $Runner) `
        -RedirectStandardOutput "$out\runner.stdout.log" `
        -RedirectStandardError  "$out\runner.stderr.log" -PassThru
    $procs += $p
    Write-Host ("instance {0}: pid {1}  debug port {2}  local MP udp {3}" -f `
        $name, $p.Id, $port, ($LocalWirelessPort + $instance))
    Start-Sleep -Seconds 3
}

Write-Host ''
Write-Host ("{0} hosts, {1} joins." -f $Names[0], ($Names[1..($Names.Count - 1)] -join '/'))
Write-Host ("Check each stderr log for '[local_mp] enabled instance=N port={0}+N'." -f $LocalWirelessPort)

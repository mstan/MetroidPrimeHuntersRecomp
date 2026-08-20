<#
Launch two visible, free-running Metroid Prime Hunters instances for a
human-driven Nintendo WFC (Wiimmfi) friend match.

Why this exists: tools\run_mph_friend_match.py drives two instances in frame
lockstep, which means each console is paused while the other is driven. That
is fine for observing menus, but it cannot ready up inside the host's room
hold window -- the host drops an un-readied guest and the guest reports "THE
HOST HAS ABANDONED THIS GAME" (beads-lqa.6). These instances instead FREE-RUN
in --interactive mode, exactly like two real consoles, and a human drives
them. That is how the first end-to-end match was completed and captured.

Each instance keeps its debug server up, so the session can be observed
(framebuffer, net_progress, net rings) WITHOUT pausing either side, and each
writes a full packet capture for later protocol analysis.

Profiles: each instance needs its own cartridge save and its own console
identity (firmware state). They must travel as a pair -- a save carrying a
WFC ID alongside a different console identity produces the in-game "the WFC
ID from the Nintendo DS and the Game Card do not match" refusal.

Usage:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    tools\launch_wifi_pair.ps1 -ProfileDir F:\path\to\profiles
#>
param(
    [Parameter(Mandatory = $true)][string]$ProfileDir,
    [string]$Runner = 'F:\Projects\ndsrecomp\ndsrecomp\runner\build-mph-release\nds_runner.exe',
    [string]$Bios   = 'F:\Projects\ndsrecomp\ndsrecomp\bios',
    [string]$Rom    = 'Metroid Prime Hunters.nds',
    [string]$Config = 'game.toml',
    # Names of the two profiles; <Name>.sav and <Name>.firmware.bin must exist
    # in -ProfileDir, or be creatable there for a fresh pair.
    [string[]]$Names = @('A', 'B'),
    [int]$BasePort = 20621,
    # Instance index drives the slirp subnet (10.64.<index>.16) and the local
    # WFC peer-bridge port (27610 + index). Index 0 is deliberately avoided so
    # a run cannot collide with a launcher-started session.
    [int]$BaseInstance = 1,
    [string]$WfcProvider = 'wiimmfi',
    # Prime mouse-look is off by default: a plain absolute stylus is what the
    # WFC menus, friend roster and hunter select need. Pass -PrimeControls to
    # validate the shipping control scheme instead.
    [switch]$PrimeControls
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $Runner)) { throw "runner not found: $Runner" }
if (-not (Test-Path $Rom))    { throw "ROM not found: $Rom" }
if (-not (Test-Path $Config)) { throw "config not found: $Config" }
New-Item -ItemType Directory -Force $ProfileDir | Out-Null

$bridgePorts = 0..($Names.Count - 1) | ForEach-Object { 27610 + $BaseInstance + $_ }
$busy = Get-NetUDPEndpoint -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in $bridgePorts }
if ($busy) {
    throw ("local WFC peer-bridge port(s) {0} already bound by pid(s) {1}; " +
           "close the other session first" -f ($bridgePorts -join ','),
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
        '--network', 'on', '--network-backend', 'slirp',
        '--wfc', 'on', '--wfc-provider', $WfcProvider,
        '--instance-index', $instance,
        '--net-capture-out', "`"$out\net-capture.ndscap`""
    ) -join ' '

    $p = Start-Process -FilePath $Runner -ArgumentList $a `
        -WorkingDirectory (Split-Path $Runner) `
        -RedirectStandardOutput "$out\runner.stdout.log" `
        -RedirectStandardError  "$out\runner.stderr.log" -PassThru
    $procs += $p
    Write-Host ("instance {0}: pid {1}  debug port {2}  subnet 10.64.{3}.16  bridge {4}" -f `
        $name, $p.Id, $port, $instance, (27610 + $instance))
    Start-Sleep -Seconds 3
}

Write-Host ''
Write-Host ("{0} hosts, {1} joins." -f $Names[0], ($Names[1..($Names.Count - 1)] -join '/'))
Write-Host 'Once the guest is in the room it shows on the host as NOT READY:'
Write-Host 'pick a hunter promptly -- the host drops an un-readied guest.'

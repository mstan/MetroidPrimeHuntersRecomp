<#
Run the scripted MPH training workload against an instrumented (profile-
generate) runner so GCC writes .gcda profile data for the profile-use build.

This script performs no build steps. It expects an already-built runner whose
build directory was configured with -DNDS_PGO_MODE=GENERATE, and it leaves the
profile data where GCC puts it: beside the object files, inside that same
build directory. The profile-use build must reuse that directory (see
ndsrecomp docs/host_optimization_strategy.md, knob C2).

Training is entirely scripted. Routes come from tools\measure_mph_scenario.py,
which drives the runner over the debug TCP surface with fixed touch/key/wait
action lists and fixed guest landmarks, so no human input is involved and the
same route runs identically every time.

The route harness shuts each repetition down with the runner's frontend_exit
command and waits for the process, which is what makes profile data appear at
all: on Windows, terminating the process bypasses GCC's profile flush and the
run contributes nothing.

Usage:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    tools\pgo_train.ps1 -RunnerBuildDir ..\ndsrecomp\runner\build-mph-pgo
#>
param(
  [string]$RunnerBuildDir = '..\ndsrecomp\runner\build-mph-pgo',
  [string]$NdsrecompRoot = '..\ndsrecomp',
  [string]$PythonExe = 'py',
  [string]$Rom = '',
  [string]$Bios = '',
  # One repetition per route is enough to train: the profile records which
  # branches and call edges are hot, and a second identical pass only scales
  # every counter by the same factor.
  [int]$Repetitions = 1,
  # Keep clear of 19842/19843 (oracle), 19870 (the measurement default) and
  # 27610 (the launcher bridge); this machine runs concurrent sessions.
  [int]$Port = 19881,
  [string[]]$Routes = @('attract', 'adventure')
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Resolve-FromRoot([string]$path) {
  if ([IO.Path]::IsPathRooted($path)) { return [IO.Path]::GetFullPath($path) }
  return [IO.Path]::GetFullPath((Join-Path $root $path))
}

$runnerBuild = Resolve-FromRoot $RunnerBuildDir
$frameworkRoot = Resolve-FromRoot $NdsrecompRoot
$runnerExe = Join-Path $runnerBuild 'nds_runner.exe'

if (-not (Test-Path -LiteralPath $runnerExe)) {
  throw "Instrumented runner not found: $runnerExe. Configure that build directory with -DNDS_PGO_MODE=GENERATE and build it first."
}

# Refuse to train a runner that is not actually instrumented. Without this the
# routes run happily, write no profile data, and the profile-use build either
# fails late or silently produces an untrained binary.
$cacheFile = Join-Path $runnerBuild 'CMakeCache.txt'
if (-not (Test-Path -LiteralPath $cacheFile)) {
  throw "No CMakeCache.txt in $runnerBuild - that is not a configured build directory."
}
$pgoMode = (Select-String -LiteralPath $cacheFile -Pattern '^NDS_PGO_MODE:' |
  Select-Object -First 1).Line
if ($pgoMode -notmatch 'GENERATE') {
  throw "Build directory $runnerBuild is not instrumented (found '$pgoMode'). Reconfigure it with -DNDS_PGO_MODE=GENERATE."
}

# Profiles accumulate across routes: GCC merges counters into an existing
# .gcda rather than replacing it, so attract and adventure both contribute.
# Clear stale profiles first so the run trains on this session only.
$stale = @(Get-ChildItem -LiteralPath $runnerBuild -Recurse -Filter '*.gcda' -ErrorAction SilentlyContinue)
if ($stale.Count -gt 0) {
  Write-Host "Removing $($stale.Count) stale profile file(s) from a previous training run"
  $stale | Remove-Item -Force
}

if (-not $Rom) {
  $Rom = Join-Path $root 'Metroid Prime Hunters.nds'
  if (-not (Test-Path -LiteralPath $Rom)) {
    $Rom = Join-Path (Split-Path -Parent $root) 'metroidprimehuntersrecomp\Metroid Prime Hunters.nds'
  }
}
if (-not (Test-Path -LiteralPath $Rom)) {
  throw "ROM not found. Pass -Rom <path to Metroid Prime Hunters.nds>."
}
if (-not $Bios) {
  # The BIOS dumps are gitignored, so a fresh framework worktree has only the
  # .toml configs. Fall back to the primary checkout, which is where they live.
  $Bios = Join-Path $frameworkRoot 'bios'
  if (-not (Test-Path -LiteralPath (Join-Path $Bios 'biosnds9.rom'))) {
    $Bios = Join-Path (Split-Path -Parent $root) 'ndsrecomp\bios'
  }
}
if (-not (Test-Path -LiteralPath (Join-Path $Bios 'biosnds9.rom'))) {
  throw "BIOS dumps not found under $Bios. Pass -Bios <dir containing biosnds9.rom>."
}

Push-Location $root
try {
  foreach ($route in $Routes) {
    Write-Host ""
    Write-Host "=== PGO training route: $route ==="
    & $PythonExe -3 (Join-Path $root 'tools\measure_mph_scenario.py') `
      --route $route `
      --exe $runnerExe `
      --rom $Rom `
      --bios $Bios `
      --port $Port `
      --repetitions $Repetitions `
      --tag "pgo-train-$route"
    if ($LASTEXITCODE -ne 0) {
      throw "Training route '$route' failed with exit code $LASTEXITCODE. Profile data is incomplete; do not proceed to the profile-use build."
    }
  }
} finally {
  Pop-Location
}

$profiles = @(Get-ChildItem -LiteralPath $runnerBuild -Recurse -Filter '*.gcda' -ErrorAction SilentlyContinue)
if ($profiles.Count -eq 0) {
  throw "Training produced no .gcda profile data in $runnerBuild. The runner most likely did not shut down through frontend_exit, which is the only path that flushes GCC's counters on Windows."
}
$bytes = ($profiles | Measure-Object -Property Length -Sum).Sum
Write-Host ""
Write-Host "Training complete: $($profiles.Count) profile file(s), $bytes bytes, in $runnerBuild"
Write-Host "Now reconfigure that same build directory with -DNDS_PGO_MODE=USE and rebuild."

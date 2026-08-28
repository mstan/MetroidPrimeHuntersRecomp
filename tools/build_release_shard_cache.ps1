<#
Build the pre-compiled native shard cache that ships inside an MPH release.

WHY THIS EXISTS
  MPH generates a lot of its hot code into RAM at runtime, so those pages
  cannot be statically recompiled into the runner; they land in Tier 3 (the
  bounded dirty-RAM interpreter) until the live-overlay tier captures a page
  and compiles it into a native shard DLL. A player who gets no cache pays
  that compile cost -- and the interpreted frame rate -- on their first visit
  to every area. Shipping a developer-built cache means the areas we have
  played are already native the moment the game starts.

  This is the mirror image of the bundled tcc toolchain staged by
  make_release.ps1: the toolchain fills the gaps a player finds on their own
  box, and this cache means there are far fewer gaps to fill.

WHAT IT DOES
  Boots the runner with the live-overlay tier armed and the gcc autocompile
  backend pointed at a dedicated cache directory, replays the benchmark routes
  (tools/measure_mph_scenario.py's route landmarks -- the same workload the
  perf harness measures), then drains the compiler's backlog and reports the
  inventory.

  gcc is the backend on purpose. This is a developer machine and gcc produces
  materially better code than the bundled tcc; the loader is backend-blind on
  CONSUMPTION, so a player with no toolchain at all still loads these shards.

IDENTITY
  The shards are built against the FLATTENED runtime header set that a shipped
  install carries (overlay_toolchain\include\), not the in-tree recompiler
  header directories. compile_live_shards.py hashes every *.h it is given, and
  those two sets differ, so building against the in-tree directories would
  produce a cache whose provider identity can never match a shipped package.
  Both this script and make_release.ps1 take that set from
  tools\overlay_shard_common.ps1 so they cannot drift apart.

USAGE
  powershell -NoProfile -ExecutionPolicy Bypass -File `
    tools\build_release_shard_cache.ps1 `
      -RunnerBuildDir ..\ndsrecomp-tier2\runner\build-tier2 `
      -RecompilerBuildDir recompiler\build-tier2
#>
param(
  # Routes replayed, in order. Add new ones here (and to
  # measure_mph_scenario.py's ROUTES) to widen release coverage.
  # mp_bots_blank is not redundant with mp_bots, which is what beads-yjp.50
  # made it look like. Measured 2026-08-27 on a clean cache: adventure alone
  # produced 38 shards, attract added 0, mp_bots added 0, and mp_bots_blank
  # added 21 -- 59 total over 34 distinct guest pages against the 30 the
  # previous release cache reached. Reaching the same Battle from a BLANK save
  # walks the nickname and file-creation code that the pre-made save skips, so
  # it is the only committed route that visits those pages.
  [string[]]$Routes = @('adventure', 'attract', 'mp_bots', 'mp_bots_blank'),
  [string]$CacheDir = 'release-shard-cache',
  # Relative to the repo root; '' auto-pairs this worktree with its framework
  # worktree the way tools/measure_mph_scenario.py does.
  [string]$NdsrecompRoot = '',
  # Relative to the repo root (runner) / framework root (recompiler).
  [string]$RunnerBuildDir = '',
  [string]$RecompilerBuildDir = 'recompiler\build',
  [string]$Rom = '',
  [string]$BiosDir = '',
  [string]$Config = '',
  [string]$Gcc = 'C:\msys64\mingw64\bin\gcc.exe',
  [string]$PythonExe = '',
  [int]$BasePort = 19910,
  [string]$LogDir = '',
  # Wipe the cache first. Off by default: a release cache is cumulative, each
  # route adds the pages it visits to the pages earlier routes found.
  [switch]$Clean
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'overlay_shard_common.ps1')
$root = Split-Path -Parent $PSScriptRoot

function Resolve-UnderRoot([string]$value, [string]$base) {
  if ([IO.Path]::IsPathRooted($value)) { return [IO.Path]::GetFullPath($value) }
  return [IO.Path]::GetFullPath((Join-Path $base $value))
}

# ---- inputs ----------------------------------------------------------------
if (-not $NdsrecompRoot) {
  $workspace = Split-Path -Parent $root
  $leaf = Split-Path -Leaf $root
  $candidates = @()
  if ($leaf -match '^[^-]+-(.+)$') {
    $candidates += (Join-Path $workspace ('ndsrecomp-' + $Matches[1]))
  }
  $candidates += (Join-Path $workspace 'ndsrecomp')
  $NdsrecompRoot = ($candidates | Where-Object {
    Test-Path -LiteralPath (Join-Path $_ 'tools\compile_live_shards.py')
  } | Select-Object -First 1)
  if (-not $NdsrecompRoot) {
    throw "No framework checkout with tools\compile_live_shards.py beside $root."
  }
}
$ndsRoot = Resolve-UnderRoot $NdsrecompRoot $root
if (-not $RunnerBuildDir) { $RunnerBuildDir = Join-Path $ndsRoot 'runner\build-tier2' }
$runnerBuild = Resolve-UnderRoot $RunnerBuildDir $root
$runner = Join-Path $runnerBuild 'nds_runner.exe'
$recompiler = Resolve-UnderRoot (Join-Path $RecompilerBuildDir 'nds_recompile.exe') $ndsRoot
$compileScript = Join-Path $ndsRoot 'tools\compile_live_shards.py'

if (-not $Rom) {
  foreach ($candidate in @(
      (Join-Path $root 'Metroid Prime Hunters.nds'),
      (Join-Path (Split-Path -Parent $root) 'metroidprimehuntersrecomp\Metroid Prime Hunters.nds'))) {
    if (Test-Path -LiteralPath $candidate) { $Rom = $candidate; break }
  }
}
if (-not $BiosDir) {
  foreach ($candidate in @(
      (Join-Path $ndsRoot 'bios'),
      (Join-Path (Split-Path -Parent $root) 'ndsrecomp\bios'))) {
    if (Test-Path -LiteralPath (Join-Path $candidate 'biosnds9.rom')) {
      $BiosDir = $candidate; break
    }
  }
}
if (-not $Config) { $Config = Join-Path $root 'game.toml' }

foreach ($required in @($runner, $recompiler, $compileScript, $Gcc, $Rom, $Config)) {
  if (-not $required -or -not (Test-Path -LiteralPath $required)) {
    throw "Shard cache input missing: $required"
  }
}
if (-not $BiosDir -or -not (Test-Path -LiteralPath $BiosDir)) {
  throw "Shard cache input missing: BIOS directory ($BiosDir)"
}
# The gcc backend links each shard against the runner's MinGW import library,
# so a runner build TREE is required, not just the exe.
if (-not (Get-ChildItem -LiteralPath $runnerBuild -Filter '*nds_runner*.a' -Recurse -ErrorAction SilentlyContinue)) {
  throw "No nds_runner import library under $runnerBuild (the gcc shard backend links against it)."
}

$cache = Resolve-UnderRoot $CacheDir $root
if ($Clean -and (Test-Path -LiteralPath $cache)) {
  Remove-Item -LiteralPath $cache -Recurse -Force
}
New-Item -ItemType Directory -Path $cache -Force | Out-Null
if (-not $LogDir) { $LogDir = Join-Path $cache '_logs' }
$logs = Resolve-UnderRoot $LogDir $root
New-Item -ItemType Directory -Path $logs -Force | Out-Null

# The include set a shipped install carries, materialized here so the release
# cache is built against exactly what the packager will hash.
$includeDir = New-OverlayToolchainIncludeDir -NdsRoot $ndsRoot `
  -Destination (Join-Path $cache '_toolchain_include')

$policy = @{} + (Get-ReleaseShardPolicy)
$python = Get-ShardPython -PythonExe $PythonExe
$identity = Get-ShardProviderIdentity -CompileScript $compileScript `
  -Recompiler $recompiler -IncludeDir $includeDir -Gcc $Gcc `
  -Policy $policy -Python $python

Write-Host "Framework      : $ndsRoot"
Write-Host "Runner         : $runner"
Write-Host "Recompiler     : $recompiler"
Write-Host "Cache          : $cache"
Write-Host "Backend        : $($policy.Compiler) ($Gcc)"
Write-Host "Provider ident : $identity"
Write-Host "Routes         : $($Routes -join ', ')"

# The command the runner spawns on every autocompile trigger. --runtime-include
# is passed EXPLICITLY (never --ndsrecomp-root) so the flattened, shippable
# header set is what the shards are built against.
$pyExe = $python[0]
$pyArgs = @()
if ($python.Count -gt 1) { $pyArgs = $python[1..($python.Count - 1)] }
$liveCommand = (@(
  ('"{0}"' -f $pyExe)) + $pyArgs + @(
  ('"{0}"' -f $compileScript),
  '--runtime-include', ('"{0}"' -f $includeDir),
  '--runner-build', ('"{0}"' -f $runnerBuild),
  '--recompiler', ('"{0}"' -f $recompiler),
  '--compiler', $policy.Compiler,
  '--gcc', ('"{0}"' -f $Gcc),
  ('--generated-opt={0}' -f $policy.GeneratedOpt),
  '--max-function-bytes', $policy.MaxFunctionBytes,
  '--max-pages', $policy.MaxPages,
  '--min-hits', $policy.MinHits
)) -join ' '
Write-Host "Autocompile    : $liveCommand"

# ---- replay ----------------------------------------------------------------
$port = $BasePort
$failed = @()
foreach ($route in $Routes) {
  Write-Host ''
  Write-Host "=== route $route (port $port) ==="
  & $pyExe @pyArgs (Join-Path $PSScriptRoot 'build_release_shard_cache.py') `
    --mph-root $root --runner $runner --bios $BiosDir --rom $Rom `
    --config $Config --cache $cache --backend $policy.Compiler `
    --route $route --port $port --live-command $liveCommand --log-dir $logs
  if ($LASTEXITCODE -ne 0) { $failed += $route }
  $port += 1
}
if ($failed.Count -ne 0) {
  throw "Route replay failed for: $($failed -join ', ')"
}

# ---- inventory -------------------------------------------------------------
$shards = @(Get-ShardsForIdentity -CacheDir $cache -Identity $identity)
$all = @(Get-ChildItem -LiteralPath (Join-Path $cache $policy.Compiler) `
  -Filter '*.dll' -ErrorAction SilentlyContinue)
Write-Host ''
Write-Host "--- shard cache $cache ---"
Write-Host "Provider identity : $identity"
Write-Host "Shards for it     : $($shards.Count)"
Write-Host "DLLs in $($policy.Compiler)\ : $($all.Count)"
if ($shards.Count -eq 0) {
  throw @"
The route replay produced no shards for provider identity $identity.

Either every autocompile run failed (check $logs\*.stderr.log and the
live_overlay_status last_error in $logs\*.summary.json), or the runner
never armed the live-overlay tier. A cache with no shards for this identity
is exactly what make_release.ps1 refuses to ship.
"@
}
$shards | Select-Object Name, Cpu, Bank, Length | Format-Table | Out-Host
Write-Host "Pass this to the packager:  -ShardCacheDir '$cache'"

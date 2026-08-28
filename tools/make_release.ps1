<#
Package a completed Metroid Prime Hunters Recomp Windows release.

The ZIP contains the portable recomp-ui launcher, the title runner with EVERY
content-validated bank compiled in (verified against CMakeLists.txt by
tools/verify_bank_inventory.ps1 and recorded in bank-manifest.txt), launcher
assets, game config, documentation, and MinGW/SDL dependencies. ROMs,
BIOS/firmware, saves, raw captures, and generated source are never staged.

Build the runner and launcher first, then run:

  powershell -File tools\make_release.ps1 -Version 0.1.0 `
    -RunnerBuildDir ..\ndsrecomp\runner\build-mph-release `
    -LauncherBuildDir launcher\recomp-ui\build-release
#>
param(
  [Parameter(Mandatory = $true)][string]$Version,
  [string]$RunnerBuildDir = '..\ndsrecomp\runner\build-mph-release',
  [string]$LauncherBuildDir = 'launcher\recomp-ui\build-release',
  [string]$RuntimeBinDir = 'C:\msys64\mingw64\bin',
  [ValidateSet('SDL3', 'SDL2')]
  [string]$SdlBackend = 'SDL3',
  # Inputs for the bundled live-overlay (tcc) toolchain. $NdsrecompRoot is
  # relative to the repo root; $RecompilerBuildDir is relative to that.
  [string]$NdsrecompRoot = '..\ndsrecomp',
  [string]$RecompilerBuildDir = 'recompiler\build',
  [switch]$SkipOverlayToolchain,
  # Developer-built native shard cache produced by
  # tools\build_release_shard_cache.ps1. Relative paths are resolved against
  # the repo root.
  [string]$ShardCacheDir = 'release-shard-cache',
  [string]$Gcc = 'C:\msys64\mingw64\bin\gcc.exe',
  [string]$PythonExe = '',
  # Ship without a prebuilt shard cache. Off by default: a cache-less package
  # makes every player's first visit to every area run interpreted.
  [switch]$AllowNoShardCache
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

# Directory parameters are documented as repo-root-relative, but an absolute
# path is the natural thing to pass when the runner or framework lives in a
# sibling worktree. Join-Path does not collapse an absolute second argument
# (it yields "F:\repo\F:\other"), so GetFullPath then throws
# "The given path's format is not supported". tools\build_release_shard_cache.ps1
# already resolves both forms; do the same here so the two scripts agree.
function Resolve-UnderRoot([string]$value, [string]$base) {
  if ([IO.Path]::IsPathRooted($value)) { return [IO.Path]::GetFullPath($value) }
  return [IO.Path]::GetFullPath((Join-Path $base $value))
}

$runnerBuild = Resolve-UnderRoot $RunnerBuildDir $root
$launcherBuild = Resolve-UnderRoot $LauncherBuildDir $root
$runner = Join-Path $runnerBuild 'nds_runner.exe'
$launcher = Join-Path $launcherBuild 'mph-recomp-ui.exe'
$assets = Join-Path $launcherBuild 'assets'

foreach ($required in @($runner, $launcher, $assets)) {
  if (-not (Test-Path -LiteralPath $required)) {
    throw "Release input missing: $required"
  }
}

# A runner missing generated banks is functional but slow: the FMV bank
# alone is worth ~2x on the opening movies, the ARM7 MP banks ~60 vs ~40 FPS
# in local multiplayer, and the ingested coverage banks cover the rest.
# v0.4.12/v0.4.13/v0.5.0 all shipped without the 63 coverage banks because
# this check used to be a single grep for "mph_arm9_fmv_runtime", which
# passes even when every other bank is absent. Assert the FULL inventory
# declared by CMakeLists.txt instead; the FMV check is kept inside it.
# Dot-sourcing runs the verifier's param() block in THIS scope, which
# clobbers $runner/$root-adjacent names with empty strings (PowerShell
# variables are case-insensitive). Re-derive the paths afterwards.
. (Join-Path $PSScriptRoot 'verify_bank_inventory.ps1')
# Shard toolchain surface + provider identity. Defined once and shared with
# tools\build_release_shard_cache.ps1 so the builder and the packager cannot
# disagree about what a shipped shard was built against. (No param() block in
# there, so this dot-source is safe.)
. (Join-Path $PSScriptRoot 'overlay_shard_common.ps1')
$root = Split-Path -Parent $PSScriptRoot
$runner = Join-Path (Resolve-UnderRoot $RunnerBuildDir $root) 'nds_runner.exe'
$bankInventory = Test-MphBankInventory -Runner $runner -RepoRoot $root

$projectText = Get-Content (Join-Path $root 'CMakeLists.txt') -Raw
if ($projectText -notmatch
    "project\(MetroidPrimeHuntersRecomp VERSION $([regex]::Escape($Version)) ") {
  throw "CMake project version does not match release $Version."
}

$out = Join-Path $root 'release-stage'
$stageName = "MetroidPrimeHuntersRecomp-windows-x64-v$Version"
$stage = Join-Path $out $stageName
$zip = Join-Path $out "$stageName.zip"
$outFull = [IO.Path]::GetFullPath($out).TrimEnd('\') + '\'
$stageFull = [IO.Path]::GetFullPath($stage)
$zipFull = [IO.Path]::GetFullPath($zip)
if (-not $stageFull.StartsWith($outFull,
      [StringComparison]::OrdinalIgnoreCase) -or
    -not $zipFull.StartsWith($outFull,
      [StringComparison]::OrdinalIgnoreCase)) {
  throw 'Refusing to clean release paths outside release-stage.'
}

if (Test-Path -LiteralPath $stage) {
  Remove-Item -LiteralPath $stage -Recurse -Force
}
if (Test-Path -LiteralPath $zip) {
  Remove-Item -LiteralPath $zip -Force
}
New-Item -ItemType Directory -Path $stage -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage 'bios') -Force |
  Out-Null

Copy-Item -LiteralPath $launcher `
  -Destination (Join-Path $stage 'MetroidPrimeHuntersRecomp.exe')
Copy-Item -LiteralPath $runner -Destination $stage
Copy-Item -LiteralPath $assets -Destination $stage -Recurse
Copy-Item -LiteralPath (Join-Path $root 'game.toml') -Destination $stage
Copy-Item -LiteralPath (Join-Path $root 'README.md') -Destination $stage
Copy-Item -LiteralPath (Join-Path $root 'LICENSE') -Destination $stage
Copy-Item -LiteralPath (Join-Path $root 'packaging\BIOS_README.txt') `
  -Destination (Join-Path $stage 'bios\README.txt')

# Audit trail: the verified bank inventory of the exact runner being shipped.
Test-MphBankInventory -Runner (Join-Path $stage 'nds_runner.exe') `
  -RepoRoot $root -ManifestPath (Join-Path $stage 'bank-manifest.txt') `
  -Quiet | Out-Null

$runtimeDlls = @(
  "$SdlBackend.dll",
  'libgcc_s_seh-1.dll',
  'libstdc++-6.dll',
  'libwinpthread-1.dll',
  # MSYS2's SDL3 links libiconv; omitting it shipped v0.6.0/v0.6.1 builds
  # that died on player machines with "libiconv-2.dll was not found"
  # (invisible on dev machines, where mingw64\bin on PATH satisfies it).
  'libiconv-2.dll'
)
foreach ($name in $runtimeDlls) {
  $source = Join-Path $RuntimeBinDir $name
  if (-not (Test-Path -LiteralPath $source)) {
    throw "Required runtime DLL missing: $source"
  }
  Copy-Item -LiteralPath $source -Destination $stage
}

# ---- DLL import-closure gate -----------------------------------------------
# Every staged PE binary's non-system imports must resolve inside the stage.
# This is the check a dev machine's PATH silently defeats: a player has no
# mingw64\bin, so an unstaged toolchain DLL is a guaranteed startup crash.
# Defined here, INVOKED after all staging (toolchain + shards included) so the
# scan covers every binary that ends up in the ZIP, not just the core files.
function Test-DllImportClosure {
$systemDlls = @(
  'kernel32.dll','user32.dll','msvcrt.dll','ole32.dll','oleaut32.dll',
  'shell32.dll','advapi32.dll','gdi32.dll','imm32.dll','setupapi.dll',
  'version.dll','winmm.dll','ws2_32.dll','iphlpapi.dll','opengl32.dll',
  'comdlg32.dll','bcrypt.dll','crypt32.dll','shlwapi.dll','dbghelp.dll',
  'ncrypt.dll','secur32.dll','winhttp.dll','wldap32.dll','normaliz.dll',
  'rpcrt4.dll','psapi.dll','userenv.dll','netapi32.dll','wsock32.dll',
  'propsys.dll'
)
$objdump = Join-Path $RuntimeBinDir 'objdump.exe'
if (Test-Path -LiteralPath $objdump) {
  $unresolved = @()
  $binaries = Get-ChildItem -LiteralPath $stage -Recurse -File |
    Where-Object { $_.Extension -in '.exe', '.dll', '.pyd' }
  foreach ($bin in $binaries) {
    $imports = & $objdump -p $bin.FullName 2>$null |
      Select-String 'DLL Name: (.+)$' |
      ForEach-Object { $_.Matches[0].Groups[1].Value.Trim() } | Sort-Object -Unique
    foreach ($dep in $imports) {
      $dl = $dep.ToLowerInvariant()
      if ($systemDlls -contains $dl) { continue }
      if ($dl.StartsWith('api-ms-win-')) { continue }
      if ($dl.StartsWith('python3')) { continue }
      if ((Test-Path -LiteralPath (Join-Path $bin.DirectoryName $dep)) -or
          (Test-Path -LiteralPath (Join-Path $stage $dep))) { continue }
      $unresolved += ('{0} needs {1}' -f
        $bin.FullName.Substring($stage.Length + 1), $dep)
    }
  }
  if ($unresolved.Count -gt 0) {
    throw ("DLL import closure is broken - these imports resolve on a dev " +
      "machine's PATH but NOT on a player machine:`n  " +
      ($unresolved -join "`n  ") +
      "`nStage the missing DLL(s) (add to `$runtimeDlls) or extend " +
      "`$systemDlls if a genuine Windows system DLL is missing from the list.")
  }
  Write-Host (("DLL import closure OK: {0} binaries scanned, every " +
    "non-system import resolves inside the stage") -f $binaries.Count)
} else {
  Write-Warning "objdump.exe not found; DLL import-closure gate SKIPPED"
}
}

# ---- Self-contained live-overlay toolchain (tcc tier) ---------------------
# A player box has no gcc and no Python, so the runner's backend policy
# (runner/src/main.cpp) resolves to tcc and builds its autocompile command out
# of <exe>\overlay_toolchain\. Everything it references must be self-contained:
# the embedded CPython and the prebuilt tcc already are, and nds_recompile.exe
# needs its MinGW runtime DLLs beside it (Windows resolves an exe's imports
# from the exe's OWN directory, not the parent stage dir).
#
# Without this the shipped build still runs -- it just leaves every tier-3 page
# the prebuilt cache misses in the interpreter forever.
if (-not $SkipOverlayToolchain) {
  $ndsRoot = Resolve-UnderRoot $NdsrecompRoot $root
  $recompiler = [IO.Path]::GetFullPath(
    (Join-Path $ndsRoot (Join-Path $RecompilerBuildDir 'nds_recompile.exe')))
  if (-not (Test-Path -LiteralPath $recompiler)) {
    throw "Overlay toolchain input missing: $recompiler (build the recompiler, or pass -SkipOverlayToolchain)"
  }

  $toolchain = Join-Path $stage 'overlay_toolchain'
  New-Item -ItemType Directory -Path $toolchain -Force | Out-Null
  $dlCache = Join-Path $root 'tools\_toolchain_cache'
  New-Item -ItemType Directory -Path $dlCache -Force | Out-Null

  # Pinned by version AND content hash. An unpinned toolchain would let the
  # bytes a player compiles their game with change silently under us.
  $downloads = @(
    @{ Name = 'python-3.13.1-embed-amd64.zip'
       Uri  = 'https://www.python.org/ftp/python/3.13.1/python-3.13.1-embed-amd64.zip'
       Sha  = '7B7923FF0183A8B8FCA90F6047184B419B108CB437F75FC1C002F9D2F8BCEC16' },
    @{ Name = 'tcc-0.9.27-win64-bin.zip'
       Uri  = 'https://download.savannah.gnu.org/releases/tinycc/tcc-0.9.27-win64-bin.zip'
       Sha  = '34A721949A2583FDFF725312DA092FA0F5F1F284B702E6F811C6954714FAABB2' }
  )
  foreach ($d in $downloads) {
    $path = Join-Path $dlCache $d.Name
    if (-not (Test-Path -LiteralPath $path)) {
      Invoke-WebRequest -Uri $d.Uri -OutFile $path
    }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    if ($actual -ne $d.Sha) {
      throw "Toolchain download hash mismatch for $($d.Name): expected $($d.Sha), got $actual"
    }
  }

  Expand-Archive -LiteralPath (Join-Path $dlCache 'python-3.13.1-embed-amd64.zip') `
    -DestinationPath (Join-Path $toolchain 'python') -Force

  # The tcc zip has a single top-level tcc\ dir (tcc.exe + libtcc.dll +
  # include\ + lib\); tcc finds its own headers relative to tcc.exe, so the
  # directory ships whole rather than cherry-picked.
  $tccTmp = Join-Path $dlCache 'tcc_extract'
  if (Test-Path -LiteralPath $tccTmp) {
    Remove-Item -LiteralPath $tccTmp -Recurse -Force
  }
  Expand-Archive -LiteralPath (Join-Path $dlCache 'tcc-0.9.27-win64-bin.zip') `
    -DestinationPath $tccTmp -Force
  Copy-Item -LiteralPath (Join-Path $tccTmp 'tcc') `
    -Destination (Join-Path $toolchain 'tcc') -Recurse

  Copy-Item -LiteralPath $recompiler -Destination $toolchain
  foreach ($name in @('libgcc_s_seh-1.dll', 'libstdc++-6.dll',
                      'libwinpthread-1.dll')) {
    Copy-Item -LiteralPath (Join-Path $RuntimeBinDir $name) `
      -Destination $toolchain
  }
  Copy-Item -LiteralPath (Join-Path $ndsRoot 'tools\compile_live_shards.py') `
    -Destination $toolchain

  # Exactly the header closure a generated shard preprocesses: it includes
  # runtime_arm.h, which includes runtime_arm_types.h out of the shared ARM
  # core, and nothing else beyond the C library. The other headers in
  # recompiler\armv4t are relative-path shims into the submodule and would
  # break if flattened, so they are deliberately NOT staged.
  # The list lives in tools\overlay_shard_common.ps1 because the prebuilt gcc
  # cache must be BUILT against the same flattened set: compile_live_shards.py
  # hashes every *.h it is handed into the provider identity, so a header set
  # that differs by one file is a different identity and the shipped cache
  # would filter down to nothing.
  $toolInc = New-OverlayToolchainIncludeDir -NdsRoot $ndsRoot `
    -Destination (Join-Path $toolchain 'include')

  $tcMB = '{0:N1}' -f ((Get-ChildItem -LiteralPath $toolchain -Recurse -File |
    Measure-Object Length -Sum).Sum / 1MB)
  Write-Host "Bundled overlay toolchain (embedded python + tcc + recompiler): ~$tcMB MB"
}

# ---- Developer-built native shard cache -----------------------------------
# MPH generates its hottest code into RAM, so those pages cannot be compiled
# into the runner: without a cache they run in the Tier-3 interpreter until the
# player's own machine has captured and compiled them. This ships the shards a
# developer already produced by playing the benchmark routes
# (tools\build_release_shard_cache.ps1), so the covered areas are native from
# the player's first frame.
#
# Only shards whose provider identity matches THESE artifacts are staged. The
# identity folds the recompiler's REPORTED CODEGEN VERSION (not its bytes --
# see beads-yjp.52), the shard compiler's emission surface, the runtime ABI
# headers, and the backend and its flags. It is computed by importing
# ndsrecomp's own compile_live_shards.py rather than being re-derived here --
# the packager drifting from the compiler is precisely how psxrecomp shipped
# v0.11.2 with a silently empty cache.
#
# Because none of those move on a rebuild any more, a cache built for one
# release can be carried forward into the next as long as the ABI, the headers
# and the codegen versions are unchanged. v0.6.5 had to ship without one
# because the old identity hashed the whole compile script (beads-yjp.56).
#
# The staged location is not a free choice: for a shipped install the launcher
# passes --live-overlay-cache <game dir>\live-shard-cache (see
# append_live_overlay_args in launcher\recomp-ui\launcher_main.cpp), and the
# runner scans that directory recursively, keying the backend off the immediate
# parent directory name (<cache>\gcc\, <cache>\tcc\). So the subtree must be
# preserved and it must land exactly there; a flat copy, or a copy anywhere
# else, ships bytes nothing ever loads.
$shardRoot = Resolve-UnderRoot $NdsrecompRoot $root
$shardCompileScript = Join-Path $shardRoot 'tools\compile_live_shards.py'
$stagedRecompiler = Join-Path $stage 'overlay_toolchain\nds_recompile.exe'
$stagedInclude = Join-Path $stage 'overlay_toolchain\include'
if (Test-Path -LiteralPath $stagedRecompiler) {
  # The exact artifacts being shipped.
  $identityRecompiler = $stagedRecompiler
  $identityInclude = $stagedInclude
} else {
  # -SkipOverlayToolchain: nothing shipped to hash, so hash the sources the
  # shipped copies would have been made from (byte-identical either way).
  $identityRecompiler = [IO.Path]::GetFullPath(
    (Join-Path $shardRoot (Join-Path $RecompilerBuildDir 'nds_recompile.exe')))
  $identityInclude = New-OverlayToolchainIncludeDir -NdsRoot $shardRoot `
    -Destination (Join-Path ([IO.Path]::GetTempPath()) "nds_shard_inc_$PID")
}

$shardCache = ''
if ($ShardCacheDir) {
  $shardCache = if ([IO.Path]::IsPathRooted($ShardCacheDir)) {
    [IO.Path]::GetFullPath($ShardCacheDir)
  } else {
    [IO.Path]::GetFullPath((Join-Path $root $ShardCacheDir))
  }
}

if (-not $shardCache -or -not (Test-Path -LiteralPath $shardCache)) {
  if (-not $AllowNoShardCache) {
    throw @"
No prebuilt native shard cache at '$shardCache', so this package would ship
without one and every player's first visit to every area would run in the
Tier-3 interpreter.

Build one against the runner and recompiler being shipped:

  powershell -NoProfile -ExecutionPolicy Bypass -File ``
    tools\build_release_shard_cache.ps1 ``
      -RunnerBuildDir $RunnerBuildDir ``
      -NdsrecompRoot $NdsrecompRoot ``
      -RecompilerBuildDir $RecompilerBuildDir

then re-run this packager, or pass -AllowNoShardCache to ship without one.
"@
  }
  Write-Warning "No native shard cache at '$shardCache' - shipping without one because -AllowNoShardCache was given"
} else {
  $shardIdentity = Get-ShardProviderIdentity `
    -CompileScript $shardCompileScript -Recompiler $identityRecompiler `
    -IncludeDir $identityInclude -Gcc $Gcc -Python (Get-ShardPython -PythonExe $PythonExe)
  Write-Host "Release shard provider identity: $shardIdentity (only shards published under it are shipped)"

  $shards = @(Get-ShardsForIdentity -CacheDir $shardCache -Identity $shardIdentity)
  if ($shards.Count -eq 0) {
    $present = @(Get-ChildItem -LiteralPath $shardCache -Recurse -File `
      -Filter '*.dll' -ErrorAction SilentlyContinue).Count
    $message = @"
The shard cache at $shardCache has $present DLL(s) but NONE published under
this build's provider identity $shardIdentity, so the package would ship an
empty cache.

The identity folds the live bank ABI, the recompiler's reported codegen version,
the shard compiler's emission surface, the runtime ABI headers, and the shard
backend with its compile flags. The usual causes of that drift are:

  * the cache was built against the in-tree recompiler\armv4t and
    external\arm-recomp-core\common header directories instead of the two-file
    flattened set a shipped install carries. Pass --runtime-include pointing at
    the flattened set (tools\build_release_shard_cache.ps1 does this for you).
  * generated-C emission changed, so kCodegenVersion in
    recompiler\src\codegen_identity.h or SHARD_CODEGEN_VERSION in
    tools\compile_live_shards.py was bumped.
  * a different gcc, -O level or --max-function-bytes was used.

Merely rebuilding the recompiler is NOT one of them any more (beads-yjp.52):
the identity reads the version the binary reports, not its bytes.

Rebuild it with tools\build_release_shard_cache.ps1 against the artifacts being
shipped, or pass -AllowNoShardCache to ship without a cache anyway.
"@
    if (-not $AllowNoShardCache) { throw $message }
    Write-Warning $message
  } else {
    $shardDst = Join-Path $stage 'live-shard-cache'
    foreach ($shard in $shards) {
      $dest = Join-Path (Join-Path $shardDst $shard.Backend) $shard.Name
      New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force |
        Out-Null
      Copy-Item -LiteralPath $shard.Path -Destination $dest
    }
    $shardBytes = ($shards | Measure-Object Length -Sum).Sum
    $namespaces = @($shards | Select-Object -ExpandProperty Backend -Unique |
      Sort-Object)
    Write-Host ("Bundled native shard cache: {0} shard(s), {1:N1} MB, namespace(s) {2}" -f `
      $shards.Count, ($shardBytes / 1MB), ($namespaces -join ', '))

    # Audit trail beside bank-manifest.txt: what was shipped, and under which
    # identity, so a support report can be matched against a build.
    $manifestLines = @(
      "Metroid Prime Hunters Recomp $Version - prebuilt native shard cache",
      "",
      "provider_identity : $shardIdentity",
      "backend           : $($namespaces -join ', ')",
      "source_cache      : $shardCache",
      "recompiler_queried: $identityRecompiler",
      "headers_hashed    : $identityInclude",
      "staged_at         : live-shard-cache\<backend>\",
      "shard_count       : $($shards.Count)",
      ("total_bytes       : {0}" -f $shardBytes),
      "",
      "shards:"
    )
    foreach ($shard in ($shards | Sort-Object Name)) {
      $manifestLines += ("  {0}\{1}  cpu={2} page={3} bytes={4}" -f `
        $shard.Backend, $shard.Name, $shard.Cpu, $shard.Bank, $shard.Length)
    }
    Set-Content -LiteralPath (Join-Path $stage 'shard-manifest.txt') `
      -Value $manifestLines -Encoding UTF8

    # Player-facing explanation, both inside the cache folder and appended to
    # the staged README so it is findable without opening the folder. Appended
    # to the STAGED copy only: the repo README is the developer document.
    $cacheReadme = Join-Path $root 'packaging\NATIVE_CACHE_README.txt'
    if (-not (Test-Path -LiteralPath $cacheReadme)) {
      throw "Player cache README missing: $cacheReadme"
    }
    Copy-Item -LiteralPath $cacheReadme `
      -Destination (Join-Path $shardDst 'README.txt')
    # Array concatenation, not @(a, b, (pipeline)): -join does not flatten a
    # nested array, it stringifies it as "System.Object[]".
    $readmeSection = @('', '## Native code cache', '') +
      @((Get-Content -LiteralPath $cacheReadme -Raw) -split "`r?`n" |
        Select-Object -Skip 3)
    Add-Content -LiteralPath (Join-Path $stage 'README.md') `
      -Value ($readmeSection -join "`n") -Encoding UTF8
  }
}

$forbidden = @(Get-ChildItem -LiteralPath $stage -File -Recurse |
  Where-Object {
    $_.Extension -in @('.nds', '.rom', '.sav', '.bin', '.gpr') -or
    $_.Name -in @('biosnds9.rom', 'biosnds7.rom', 'firmware.bin') -or
    $_.FullName -match '[\\/]generated[\\/]'
  })
if ($forbidden.Count -ne 0) {
  throw "Release stage contains forbidden private/derived material: $($forbidden.FullName -join ', ')"
}

# Full stage is assembled; scan EVERYTHING before archiving.
Test-DllImportClosure

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stagePrefix = $stageFull.TrimEnd('\') + '\'
$files = @(Get-ChildItem -LiteralPath $stage -File -Recurse |
  Sort-Object FullName)
$archive = [IO.Compression.ZipFile]::Open(
  $zipFull, [IO.Compression.ZipArchiveMode]::Create)
try {
  foreach ($file in $files) {
    $fileFull = [IO.Path]::GetFullPath($file.FullName)
    if (-not $fileFull.StartsWith(
        $stagePrefix, [StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to archive a file outside release stage: $fileFull"
    }
    $entryName = $fileFull.Substring($stagePrefix.Length).Replace('\', '/')
    if ($entryName.StartsWith('/') -or
        $entryName -match '(^|/)\.\.(/|$)') {
      throw "Unsafe ZIP entry name: $entryName"
    }
    [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
      $archive, $fileFull, $entryName,
      [IO.Compression.CompressionLevel]::Optimal) | Out-Null
  }
} finally {
  $archive.Dispose()
}

$archive = [IO.Compression.ZipFile]::OpenRead($zipFull)
try {
  $badEntries = @($archive.Entries | Where-Object {
    $_.FullName.Contains('\') -or $_.FullName.StartsWith('/') -or
    $_.FullName -match '(^|/)\.\.(/|$)' -or
    [IO.Path]::GetExtension($_.FullName) -in
      @('.nds', '.rom', '.sav', '.bin', '.gpr') -or
    [IO.Path]::GetFileName($_.FullName) -in
      @('biosnds9.rom', 'biosnds7.rom', 'firmware.bin')
  })
  if ($badEntries.Count -ne 0) {
    throw "ZIP contains unsafe entry names."
  }
  if ($archive.Entries.Count -ne $files.Count) {
    throw "ZIP entry count mismatch: expected $($files.Count), got $($archive.Entries.Count)"
  }
} finally {
  $archive.Dispose()
}

Write-Host "--- $stageName ---"
Get-ChildItem -LiteralPath $stage | Select-Object Name, Length | Out-Host
Get-FileHash -LiteralPath $zip -Algorithm SHA256 | Out-Host


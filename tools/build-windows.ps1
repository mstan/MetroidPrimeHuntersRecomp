<#
Build and package the Metroid Prime Hunters Recomp Windows release.

This script builds the title banks, the sibling ndsrecomp runner, and the
Windows recomp-ui launcher, then stages a portable ZIP with tools\make_release.ps1.
It does not publish a release.

Usage:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    tools\build-windows.ps1 -Version 0.1.0
#>
param(
  [string]$Version = '0.1.0',
  [string]$CMake = 'C:\msys64\mingw64\bin\cmake.exe',
  [string]$Generator = 'Ninja',
  [int]$Jobs = 12,
  [string]$GameBuildDir = 'build-release',
  [string]$RunnerBuildDir = '..\ndsrecomp\runner\build-mph-release',
  [string]$LauncherBuildDir = 'launcher\recomp-ui\build-release',
  [string]$RuntimeBinDir = 'C:\msys64\mingw64\bin',
  [string]$NdsrecompRoot = '..\ndsrecomp',
  [string]$RecompilerBuildDir = 'recompiler\build',
  [string]$RecompUiRoot = 'F:\Projects\recomp-ui',
  [ValidateSet('SDL3', 'SDL2')]
  [string]$SdlBackend = 'SDL3',
  [string]$ShardCacheDir = 'release-shard-cache',
  [string]$Gcc = 'C:\msys64\mingw64\bin\gcc.exe',
  [string]$PythonExe = '',
  [switch]$AllowNoShardCache,
  # Opt-in profile-guided optimization of the runner. Off by default; with it
  # off this script behaves exactly as before, down to the CMake arguments.
  # With it on the runner is built three times in one build directory:
  # instrumented, then trained on the scripted routes, then rebuilt with the
  # profile. Only runner-owned host code carries PGO flags, so the generated
  # bank objects compile once and are reused by every pass.
  [switch]$Pgo,
  [string]$PgoTrainRoutes = 'attract,adventure'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$cmakePath = [IO.Path]::GetFullPath($CMake)
if (-not (Test-Path -LiteralPath $cmakePath)) {
  throw "CMake not found: $cmakePath"
}

if ([IO.Path]::IsPathRooted($NdsrecompRoot)) {
  $frameworkRoot = [IO.Path]::GetFullPath($NdsrecompRoot)
} else {
  $frameworkRoot = [IO.Path]::GetFullPath((Join-Path $root $NdsrecompRoot))
}
$gameBuild = [IO.Path]::GetFullPath((Join-Path $root $GameBuildDir))
$runnerBuild = [IO.Path]::GetFullPath((Join-Path $root $RunnerBuildDir))
$launcherBuild = [IO.Path]::GetFullPath((Join-Path $root $LauncherBuildDir))
$titleBankDir = [IO.Path]::GetFullPath((Join-Path $root 'generated\recomp'))
$romSha1 = '90164d1ac127ee5f9815ea4ae7de798c7b5fc629'

Push-Location $root
try {
  & $cmakePath -G $Generator -S $root -B $gameBuild `
    -DCMAKE_BUILD_TYPE=Release `
    -DNDSRECOMP_ROOT="$frameworkRoot"
  if ($LASTEXITCODE -ne 0) { throw 'Game CMake configure failed.' }
  & $cmakePath --build $gameBuild --target metroidprimehuntersrecomp -j $Jobs
  if ($LASTEXITCODE -ne 0) { throw 'Game bank build failed.' }

  # Shared across every runner configure below so the PGO passes differ from
  # the plain build in exactly one argument.
  $runnerArgs = @(
    '-G', $Generator, '-S', "$frameworkRoot\runner", '-B', $runnerBuild,
    '-DCMAKE_BUILD_TYPE=Release',
    "-DNDS_SDL_BACKEND=$SdlBackend",
    '-DNDS_BOOTSTRAP_FIRMWARE=ON',
    "-DNDS_TITLE_BANK_DIR=$titleBankDir",
    "-DNDS_TITLE_ROM_SHA1=$romSha1")

  if (-not $Pgo) {
    & $cmakePath @runnerArgs
    if ($LASTEXITCODE -ne 0) { throw 'Runner CMake configure failed.' }
    & $cmakePath --build $runnerBuild -j $Jobs
    if ($LASTEXITCODE -ne 0) { throw 'Runner build failed.' }
  } else {
    # A compiler cache must not sit between the profile data and the objects,
    # so PGO builds compile directly. The framework refuses to configure a PGO
    # build with a cache enabled.
    $pgoArgs = $runnerArgs + @('-DNDSRECOMP_COMPILER_CACHE=OFF')

    # Pass 1: instrument. GCC writes .gcda beside the object files, so all
    # three passes must share this one build directory - there is no working
    # -fprofile-dir on mingw-gcc (it mangles the object path into a nested
    # directory it cannot create and silently writes no profile at all).
    Write-Host '=== PGO pass 1/3: instrumented runner ==='
    & $cmakePath @pgoArgs -DNDS_PGO_MODE=GENERATE
    if ($LASTEXITCODE -ne 0) { throw 'Instrumented runner CMake configure failed.' }
    & $cmakePath --build $runnerBuild -j $Jobs
    if ($LASTEXITCODE -ne 0) { throw 'Instrumented runner build failed.' }

    # Pass 2: train on the scripted routes. No human input; the harness exits
    # each repetition through frontend_exit, which is what flushes the
    # counters on Windows.
    Write-Host '=== PGO pass 2/3: scripted training ==='
    $routes = @($PgoTrainRoutes.Split(',') | ForEach-Object { $_.Trim() } |
      Where-Object { $_ })
    if ($routes.Count -eq 0) { throw 'PgoTrainRoutes is empty.' }
    # Invoked in-process rather than through powershell.exe -File: an array
    # parameter does not bind reliably across -File, and pgo_train.ps1 throws
    # on failure, which propagates here directly.
    & "$root\tools\pgo_train.ps1" `
      -RunnerBuildDir $runnerBuild `
      -NdsrecompRoot $frameworkRoot `
      -Routes $routes

    # Pass 3: rebuild with the profile. Only runner-owned translation units
    # recompile here; every generated bank object from pass 1 is reused.
    Write-Host '=== PGO pass 3/3: profile-optimized runner ==='
    & $cmakePath @pgoArgs -DNDS_PGO_MODE=USE
    if ($LASTEXITCODE -ne 0) { throw 'Profile-use runner CMake configure failed.' }
    & $cmakePath --build $runnerBuild -j $Jobs
    if ($LASTEXITCODE -ne 0) { throw 'Profile-use runner build failed.' }
  }

  & $cmakePath -G $Generator -S "$root\launcher\recomp-ui" -B $launcherBuild `
    -DCMAKE_BUILD_TYPE=Release `
    -DNDSRECOMP_ROOT="$frameworkRoot" `
    -DRECOMP_UI_ROOT="$RecompUiRoot" `
    "-DMPH_LAUNCHER_SDL_BACKEND=$SdlBackend" `
    -DCMAKE_PREFIX_PATH="$RuntimeBinDir\..\lib\cmake"
  if ($LASTEXITCODE -ne 0) { throw 'Launcher CMake configure failed.' }
  & $cmakePath --build $launcherBuild -j $Jobs
  if ($LASTEXITCODE -ne 0) { throw 'Launcher build failed.' }

  & "$root\tools\make_release.ps1" `
    -Version $Version `
    -RunnerBuildDir $RunnerBuildDir `
    -LauncherBuildDir $LauncherBuildDir `
    -RuntimeBinDir $RuntimeBinDir `
    -NdsrecompRoot $NdsrecompRoot `
    -RecompilerBuildDir $RecompilerBuildDir `
    -SdlBackend $SdlBackend `
    -ShardCacheDir $ShardCacheDir `
    -Gcc $Gcc `
    -PythonExe $PythonExe `
    -AllowNoShardCache:$AllowNoShardCache
} finally {
  Pop-Location
}

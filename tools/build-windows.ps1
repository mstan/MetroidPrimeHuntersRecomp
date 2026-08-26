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
  [string]$RecompUiRoot = 'F:\Projects\recomp-ui',
  [ValidateSet('SDL3', 'SDL2')]
  [string]$SdlBackend = 'SDL3'
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

  & $cmakePath -G $Generator -S "$frameworkRoot\runner" -B $runnerBuild `
    -DCMAKE_BUILD_TYPE=Release `
    "-DNDS_SDL_BACKEND=$SdlBackend" `
    -DNDS_BOOTSTRAP_FIRMWARE=ON `
    "-DNDS_TITLE_BANK_DIR=$titleBankDir" `
    "-DNDS_TITLE_ROM_SHA1=$romSha1"
  if ($LASTEXITCODE -ne 0) { throw 'Runner CMake configure failed.' }
  & $cmakePath --build $runnerBuild -j $Jobs
  if ($LASTEXITCODE -ne 0) { throw 'Runner build failed.' }

  & $cmakePath -G $Generator -S "$root\launcher\recomp-ui" -B $launcherBuild `
    -DCMAKE_BUILD_TYPE=Release `
    -DNDSRECOMP_ROOT="$frameworkRoot" `
    -DRECOMP_UI_ROOT="$RecompUiRoot" `
    "-DMPH_LAUNCHER_SDL_BACKEND=$SdlBackend" `
    -DCMAKE_PREFIX_PATH="$RuntimeBinDir\..\lib\cmake"
  if ($LASTEXITCODE -ne 0) { throw 'Launcher CMake configure failed.' }
  & $cmakePath --build $launcherBuild -j $Jobs
  if ($LASTEXITCODE -ne 0) { throw 'Launcher build failed.' }

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    "$root\tools\make_release.ps1" `
    -Version $Version `
    -RunnerBuildDir $RunnerBuildDir `
    -LauncherBuildDir $LauncherBuildDir `
    -RuntimeBinDir $RuntimeBinDir `
    -SdlBackend $SdlBackend
  if ($LASTEXITCODE -ne 0) { throw 'Release packaging failed.' }
} finally {
  Pop-Location
}

<#
Build Metroid Prime Hunters Recomp for one configured retail revision.

US1_0 keeps the existing release paths. EU1_1 uses isolated generated banks,
a revision-specific game config, a profile-specific launcher identity/policy,
and the shared exact-ROM runtime-address shim for Prime Controls/direct mouse
aim.

Usage:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    tools\build-windows.ps1 -Version 0.3.0 -MphVersion EU1_1 `
    -RomPath 'D:\ROMs\Metroid Prime Hunters (Europe) (Rev 1).nds'
#>
param(
  [string]$Version = '0.1.0',
  [ValidateSet('US1_0', 'EU1_1')]
  [string]$MphVersion = 'US1_0',
  [string]$RomPath = '',
  [string]$CMake = 'C:\msys64\mingw64\bin\cmake.exe',
  [string]$Generator = 'Ninja',
  [int]$Jobs = 12,
  [string]$GameBuildDir = '',
  [string]$RunnerBuildDir = '',
  [string]$LauncherBuildDir = '',
  [string]$RuntimeBinDir = 'C:\msys64\mingw64\bin',
  [string]$RecompUiRoot = 'F:\Projects\recomp-ui'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$cmakePath = [IO.Path]::GetFullPath($CMake)
if (-not (Test-Path -LiteralPath $cmakePath)) {
  throw "CMake not found: $cmakePath"
}

$profileFile = Join-Path $root 'config\mph_rom_profiles.json'
$registry = Get-Content -LiteralPath $profileFile -Raw | ConvertFrom-Json
$profileProperty = $registry.profiles.PSObject.Properties[$MphVersion]
if ($null -eq $profileProperty) {
  throw "Unknown MPH profile: $MphVersion"
}
$profile = $profileProperty.Value
$romSha1 = [string]$profile.sha1
$region = [string]$profile.region
$launcherDefaultRom = [string]$profile.launcher_default_rom
$launcherAdaptive = if ([bool]$profile.adaptive_widescreen) { 'ON' } else { 'OFF' }
$gameConfig = [IO.Path]::GetFullPath(
  (Join-Path $root ([string]$profile.game_config)))

if ([string]::IsNullOrWhiteSpace($RomPath)) {
  $RomPath = Join-Path $root $launcherDefaultRom
}
$romFull = [IO.Path]::GetFullPath($RomPath)
if (-not (Test-Path -LiteralPath $romFull)) {
  throw "ROM not found: $romFull"
}

if ([string]::IsNullOrWhiteSpace($GameBuildDir)) {
  if ($MphVersion -eq 'US1_0') {
    $GameBuildDir = 'build-release'
  } else {
    $GameBuildDir = "build-release-$MphVersion"
  }
}
if ([string]::IsNullOrWhiteSpace($RunnerBuildDir)) {
  if ($MphVersion -eq 'US1_0') {
    $RunnerBuildDir = '..\ndsrecomp\runner\build-mph-release'
  } else {
    $RunnerBuildDir = "..\ndsrecomp\runner\build-mph-release-$MphVersion"
  }
}
if ([string]::IsNullOrWhiteSpace($LauncherBuildDir)) {
  if ($MphVersion -eq 'US1_0') {
    $LauncherBuildDir = 'launcher\recomp-ui\build-release'
  } else {
    $LauncherBuildDir = "launcher\recomp-ui\build-release-$MphVersion"
  }
}

$frameworkRoot = [IO.Path]::GetFullPath((Join-Path $root '..\ndsrecomp'))
$gameBuild = [IO.Path]::GetFullPath((Join-Path $root $GameBuildDir))
$runnerBuild = [IO.Path]::GetFullPath((Join-Path $root $RunnerBuildDir))
$launcherBuild = [IO.Path]::GetFullPath((Join-Path $root $LauncherBuildDir))
if ($MphVersion -eq 'US1_0') {
  $titleBankDir = [IO.Path]::GetFullPath((Join-Path $root 'generated\recomp'))
} else {
  $titleBankDir = [IO.Path]::GetFullPath(
    (Join-Path $root "generated\$MphVersion\recomp"))
}

$patchPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $patchPython)) {
  $patchPython = 'python'
}

Push-Location $root
try {
  Write-Host "Building MPH profile $MphVersion ($($profile.game_code) rev $($profile.revision))"
  Write-Host "Launcher adaptive widescreen: $launcherAdaptive"

  & $cmakePath -G $Generator -S $root -B $gameBuild `
    -DCMAKE_BUILD_TYPE=Release `
    -DNDSRECOMP_ROOT="$frameworkRoot" `
    -DMPH_VERSION="$MphVersion" `
    -DMPH_ROM="$romFull"
  if ($LASTEXITCODE -ne 0) { throw 'Game CMake configure failed.' }

  & $cmakePath --build $gameBuild --target metroidprimehuntersrecomp -j $Jobs
  if ($LASTEXITCODE -ne 0) { throw 'Game bank build failed.' }

  & $patchPython "$root\tools\patch_ndsrecomp_mph_runtime.py" `
    --framework-root "$frameworkRoot" --profiles "$profileFile"
  if ($LASTEXITCODE -ne 0) { throw 'ndsrecomp MPH runtime-profile patch failed.' }

  & $cmakePath -G $Generator -S "$frameworkRoot\runner" -B $runnerBuild `
    -DCMAKE_BUILD_TYPE=Release `
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
    -DCMAKE_PREFIX_PATH="$RuntimeBinDir\..\lib\cmake" `
    "-DMPH_LAUNCHER_ROM_SHA1=$romSha1" `
    "-DMPH_LAUNCHER_REGION=$region" `
    "-DMPH_LAUNCHER_DEFAULT_ROM=$launcherDefaultRom" `
    "-DMPH_LAUNCHER_ADAPTIVE_WIDESCREEN=$launcherAdaptive"
  if ($LASTEXITCODE -ne 0) { throw 'Launcher CMake configure failed.' }

  & $cmakePath --build $launcherBuild -j $Jobs
  if ($LASTEXITCODE -ne 0) { throw 'Launcher build failed.' }

  $releaseArgs = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
    "$root\tools\make_release.ps1",
    '-Version', $Version,
    '-RunnerBuildDir', $RunnerBuildDir,
    '-LauncherBuildDir', $LauncherBuildDir,
    '-RuntimeBinDir', $RuntimeBinDir,
    '-GameConfig', $gameConfig,
    '-Profile', $MphVersion
  )
  if (-not [bool]$profile.fmv_runtime) {
    $releaseArgs += '-AllowNoFmvRuntime'
  }
  & powershell.exe @releaseArgs
  if ($LASTEXITCODE -ne 0) { throw 'Release packaging failed.' }
} finally {
  Pop-Location
}

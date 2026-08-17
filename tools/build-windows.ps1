<#
Build Metroid Prime Hunters Recomp for one configured retail revision.

US1_0 keeps the existing release path, including the recomp-ui launcher and
portable ZIP. Other profiles currently build the title banks and runner only;
they are bring-up builds until their title-specific runtime hooks are validated.

Usage:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    tools\build-windows.ps1 -Version 0.3.0 -MphVersion EU1_1
#>
param(
  [string]$Version = '0.1.0',
  [ValidateSet('US1_0', 'EU1_1')]
  [string]$MphVersion = 'US1_0',
  [string]$CMake = 'C:\msys64\mingw64\bin\cmake.exe',
  [string]$Generator = 'Ninja',
  [int]$Jobs = 12,
  [string]$GameBuildDir = '',
  [string]$RunnerBuildDir = '',
  [string]$LauncherBuildDir = 'launcher\recomp-ui\build-release',
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

Push-Location $root
try {
  Write-Host "Building MPH profile $MphVersion ($($profile.game_code) rev $($profile.revision))"

  & $cmakePath -G $Generator -S $root -B $gameBuild `
    -DCMAKE_BUILD_TYPE=Release `
    -DNDSRECOMP_ROOT="$frameworkRoot" `
    -DMPH_VERSION="$MphVersion"
  if ($LASTEXITCODE -ne 0) { throw 'Game CMake configure failed.' }

  & $cmakePath --build $gameBuild --target metroidprimehuntersrecomp -j $Jobs
  if ($LASTEXITCODE -ne 0) { throw 'Game bank build failed.' }

  & $cmakePath -G $Generator -S "$frameworkRoot\runner" -B $runnerBuild `
    -DCMAKE_BUILD_TYPE=Release `
    -DNDS_BOOTSTRAP_FIRMWARE=ON `
    "-DNDS_TITLE_BANK_DIR=$titleBankDir" `
    "-DNDS_TITLE_ROM_SHA1=$romSha1"
  if ($LASTEXITCODE -ne 0) { throw 'Runner CMake configure failed.' }

  & $cmakePath --build $runnerBuild -j $Jobs
  if ($LASTEXITCODE -ne 0) { throw 'Runner build failed.' }

  if ($MphVersion -ne 'US1_0') {
    $gameConfig = [IO.Path]::GetFullPath(
      (Join-Path $root ([string]$profile.game_config)))
    Write-Host ''
    Write-Host "Bring-up runner built: $runnerBuild\nds_runner.exe"
    Write-Host "Use the revision-specific config: $gameConfig"
    Write-Host 'Launcher/release packaging intentionally skipped for this profile.'
    Write-Host 'Prime Controls and direct mouse aim remain USA-only until revision addresses are validated.'
    return
  }

  & $cmakePath -G $Generator -S "$root\launcher\recomp-ui" -B $launcherBuild `
    -DCMAKE_BUILD_TYPE=Release `
    -DRECOMP_UI_ROOT="$RecompUiRoot" `
    -DCMAKE_PREFIX_PATH="$RuntimeBinDir\..\lib\cmake"
  if ($LASTEXITCODE -ne 0) { throw 'Launcher CMake configure failed.' }

  & $cmakePath --build $launcherBuild -j $Jobs
  if ($LASTEXITCODE -ne 0) { throw 'Launcher build failed.' }

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    "$root\tools\make_release.ps1" `
    -Version $Version `
    -RunnerBuildDir $RunnerBuildDir `
    -LauncherBuildDir $LauncherBuildDir `
    -RuntimeBinDir $RuntimeBinDir
  if ($LASTEXITCODE -ne 0) { throw 'Release packaging failed.' }
} finally {
  Pop-Location
}

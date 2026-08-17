<#
Package a completed Metroid Prime Hunters Recomp Windows release.

The ZIP contains the portable recomp-ui launcher, the title runner, launcher
assets, the selected revision's game config, documentation, and MinGW/SDL
dependencies. ROMs, BIOS/firmware, saves, raw captures, and generated source
are never staged.

US1_0 keeps the historical release name and requires the validated FMV runtime
bank. Other revision profiles may opt out of that bank until a revision-
specific runtime capture has been produced.
#>
param(
  [Parameter(Mandatory = $true)][string]$Version,
  [string]$RunnerBuildDir = '..\ndsrecomp\runner\build-mph-release',
  [string]$LauncherBuildDir = 'launcher\recomp-ui\build-release',
  [string]$RuntimeBinDir = 'C:\msys64\mingw64\bin',
  [string]$GameConfig = 'game.toml',
  [string]$Profile = 'US1_0',
  [switch]$AllowNoFmvRuntime
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runnerBuild = [IO.Path]::GetFullPath((Join-Path $root $RunnerBuildDir))
$launcherBuild = [IO.Path]::GetFullPath((Join-Path $root $LauncherBuildDir))
$runner = Join-Path $runnerBuild 'nds_runner.exe'
$launcher = Join-Path $launcherBuild 'mph-recomp-ui.exe'
$assets = Join-Path $launcherBuild 'assets'
$gameConfigPath = if ([IO.Path]::IsPathRooted($GameConfig)) {
  [IO.Path]::GetFullPath($GameConfig)
} else {
  [IO.Path]::GetFullPath((Join-Path $root $GameConfig))
}

foreach ($required in @($runner, $launcher, $assets, $gameConfigPath)) {
  if (-not (Test-Path -LiteralPath $required)) {
    throw "Release input missing: $required"
  }
}

if (-not $AllowNoFmvRuntime) {
  # A US1.0 static-only runner is functional but drops the opening movies to
  # roughly half speed. Keep the established release gate for that profile.
  $runnerText = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($runner))
  if (-not $runnerText.Contains('mph_arm9_fmv_runtime')) {
    throw 'Runner does not contain the MPH FMV runtime bank.'
  }
}

$projectText = Get-Content (Join-Path $root 'CMakeLists.txt') -Raw
if ($projectText -notmatch
    "project\(MetroidPrimeHuntersRecomp VERSION $([regex]::Escape($Version)) ") {
  throw "CMake project version does not match release $Version."
}

$out = Join-Path $root 'release-stage'
if ($Profile -eq 'US1_0') {
  $stageName = "MetroidPrimeHuntersRecomp-windows-x64-v$Version"
} else {
  $stageName = "MetroidPrimeHuntersRecomp-$Profile-windows-x64-v$Version"
}
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
Copy-Item -LiteralPath $gameConfigPath `
  -Destination (Join-Path $stage 'game.toml')
Copy-Item -LiteralPath (Join-Path $root 'README.md') -Destination $stage
Copy-Item -LiteralPath (Join-Path $root 'LICENSE') -Destination $stage
Copy-Item -LiteralPath (Join-Path $root 'packaging\BIOS_README.txt') `
  -Destination (Join-Path $stage 'bios\README.txt')

$runtimeDlls = @(
  'SDL2.dll',
  'libgcc_s_seh-1.dll',
  'libstdc++-6.dll',
  'libwinpthread-1.dll'
)
foreach ($name in $runtimeDlls) {
  $source = Join-Path $RuntimeBinDir $name
  if (-not (Test-Path -LiteralPath $source)) {
    throw "Required runtime DLL missing: $source"
  }
  Copy-Item -LiteralPath $source -Destination $stage
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

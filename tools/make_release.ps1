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
  [string]$RuntimeBinDir = 'C:\msys64\mingw64\bin'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runnerBuild = [IO.Path]::GetFullPath((Join-Path $root $RunnerBuildDir))
$launcherBuild = [IO.Path]::GetFullPath((Join-Path $root $LauncherBuildDir))
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
$root = Split-Path -Parent $PSScriptRoot
$runner = Join-Path ([IO.Path]::GetFullPath((Join-Path $root $RunnerBuildDir))) 'nds_runner.exe'
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

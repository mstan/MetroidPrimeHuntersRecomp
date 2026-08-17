<#
Package a ROM-free Metroid Prime Hunters Recomp Windows Nightly.

Unlike tools/make_release.ps1, this packager intentionally does not require a
ROM-derived MPH/FMV native bank. The title executes through Tier-3 when no
content-specific optimization bank exists. FreeBIOS native banks are built from
the redistributable BSD-2-Clause FreeBIOS source path.
#>
param(
  [Parameter(Mandatory = $true)][string]$Version,
  [Parameter(Mandatory = $true)][string]$RunnerBuildDir,
  [Parameter(Mandatory = $true)][string]$LauncherBuildDir,
  [Parameter(Mandatory = $true)][string]$RuntimeBinDir,
  [string]$OutputDir = 'release-stage'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runnerBuild = [IO.Path]::GetFullPath((Join-Path $root $RunnerBuildDir))
$launcherBuild = [IO.Path]::GetFullPath((Join-Path $root $LauncherBuildDir))
$runtimeBin = [IO.Path]::GetFullPath($RuntimeBinDir)
$runner = Join-Path $runnerBuild 'nds_runner.exe'
$launcher = Join-Path $launcherBuild 'mph-recomp-ui.exe'
$assets = Join-Path $launcherBuild 'assets'

foreach ($required in @($runner, $launcher, $assets)) {
  if (-not (Test-Path -LiteralPath $required)) {
    throw "Nightly input missing: $required"
  }
}

$projectText = Get-Content (Join-Path $root 'CMakeLists.txt') -Raw
if ($projectText -notmatch
    "project\(MetroidPrimeHuntersRecomp VERSION $([regex]::Escape($Version)) ") {
  throw "CMake project version does not match Nightly package $Version."
}

# A ROM-free Nightly must not accidentally link a title-specific generated
# bank. The symbols are intentionally left visible in MinGW builds; reject the
# known MPH bank identities if they ever leak back into this package path.
$runnerText = [Text.Encoding]::ASCII.GetString([IO.File]::ReadAllBytes($runner))
foreach ($forbiddenBank in @('g_dispatch_mph_arm9', 'g_dispatch_mph_arm7',
                             'mph_arm9_fmv_runtime')) {
  if ($runnerText.Contains($forbiddenBank)) {
    throw "ROM-free Nightly unexpectedly contains title bank: $forbiddenBank"
  }
}

$out = [IO.Path]::GetFullPath((Join-Path $root $OutputDir))
$stageName = "MetroidPrimeHuntersRecomp-windows-x64-v$Version"
$stage = Join-Path $out $stageName
$zip = Join-Path $out "$stageName.zip"

if (Test-Path -LiteralPath $stage) { Remove-Item $stage -Recurse -Force }
if (Test-Path -LiteralPath $zip) { Remove-Item $zip -Force }
New-Item -ItemType Directory -Path $stage -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage 'bios') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $stage 'cache\banks') -Force | Out-Null

Copy-Item -LiteralPath $launcher -Destination (Join-Path $stage 'MetroidPrimeHuntersRecomp.exe')
Copy-Item -LiteralPath $runner -Destination $stage
Copy-Item -LiteralPath $assets -Destination $stage -Recurse
Copy-Item -LiteralPath (Join-Path $root 'game.toml') -Destination $stage
Copy-Item -LiteralPath (Join-Path $root 'README.md') -Destination $stage
Copy-Item -LiteralPath (Join-Path $root 'LICENSE') -Destination $stage
Copy-Item -LiteralPath (Join-Path $root 'packaging\BIOS_README.txt') `
  -Destination (Join-Path $stage 'bios\README.txt')
Copy-Item -LiteralPath (Join-Path $root 'packaging\CACHE_README.txt') `
  -Destination (Join-Path $stage 'cache\banks\README.txt')

$runtimeDlls = @(
  'SDL2.dll',
  'libgcc_s_seh-1.dll',
  'libstdc++-6.dll',
  'libwinpthread-1.dll'
)
foreach ($name in $runtimeDlls) {
  $source = Join-Path $runtimeBin $name
  if (-not (Test-Path -LiteralPath $source)) {
    throw "Required MinGW runtime DLL missing: $source"
  }
  Copy-Item -LiteralPath $source -Destination $stage
}

$forbidden = @(Get-ChildItem -LiteralPath $stage -File -Recurse |
  Where-Object {
    $_.Extension.ToLowerInvariant() -in @('.nds', '.sav', '.dsv', '.gpr') -or
    $_.Name.ToLowerInvariant() -in @('biosnds9.rom', 'biosnds7.rom', 'firmware.bin') -or
    $_.FullName -match '[\\/](generated|capture|captures|saves)[\\/]'
  })
if ($forbidden.Count -ne 0) {
  throw "Nightly stage contains forbidden material: $($forbidden.FullName -join ', ')"
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$stageFull = [IO.Path]::GetFullPath($stage)
$stagePrefix = $stageFull.TrimEnd('\') + '\'
$files = @(Get-ChildItem -LiteralPath $stage -File -Recurse | Sort-Object FullName)
$archive = [IO.Compression.ZipFile]::Open(
  $zip, [IO.Compression.ZipArchiveMode]::Create)
try {
  foreach ($file in $files) {
    $fileFull = [IO.Path]::GetFullPath($file.FullName)
    if (-not $fileFull.StartsWith($stagePrefix,
        [StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to archive a file outside release stage: $fileFull"
    }
    $entryName = $fileFull.Substring($stagePrefix.Length).Replace('\', '/')
    if ($entryName.StartsWith('/') -or $entryName -match '(^|/)\.\.(/|$)') {
      throw "Unsafe ZIP entry name: $entryName"
    }
    [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
      $archive, $fileFull, $entryName,
      [IO.Compression.CompressionLevel]::Optimal) | Out-Null
  }
} finally {
  $archive.Dispose()
}

if (-not (Test-Path -LiteralPath $zip) -or (Get-Item $zip).Length -eq 0) {
  throw 'Nightly ZIP was not created.'
}
Get-FileHash -LiteralPath $zip -Algorithm SHA256 | Format-Table -AutoSize
Write-Host "Created $zip"

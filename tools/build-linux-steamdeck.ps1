<#
Build the Linux AppImage inside an Ubuntu 22.04 container.

This keeps the packaged runner and launcher on an older glibc baseline than a
rolling/current desktop build host. SteamOS 3.x systems that reject newer
GLIBC_2.38+ symbols should be able to load binaries built this way.

Usage:
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    tools\build-linux-steamdeck.ps1 -Version 0.4.4
#>
param(
  [string]$Version = '0.1.0',
  [int]$Jobs = 0,
  [string]$Image = 'mph-linux-steamdeck-builder:ubuntu22.04',
  [string]$Out = 'release-linux-steamdeck',
  [string]$NdsrecompRoot = '..\ndsrecomp',
  [string]$RecompUiRoot = '..\recomp-ui',
  [switch]$NoPackage,
  [switch]$SkipImageBuild
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Resolve-HostPath([string]$Path) {
  if ([IO.Path]::IsPathRooted($Path)) {
    $full = [IO.Path]::GetFullPath($Path)
  } else {
    $full = [IO.Path]::GetFullPath((Join-Path $root $Path))
  }
  $item = Get-Item -LiteralPath $full
  if ($item.LinkType -and $item.Target) {
    return [IO.Path]::GetFullPath($item.Target)
  }
  if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -and
      (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    $drive = $full.Substring(0, 1).ToLowerInvariant()
    $tail = $full.Substring(2).Replace('\', '/')
    $wslPath = "/mnt/$drive$tail"
    $wslResolved = (& wsl.exe readlink -f $wslPath).Trim()
    if ($wslResolved) {
      if ($wslResolved -match '^/mnt/([a-zA-Z])/(.*)$') {
        $winResolved = "$($Matches[1].ToUpperInvariant()):\$($Matches[2].Replace('/', '\'))"
      } else {
        $winResolved = (& wsl.exe wslpath -w $wslResolved).Trim()
      }
      if (Test-Path -LiteralPath $winResolved) {
        return (Get-Item -LiteralPath $winResolved).FullName
      }
    }
  }
  return $item.FullName
}

$frameworkRoot = Resolve-HostPath $NdsrecompRoot
$recompUiRoot = Resolve-HostPath $RecompUiRoot
$dockerfile = Join-Path $root 'packaging\linux\steamdeck.Dockerfile'

if (-not (Test-Path -LiteralPath (Join-Path $root 'Metroid Prime Hunters.nds'))) {
  throw "Verified ROM missing from repo root: $(Join-Path $root 'Metroid Prime Hunters.nds')"
}

if (-not $SkipImageBuild) {
  & docker build -t $Image -f $dockerfile (Split-Path -Parent $dockerfile)
  if ($LASTEXITCODE -ne 0) { throw 'Docker image build failed.' }
}

if ($Jobs -le 0) {
  $Jobs = [Math]::Max(1, [Environment]::ProcessorCount - 2)
}

$buildArgs = @(
  'bash', 'tools/build-linux.sh',
  '--version', $Version,
  '--jobs', [string]$Jobs,
  '--out', "/work/mph/$Out",
  '--ndsrecomp-root', '/work/ndsrecomp',
  '--recomp-ui-root', '/work/recomp-ui',
  '--build-flavor', 'steamdeck'
)
if ($NoPackage) {
  $buildArgs += '--no-package'
}

$dockerArgs = @(
  'run', '--rm',
  '-v', "${root}:/work/mph",
  '-v', "${frameworkRoot}:/work/ndsrecomp",
  '-v', "${recompUiRoot}:/work/recomp-ui",
  '-w', '/work/mph',
  '-e', 'NDSRECOMP_ROOT=/work/ndsrecomp',
  '-e', 'RECOMP_UI_ROOT=/work/recomp-ui',
  $Image
) + $buildArgs

& docker @dockerArgs
if ($LASTEXITCODE -ne 0) { throw 'Containerized Linux build failed.' }

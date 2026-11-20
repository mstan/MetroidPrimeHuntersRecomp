<#
Run a command in the Linux release build container with the standard mounts.

This is the one place that defines the Linux release container: the image
(the pinned release toolchain plus ccache, packaging/linux/
steamdeck-ccache.Dockerfile), the /work source mounts, the persistent
compiler cache and the extra git mounts that let the framework build id
resolve inside the container. tools/build-linux-steamdeck.ps1 uses it, and
step-wise release scripts can use it directly:

  powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    tools\run-linux-release-container.ps1 -ScriptsDir <dir> `
    -BiosDir <dir> -Env JOBS=8 -Command bash,/scripts/build-title-banks.sh

Mounts: repo -> /work/mph, framework -> /work/ndsrecomp, recomp-ui ->
/work/recomp-ui, cache -> /ccache, optional -BiosDir -> /bios (read-only),
optional -ScriptsDir -> /scripts (read-only).

The compiler cache lives on the host (-CompilerCacheDir, default
$env:MPH_LINUX_CCACHE_DIR or F:\ccache-linux; never the system drive) so it
survives containers and is shared by every worktree: the container paths are
always /work/..., so a fresh worktree at the same sources hits the cache.
ccache statistics are zeroed before and printed after the command.
#>
param(
  [Parameter(Mandatory = $true)]
  [string[]]$Command,
  [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
  [string]$NdsrecompRoot = 'ndsrecomp',
  [string]$RecompUiRoot = 'third_party\recomp-ui',
  [string]$Image = 'mph-linux-release14-ccache:ubuntu22.04',
  [string]$BaseImage = '',
  [switch]$SkipImageBuild,
  [string]$CompilerCacheDir = '',
  [string]$CompilerCacheMaxSize = '40G',
  [switch]$NoCompilerCache,
  [string]$BiosDir = '',
  [string]$ScriptsDir = '',
  [string]$Name = '',
  [string[]]$Env = @()
)

$ErrorActionPreference = 'Stop'
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)

function Resolve-HostPath([string]$Path) {
  if ([IO.Path]::IsPathRooted($Path)) {
    $full = [IO.Path]::GetFullPath($Path)
  } else {
    $full = [IO.Path]::GetFullPath((Join-Path $RepoRoot $Path))
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

# Windows PowerShell turns native stderr into error records when output is
# redirected (for example 2>&1 | Tee-Object); with 'Stop' that would abort on
# docker's normal progress output. Exit codes are checked explicitly instead.
function Invoke-Docker([string[]]$Arguments) {
  $saved = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { & docker @Arguments } finally { $ErrorActionPreference = $saved }
}

function Join-PosixPath([string]$Base, [string]$Relative) {
  $stack = New-Object System.Collections.Generic.List[string]
  foreach ($part in (($Base.TrimEnd('/') + '/' + $Relative.Replace('\', '/')) -split '/')) {
    if ($part -eq '' -or $part -eq '.') { continue }
    if ($part -eq '..') {
      if ($stack.Count -gt 0) { $stack.RemoveAt($stack.Count - 1) }
      continue
    }
    $stack.Add($part)
  }
  return '/' + ($stack -join '/')
}

function Test-UnderPath([string]$Path, [string]$Parent) {
  $p = $Path.TrimEnd('\') + '\'
  $q = $Parent.TrimEnd('\') + '\'
  return $p.StartsWith($q, [StringComparison]::OrdinalIgnoreCase)
}

# A git worktree or submodule checkout has a .git FILE naming its git dir,
# usually by a relative path. Inside the container that path resolves against
# the /work mount point, so mount the host git dir (and its common dir) where
# the relative path lands, and the checkout again where the git dir's
# core.worktree lands. NdsBuildIdScript.cmake then reads the real HEAD and
# clean/dirty state instead of falling back to "unknown".
function Get-GitMountArgs([string]$HostDir, [string]$ContainerDir) {
  $dotGit = Join-Path $HostDir '.git'
  if (-not (Test-Path -LiteralPath $dotGit -PathType Leaf)) { return @() }
  $line = (Get-Content -LiteralPath $dotGit -TotalCount 1).Trim()
  if ($line -notmatch '^gitdir:\s*(.+)$') { return @() }
  $gitdir = $Matches[1].Trim()
  if ($gitdir -match '^[A-Za-z]:' -or $gitdir.StartsWith('\\')) {
    Write-Warning "${HostDir}: .git names an absolute Windows git dir; git cannot resolve it inside the container."
    return @()
  }
  $hostGit = [IO.Path]::GetFullPath((Join-Path $HostDir $gitdir))
  $containerGit = Join-PosixPath $ContainerDir $gitdir
  $mounts = @('-v', "${hostGit}:${containerGit}:ro")

  $commonFile = Join-Path $hostGit 'commondir'
  if (Test-Path -LiteralPath $commonFile) {
    $common = (Get-Content -LiteralPath $commonFile -TotalCount 1).Trim()
    $hostCommon = [IO.Path]::GetFullPath((Join-Path $hostGit $common))
    if (-not (Test-UnderPath $hostGit $hostCommon) -and -not (Test-UnderPath $hostCommon $hostGit)) {
      $mounts += @('-v', "${hostCommon}:$(Join-PosixPath $containerGit $common):ro")
    } elseif (Test-UnderPath $hostGit $hostCommon) {
      # Worktree git dir inside its common dir: mount the common dir; the
      # nested worktree git dir mount above stays on top of it.
      $mounts = @('-v', "${hostCommon}:$(Join-PosixPath $containerGit $common):ro") + $mounts
    }
  }

  $worktree = $null
  try {
    $worktree = (& git config --file (Join-Path $hostGit 'config') --get core.worktree)
  } catch { $worktree = $null }
  if ($worktree) {
    $worktree = $worktree.Trim()
    if ($worktree -notmatch '^[A-Za-z]:' -and -not $worktree.StartsWith('/')) {
      $containerWorktree = Join-PosixPath $containerGit $worktree
      if ($containerWorktree -ne $ContainerDir) {
        $mounts += @('-v', "${HostDir}:${containerWorktree}:ro")
      }
    }
  }
  return $mounts
}

$frameworkRoot = Resolve-HostPath $NdsrecompRoot
$recompUiRoot = Resolve-HostPath $RecompUiRoot

if (-not $SkipImageBuild) {
  # The image recipe always comes from this script's own checkout.
  $dockerfile = Join-Path (Split-Path -Parent $PSScriptRoot) 'packaging\linux\steamdeck-ccache.Dockerfile'
  $build = @('build', '-t', $Image, '-f', $dockerfile)
  if ($BaseImage) { $build += @('--build-arg', "BASE_IMAGE=$BaseImage") }
  $build += (Split-Path -Parent $dockerfile)
  Invoke-Docker $build
  if ($LASTEXITCODE -ne 0) { throw 'Docker image build failed.' }
}

$dockerArgs = @('run', '--rm')
if ($Name) { $dockerArgs += @('--name', $Name) }
$dockerArgs += @(
  '-v', "${RepoRoot}:/work/mph",
  '-v', "${frameworkRoot}:/work/ndsrecomp",
  '-v', "${recompUiRoot}:/work/recomp-ui",
  '-w', '/work/mph',
  '-e', 'NDSRECOMP_ROOT=/work/ndsrecomp',
  '-e', 'RECOMP_UI_ROOT=/work/recomp-ui',
  '-e', 'GIT_CONFIG_COUNT=1',
  '-e', 'GIT_CONFIG_KEY_0=safe.directory',
  '-e', 'GIT_CONFIG_VALUE_0=*'
)
$dockerArgs += Get-GitMountArgs $frameworkRoot '/work/ndsrecomp'

if ($NoCompilerCache) {
  $dockerArgs += @('-e', 'CCACHE_DISABLE=1')
} else {
  if (-not $CompilerCacheDir) {
    $CompilerCacheDir = if ($env:MPH_LINUX_CCACHE_DIR) { $env:MPH_LINUX_CCACHE_DIR } else { 'F:\ccache-linux' }
  }
  $CompilerCacheDir = [IO.Path]::GetFullPath($CompilerCacheDir)
  $cacheDrive = [IO.Path]::GetPathRoot($CompilerCacheDir)
  if (-not (Test-Path -LiteralPath $cacheDrive)) {
    throw "Compiler cache drive $cacheDrive does not exist; pass -CompilerCacheDir or -NoCompilerCache."
  }
  if ($env:SystemDrive -and $cacheDrive.TrimEnd('\') -ieq $env:SystemDrive) {
    throw "Refusing a compiler cache on the system drive ($CompilerCacheDir); pass -CompilerCacheDir on another drive."
  }
  New-Item -ItemType Directory -Force -Path $CompilerCacheDir | Out-Null
  # No CCACHE_BASEDIR: the /work paths are identical for every worktree, and
  # base_dir would hand gcc relative paths, changing __FILE__ strings and so
  # the runner bytes versus an uncached build.
  $dockerArgs += @(
    '-v', "${CompilerCacheDir}:/ccache",
    '-e', 'CCACHE_DIR=/ccache',
    '-e', 'CCACHE_NOHASHDIR=1',
    '-e', "CCACHE_MAXSIZE=$CompilerCacheMaxSize"
  )
}
if ($BiosDir) {
  $dockerArgs += @('-v', "$([IO.Path]::GetFullPath($BiosDir)):/bios:ro")
}
if ($ScriptsDir) {
  $dockerArgs += @('-v', "$([IO.Path]::GetFullPath($ScriptsDir)):/scripts:ro")
}
foreach ($pair in $Env) { $dockerArgs += @('-e', $pair) }
$dockerArgs += $Image

if ($NoCompilerCache) {
  $dockerArgs += $Command
} else {
  # mph-ccache-run (packaging/linux/ccache-run.sh) zeroes the counters, runs
  # the command and prints this run's ccache statistics.
  $dockerArgs += @('mph-ccache-run') + $Command
}

Invoke-Docker $dockerArgs
if ($LASTEXITCODE -ne 0) { throw "Containerized command failed (exit $LASTEXITCODE)." }

<#
Shared definition of the live-overlay shard SURFACE.

Dot-source this from both tools\build_release_shard_cache.ps1 (which BUILDS the
release shard cache) and tools\make_release.ps1 (which SHIPS it). Everything a
shard's provider identity folds in is defined exactly once, here, because the
one failure mode that matters is the builder and the packager disagreeing:
psxrecomp shipped v0.11.2 with an empty overlay cache because the packager
re-derived the codegen tag independently and drifted from the compiler.

The identity itself is never recomputed in PowerShell. It is read out of
ndsrecomp's tools\compile_live_shards.py by importing that module in-process
and calling its own provider_identity(), the same way psxrecomp's
package_release.ps1 imports compile_overlays.py. A PowerShell reimplementation
would be a second definition, i.e. the drift this file exists to prevent.

NOTE: no param() block here on purpose. Dot-sourcing runs a param() block in
the CALLER's scope, which is how make_release.ps1 once clobbered $root/$runner
with empty strings (see the comment there).
#>

# The exact header closure a generated shard preprocesses: it includes
# runtime_arm.h, which includes runtime_arm_types.h out of the shared ARM core
# submodule, and nothing else beyond the C library.
#
# This list is LOAD-BEARING for the identity, not just for compilation.
# compile_live_shards.py::runtime_headers() globs *.h out of every
# --runtime-include directory and hashes all of them. Pointed at the in-tree
# recompiler\armv4t + external\arm-recomp-core\common pair that is 20 headers;
# pointed at the flattened toolchain include\ it is 2. Those hash differently,
# so a cache built against the in-tree directories can NEVER match the identity
# of a shipped install. The release cache is therefore built against the same
# flattened set the player's bundled toolchain gets.
$script:OverlayToolchainHeaderRelPaths = @(
  'recompiler\armv4t\runtime_arm.h',
  'external\arm-recomp-core\common\runtime_arm_types.h'
)

function Get-OverlayToolchainHeaders {
  param([Parameter(Mandatory = $true)][string]$NdsRoot)
  $paths = @()
  foreach ($rel in $script:OverlayToolchainHeaderRelPaths) {
    $path = Join-Path $NdsRoot $rel
    if (-not (Test-Path -LiteralPath $path)) {
      throw "Overlay toolchain header missing: $path (is the arm-recomp-core submodule checked out?)"
    }
    $paths += (Resolve-Path -LiteralPath $path).Path
  }
  return $paths
}

# Materialize the flattened include directory a shard is compiled against.
function New-OverlayToolchainIncludeDir {
  param(
    [Parameter(Mandatory = $true)][string]$NdsRoot,
    [Parameter(Mandatory = $true)][string]$Destination
  )
  New-Item -ItemType Directory -Path $Destination -Force | Out-Null
  foreach ($h in (Get-OverlayToolchainHeaders -NdsRoot $NdsRoot)) {
    Copy-Item -LiteralPath $h -Destination $Destination -Force
  }
  return [IO.Path]::GetFullPath($Destination)
}

# Compile settings the release cache is built with. Every one of them is folded
# into the provider identity, so the builder and the packager must agree on all
# of them or the shipped cache filters down to nothing.
function Get-ReleaseShardPolicy {
  return [ordered]@{
    Compiler           = 'gcc'
    GeneratedOpt       = '-O2'
    MaxFunctionBytes   = 512
    IncludeRoots       = $false
    MergeCacheSnapshots = $false
    MaxPages           = 6
    MinHits            = 8
  }
}

# A Python that is NOT the devkitPro MSYS build on PATH (that one mangles
# Windows paths and dies on argparse Path arguments). Returns @(exe, args...).
function Get-ShardPython {
  param([string]$PythonExe = '')
  if ($PythonExe) { return , @($PythonExe) }
  $py = Get-Command 'py.exe' -ErrorAction SilentlyContinue
  if ($py) { return , @($py.Source, '-3') }
  $fallback = 'C:\Users\Matthew\AppData\Local\Programs\Python\Python312\python.exe'
  if (Test-Path -LiteralPath $fallback) { return , @($fallback) }
  throw 'No usable Python found (need the Windows launcher py.exe or a CPython install; bare "python" on PATH is the devkitPro MSYS build and must not be used).'
}

<#
Provider identity of a gcc shard produced by, and consumable by, EXACTLY the
artifacts passed in. Computed by importing compile_live_shards.py and calling
its provider_identity(), so this can never drift from the compiler.
#>
function Get-ShardProviderIdentity {
  param(
    [Parameter(Mandatory = $true)][string]$CompileScript,
    [Parameter(Mandatory = $true)][string]$Recompiler,
    [Parameter(Mandatory = $true)][string]$IncludeDir,
    [Parameter(Mandatory = $true)][string]$Gcc,
    [hashtable]$Policy = $null,
    [string[]]$Python = $null
  )
  if (-not $Policy) { $Policy = @{} + (Get-ReleaseShardPolicy) }
  if (-not $Python) { $Python = Get-ShardPython }
  foreach ($required in @($CompileScript, $Recompiler, $Gcc)) {
    if (-not (Test-Path -LiteralPath $required)) {
      throw "Cannot compute the shard provider identity, input missing: $required"
    }
  }
  if (-not (Test-Path -LiteralPath $IncludeDir)) {
    throw "Cannot compute the shard provider identity, include dir missing: $IncludeDir"
  }
  $script = Join-Path ([IO.Path]::GetTempPath()) ("nds_shard_identity_{0}.py" -f $PID)
  $body = @"
import argparse, importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location('nds_compile_live_shards', r'$CompileScript')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
args = argparse.Namespace(
    compiler='$($Policy.Compiler)',
    gcc=r'$Gcc',
    tcc='tcc',
    recompiler=pathlib.Path(r'$Recompiler'),
    runtime_include=[pathlib.Path(r'$IncludeDir')],
    generated_opt='$($Policy.GeneratedOpt)',
    max_function_bytes=$($Policy.MaxFunctionBytes),
    include_roots=$(if ($Policy.IncludeRoots) { 'True' } else { 'False' }),
    merge_cache_snapshots=$(if ($Policy.MergeCacheSnapshots) { 'True' } else { 'False' }),
)
sys.stdout.write(mod.provider_identity(args))
"@
  Set-Content -LiteralPath $script -Value $body -Encoding ASCII
  try {
    $exe = $Python[0]
    $rest = @()
    if ($Python.Count -gt 1) { $rest = $Python[1..($Python.Count - 1)] }
    $identity = (& $exe @rest $script)
    if ($LASTEXITCODE -ne 0 -or -not $identity) {
      throw "provider_identity() failed (exit $LASTEXITCODE): $identity"
    }
    return ([string]$identity).Trim()
  } finally {
    Remove-Item -LiteralPath $script -Force -ErrorAction SilentlyContinue
  }
}

<#
Every shard in $CacheDir that was published by $Identity, as objects with
Path / Backend / Bank / Candidate.

The on-disk layout is <cache>\<backend>\<bank>_<candidate>.dll -- flat, with no
identity component in the path (the loader keys the backend off that immediate
parent directory name, so it must not gain a level). The identity lives in
live-index.json, which records provider_id per published capture, so that index
is what a per-identity filter has to read.
#>
function Get-ShardsForIdentity {
  param(
    [Parameter(Mandatory = $true)][string]$CacheDir,
    [Parameter(Mandatory = $true)][string]$Identity
  )
  $index = Join-Path $CacheDir 'live-index.json'
  if (-not (Test-Path -LiteralPath $index)) { return @() }
  $data = Get-Content -LiteralPath $index -Raw | ConvertFrom-Json
  $out = @()
  if (-not $data.captures) { return @() }
  foreach ($property in $data.captures.PSObject.Properties) {
    $entry = $property.Value
    if ($entry.provider_id -ne $Identity) { continue }
    if (-not $entry.dll) { continue }
    $path = $entry.dll -replace '/', '\'
    if (-not (Test-Path -LiteralPath $path)) { continue }
    $file = Get-Item -LiteralPath $path
    $out += [pscustomobject]@{
      Path      = $file.FullName
      Length    = $file.Length
      Backend   = $file.Directory.Name
      Bank      = $entry.page
      Cpu       = $entry.cpu
      Candidate = $entry.candidate_id
      Name      = $file.Name
    }
  }
  return @($out | Sort-Object Name -Unique)
}

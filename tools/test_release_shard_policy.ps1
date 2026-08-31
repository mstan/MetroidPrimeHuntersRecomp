param(
  [string]$NdsrecompRoot = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'overlay_shard_common.ps1')

function Require([bool]$Condition, [string]$Message) {
  if (-not $Condition) { throw "FAIL: $Message" }
  Write-Host "ok: $Message"
}

function Resolve-RepoPath([string]$Value, [string]$Base) {
  if ([IO.Path]::IsPathRooted($Value)) { return [IO.Path]::GetFullPath($Value) }
  return [IO.Path]::GetFullPath((Join-Path $Base $Value))
}

if (-not $NdsrecompRoot) {
  $workspace = Split-Path -Parent $root
  $NdsrecompRoot = Join-Path $workspace 'ndsrecomp'
}
$ndsRoot = Resolve-RepoPath $NdsrecompRoot $root
$compileScript = Join-Path $ndsRoot 'tools\compile_live_shards.py'
if (-not (Test-Path -LiteralPath $compileScript)) {
  throw "compile_live_shards.py not found: $compileScript"
}

$policy = @{} + (Get-ReleaseShardPolicy)
Require ($policy.Compiler -eq 'gcc') 'release shard cache uses gcc backend'
Require ($policy.IncludeRoots -eq $true) 'release shard policy includes root-map PCs'

$command = New-ReleaseShardCompileCommand `
  -Python @('C:\Python313\python.exe', '-3') `
  -CompileScript 'D:\src\compile_live_shards.py' `
  -IncludeDir 'D:\game\overlay_toolchain\include' `
  -RunnerBuild 'D:\runner\build' `
  -Recompiler 'D:\game\overlay_toolchain\nds_recompile.exe' `
  -Gcc 'C:\msys64\mingw64\bin\gcc.exe' `
  -Policy $policy
$expected = '"C:\Python313\python.exe" -3 "D:\src\compile_live_shards.py" --runtime-include "D:\game\overlay_toolchain\include" --runner-build "D:\runner\build" --recompiler "D:\game\overlay_toolchain\nds_recompile.exe" --compiler gcc --gcc "C:\msys64\mingw64\bin\gcc.exe" --generated-opt=-O2 --max-function-bytes 512 --max-pages 6 --min-hits 8 --include-roots'
Require ($command -eq $expected) 'prebuilt gcc autocompile command is exact'
Require (-not $command.Contains('--merge-cache-snapshots')) `
  'default prebuilt command does not merge stale cache snapshots'

$withoutRoots = @{} + $policy
$withoutRoots.IncludeRoots = $false
$withoutRootsCommand = New-ReleaseShardCompileCommand `
  -Python @('C:\Python313\python.exe', '-3') `
  -CompileScript 'D:\src\compile_live_shards.py' `
  -IncludeDir 'D:\game\overlay_toolchain\include' `
  -RunnerBuild 'D:\runner\build' `
  -Recompiler 'D:\game\overlay_toolchain\nds_recompile.exe' `
  -Gcc 'C:\msys64\mingw64\bin\gcc.exe' `
  -Policy $withoutRoots
Require (-not $withoutRootsCommand.Contains('--include-roots')) `
  'command helper still discriminates IncludeRoots=false'

$tmp = Join-Path ([IO.Path]::GetTempPath()) `
  ("mph_release_shard_policy_test_{0}" -f ([Guid]::NewGuid().ToString('N')))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
  $python = Get-ShardPython
  $rootOnlyProbe = Join-Path $tmp 'root_only_probe.py'
  $probe = @'
import argparse
import base64
import importlib.util
import pathlib
import sys

compile_script = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("nds_compile_live_shards", compile_script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

rom_sha1 = "1" * 40
page_base = 0x02000000
root = page_base + 0x100
raw = bytearray(4096 // 4 // 8)
bit = (root - page_base) // 4
raw[bit // 8] |= 1 << (bit % 8)
page = {
    "cpu": 9,
    "addr": f"0x{page_base:08X}",
    "sha1": "2" * 40,
    "executions": 11,
    "root_arm": base64.b64encode(bytes(raw)).decode("ascii"),
    "root_hits": [8],
    "entry_points": [],
}
manifest = {
    "rom_sha1": rom_sha1,
    "pages": {"entries": [page]},
}

args = argparse.Namespace(
    rom_sha1=rom_sha1,
    exclude_range=[],
    include_roots=False,
    min_hits=8,
)
without_roots = mod.collect_candidates(
    args, [(pathlib.Path("root-only.json"), manifest)], {9}, {}, {})
if without_roots:
    raise SystemExit("root-only manifest produced a candidate without include_roots")

args.include_roots = True
with_roots = mod.collect_candidates(
    args, [(pathlib.Path("root-only.json"), manifest)], {9}, {}, {})
if len(with_roots) != 1:
    raise SystemExit(f"expected one root-only candidate, got {len(with_roots)}")
entries = with_roots[0][3]
if len(entries) != 1:
    raise SystemExit(f"expected one entry, got {len(entries)}")
entry = entries[0]
if entry["addr"] != root or entry["mode"] != "arm" or entry["hits"] != 8:
    raise SystemExit(f"unexpected root entry: {entry!r}")
if "root" not in entry.get("kinds", []):
    raise SystemExit(f"root entry provenance missing: {entry!r}")
print("ok: root-only manifest qualifies only when include_roots is set")
'@
  Set-Content -LiteralPath $rootOnlyProbe -Value $probe -Encoding ASCII
  $pyExe = $python[0]
  $pyRest = @()
  if ($python.Count -gt 1) { $pyRest = $python[1..($python.Count - 1)] }
  & $pyExe @pyRest $rootOnlyProbe $compileScript
  if ($LASTEXITCODE -ne 0) {
    throw "root-only compile_live_shards.py probe failed with exit $LASTEXITCODE"
  }

  $emptyCache = Join-Path $tmp 'empty-cache'
  New-Item -ItemType Directory -Path $emptyCache | Out-Null
  $threw = $false
  try {
    Assert-ReleaseShardCacheUsable -CacheDir $emptyCache -Identity 'wanted' |
      Out-Null
  } catch {
    $threw = $_.Exception.Message.Contains('empty cache') -and
      $_.Exception.Message.Contains('0 DLL')
  }
  Require $threw 'packaging gate rejects an empty prebuilt cache'

  $oldWarningPreference = $WarningPreference
  $WarningPreference = 'SilentlyContinue'
  $allowed = @(Assert-ReleaseShardCacheUsable -CacheDir $emptyCache `
    -Identity 'wanted' -AllowNoShardCache)
  $WarningPreference = $oldWarningPreference
  Require ($allowed.Count -eq 0) `
    'packaging gate can explicitly flag and skip a cache when allowed'

  $mismatched = Join-Path $tmp 'mismatched-cache'
  New-Item -ItemType Directory -Path (Join-Path $mismatched 'gcc') |
    Out-Null
  $dll = Join-Path $mismatched 'gcc\page_candidate.dll'
  Set-Content -LiteralPath $dll -Value 'not a real dll' -Encoding ASCII
  $index = @{
    captures = @{
      one = @{
        provider_id = 'other'
        dll = $dll.Replace('\', '/')
        page = '0x02000000'
        cpu = 9
        candidate_id = 'one'
      }
    }
  } | ConvertTo-Json -Depth 6
  Set-Content -LiteralPath (Join-Path $mismatched 'live-index.json') `
    -Value $index -Encoding UTF8
  $threw = $false
  try {
    Assert-ReleaseShardCacheUsable -CacheDir $mismatched -Identity 'wanted' |
      Out-Null
  } catch {
    $threw = $_.Exception.Message.Contains('empty cache') -and
      $_.Exception.Message.Contains('1 DLL')
  }
  Require $threw 'packaging gate rejects a cache with only wrong-identity DLLs'

  $matching = @(Assert-ReleaseShardCacheUsable -CacheDir $mismatched `
    -Identity 'other')
  Require ($matching.Count -eq 1 -and $matching[0].Backend -eq 'gcc') `
    'packaging gate returns matching prebuilt shards'

  $buildWindows = Get-Content -LiteralPath (Join-Path $PSScriptRoot `
    'build-windows.ps1') -Raw
  foreach ($paramName in @('NdsrecompRoot', 'RecompilerBuildDir',
      'ShardCacheDir', 'ShardPerformanceGate', 'Gcc', 'PythonExe',
      'AllowNoShardCache')) {
    Require ($buildWindows -match "(?m)\[.*\]\`$$paramName\b") `
      "build-windows exposes $paramName for release packaging"
    Require ($buildWindows -match "(?m)-$paramName\s+\`$$paramName\b" -or
        $buildWindows -match "(?m)-$paramName`:\`$$paramName\b") `
      "build-windows forwards $paramName to make_release"
  }
  $makeRelease = Get-Content -LiteralPath (Join-Path $PSScriptRoot `
    'make_release.ps1') -Raw
  Require ($makeRelease.Contains('shard_performance_gate.py')) `
    'Windows packager verifies the measured shard performance gate'
  Require ($makeRelease.Contains('verify-package')) `
    'Windows packager binds the gate to the staged shard inventory'
  $buildLinux = Get-Content -LiteralPath (Join-Path $PSScriptRoot `
    'build-linux.sh') -Raw
  Require ($buildLinux.Contains('shard_performance_gate.py')) `
    'Linux packager verifies the measured shard performance gate'
} finally {
  $tmpFull = [IO.Path]::GetFullPath($tmp)
  $systemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
  if ($tmpFull.StartsWith($systemTemp, [StringComparison]::OrdinalIgnoreCase) -and
      (Test-Path -LiteralPath $tmpFull)) {
    Remove-Item -LiteralPath $tmpFull -Recurse -Force
  }
}

Write-Host 'release shard policy: all assertions hold'

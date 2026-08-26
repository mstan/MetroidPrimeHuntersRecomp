<#
Assert that a built nds_runner binary contains EVERY bank this project
declares.

Releases v0.4.12/v0.4.13/v0.5.0 shipped without the 63 ingested coverage
banks: CMake silently skipped banks whose capture image was absent, and the
packaging script only grepped the runner for the single string
"mph_arm9_fmv_runtime" -- which is present even when every other bank is
missing. This script replaces that one-string smoke test with a full
inventory assertion derived from CMakeLists.txt itself.

The expected inventory is built exactly the way CMakeLists.txt builds it:

  * the mph_arm9 / mph_arm7 main closures (every "--bank <name>" literal),
  * every entry of MPH_OVERLAY_BANKS,
  * every entry of MPH_RUNTIME_BANKS,
  * every config/coverage_arm*.toml (globbed into MPH_RUNTIME_BANKS).

A bank is present in the binary iff the symbol "g_dispatch_<bank>_len"
appears in its bytes -- the per-bank dispatch table the recompiler emits.
That token is exact and collision-free (the bare bank name is not: it is a
substring of the sharded symbol names of unrelated banks, and "mph_arm9" is
a prefix of every mph_arm9_* bank).

Usage:
  powershell -File tools\verify_bank_inventory.ps1 -Runner <path\nds_runner.exe>
  powershell -File tools\verify_bank_inventory.ps1 -Runner <...> `
      -ManifestPath <stage>\bank-manifest.txt

Exits non-zero (throws) listing every missing identity.
#>
param(
  # Not [Mandatory]: make_release.ps1 dot-sources this file to pick up
  # Test-MphBankInventory, and a mandatory parameter would prompt there.
  [string]$Runner,
  [string]$RepoRoot,
  [string]$ManifestPath,
  [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

function Get-MphExpectedBanks {
  param([Parameter(Mandatory = $true)][string]$RepoRoot)

  $cmakeFile = Join-Path $RepoRoot 'CMakeLists.txt'
  if (-not (Test-Path -LiteralPath $cmakeFile)) {
    throw "CMakeLists.txt not found under repo root: $RepoRoot"
  }
  $cmake = Get-Content -LiteralPath $cmakeFile -Raw
  $configDir = Join-Path $RepoRoot 'config'

  $banks = [ordered]@{}
  $add = {
    param($name, $kind)
    if (-not $banks.Contains($name)) {
      $banks[$name] = $kind
    }
  }

  # Main closures: every literal "--bank <name>" argument in CMakeLists.txt
  # that is not a ${variable} expansion (those are the loop-driven banks
  # enumerated from their list variables below).
  foreach ($m in [regex]::Matches($cmake, '--bank\s+"?([A-Za-z0-9_]+)"?')) {
    & $add $m.Groups[1].Value 'main'
  }

  # set(MPH_OVERLAY_BANKS "<bank>:<shards>:<overlay-id>" ...)
  # set(MPH_RUNTIME_BANKS "<bank>:<shards>" ...)
  foreach ($listVar in @(
      @{ Name = 'MPH_OVERLAY_BANKS'; Kind = 'overlay' },
      @{ Name = 'MPH_RUNTIME_BANKS'; Kind = 'runtime' })) {
    $m = [regex]::Match(
      $cmake, "set\($($listVar.Name)\s*(?<body>[^)]*)\)")
    if (-not $m.Success) {
      throw "Could not parse set($($listVar.Name) ...) from CMakeLists.txt."
    }
    $entries = [regex]::Matches($m.Groups['body'].Value, '"([^"]+)"')
    if ($entries.Count -eq 0) {
      throw "set($($listVar.Name) ...) parsed but contained no banks."
    }
    foreach ($e in $entries) {
      & $add ($e.Groups[1].Value -split ':')[0] $listVar.Kind
    }
  }

  # file(GLOB MPH_INGESTED_RUNTIME_BANK_CONFIGS ... config/coverage_arm*.toml)
  $globMatch = [regex]::Match(
    $cmake,
    'file\(GLOB\s+MPH_INGESTED_RUNTIME_BANK_CONFIGS[^)]*?config/(?<pat>[^"]+)\.toml')
  if (-not $globMatch.Success) {
    throw 'Could not parse the ingested coverage bank glob from CMakeLists.txt.'
  }
  $globPattern = $globMatch.Groups['pat'].Value + '.toml'
  $ingested = @(Get-ChildItem -LiteralPath $configDir -Filter $globPattern -File |
    Sort-Object Name)
  if ($ingested.Count -eq 0) {
    throw "No config/$globPattern bank configs found under $configDir."
  }
  foreach ($cfg in $ingested) {
    & $add ([IO.Path]::GetFileNameWithoutExtension($cfg.Name)) 'coverage'
  }

  $result = @()
  foreach ($name in $banks.Keys) {
    $cfg = Join-Path $configDir "$name.toml"
    $programId = ''
    if (Test-Path -LiteralPath $cfg) {
      $idMatch = [regex]::Match(
        (Get-Content -LiteralPath $cfg -Raw), '(?m)^\s*id\s*=\s*"([^"]+)"')
      if ($idMatch.Success) { $programId = $idMatch.Groups[1].Value }
    }
    $result += [pscustomobject]@{
      Bank      = $name
      Kind      = $banks[$name]
      ProgramId = $programId
      Token     = "g_dispatch_${name}_len"
    }
  }
  return $result
}

function Test-MphBankInventory {
  param(
    [Parameter(Mandatory = $true)][string]$Runner,
    [Parameter(Mandatory = $true)][string]$RepoRoot,
    [string]$ManifestPath,
    [switch]$Quiet
  )

  if (-not (Test-Path -LiteralPath $Runner)) {
    throw "Runner binary not found: $Runner"
  }
  $expected = Get-MphExpectedBanks -RepoRoot $RepoRoot

  # Latin-1 maps every byte 1:1 to a char, so Contains() is a byte search.
  $bytes = [IO.File]::ReadAllBytes($Runner)
  $text = [Text.Encoding]::GetEncoding(28591).GetString($bytes)

  $missing = @()
  foreach ($b in $expected) {
    if (-not $text.Contains($b.Token)) { $missing += $b }
  }

  # Original FMV smoke test, kept as an explicit named check so its failure
  # message stays recognisable.
  if (-not $text.Contains('mph_arm9_fmv_runtime')) {
    throw 'Runner does not contain the MPH FMV runtime bank.'
  }

  if ($missing.Count -ne 0) {
    $lines = ($missing | ForEach-Object { "  $($_.Kind.PadRight(8)) $($_.Bank)" })
    throw ("Runner is missing $($missing.Count) of $($expected.Count) " +
      "declared banks -- this is NOT a release build:`n" +
      ($lines -join "`n") + "`n" +
      "Rebuild the runner against a fully populated tree (every " +
      "generated/capture/<bank>.bin present) before packaging.")
  }

  if ($ManifestPath) {
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $manifest = @(
      "Metroid Prime Hunters Recomp -- compiled bank inventory",
      "verified: $stamp",
      "runner:   $([IO.Path]::GetFileName($Runner))",
      "sha256:   $((Get-FileHash -LiteralPath $Runner -Algorithm SHA256).Hash)",
      "banks:    $($expected.Count)",
      ""
    )
    foreach ($kind in @('main', 'overlay', 'runtime', 'coverage')) {
      $group = @($expected | Where-Object { $_.Kind -eq $kind })
      if ($group.Count -eq 0) { continue }
      $manifest += "[$kind] $($group.Count)"
      foreach ($b in ($group | Sort-Object Bank)) {
        if ($b.ProgramId -and $b.ProgramId -ne $b.Bank) {
          $manifest += "  $($b.Bank)  (program id: $($b.ProgramId))"
        } else {
          $manifest += "  $($b.Bank)"
        }
      }
      $manifest += ""
    }
    Set-Content -LiteralPath $ManifestPath -Value $manifest -Encoding utf8
  }

  if (-not $Quiet) {
    $byKind = $expected | Group-Object Kind |
      ForEach-Object { "$($_.Count) $($_.Name)" }
    Write-Host ("Bank inventory OK: $($expected.Count) banks verified in " +
      "$([IO.Path]::GetFileName($Runner)) ($($byKind -join ', ')).")
  }
  return $expected
}

# Run standalone when invoked directly (dot-sourcing only defines the
# functions, which is how make_release.ps1 consumes this file).
if ($MyInvocation.InvocationName -ne '.') {
  if (-not $Runner) {
    throw 'verify_bank_inventory.ps1: -Runner <path to nds_runner.exe> is required.'
  }
  if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $PSScriptRoot }
  Test-MphBankInventory -Runner $Runner -RepoRoot $RepoRoot `
    -ManifestPath $ManifestPath -Quiet:$Quiet | Out-Null
}

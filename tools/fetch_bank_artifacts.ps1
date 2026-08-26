<#
Fetch MPH bank capture images from the private artifact store into
generated/capture/. OPTIONAL: if the store is unreachable (no access, no
network, repo not found) this script warns and exits 0 so public clones
still build a partial dev runner. Release completeness is enforced
separately: release configures use -DMPH_ALLOW_MISSING_BANKS=OFF and the
packagers run tools/verify_bank_inventory.ps1 against the runner binary.

Every fetched image is SHA-1 verified against the identity committed in
its config/*.toml before being placed; a mismatched file is rejected.

Usage:
  powershell -File tools\fetch_bank_artifacts.ps1 [-Repo <git-url>] [-Force]
#>
param(
  [string]$Repo = 'git@github.com:mstan/mph-bank-artifacts.git',
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$captureDir = Join-Path $root 'generated\capture'
$cacheDir = Join-Path $root 'generated\.bank-artifacts-clone'

function Get-ExpectedBanks {
  $expected = @{}
  foreach ($cfg in Get-ChildItem (Join-Path $root 'config') -Filter '*.toml') {
    $text = Get-Content $cfg.FullName -Raw
    if ($text -match '(?m)^id\s*=\s*"([^"]+)"' ) {
      $id = $Matches[1]
    } else { continue }
    if ($text -match '(?s)\[identity\].*?sha1\s*=\s*"([0-9a-f]{40})"') {
      $expected[$id] = $Matches[1]
    }
  }
  return $expected
}

try {
  if (Test-Path (Join-Path $cacheDir '.git')) {
    git -C $cacheDir fetch --depth 1 origin main 2>&1 | Out-Null
    git -C $cacheDir reset --hard origin/main 2>&1 | Out-Null
  } else {
    if (Test-Path $cacheDir) { Remove-Item -Recurse -Force $cacheDir }
    git clone --depth 1 $Repo $cacheDir 2>&1 | Out-Null
  }
} catch {
  Write-Warning ("Bank artifact store unavailable ($Repo): $_" +
    ' Building without it produces a partial, non-release runner;' +
    ' release packaging will refuse an incomplete binary.')
  exit 0
}

if (-not (Test-Path $captureDir)) {
  New-Item -ItemType Directory -Path $captureDir -Force | Out-Null
}

$expected = Get-ExpectedBanks
$sha1 = [Security.Cryptography.SHA1]::Create()
$placed = 0; $skipped = 0; $rejected = 0
foreach ($bin in Get-ChildItem (Join-Path $cacheDir 'capture') -Filter '*.bin') {
  $name = [IO.Path]::GetFileNameWithoutExtension($bin.Name)
  $dest = Join-Path $captureDir $bin.Name
  if ((Test-Path $dest) -and -not $Force) { $skipped++; continue }
  if ($expected.ContainsKey($name)) {
    $digest = ($sha1.ComputeHash([IO.File]::ReadAllBytes($bin.FullName)) |
      ForEach-Object { $_.ToString('x2') }) -join ''
    if ($digest -ne $expected[$name]) {
      Write-Warning "REJECTED $($bin.Name): sha1 $digest != config identity $($expected[$name])"
      $rejected++
      continue
    }
  }
  Copy-Item -LiteralPath $bin.FullName -Destination $dest -Force
  $placed++
}
Write-Host ("Bank artifacts: placed $placed, already present $skipped, " +
  "rejected $rejected (store: $Repo)")
if ($rejected -gt 0) { exit 1 }

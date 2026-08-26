#!/usr/bin/env bash
# Assert that a built nds_runner binary contains EVERY bank this project
# declares. Linux mirror of tools/verify_bank_inventory.ps1 -- same expected
# inventory, same token, same failure semantics.
#
# Releases v0.4.12/v0.4.13/v0.5.0 shipped without the 63 ingested coverage
# banks: CMake silently skipped banks whose capture image was absent, and the
# packaging scripts only checked for the single string "mph_arm9_fmv_runtime",
# which is present even when every other bank is missing.
#
# The expected inventory is derived from CMakeLists.txt exactly the way CMake
# builds it:
#   * every literal "--bank <name>" (the mph_arm9 / mph_arm7 main closures),
#   * every entry of MPH_OVERLAY_BANKS,
#   * every entry of MPH_RUNTIME_BANKS,
#   * every config/coverage_arm*.toml (globbed into MPH_RUNTIME_BANKS).
#
# A bank is present iff the symbol "g_dispatch_<bank>_len" appears in the
# binary -- the per-bank dispatch table the recompiler emits. The bare bank
# name is NOT a safe token: it is a substring of unrelated banks' sharded
# symbols, and "mph_arm9" is a prefix of every mph_arm9_* bank.
#
# Usage: bash tools/verify_bank_inventory.sh <runner-binary> [--repo <dir>]
#                                            [--manifest <out.txt>] [--quiet]
set -euo pipefail

BIN=""
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST=""
QUIET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --repo) REPO="$(cd "$2" && pwd)"; shift 2;;
    --manifest) MANIFEST="$2"; shift 2;;
    --quiet) QUIET=1; shift;;
    -h|--help) sed -n '2,26p' "$0"; exit 0;;
    -*) echo "unknown arg: $1" >&2; exit 2;;
    *) BIN="$1"; shift;;
  esac
done
[ -n "$BIN" ] || { echo "ERROR: runner binary argument required." >&2; exit 2; }
[ -f "$BIN" ] || { echo "ERROR: runner binary not found: $BIN" >&2; exit 1; }

CMAKE="$REPO/CMakeLists.txt"
CONFIG_DIR="$REPO/config"
[ -f "$CMAKE" ] || {
  echo "ERROR: CMakeLists.txt not found under repo root: $REPO" >&2
  exit 1
}

# Entries of a set(<NAME> "a:b" "c:d" ...) list, first colon field only.
cmake_bank_list() {
  awk -v want="set($1" '
    index($0, want) == 1 { inb = 1 }
    inb { print; if (index($0, ")")) exit }
  ' "$CMAKE" | grep -o '"[^"]*"' | tr -d '"' | cut -d: -f1
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

{
  grep -o -- '--bank [A-Za-z0-9_]\+' "$CMAKE" | awk '{print $2 "\tmain"}'
  cmake_bank_list MPH_OVERLAY_BANKS | sed 's/$/\toverlay/'
  cmake_bank_list MPH_RUNTIME_BANKS | sed 's/$/\truntime/'
  for cfg in "$CONFIG_DIR"/coverage_arm*.toml; do
    [ -e "$cfg" ] || continue
    b="$(basename "$cfg" .toml)"
    printf '%s\tcoverage\n' "$b"
  done
} | awk -F'\t' '!seen[$1]++' > "$WORK/expected"

for required in main overlay runtime coverage; do
  if ! grep -q "	$required\$" "$WORK/expected"; then
    echo "ERROR: parsed no '$required' banks from $CMAKE -- parser is stale." >&2
    exit 1
  fi
done

# One pass over the (large) binary rather than one grep per bank.
grep -ao 'g_dispatch_[A-Za-z0-9_]*_len' "$BIN" | sort -u > "$WORK/present"

MISSING="$WORK/missing"
: > "$MISSING"
while IFS=$'\t' read -r bank kind; do
  if ! grep -qxF "g_dispatch_${bank}_len" "$WORK/present"; then
    printf '  %-8s %s\n' "$kind" "$bank" >> "$MISSING"
  fi
done < "$WORK/expected"

# Original FMV smoke test, kept as an explicit named check.
grep -a -q mph_arm9_fmv_runtime "$BIN" || {
  echo "ERROR: runner does not contain the MPH FMV runtime bank." >&2
  exit 1
}

TOTAL="$(wc -l < "$WORK/expected" | tr -d ' ')"
NMISSING="$(wc -l < "$MISSING" | tr -d ' ')"
if [ "$NMISSING" != "0" ]; then
  {
    echo "ERROR: runner is missing $NMISSING of $TOTAL declared banks --" \
         "this is NOT a release build:"
    cat "$MISSING"
    echo "Rebuild the runner against a fully populated tree (every" \
         "generated/capture/<bank>.bin present) before packaging."
  } >&2
  exit 1
fi

if [ -n "$MANIFEST" ]; then
  {
    echo "Metroid Prime Hunters Recomp -- compiled bank inventory"
    echo "verified: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "runner:   $(basename "$BIN")"
    echo "sha256:   $(sha256sum "$BIN" | awk '{print $1}')"
    echo "banks:    $TOTAL"
    echo
    for kind in main overlay runtime coverage; do
      n="$(awk -F'\t' -v k="$kind" '$2 == k' "$WORK/expected" | wc -l |
        tr -d ' ')"
      [ "$n" != "0" ] || continue
      echo "[$kind] $n"
      awk -F'\t' -v k="$kind" '$2 == k {print "  " $1}' "$WORK/expected" |
        sort
      echo
    done
  } > "$MANIFEST"
fi

if [ "$QUIET" = "0" ]; then
  echo "Bank inventory OK: $TOTAL banks verified in $(basename "$BIN")."
fi

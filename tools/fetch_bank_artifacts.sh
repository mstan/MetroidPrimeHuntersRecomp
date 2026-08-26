#!/usr/bin/env bash
# Fetch MPH bank capture images from the private artifact store into
# generated/capture/. OPTIONAL: unreachable store => warning + exit 0 so
# public clones still build a partial dev runner. Release completeness is
# enforced by -DMPH_ALLOW_MISSING_BANKS=OFF configures and by
# tools/verify_bank_inventory.sh in the packagers.
# Every image is SHA-1 verified against its config/*.toml identity.
set -u
REPO="${1:-git@github.com:mstan/mph-bank-artifacts.git}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CAPTURE="$ROOT/generated/capture"
CACHE="$ROOT/generated/.bank-artifacts-clone"

if [ -d "$CACHE/.git" ]; then
  git -C "$CACHE" fetch --depth 1 origin main >/dev/null 2>&1 \
    && git -C "$CACHE" reset --hard origin/main >/dev/null 2>&1
else
  rm -rf "$CACHE"
  git clone --depth 1 "$REPO" "$CACHE" >/dev/null 2>&1
fi
if [ ! -d "$CACHE/capture" ]; then
  echo "warning: bank artifact store unavailable ($REPO)." \
       "Building without it produces a partial, non-release runner;" \
       "release packaging will refuse an incomplete binary." >&2
  exit 0
fi

mkdir -p "$CAPTURE"
placed=0 skipped=0 rejected=0
for bin in "$CACHE"/capture/*.bin; do
  [ -e "$bin" ] || continue
  name="$(basename "$bin" .bin)"
  dest="$CAPTURE/$(basename "$bin")"
  if [ -e "$dest" ] && [ "${FORCE:-0}" != "1" ]; then
    skipped=$((skipped+1)); continue
  fi
  cfg="$ROOT/config/$name.toml"
  if [ -f "$cfg" ]; then
    want="$(sed -n '/\[identity\]/,/^\[/{s/^sha1[[:space:]]*=[[:space:]]*"\([0-9a-f]\{40\}\)".*/\1/p;}' "$cfg" | head -1)"
    if [ -n "$want" ]; then
      got="$(sha1sum "$bin" | cut -d' ' -f1)"
      if [ "$got" != "$want" ]; then
        echo "warning: REJECTED $name: sha1 $got != config identity $want" >&2
        rejected=$((rejected+1)); continue
      fi
    fi
  fi
  cp -f "$bin" "$dest"; placed=$((placed+1))
done
echo "Bank artifacts: placed $placed, already present $skipped, rejected $rejected (store: $REPO)"
[ "$rejected" -eq 0 ] || exit 1

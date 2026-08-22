#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 /path/to/AppDir" >&2
  exit 2
fi

APPDIR="$(cd "$1" && pwd)"
test -x "$APPDIR/usr/bin/nds_runner"
test -x "$APPDIR/usr/bin/mph-recomp-ui"
test -f "$APPDIR/usr/bin/game.toml"
test -d "$APPDIR/usr/bin/assets"
test -f "$APPDIR/usr/bin/bios/README.txt"

for pattern in '*.nds' '*.NDS' '*.sav' '*.bin' '*.rom' '*.gpr' 'biosnds9.rom' 'biosnds7.rom' 'firmware.bin'; do
  found="$(find "$APPDIR" -name "$pattern" -print -quit)"
  if [ -n "$found" ]; then
    echo "forbidden private or generated payload in AppDir: $found" >&2
    exit 1
  fi
done
if find "$APPDIR" -path '*/generated/*' -print -quit | grep -q .; then
  echo "generated source leaked into AppDir" >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'chmod -R u+w "$APPDIR" "$tmp" 2>/dev/null || true; rm -rf "$tmp"' EXIT
chmod -R a-w "$APPDIR"

run_apprun() {
  local sim="$1"
  mkdir -p "$(dirname "$sim")"
  APPIMAGE="$sim" \
  SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
  timeout 10 "$APPDIR/AppRun" >/dev/null 2>&1 || true
}

state="$tmp/state"
run_apprun "$state/MetroidPrimeHuntersRecomp.AppImage"
test -f "$state/bios/README.txt" || {
  echo "BIOS README was not seeded beside the AppImage" >&2
  exit 1
}

for leak in keybinds.ini rom.cfg saves net_capture; do
  found="$(find "$APPDIR" -name "$leak" -print -quit)"
  if [ -n "$found" ]; then
    echo "state leaked into read-only AppDir: $found" >&2
    exit 1
  fi
done

echo "AppImage layout test passed"

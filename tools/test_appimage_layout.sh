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

probe_appdir="$tmp/AppDir-probe"
cp -a "$APPDIR" "$probe_appdir"
chmod -R u+w "$probe_appdir"
cat > "$probe_appdir/usr/bin/mph-recomp-ui" <<'EOF'
#!/bin/sh
{
  printf 'MPH_RECOMP_DATA_DIR=%s\n' "${MPH_RECOMP_DATA_DIR:-}"
  printf 'RECOMP_APPIMAGE_PATH=%s\n' "${RECOMP_APPIMAGE_PATH:-}"
  printf 'RECOMP_UI_BUILTIN_FILE_PICKER=%s\n' "${RECOMP_UI_BUILTIN_FILE_PICKER:-}"
  printf 'RECOMP_DISC_HINT=%s\n' "${RECOMP_DISC_HINT:-}"
} > "$MPH_RECOMP_PROBE"
EOF
chmod +x "$probe_appdir/usr/bin/mph-recomp-ui"

probe_state="$tmp/probe-state"
mkdir -p "$probe_state"
: > "$probe_state/Metroid Prime Hunters.nds"
MPH_RECOMP_PROBE="$probe_state/env.txt" \
APPIMAGE="$probe_state/MetroidPrimeHuntersRecomp.AppImage" \
"$probe_appdir/AppRun" >/dev/null 2>&1
grep -Fx "MPH_RECOMP_DATA_DIR=$probe_state" "$probe_state/env.txt" >/dev/null || {
  echo "AppRun did not anchor MPH_RECOMP_DATA_DIR beside the AppImage" >&2
  cat "$probe_state/env.txt" >&2
  exit 1
}
grep -Fx "RECOMP_APPIMAGE_PATH=$probe_state/MetroidPrimeHuntersRecomp.AppImage" "$probe_state/env.txt" >/dev/null || {
  echo "AppRun did not pass RECOMP_APPIMAGE_PATH to recomp-ui" >&2
  cat "$probe_state/env.txt" >&2
  exit 1
}
grep -Fx "RECOMP_UI_BUILTIN_FILE_PICKER=1" "$probe_state/env.txt" >/dev/null || {
  echo "AppRun did not force the built-in file picker" >&2
  cat "$probe_state/env.txt" >&2
  exit 1
}
grep -Fx "RECOMP_DISC_HINT=$probe_state/Metroid Prime Hunters.nds" "$probe_state/env.txt" >/dev/null || {
  echo "AppRun did not hint the adjacent ROM to recomp-ui" >&2
  cat "$probe_state/env.txt" >&2
  exit 1
}

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

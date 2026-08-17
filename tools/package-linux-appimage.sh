#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="0.4.0"
MPH_VERSION="US1_0"
RUNNER=""
OUT="$ROOT/release-stage"
APPIMAGE_TOOL="${APPIMAGE_TOOL:-appimagetool}"
LINUXDEPLOY_BIN="${LINUXDEPLOY_BIN:-linuxdeploy}"

usage() {
  cat <<'EOF'
Package an already-built MPH runner as a Linux x86_64 AppImage.

Usage:
  tools/package-linux-appimage.sh --runner PATH [options]

Options:
  --version VERSION       Package version
  --mph-version PROFILE   Content profile (default: US1_0)
  --runner PATH           Built nds_runner executable (required)
  --out PATH              Output directory (default: release-stage)
  --appimage-tool PATH    appimagetool executable/AppImage
  --linuxdeploy PATH      linuxdeploy executable/AppImage
EOF
}

while (($#)); do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --mph-version) MPH_VERSION="$2"; shift 2 ;;
    --runner) RUNNER="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --appimage-tool) APPIMAGE_TOOL="$2"; shift 2 ;;
    --linuxdeploy) LINUXDEPLOY_BIN="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$RUNNER" || ! -x "$RUNNER" ]]; then
  printf 'Built runner is required: %s\n' "$RUNNER" >&2
  exit 1
fi
if [[ ! -x "$APPIMAGE_TOOL" ]] && ! command -v "$APPIMAGE_TOOL" >/dev/null 2>&1; then
  printf 'appimagetool not found: %s\n' "$APPIMAGE_TOOL" >&2
  exit 1
fi
if [[ ! -x "$LINUXDEPLOY_BIN" ]] && ! command -v "$LINUXDEPLOY_BIN" >/dev/null 2>&1; then
  printf 'linuxdeploy not found: %s\n' "$LINUXDEPLOY_BIN" >&2
  exit 1
fi

PROFILE_FILE="$ROOT/config/mph_rom_profiles.json"
GAME_CONFIG_REL="$(python3 - "$PROFILE_FILE" "$MPH_VERSION" <<'PY'
import json, sys
registry = json.load(open(sys.argv[1], encoding='utf-8'))
profile = registry.get('profiles', {}).get(sys.argv[2])
if not isinstance(profile, dict):
    raise SystemExit(f'unknown MPH profile: {sys.argv[2]}')
print(profile['game_config'])
PY
)"
GAME_CONFIG="$ROOT/$GAME_CONFIG_REL"
[[ -f "$GAME_CONFIG" ]] || { printf 'Game config missing: %s\n' "$GAME_CONFIG" >&2; exit 1; }

mkdir -p "$OUT"
APP_NAME="MetroidPrimeHuntersRecomp"
APPDIR="$OUT/${APP_NAME}-${MPH_VERSION}-linux-x86_64.AppDir"
rm -rf "$APPDIR"
mkdir -p \
  "$APPDIR/usr/bin/bios" \
  "$APPDIR/usr/share/applications" \
  "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp "$RUNNER" "$APPDIR/usr/bin/nds_runner"
cp "$GAME_CONFIG" "$APPDIR/usr/bin/game.toml"
cp "$ROOT/README.md" "$APPDIR/usr/bin/README.md"
cp "$ROOT/LICENSE" "$APPDIR/usr/bin/LICENSE"
cp "$ROOT/packaging/BIOS_README.txt" "$APPDIR/usr/bin/bios/README.txt"
chmod 0755 "$APPDIR/usr/bin/nds_runner"

ICON="$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png"
python3 - "$ICON" <<'PY'
import struct, sys, zlib
out = sys.argv[1]
n = 256
raw = b''.join(bytes([0]) + bytes([162, 62, 64]) * n for _ in range(n))
def chunk(kind, data):
    body = kind + data
    return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)
png = b'\x89PNG\r\n\x1a\n'
png += chunk(b'IHDR', struct.pack('>IIBBBBB', n, n, 8, 2, 0, 0, 0))
png += chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
open(out, 'wb').write(png)
PY

DESKTOP="$APPDIR/usr/share/applications/$APP_NAME.desktop"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Metroid Prime Hunters Recomp
Exec=nds_runner
Icon=$APP_NAME
Categories=Game;
Terminal=false
EOF

# Let linuxdeploy collect the host libraries used by the runner. It may create
# its own AppRun; the title-specific wrapper below deliberately replaces it.
"$LINUXDEPLOY_BIN" --appimage-extract-and-run \
  --appdir "$APPDIR" \
  --executable "$APPDIR/usr/bin/nds_runner" \
  --desktop-file "$DESKTOP" \
  --icon-file "$ICON" >/dev/null

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export LD_LIBRARY_PATH="$HERE/usr/lib:${LD_LIBRARY_PATH:-}"
export SDL_JOYSTICK_HIDAPI_STEAM=1
export SDL_GAMECONTROLLER_ALLOW_STEAM_VIRTUAL_GAMEPAD=1
SELF="${APPIMAGE:-$0}"
RUNDIR="$(dirname "$(readlink -f "$SELF")")"
mkdir -p "$RUNDIR/bios" 2>/dev/null || true
if [ ! -f "$RUNDIR/bios/README.txt" ] && [ -f "$HERE/usr/bin/bios/README.txt" ]; then
  cp "$HERE/usr/bin/bios/README.txt" "$RUNDIR/bios/README.txt" 2>/dev/null || true
fi
ROM=""
for f in "$RUNDIR"/*.nds "$RUNDIR"/*.NDS; do
  [ -e "$f" ] && ROM="$f" && break
done
cd "$RUNDIR" 2>/dev/null || true
if [ "$#" -eq 0 ]; then
  if [ -n "$ROM" ]; then
    exec "$HERE/usr/bin/nds_runner" "$RUNDIR/bios" --interactive --rom "$ROM" \
      --config "$HERE/usr/bin/game.toml" --screen-layout separate \
      --adaptive-widescreen top --startup-mode automatic
  fi
  exec "$HERE/usr/bin/nds_runner" "$RUNDIR/bios" --interactive \
    --config "$HERE/usr/bin/game.toml" --screen-layout separate \
    --adaptive-widescreen top --startup-mode automatic
fi
exec "$HERE/usr/bin/nds_runner" "$@"
EOF
chmod 0755 "$APPDIR/AppRun"

# Safety gate: the AppDir may contain only the runner/package support material.
if find "$APPDIR" -type f \( \
    -iname '*.nds' -o -iname '*.sav' -o -iname '*.dsv' -o \
    -iname 'biosnds9.rom' -o -iname 'biosnds7.rom' -o -iname 'firmware.bin' \
  \) -print -quit | grep -q .; then
  echo 'Refusing to package ROM/save/BIOS/firmware material.' >&2
  exit 1
fi

if [[ "$MPH_VERSION" == "US1_0" ]]; then
  OUTPUT="$OUT/${APP_NAME}-linux-v${VERSION}-x86_64.AppImage"
else
  OUTPUT="$OUT/${APP_NAME}-${MPH_VERSION}-linux-v${VERSION}-x86_64.AppImage"
fi
rm -f "$OUTPUT"
ARCH=x86_64 "$APPIMAGE_TOOL" --appimage-extract-and-run "$APPDIR" "$OUTPUT" >/dev/null
chmod 0755 "$OUTPUT"
test -s "$OUTPUT"
sha256sum "$OUTPUT"
printf 'Created %s\n' "$OUTPUT"

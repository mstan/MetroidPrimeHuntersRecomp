#!/usr/bin/env bash
# Build Metroid Prime Hunters Recomp for a configured retail revision.
#
# US1_0 keeps the existing AppImage naming. EU1_1 uses isolated generated
# banks, its own game config, and the exact-ROM runtime-address shim used by
# Prime Controls/direct mouse aim.
set -euo pipefail

APP_NAME="MetroidPrimeHuntersRecomp"
TITLE_TARGET="metroidprimehuntersrecomp"
RUNNER_NAME="nds_runner"
VERSION="0.1.0"
MPH_VERSION="US1_0"
ROM_PATH=""
JOBS="$(nproc 2>/dev/null || echo 4)"
DO_PACKAGE=1

REPO="$(cd "$(dirname "$0")/.." && pwd)"
FRAMEWORK_ROOT="$(cd "$REPO/../ndsrecomp" && pwd)"
OUT="$REPO/release-linux"
PROFILE_FILE="$REPO/config/mph_rom_profiles.json"

while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="$2"; shift 2;;
    --mph-version) MPH_VERSION="$2"; shift 2;;
    --rom) ROM_PATH="$2"; shift 2;;
    --jobs) JOBS="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    --no-package) DO_PACKAGE=0; shift;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

profile_value() {
  python3 - "$PROFILE_FILE" "$MPH_VERSION" "$1" <<'PY'
import json
import sys
path, version, key = sys.argv[1:]
with open(path, encoding="utf-8") as f:
    registry = json.load(f)
try:
    value = registry["profiles"][version][key]
except KeyError as exc:
    raise SystemExit(f"unknown profile/field: {version}.{key}") from exc
if isinstance(value, bool):
    print("1" if value else "0")
else:
    print(value)
PY
}

ROM_SHA1="$(profile_value sha1)"
GAME_CONFIG_REL="$(profile_value game_config)"
FMV_RUNTIME="$(profile_value fmv_runtime)"
GAME_CONFIG="$REPO/$GAME_CONFIG_REL"
if [ -z "$ROM_PATH" ]; then
  ROM_PATH="$REPO/Metroid Prime Hunters.nds"
fi
ROM_PATH="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$ROM_PATH")"

if [ "$MPH_VERSION" = "US1_0" ]; then
  GAME_BUILD="$REPO/build-linux-release"
  RUNNER_BUILD="$FRAMEWORK_ROOT/runner/build-mph-linux-release"
  TITLE_BANK_DIR="$REPO/generated/recomp"
else
  GAME_BUILD="$REPO/build-linux-release-$MPH_VERSION"
  RUNNER_BUILD="$FRAMEWORK_ROOT/runner/build-mph-linux-release-$MPH_VERSION"
  TITLE_BANK_DIR="$REPO/generated/$MPH_VERSION/recomp"
fi

cd "$REPO"
test -f "$FRAMEWORK_ROOT/recompiler/CMakeLists.txt" || {
  echo "ERROR: sibling ndsrecomp checkout is missing." >&2
  exit 1
}
test -f "$ROM_PATH" || {
  echo "ERROR: Metroid Prime Hunters ROM is missing: $ROM_PATH" >&2
  exit 1
}
test -f "$GAME_CONFIG" || {
  echo "ERROR: game config for $MPH_VERSION is missing: $GAME_CONFIG" >&2
  exit 1
}

echo "[1/5] configure title banks ($MPH_VERSION)"
cmake -S "$REPO" -B "$GAME_BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DNDSRECOMP_ROOT="$FRAMEWORK_ROOT" \
  -DMPH_VERSION="$MPH_VERSION" \
  -DMPH_ROM="$ROM_PATH"
echo "[2/5] build title banks"
cmake --build "$GAME_BUILD" --target "$TITLE_TARGET" -j"$JOBS"

echo "[3/5] install exact-ROM MPH runtime profile into pinned ndsrecomp runner"
python3 "$REPO/tools/patch_ndsrecomp_mph_runtime.py" \
  --framework-root "$FRAMEWORK_ROOT" \
  --profiles "$PROFILE_FILE"

echo "[4/5] configure runner"
cmake -S "$FRAMEWORK_ROOT/runner" -B "$RUNNER_BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DNDS_BOOTSTRAP_FIRMWARE=ON \
  -DNDS_TITLE_BANK_DIR="$TITLE_BANK_DIR" \
  -DNDS_TITLE_ROM_SHA1="$ROM_SHA1"
echo "      build runner"
cmake --build "$RUNNER_BUILD" -j"$JOBS"

if [ "$DO_PACKAGE" = "0" ]; then
  echo "done: $RUNNER_BUILD/$RUNNER_NAME"
  echo "config: $GAME_CONFIG"
  exit 0
fi

BIN="$RUNNER_BUILD/$RUNNER_NAME"
test -f "$BIN" || { echo "ERROR: runner not built: $BIN" >&2; exit 1; }
if [ "$FMV_RUNTIME" = "1" ]; then
  strings "$BIN" | grep -q mph_arm9_fmv_runtime || {
    echo "ERROR: runner does not contain the MPH FMV runtime bank." >&2
    exit 1
  }
fi

LINUXDEPLOY_URL=https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage
LINUXDEPLOY_SHA=421ca71d5c69ea97c6309276232990d43df1dcece0edfaa26bbf926ff96ed12e
APPIMAGETOOL_URL=https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
APPIMAGETOOL_SHA=a6d71e2b6cd66f8e8d16c37ad164658985e0cf5fcaa950c90a482890cb9d13e0

TOOLS_DIR="$RUNNER_BUILD/appimage-tools"
mkdir -p "$TOOLS_DIR" "$OUT"
fetch_tool() {
  local url="$1" sha="$2" dest="$3"
  if [ ! -f "$dest" ] || [ "$(sha256sum "$dest" | awk '{print $1}')" != "$sha" ]; then
    curl -fL --retry 3 "$url" -o "$dest.tmp"
    printf '%s  %s\n' "$sha" "$dest.tmp" | sha256sum -c - >/dev/null
    mv "$dest.tmp" "$dest"
  fi
  chmod 0755 "$dest"
}
LINUXDEPLOY_BIN="$TOOLS_DIR/linuxdeploy-x86_64.AppImage"
APPIMAGETOOL_BIN="$TOOLS_DIR/appimagetool-x86_64.AppImage"
fetch_tool "$LINUXDEPLOY_URL" "$LINUXDEPLOY_SHA" "$LINUXDEPLOY_BIN"
fetch_tool "$APPIMAGETOOL_URL" "$APPIMAGETOOL_SHA" "$APPIMAGETOOL_BIN"

WORK="$(mktemp -d)"
trap 'chmod -R u+w "$WORK" 2>/dev/null || true; rm -rf "$WORK"' EXIT
APPDIR="$WORK/AppDir"
mkdir -p "$APPDIR/usr/bin/bios" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"

cp "$BIN" "$APPDIR/usr/bin/$RUNNER_NAME"
cp "$GAME_CONFIG" "$APPDIR/usr/bin/game.toml"
cp "$REPO/README.md" "$APPDIR/usr/bin/README.md"
cp "$REPO/LICENSE" "$APPDIR/usr/bin/LICENSE"
cp "$REPO/packaging/BIOS_README.txt" "$APPDIR/usr/bin/bios/README.txt"

python3 - "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png" <<'PY'
import struct, sys, zlib
out = sys.argv[1]
n = 256
raw = b''.join(bytes([0]) + bytes([162, 62, 64]) * n for _ in range(n))
def chunk(t, d):
    c = t + d
    return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
png = b"\x89PNG\r\n\x1a\n"
png += chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0))
png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
open(out, "wb").write(png)
PY
cat > "$APPDIR/usr/share/applications/$APP_NAME.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Metroid Prime Hunters Recomp
Exec=$RUNNER_NAME
Icon=$APP_NAME
Categories=Game;
Terminal=false
EOF

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
    exec "$HERE/usr/bin/nds_runner" "$RUNDIR/bios" --interactive --rom "$ROM" --config "$HERE/usr/bin/game.toml"
  fi
  exec "$HERE/usr/bin/nds_runner" "$RUNDIR/bios" --interactive --config "$HERE/usr/bin/game.toml"
fi
exec "$HERE/usr/bin/nds_runner" "$@"
EOF
chmod +x "$APPDIR/AppRun" "$APPDIR/usr/bin/$RUNNER_NAME"

echo "[5/5] package AppImage"
"$LINUXDEPLOY_BIN" --appimage-extract-and-run --appdir "$APPDIR" --executable "$APPDIR/usr/bin/$RUNNER_NAME" \
  --desktop-file "$APPDIR/usr/share/applications/$APP_NAME.desktop" \
  --icon-file "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png" >/dev/null

if [ "$MPH_VERSION" = "US1_0" ]; then
  APP="$OUT/$APP_NAME-linux-v$VERSION-x86_64.AppImage"
else
  APP="$OUT/$APP_NAME-$MPH_VERSION-linux-v$VERSION-x86_64.AppImage"
fi
rm -f "$APP"
ARCH=x86_64 "$APPIMAGETOOL_BIN" --appimage-extract-and-run "$APPDIR" "$APP" >/dev/null
chmod +x "$APP"
bash "$REPO/tools/test_appimage_layout.sh" "$APPDIR"
sha256sum "$APP"

#!/usr/bin/env bash
# Build a Metroid Prime Hunters Recomp Linux x86_64 AppImage.
#
# Packages the native Linux recomp-ui launcher together with the title runner.
# Put a legally dumped Metroid Prime Hunters .nds and an optional bios/ folder
# beside the AppImage; launcher state remains outside the read-only AppImage.
#
# Sibling checkouts are auto-detected by default. Override them with
# NDSRECOMP_ROOT / RECOMP_UI_ROOT or the matching CLI options when building in
# a container with explicit mounts.
set -euo pipefail

APP_NAME="MetroidPrimeHuntersRecomp"
TITLE_TARGET="metroidprimehuntersrecomp"
ROM_SHA1="90164d1ac127ee5f9815ea4ae7de798c7b5fc629"
RUNNER_NAME="nds_runner"
LAUNCHER_NAME="mph-recomp-ui"
VERSION="0.1.0"
JOBS="$(nproc 2>/dev/null || echo 4)"
DO_PACKAGE=1
BUILD_FLAVOR="release"
SDL_BACKEND="${NDS_SDL_BACKEND:-SDL3}"

REPO="$(cd "$(dirname "$0")/.." && pwd)"
FRAMEWORK_ROOT="${NDSRECOMP_ROOT:-$REPO/../ndsrecomp}"
RECOMP_UI_ROOT="${RECOMP_UI_ROOT:-$REPO/../recomp-ui}"
FRAMEWORK_ROOT="$(cd "$FRAMEWORK_ROOT" && pwd)"
RECOMP_UI_ROOT="$(cd "$RECOMP_UI_ROOT" && pwd)"
OUT="$REPO/release-linux"

while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="$2"; shift 2;;
    --jobs) JOBS="$2"; shift 2;;
    --out) OUT="$2"; shift 2;;
    --ndsrecomp-root) FRAMEWORK_ROOT="$(cd "$2" && pwd)"; shift 2;;
    --recomp-ui-root) RECOMP_UI_ROOT="$(cd "$2" && pwd)"; shift 2;;
    --build-flavor) BUILD_FLAVOR="$2"; shift 2;;
    --sdl-backend) SDL_BACKEND="$2"; shift 2;;
    --no-package) DO_PACKAGE=0; shift;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

case "$SDL_BACKEND" in
  SDL3|SDL2) ;;
  *) echo "ERROR: --sdl-backend must be SDL3 or SDL2." >&2; exit 2;;
esac

GAME_BUILD="$REPO/build-linux-$BUILD_FLAVOR"
RUNNER_BUILD="$FRAMEWORK_ROOT/runner/build-mph-linux-$BUILD_FLAVOR"
LAUNCHER_BUILD="$REPO/launcher/recomp-ui/build-linux-$BUILD_FLAVOR"
TITLE_BANK_DIR="$REPO/generated/recomp"

cd "$REPO"
test -f "$FRAMEWORK_ROOT/recompiler/CMakeLists.txt" || {
  echo "ERROR: sibling ndsrecomp checkout is missing." >&2
  exit 1
}
test -f "$RECOMP_UI_ROOT/recomp_ui.cmake" || {
  echo "ERROR: sibling recomp-ui checkout is missing." >&2
  exit 1
}
test -f "$REPO/Metroid Prime Hunters.nds" || {
  echo "ERROR: verified Metroid Prime Hunters ROM is missing from the repo root." >&2
  exit 1
}

echo "[1/4] configure title banks"
cmake -S "$REPO" -B "$GAME_BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DNDSRECOMP_ROOT="$FRAMEWORK_ROOT"
echo "[2/4] build title banks"
cmake --build "$GAME_BUILD" --target "$TITLE_TARGET" -j"$JOBS"

echo "[3/4] configure runner"
cmake -S "$FRAMEWORK_ROOT/runner" -B "$RUNNER_BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DNDS_SDL_BACKEND="$SDL_BACKEND" \
  -DNDS_BOOTSTRAP_FIRMWARE=ON \
  -DNDS_TITLE_BANK_DIR="$TITLE_BANK_DIR" \
  -DNDS_TITLE_ROM_SHA1="$ROM_SHA1"
echo "      build runner"
cmake --build "$RUNNER_BUILD" -j"$JOBS"

echo "      configure Linux launcher"
cmake -S "$REPO/launcher/recomp-ui" -B "$LAUNCHER_BUILD" -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DNDSRECOMP_ROOT="$FRAMEWORK_ROOT" \
  -DRECOMP_UI_ROOT="$RECOMP_UI_ROOT" \
  -DMPH_LAUNCHER_SDL_BACKEND="$SDL_BACKEND"
echo "      build Linux launcher"
cmake --build "$LAUNCHER_BUILD" --target "$LAUNCHER_NAME" -j"$JOBS"

BIN="$RUNNER_BUILD/$RUNNER_NAME"
LAUNCHER_BIN="$LAUNCHER_BUILD/$LAUNCHER_NAME"

print_glibc_floor() {
  local elf="$1"
  local floor
  floor="$(strings "$elf" | grep -ao 'GLIBC_[0-9][0-9.]*' | sort -Vu | tail -1 || true)"
  if [ -n "$floor" ]; then
    echo "      glibc requirement $(basename "$elf"): $floor"
  else
    echo "      glibc requirement $(basename "$elf"): none detected"
  fi
}
print_glibc_floor "$BIN"
print_glibc_floor "$LAUNCHER_BIN"

if [ "$DO_PACKAGE" = "0" ]; then
  echo "done: $RUNNER_BUILD/$RUNNER_NAME"
  echo "done: $LAUNCHER_BUILD/$LAUNCHER_NAME"
  exit 0
fi

test -f "$BIN" || { echo "ERROR: runner not built: $BIN" >&2; exit 1; }
test -f "$LAUNCHER_BIN" || {
  echo "ERROR: launcher not built: $LAUNCHER_BIN" >&2
  exit 1
}
# Assert the FULL declared bank inventory, not just the FMV bank: a runner
# missing the ingested coverage banks still contains "mph_arm9_fmv_runtime",
# which is how v0.4.12/v0.4.13/v0.5.0 shipped without 63 of them.
bash "$REPO/tools/verify_bank_inventory.sh" "$BIN" --repo "$REPO"

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
cp "$LAUNCHER_BIN" "$APPDIR/usr/bin/$LAUNCHER_NAME"
cp -a "$LAUNCHER_BUILD/assets" "$APPDIR/usr/bin/assets"
cp "$REPO/game.toml" "$APPDIR/usr/bin/game.toml"
cp "$REPO/README.md" "$APPDIR/usr/bin/README.md"
cp "$REPO/LICENSE" "$APPDIR/usr/bin/LICENSE"
cp "$REPO/packaging/BIOS_README.txt" "$APPDIR/usr/bin/bios/README.txt"

# Audit trail: the verified bank inventory of the exact runner being shipped.
bash "$REPO/tools/verify_bank_inventory.sh" "$APPDIR/usr/bin/$RUNNER_NAME" \
  --repo "$REPO" --manifest "$APPDIR/usr/bin/bank-manifest.txt" --quiet

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
Exec=$LAUNCHER_NAME
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
export SDL_GAMEPAD_ALLOW_STEAM_VIRTUAL_GAMEPAD=1
SELF="${APPIMAGE:-$0}"
RUNDIR="$(dirname "$(readlink -f "$SELF")")"
export RECOMP_APPIMAGE_PATH="$SELF"
export RECOMP_UI_BUILTIN_FILE_PICKER=1
ROM=""
for ext in nds NDS srl SRL; do
  for f in "$RUNDIR"/*."$ext"; do
    [ -e "$f" ] && ROM="$f" && break 2
  done
done
if [ -n "$ROM" ]; then
  export RECOMP_DISC_HINT="$ROM"
fi
mkdir -p "$RUNDIR/bios" 2>/dev/null || true
if [ ! -f "$RUNDIR/bios/README.txt" ] && [ -f "$HERE/usr/bin/bios/README.txt" ]; then
  cp "$HERE/usr/bin/bios/README.txt" "$RUNDIR/bios/README.txt" 2>/dev/null || true
fi
cd "$RUNDIR" 2>/dev/null || true
if [ "$#" -eq 0 ]; then
  export MPH_RECOMP_DATA_DIR="$RUNDIR"
  exec "$HERE/usr/bin/mph-recomp-ui"
fi
exec "$HERE/usr/bin/nds_runner" "$@"
EOF
chmod +x "$APPDIR/AppRun" \
  "$APPDIR/usr/bin/$RUNNER_NAME" \
  "$APPDIR/usr/bin/$LAUNCHER_NAME"

echo "[4/4] package AppImage"
"$LINUXDEPLOY_BIN" --appimage-extract-and-run --appdir "$APPDIR" \
  --executable "$APPDIR/usr/bin/$RUNNER_NAME" \
  --executable "$APPDIR/usr/bin/$LAUNCHER_NAME" \
  --desktop-file "$APPDIR/usr/share/applications/$APP_NAME.desktop" \
  --icon-file "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png" >/dev/null

APP="$OUT/$APP_NAME-linux-v$VERSION-x86_64.AppImage"
rm -f "$APP"
ARCH=x86_64 "$APPIMAGETOOL_BIN" --appimage-extract-and-run "$APPDIR" "$APP" >/dev/null
chmod +x "$APP"
bash "$REPO/tools/test_appimage_layout.sh" "$APPDIR"
sha256sum "$APP"

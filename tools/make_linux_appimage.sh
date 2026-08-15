#!/usr/bin/env bash
# make_linux_appimage.sh — package the Linux MPH release as an AppImage.
#
# Mirrors snesrecomp's MegaMan X pipeline (tools/make-linux-appimage.sh
# there): build nds_runner in WSL/Linux first, then wrap it. There is no
# GUI launcher on Linux yet — AppRun does the launcher's job: it finds the
# ROM sitting NEXT TO the .AppImage, decides retail-vs-FreeBIOS from the
# bios folder beside the .AppImage (all three dumps present = retail;
# otherwise the built-in FreeBIOS + generated firmware), and launches with
# the same defaults the Windows launcher passes. All state (bios/,
# identity, .sav) lives next to the .AppImage, never inside the read-only
# squashfs.
#
# Usage: bash tools/make_linux_appimage.sh <version> [runner-build-dir]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION="${1:?version required}"
BUILD="${2:-/mnt/f/Projects/ndsrecomp/ndsrecomp/runner/build-mph-linux}"
RUNTIME="${APPIMAGE_RUNTIME:-$ROOT/release-stage/appimage-runtime-x86_64}"
OUT="$ROOT/release-stage"
NAME="MetroidPrimeHuntersRecomp-linux-x86_64-v$VERSION.AppImage"

BIN="$BUILD/nds_runner"
[ -f "$BIN" ] || { echo "runner not built: $BIN" >&2; exit 1; }

if [ ! -f "$RUNTIME" ]; then
  echo "=== fetch AppImage type2 runtime ==="
  curl -sL -o "$RUNTIME" \
    "https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64"
fi
[ -s "$RUNTIME" ] || { echo "runtime download failed" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
APP="$WORK/AppDir"
mkdir -p "$APP/usr/bin" "$APP/usr/lib" \
  "$APP/usr/share/applications" \
  "$APP/usr/share/icons/hicolor/256x256/apps"

cp "$BIN" "$APP/usr/bin/nds_runner"
cp "$ROOT/game.toml" "$APP/usr/bin/"
cp "$ROOT/README.md" "$APP/usr/bin/" 2>/dev/null || true

# Bundle non-core shared libraries (SDL2, libstdc++, libgcc, slirp deps…)
# so the ELF runs without the build distro. glibc itself stays on the host.
echo "=== bundle shared libraries ==="
ldd "$BIN" | awk '/=> \// {print $3}' | while read -r lib; do
  base="$(basename "$lib")"
  case "$base" in
    libc.so*|libm.so*|libdl.so*|libpthread.so*|librt.so*|ld-linux*|\
    libresolv.so*|libnss*|libgcc_s.so.1) ;;
    *) cp -u "$lib" "$APP/usr/lib/" && echo "  + $base" ;;
  esac
done
# libgcc travels with libstdc++ for exception unwinding parity.
ldd "$BIN" | awk '/libgcc_s/ {print $3}' | while read -r lib; do
  cp -u "$lib" "$APP/usr/lib/"
done

cat > "$APP/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export LD_LIBRARY_PATH="$HERE/usr/lib:${LD_LIBRARY_PATH:-}"
export SDL_JOYSTICK_HIDAPI_STEAM=1
export SDL_GAMECONTROLLER_ALLOW_STEAM_VIRTUAL_GAMEPAD=1
ANCHOR="$(dirname "$(readlink -f "${APPIMAGE:-$0}")")"
cd "$ANCHOR" 2>/dev/null || true
[ "$#" -gt 0 ] && exec "$HERE/usr/bin/nds_runner" "$@"

ROM=""
for f in "$ANCHOR"/*.nds "$ANCHOR"/*.srl; do
  [ -e "$f" ] && ROM="$f" && break
done
if [ -z "$ROM" ]; then
  echo "Drop your Metroid Prime Hunters (USA) .nds ROM next to the" \
       ".AppImage and run it again." >&2
  exit 1
fi

# BIOS policy, matching the Windows launcher: a bios folder next to the
# .AppImage holding all three verified dumps selects the fully faithful
# path; otherwise the built-in FreeBIOS + generated firmware boots the
# game directly. The folder also persists the per-install identity.
BIOS="$ANCHOR/bios"
mkdir -p "$BIOS"
MODE=""
if [ ! -f "$BIOS/biosnds9.rom" ] || [ ! -f "$BIOS/biosnds7.rom" ] || \
   [ ! -f "$BIOS/firmware.bin" ]; then
  MODE="--freebios --generated-firmware --boot direct"
fi

exec "$HERE/usr/bin/nds_runner" "$BIOS" --interactive \
  --rom "$ROM" --config "$HERE/usr/bin/game.toml" \
  --screen-layout separate --adaptive-widescreen top \
  --relative-mouse-touch on --relative-mouse-sensitivity 30 \
  --relative-mouse-invert-y off --relative-mouse-fire-key l \
  --mph-prime-controls on --mph-virtual-stylus-sensitivity 20 \
  --startup-mode automatic \
  --network on --wfc on --wfc-provider wiimmfi \
  $MODE
EOF
chmod +x "$APP/AppRun"

cat > "$APP/usr/share/applications/mphrecomp.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Metroid Prime Hunters Recomp
Exec=nds_runner
Icon=mphrecomp
Categories=Game;
Terminal=false
EOF
cp "$APP/usr/share/applications/mphrecomp.desktop" "$APP/mphrecomp.desktop"
# AppImage tooling wants a top-level icon; a zero-byte placeholder is valid.
touch "$APP/mphrecomp.png" "$APP/usr/share/icons/hicolor/256x256/apps/mphrecomp.png"

echo "=== squash + assemble ==="
mkdir -p "$OUT"
mksquashfs "$APP" "$WORK/filesystem.squashfs" -all-root -noappend -quiet
cat "$RUNTIME" "$WORK/filesystem.squashfs" > "$OUT/$NAME"
chmod +x "$OUT/$NAME"
echo "BUILT: $OUT/$NAME"
sha256sum "$OUT/$NAME"

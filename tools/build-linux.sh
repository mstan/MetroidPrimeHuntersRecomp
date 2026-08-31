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
SHARD_CACHE="${MPH_RELEASE_SHARD_CACHE:-}"
SHARD_PERFORMANCE_GATE="${MPH_SHARD_PERFORMANCE_GATE:-}"
GCC="${CC:-gcc}"
ALLOW_NO_SHARD_CACHE=0
SKIP_OVERLAY_TOOLCHAIN=0
STAGE_FOR_SHARD_PERFORMANCE_GATE=0

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
    --shard-cache) SHARD_CACHE="$2"; shift 2;;
    --shard-performance-gate) SHARD_PERFORMANCE_GATE="$2"; shift 2;;
    --gcc) GCC="$2"; shift 2;;
    --allow-no-shard-cache) ALLOW_NO_SHARD_CACHE=1; shift;;
    --skip-overlay-toolchain) SKIP_OVERLAY_TOOLCHAIN=1; shift;;
    --stage-for-shard-performance-gate) STAGE_FOR_SHARD_PERFORMANCE_GATE=1; shift;;
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
SHARD_CACHE="${SHARD_CACHE:-$REPO/release-shard-cache-linux}"
SHARD_PERFORMANCE_GATE="${SHARD_PERFORMANCE_GATE:-$SHARD_CACHE/performance-gate.json}"

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
if [ "$SKIP_OVERLAY_TOOLCHAIN" = 1 ] && [ "$ALLOW_NO_SHARD_CACHE" != 1 ]; then
  echo "ERROR: --skip-overlay-toolchain requires --allow-no-shard-cache" >&2
  exit 2
fi
if [ "$STAGE_FOR_SHARD_PERFORMANCE_GATE" = 1 ] && \
   { [ "$ALLOW_NO_SHARD_CACHE" = 1 ] || [ "$SKIP_OVERLAY_TOOLCHAIN" = 1 ]; }; then
  echo "ERROR: --stage-for-shard-performance-gate requires shards and bundled TCC" >&2
  exit 2
fi

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

# The live compiler and cache are a release unit. The cache is filtered
# against these exact staged artifacts; the player-side TCC command discovers
# this fixed layout beside nds_runner.
TOOLCHAIN=""
if [ "$SKIP_OVERLAY_TOOLCHAIN" != 1 ]; then
  TOOLCHAIN="$APPDIR/usr/bin/overlay_toolchain"
  mkdir -p "$TOOLCHAIN/include" "$TOOLCHAIN/python/bin" \
    "$TOOLCHAIN/python/lib" "$TOOLCHAIN/tcc/lib/tcc"
  RECOMPILER="$GAME_BUILD/ndsrecomp-recompiler/nds_recompile"
  for required in "$FRAMEWORK_ROOT/tools/compile_live_shards.py" \
      "$FRAMEWORK_ROOT/recompiler/armv4t/runtime_arm.h" \
      "$FRAMEWORK_ROOT/external/arm-recomp-core/common/runtime_arm_types.h" \
      "$RECOMPILER"; do
    [ -f "$required" ] || {
      echo "ERROR: overlay toolchain input missing: $required" >&2; exit 1;
    }
  done
  cp "$FRAMEWORK_ROOT/tools/compile_live_shards.py" "$TOOLCHAIN/"
  cp "$RECOMPILER" "$TOOLCHAIN/nds_recompile"
  cp "$FRAMEWORK_ROOT/recompiler/armv4t/runtime_arm.h" "$TOOLCHAIN/include/"
  cp "$FRAMEWORK_ROOT/external/arm-recomp-core/common/runtime_arm_types.h" \
    "$TOOLCHAIN/include/"
  cp "$REPO/tools/install_prebuilt_shards.py" "$TOOLCHAIN/"

  SYSTEM_PYTHON="$(readlink -f "$(command -v python3)")"
  PY_STDLIB="$(python3 -c 'import sysconfig; print(sysconfig.get_path("stdlib"))')"
  [ -x "$SYSTEM_PYTHON" ] && [ -d "$PY_STDLIB" ] || {
    echo "ERROR: a relocatable Python runtime could not be staged" >&2; exit 1;
  }
  cp "$SYSTEM_PYTHON" "$TOOLCHAIN/python/bin/python3-runtime"
  cp -a "$PY_STDLIB" "$TOOLCHAIN/python/lib/"
  cat > "$TOOLCHAIN/python/bin/python3" <<'EOF'
#!/bin/sh
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export PYTHONHOME="$(dirname "$HERE")"
export PYTHONDONTWRITEBYTECODE=1
exec "$HERE/python3-runtime" "$@"
EOF

  command -v tcc >/dev/null 2>&1 || {
    echo "ERROR: tcc is required to package runtime live shards" >&2; exit 1;
  }
  TCC_SYSTEM="$(readlink -f "$(command -v tcc)")"
  TCC_SUPPORT="$(dpkg-query -L tcc 2>/dev/null | \
    sed -n 's#\(/.*\)/libtcc1\.a$#\1#p' | head -1)"
  [ -n "$TCC_SUPPORT" ] && [ -f "$TCC_SUPPORT/libtcc1.a" ] || {
    echo "ERROR: cannot locate tcc runtime support (libtcc1.a)" >&2; exit 1;
  }
  cp "$TCC_SYSTEM" "$TOOLCHAIN/tcc/tcc-runtime"
  cp -a "$TCC_SUPPORT/." "$TOOLCHAIN/tcc/lib/tcc/"
  write_tcc_wrapper() {
    local runtime_sha tree_sha
    runtime_sha="$(sha256sum "$TOOLCHAIN/tcc/tcc-runtime" | awk '{print $1}')"
    tree_sha="$(cd "$TOOLCHAIN/tcc" && \
      find tcc-runtime lib -type f -print0 | LC_ALL=C sort -z | \
      xargs -0 sha256sum | sha256sum | awk '{print $1}')"
    printf '#!/bin/sh\n# tcc-runtime-sha256=%s\n# tcc-toolchain-sha256=%s\n' \
      "$runtime_sha" "$tree_sha" > "$TOOLCHAIN/tcc/tcc"
    cat >> "$TOOLCHAIN/tcc/tcc" <<'EOF'
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$HERE/tcc-runtime" -B"$HERE/lib/tcc" "$@"
EOF
    chmod 0755 "$TOOLCHAIN/tcc/tcc"
  }
  write_tcc_wrapper
  chmod 0755 "$TOOLCHAIN/nds_recompile" "$TOOLCHAIN/python/bin/python3" \
    "$TOOLCHAIN/python/bin/python3-runtime" "$TOOLCHAIN/tcc/tcc" \
    "$TOOLCHAIN/tcc/tcc-runtime"

  command -v "$GCC" >/dev/null 2>&1 || {
    echo "ERROR: release-cache gcc not found: $GCC" >&2; exit 1;
  }
  RUNNER_SHA="$(sha256sum "$APPDIR/usr/bin/$RUNNER_NAME" | awk '{print $1}')"
  STAGE_ARGS=(stage-cache
    --compile-script "$TOOLCHAIN/compile_live_shards.py"
    --runtime-include "$TOOLCHAIN/include"
    --recompiler "$TOOLCHAIN/nds_recompile"
    --gcc "$(command -v "$GCC")"
    --cache "$SHARD_CACHE"
    --destination "$APPDIR/usr/bin/prebuilt-live-shard-cache"
    --extension .so --rom-sha1 "$ROM_SHA1" --runner-sha256 "$RUNNER_SHA")
  if [ "$ALLOW_NO_SHARD_CACHE" = 1 ]; then
    STAGE_ARGS+=(--allow-empty)
  fi
  python3 "$REPO/tools/release_shard_common.py" "${STAGE_ARGS[@]}"
  if [ "$ALLOW_NO_SHARD_CACHE" != 1 ] && \
     [ "$STAGE_FOR_SHARD_PERFORMANCE_GATE" != 1 ]; then
    test -f "$SHARD_PERFORMANCE_GATE" || {
      echo "ERROR: no bot-route shard performance gate: $SHARD_PERFORMANCE_GATE" >&2
      exit 1
    }
    python3 "$REPO/tools/shard_performance_gate.py" verify-package \
      --gate "$SHARD_PERFORMANCE_GATE" \
      --cache "$APPDIR/usr/bin/prebuilt-live-shard-cache" \
      --runner-sha256 "$RUNNER_SHA"
    cp "$SHARD_PERFORMANCE_GATE" \
      "$APPDIR/usr/bin/shard-performance-gate.json"
  fi

  "$TOOLCHAIN/python/bin/python3" -c \
    'import argparse, hashlib, json, pathlib, subprocess, sysconfig'
  "$TOOLCHAIN/tcc/tcc" -v >/dev/null 2>&1
fi

# Audit trail: the verified bank inventory of the exact runner being shipped.
bash "$REPO/tools/verify_bank_inventory.sh" "$APPDIR/usr/bin/$RUNNER_NAME" \
  --repo "$REPO" --manifest "$APPDIR/usr/bin/bank-manifest.txt" --quiet
if [ "$STAGE_FOR_SHARD_PERFORMANCE_GATE" = 1 ]; then
  CANDIDATE="$OUT/shard-performance-candidate"
  rm -rf -- "$CANDIDATE"
  cp -a "$APPDIR" "$CANDIDATE"
  echo "Shard performance candidate staged at: $CANDIDATE"
  echo "No AppImage was produced; run the bot-route gate, then package again with --shard-performance-gate."
  exit 0
fi

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
if [ -d "$HERE/usr/bin/prebuilt-live-shard-cache" ]; then
  "$HERE/usr/bin/overlay_toolchain/python/bin/python3" \
    "$HERE/usr/bin/overlay_toolchain/install_prebuilt_shards.py" \
    --source "$HERE/usr/bin/prebuilt-live-shard-cache" \
    --cache "$RUNDIR/live-shard-cache" || exit 1
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
DEPLOY_TOOLCHAIN_ARGS=()
if [ -n "$TOOLCHAIN" ]; then
  DEPLOY_TOOLCHAIN_ARGS+=(
    --executable "$TOOLCHAIN/nds_recompile"
    --executable "$TOOLCHAIN/python/bin/python3-runtime"
    --executable "$TOOLCHAIN/tcc/tcc-runtime")
  while IFS= read -r extension; do
    DEPLOY_TOOLCHAIN_ARGS+=(--library "$extension")
  done < <(find "$TOOLCHAIN/python/lib" -type f -name '*.so')
fi
"$LINUXDEPLOY_BIN" --appimage-extract-and-run --appdir "$APPDIR" \
  --executable "$APPDIR/usr/bin/$RUNNER_NAME" \
  --executable "$APPDIR/usr/bin/$LAUNCHER_NAME" \
  "${DEPLOY_TOOLCHAIN_ARGS[@]}" \
  --desktop-file "$APPDIR/usr/share/applications/$APP_NAME.desktop" \
  --icon-file "$APPDIR/usr/share/icons/hicolor/256x256/apps/$APP_NAME.png" >/dev/null
if [ -n "$TOOLCHAIN" ]; then
  # linuxdeploy may rewrite ELF RPATHs. Refresh the wrapper identity against
  # the bytes that actually enter the AppImage.
  write_tcc_wrapper
fi

APP="$OUT/$APP_NAME-linux-v$VERSION-x86_64.AppImage"
rm -f "$APP"
ARCH=x86_64 "$APPIMAGETOOL_BIN" --appimage-extract-and-run "$APPDIR" "$APP" >/dev/null
chmod +x "$APP"
EXPECT_LIVE_TOOLCHAIN="$((1 - SKIP_OVERLAY_TOOLCHAIN))" \
EXPECT_LIVE_SHARDS="$((1 - ALLOW_NO_SHARD_CACHE))" \
  bash "$REPO/tools/test_appimage_layout.sh" "$APPDIR"
sha256sum "$APP"

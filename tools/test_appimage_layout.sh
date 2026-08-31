#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 /path/to/AppDir" >&2
  exit 2
fi

APPDIR="$(cd "$1" && pwd)"
EXPECT_LIVE_TOOLCHAIN="${EXPECT_LIVE_TOOLCHAIN:-1}"
EXPECT_LIVE_SHARDS="${EXPECT_LIVE_SHARDS:-1}"
test -x "$APPDIR/usr/bin/nds_runner"
test -x "$APPDIR/usr/bin/mph-recomp-ui"
test -f "$APPDIR/usr/bin/game.toml"
test -d "$APPDIR/usr/bin/assets"
test -f "$APPDIR/usr/bin/bios/README.txt"

if [ "$EXPECT_LIVE_TOOLCHAIN" = 1 ]; then
  TOOLCHAIN="$APPDIR/usr/bin/overlay_toolchain"
  test -f "$TOOLCHAIN/compile_live_shards.py"
  test -x "$TOOLCHAIN/nds_recompile"
  test -f "$TOOLCHAIN/include/runtime_arm.h"
  test -f "$TOOLCHAIN/include/runtime_arm_types.h"
  test -x "$TOOLCHAIN/python/bin/python3"
  test -x "$TOOLCHAIN/tcc/tcc"
  tcc_sha="$(sha256sum "$TOOLCHAIN/tcc/tcc-runtime" | awk '{print $1}')"
  grep -Fx "# tcc-runtime-sha256=$tcc_sha" "$TOOLCHAIN/tcc/tcc" >/dev/null || {
    echo "tcc provider wrapper does not identify its runtime binary" >&2
    exit 1
  }
  tcc_tree_sha="$(cd "$TOOLCHAIN/tcc" && \
    find tcc-runtime lib -type f -print0 | LC_ALL=C sort -z | \
    xargs -0 sha256sum | sha256sum | awk '{print $1}')"
  grep -Fx "# tcc-toolchain-sha256=$tcc_tree_sha" \
      "$TOOLCHAIN/tcc/tcc" >/dev/null || {
    echo "tcc provider wrapper does not identify its support files" >&2
    exit 1
  }
  "$TOOLCHAIN/python/bin/python3" "$TOOLCHAIN/compile_live_shards.py" \
    --help >/dev/null
  "$TOOLCHAIN/nds_recompile" --codegen-identity >/dev/null
  "$TOOLCHAIN/tcc/tcc" -v -E /dev/null >/dev/null 2>&1
fi
if [ "$EXPECT_LIVE_SHARDS" = 1 ]; then
  PREBUILT="$APPDIR/usr/bin/prebuilt-live-shard-cache"
  test -s "$PREBUILT/live-index.json"
  test -s "$PREBUILT/release-id.txt"
  test -s "$PREBUILT/shard-manifest.txt"
  count="$(find "$PREBUILT/gcc" -maxdepth 1 -type f -name '*.so' | wc -l)"
  [ "$count" -gt 0 ] || {
    echo "prebuilt Linux shard cache is empty" >&2; exit 1;
  }
  if find "$PREBUILT" -type f \( -name '*.dll' -o -name '*.stage.so' \) \
      -print -quit | grep -q .; then
    echo "foreign or interrupted shard leaked into prebuilt cache" >&2
    exit 1
  fi
  python3 - "$PREBUILT" <<'PY'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
index = json.loads((root / "live-index.json").read_text(encoding="utf-8"))
captures = index.get("captures", {})
if not captures:
    raise SystemExit("prebuilt cache index has no captures")
identities = {entry.get("provider_id") for entry in captures.values()}
if len(identities) != 1 or None in identities:
    raise SystemExit(f"prebuilt cache is not an exact identity projection: {identities}")
for entry in captures.values():
    path = pathlib.Path(entry["dll"])
    if path.is_absolute() or path.parts[0] != "gcc" or path.suffix != ".so":
        raise SystemExit(f"unsafe staged shard path: {path}")
    if not (root / path).is_file():
        raise SystemExit(f"indexed shard is missing: {path}")
PY
fi

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

if [ "$EXPECT_LIVE_TOOLCHAIN" = 1 ]; then
  cat > "$tmp/tcc-smoke.c" <<'EOF'
#include <stdint.h>
__attribute__((visibility("default"))) uint32_t mph_tcc_smoke(uint32_t x) {
  return x + 1;
}
EOF
  "$TOOLCHAIN/tcc/tcc" -shared -o "$tmp/tcc-smoke.so" "$tmp/tcc-smoke.c"
  test -s "$tmp/tcc-smoke.so" || {
    echo "bundled tcc cannot compile a shared object" >&2; exit 1;
  }
fi

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
if [ "$EXPECT_LIVE_SHARDS" = 1 ]; then
  test -s "$probe_state/live-shard-cache/.mph-prebuilt-release-id"
  test -s "$probe_state/live-shard-cache/live-index.json"
  seeded="$(find "$probe_state/live-shard-cache/gcc" -maxdepth 1 \
    -type f -name '*.so' | wc -l)"
  [ "$seeded" -gt 0 ] || {
    echo "AppRun did not seed the writable prebuilt shard cache" >&2; exit 1;
  }

  # A different release marker must reset, not merge, the prior native cache.
  printf 'stale\n' > "$probe_state/live-shard-cache/.mph-prebuilt-release-id"
  printf 'stale\n' > "$probe_state/live-shard-cache/stale-provider.so"
  MPH_RECOMP_PROBE="$probe_state/env.txt" \
  APPIMAGE="$probe_state/MetroidPrimeHuntersRecomp.AppImage" \
    "$probe_appdir/AppRun" >/dev/null 2>&1
  test ! -e "$probe_state/live-shard-cache/stale-provider.so" || {
    echo "AppRun merged a stale shard cache into the packaged provider" >&2
    exit 1
  }
fi

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

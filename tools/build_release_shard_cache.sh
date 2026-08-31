#!/usr/bin/env bash
# Warm the Linux gcc shard cache over the committed benchmark routes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRAMEWORK_ROOT="${NDSRECOMP_ROOT:-$ROOT/../ndsrecomp}"
RUNNER_BUILD=""
RECOMPILER=""
CACHE="$ROOT/release-shard-cache-linux"
ROM="$ROOT/Metroid Prime Hunters.nds"
BIOS="${NDS_BIOS_DIR:-$FRAMEWORK_ROOT/bios}"
GCC="${CC:-gcc}"
BASE_PORT=19910
CLEAN=0
ROUTES=(adventure attract mp_bots mp_bots_blank)

while [ $# -gt 0 ]; do
  case "$1" in
    --ndsrecomp-root) FRAMEWORK_ROOT="$(cd "$2" && pwd)"; shift 2;;
    --runner-build) RUNNER_BUILD="$(cd "$2" && pwd)"; shift 2;;
    --recompiler) RECOMPILER="$(realpath "$2")"; shift 2;;
    --cache) CACHE="$(realpath -m "$2")"; shift 2;;
    --rom) ROM="$(realpath "$2")"; shift 2;;
    --bios) BIOS="$(realpath "$2")"; shift 2;;
    --gcc) GCC="$2"; shift 2;;
    --base-port) BASE_PORT="$2"; shift 2;;
    --routes) IFS=',' read -r -a ROUTES <<< "$2"; shift 2;;
    --clean) CLEAN=1; shift;;
    -h|--help) sed -n '2,22p' "$0"; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

FRAMEWORK_ROOT="$(cd "$FRAMEWORK_ROOT" && pwd)"
RUNNER_BUILD="${RUNNER_BUILD:-$FRAMEWORK_ROOT/runner/build-mph-linux-release}"
RECOMPILER="${RECOMPILER:-$ROOT/build-linux-release/ndsrecomp-recompiler/nds_recompile}"
RUNNER="$RUNNER_BUILD/nds_runner"
COMPILE_SCRIPT="$FRAMEWORK_ROOT/tools/compile_live_shards.py"
INCLUDE="$CACHE/_toolchain_include"
LOGS="$CACHE/_logs"

for required in "$RUNNER" "$RECOMPILER" "$COMPILE_SCRIPT" "$ROM" \
                "$ROOT/game.toml" "$BIOS"; do
  [ -e "$required" ] || { echo "ERROR: shard input missing: $required" >&2; exit 1; }
done
command -v "$GCC" >/dev/null 2>&1 || {
  echo "ERROR: gcc not found: $GCC" >&2; exit 1;
}
if [ "$CLEAN" = 1 ] && [ -d "$CACHE" ]; then
  rm -rf -- "$CACHE"
fi
mkdir -p "$INCLUDE" "$LOGS"
cp "$FRAMEWORK_ROOT/recompiler/armv4t/runtime_arm.h" "$INCLUDE/"
cp "$FRAMEWORK_ROOT/external/arm-recomp-core/common/runtime_arm_types.h" "$INCLUDE/"

LIVE_COMMAND="$(python3 "$SCRIPT_DIR/release_shard_common.py" compile-command \
  --python "$(command -v python3)" --compile-script "$COMPILE_SCRIPT" \
  --runtime-include "$INCLUDE" --runner-build "$RUNNER_BUILD" \
  --recompiler "$RECOMPILER" --gcc "$(command -v "$GCC")")"
echo "Autocompile: $LIVE_COMMAND"

port="$BASE_PORT"
for route in "${ROUTES[@]}"; do
  python3 "$SCRIPT_DIR/build_release_shard_cache.py" \
    --mph-root "$ROOT" --runner "$RUNNER" --bios "$BIOS" --rom "$ROM" \
    --config "$ROOT/game.toml" --cache "$CACHE" --backend gcc \
    --route "$route" --port "$port" --live-command "$LIVE_COMMAND" \
    --log-dir "$LOGS"
  port=$((port + 1))
done

IDENTITY="$(python3 "$SCRIPT_DIR/release_shard_common.py" identity \
  --compile-script "$COMPILE_SCRIPT" --runtime-include "$INCLUDE" \
  --recompiler "$RECOMPILER" --gcc "$(command -v "$GCC")")"
count=0
if [ -d "$CACHE/gcc" ]; then
  count="$(find "$CACHE/gcc" -maxdepth 1 -type f -name '*.so' | wc -l)"
fi
[ "$count" -gt 0 ] || {
  echo "ERROR: routes produced no Linux shards for $IDENTITY" >&2; exit 1;
}
echo "Linux release cache: $count shard(s), provider $IDENTITY"

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRAMEWORK_ROOT="$(cd "$ROOT/../ndsrecomp" && pwd)"
VERSION="0.1.0"
MPH_VERSION="US1_0"
ROM_PATH="$ROOT/Metroid Prime Hunters.nds"
BUILD_DIR=""
RUNNER_BUILD_DIR=""
APPDIR=""
PACKAGE=1
JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || printf '4')"

usage() {
  cat <<'EOF'
Build Metroid Prime Hunters Recomp for Linux.

Usage:
  tools/build-linux.sh [options]

Options:
  --version VERSION       Package version (default: 0.1.0)
  --mph-version PROFILE   MPH ROM profile (US1_0 or EU1_1; default: US1_0)
  --rom PATH              Path to the selected retail ROM
  --build-dir PATH        Game build directory
  --runner-build PATH     ndsrecomp runner build directory
  --appdir PATH           AppImage staging directory
  --jobs N                Parallel build jobs
  --no-package            Build runner only; do not create AppImage
  -h, --help              Show this help
EOF
}

while (($#)); do
  case "$1" in
    --version)
      VERSION="$2"
      shift 2
      ;;
    --mph-version)
      MPH_VERSION="$2"
      shift 2
      ;;
    --rom)
      ROM_PATH="$2"
      shift 2
      ;;
    --build-dir)
      BUILD_DIR="$2"
      shift 2
      ;;
    --runner-build)
      RUNNER_BUILD_DIR="$2"
      shift 2
      ;;
    --appdir)
      APPDIR="$2"
      shift 2
      ;;
    --jobs)
      JOBS="$2"
      shift 2
      ;;
    --no-package)
      PACKAGE=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

PROFILE_FILE="$ROOT/config/mph_rom_profiles.json"
readarray -t PROFILE_VALUES < <(
  python3 - "$PROFILE_FILE" "$MPH_VERSION" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
key = sys.argv[2]
registry = json.loads(path.read_text(encoding="utf-8"))
profile = registry.get("profiles", {}).get(key)
if not isinstance(profile, dict):
    choices = ", ".join(sorted(registry.get("profiles", {})))
    raise SystemExit(f"unknown MPH profile {key!r}; configured: {choices}")
for field in (
    "sha1", "game_config", "game_code", "revision",
    "launcher_default_rom", "fmv_runtime_bank",
):
    if field not in profile:
        raise SystemExit(f"{key}: missing profile field {field}")
print(profile["sha1"])
print(profile["game_config"])
print(profile["game_code"])
print(profile["revision"])
print("1" if profile.get("fmv_runtime") else "0")
print(profile["launcher_default_rom"])
print(profile["fmv_runtime_bank"])
PY
)

ROM_SHA1="${PROFILE_VALUES[0]}"
GAME_CONFIG_REL="${PROFILE_VALUES[1]}"
GAME_CODE="${PROFILE_VALUES[2]}"
REVISION="${PROFILE_VALUES[3]}"
FMV_RUNTIME="${PROFILE_VALUES[4]}"
DEFAULT_ROM_NAME="${PROFILE_VALUES[5]}"
FMV_RUNTIME_BANK="${PROFILE_VALUES[6]}"
GAME_CONFIG="$ROOT/$GAME_CONFIG_REL"

if [[ "$ROM_PATH" == "$ROOT/Metroid Prime Hunters.nds" && "$MPH_VERSION" != "US1_0" ]]; then
  ROM_PATH="$ROOT/$DEFAULT_ROM_NAME"
fi

if [[ ! -f "$ROM_PATH" ]]; then
  printf 'ROM not found: %s\n' "$ROM_PATH" >&2
  exit 1
fi
if [[ ! -f "$GAME_CONFIG" ]]; then
  printf 'Game config not found: %s\n' "$GAME_CONFIG" >&2
  exit 1
fi

if [[ -z "$BUILD_DIR" ]]; then
  if [[ "$MPH_VERSION" == "US1_0" ]]; then
    BUILD_DIR="$ROOT/build-linux-release"
  else
    BUILD_DIR="$ROOT/build-linux-release-$MPH_VERSION"
  fi
fi
if [[ -z "$RUNNER_BUILD_DIR" ]]; then
  if [[ "$MPH_VERSION" == "US1_0" ]]; then
    RUNNER_BUILD_DIR="$FRAMEWORK_ROOT/runner/build-mph-linux-release"
  else
    RUNNER_BUILD_DIR="$FRAMEWORK_ROOT/runner/build-mph-linux-release-$MPH_VERSION"
  fi
fi
if [[ -z "$APPDIR" ]]; then
  if [[ "$MPH_VERSION" == "US1_0" ]]; then
    APPDIR="$ROOT/release-stage/MetroidPrimeHuntersRecomp-linux-x86_64.AppDir"
  else
    APPDIR="$ROOT/release-stage/MetroidPrimeHuntersRecomp-$MPH_VERSION-linux-x86_64.AppDir"
  fi
fi

if [[ "$MPH_VERSION" == "US1_0" ]]; then
  TITLE_BANK_DIR="$ROOT/generated/recomp"
else
  TITLE_BANK_DIR="$ROOT/generated/$MPH_VERSION/recomp"
fi

printf 'Building MPH profile %s (%s rev %s)\n' "$MPH_VERSION" "$GAME_CODE" "$REVISION"

cmake -S "$ROOT" -B "$BUILD_DIR" \
  -DCMAKE_BUILD_TYPE=Release \
  -DNDSRECOMP_ROOT="$FRAMEWORK_ROOT" \
  -DMPH_VERSION="$MPH_VERSION" \
  -DMPH_ROM="$ROM_PATH"
cmake --build "$BUILD_DIR" --target metroidprimehuntersrecomp -j "$JOBS"

python3 "$ROOT/tools/patch_ndsrecomp_mph_runtime.py" \
  --framework-root "$FRAMEWORK_ROOT" \
  --profiles "$PROFILE_FILE"

cmake -S "$FRAMEWORK_ROOT/runner" -B "$RUNNER_BUILD_DIR" \
  -DCMAKE_BUILD_TYPE=Release \
  -DNDS_BOOTSTRAP_FIRMWARE=ON \
  -DNDS_TITLE_BANK_DIR="$TITLE_BANK_DIR" \
  -DNDS_TITLE_ROM_SHA1="$ROM_SHA1"
cmake --build "$RUNNER_BUILD_DIR" -j "$JOBS"

RUNNER="$RUNNER_BUILD_DIR/nds_runner"
if [[ ! -x "$RUNNER" ]]; then
  printf 'Runner missing after build: %s\n' "$RUNNER" >&2
  exit 1
fi

if [[ "$FMV_RUNTIME" == "1" ]]; then
  if ! grep -a -q "$FMV_RUNTIME_BANK" "$RUNNER"; then
    printf 'Runner does not contain required FMV runtime bank %s.\n' \
      "$FMV_RUNTIME_BANK" >&2
    exit 1
  fi
fi

if ((PACKAGE == 0)); then
  printf 'Runner ready: %s\n' "$RUNNER"
  printf 'Profile config: %s\n' "$GAME_CONFIG"
  exit 0
fi

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/mph-recomp" "$APPDIR/bios"
cp "$RUNNER" "$APPDIR/usr/bin/nds_runner"
cp "$GAME_CONFIG" "$APPDIR/usr/share/mph-recomp/game.toml"
cp "$ROOT/packaging/BIOS_README.txt" "$APPDIR/bios/README.txt"
cp "$ROOT/README.md" "$APPDIR/README.md"
cp "$ROOT/LICENSE" "$APPDIR/LICENSE"

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROM="${1:-}"
if [[ -z "$ROM" ]]; then
  printf 'Usage: %s /path/to/MetroidPrimeHunters.nds\n' "$0" >&2
  exit 2
fi
shift || true
exec "$HERE/usr/bin/nds_runner" "$HERE/bios" \
  --interactive \
  --rom "$ROM" \
  --config "$HERE/usr/share/mph-recomp/game.toml" \
  "$@"
EOF
chmod +x "$APPDIR/AppRun"

APPIMAGE_TOOL="${APPIMAGE_TOOL:-appimagetool}"
if ! command -v "$APPIMAGE_TOOL" >/dev/null 2>&1; then
  printf 'appimagetool not found; staged AppDir at %s\n' "$APPDIR" >&2
  exit 1
fi

if [[ "$MPH_VERSION" == "US1_0" ]]; then
  OUTPUT="$ROOT/release-stage/MetroidPrimeHuntersRecomp-linux-v${VERSION}-x86_64.AppImage"
else
  OUTPUT="$ROOT/release-stage/MetroidPrimeHuntersRecomp-${MPH_VERSION}-linux-v${VERSION}-x86_64.AppImage"
fi
ARCH=x86_64 "$APPIMAGE_TOOL" "$APPDIR" "$OUTPUT"
printf 'Created %s\n' "$OUTPUT"
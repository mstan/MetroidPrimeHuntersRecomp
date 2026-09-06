#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 /path/to/AppDir" >&2
  exit 2
fi

APPDIR="$(cd "$1" && pwd)"
TOOLCHAIN="$APPDIR/usr/bin/overlay_toolchain"

set_rpath() {
  local elf="$1" rpath="$2"
  if [ -f "$elf" ]; then
    local current
    current="$(patchelf --print-rpath "$elf" 2>/dev/null || true)"
    [ "$current" = "$rpath" ] && return 0
    patchelf --set-rpath "$rpath" "$elf"
  fi
}

set_app_lib_rpath() {
  local elf="$1"
  [ -f "$elf" ] || return 0
  local rel
  rel="$(realpath --relative-to="$(dirname "$elf")" "$APPDIR/usr/lib")"
  set_rpath "$elf" '$ORIGIN/'"$rel"
}

set_python_extension_rpath() {
  local elf="$1"
  local rel
  rel="$(realpath --relative-to="$(dirname "$elf")" "$APPDIR/usr/lib")"
  set_rpath "$elf" '$ORIGIN:$ORIGIN/'"$rel"
}

refresh_tcc_wrapper() {
  local tcc_dir="$TOOLCHAIN/tcc"
  local runtime="$tcc_dir/tcc-runtime"
  [ -f "$runtime" ] || return 0

  local runtime_sha tree_sha
  runtime_sha="$(sha256sum "$runtime" | awk '{print $1}')"
  tree_sha="$(cd "$tcc_dir" && \
    find tcc-runtime lib -type f -print0 | LC_ALL=C sort -z | \
    xargs -0 sha256sum | sha256sum | awk '{print $1}')"
  printf '#!/bin/sh\n# tcc-runtime-sha256=%s\n# tcc-toolchain-sha256=%s\n' \
    "$runtime_sha" "$tree_sha" > "$tcc_dir/tcc"
  cat >> "$tcc_dir/tcc" <<'EOF'
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$HERE/tcc-runtime" -B"$HERE/lib/tcc" "$@"
EOF
  chmod 0755 "$tcc_dir/tcc"
}

drop_global_ld_library_path() {
  local apprun="$APPDIR/AppRun"
  [ -f "$apprun" ] || return 0
  python3 - "$apprun" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = 'export LD_LIBRARY_PATH="$HERE/usr/lib:${LD_LIBRARY_PATH:-}"\n'
if old in text:
    path.write_text(text.replace(old, ""), encoding="utf-8")
PY
}

if [ -d "$TOOLCHAIN" ]; then
  command -v patchelf >/dev/null 2>&1 || {
    echo "ERROR: patchelf is required to fix Linux AppDir runtime paths" >&2
    exit 1
  }
  set_app_lib_rpath "$TOOLCHAIN/nds_recompile"
  set_app_lib_rpath "$TOOLCHAIN/python/bin/python3-runtime"
  set_app_lib_rpath "$TOOLCHAIN/tcc/tcc-runtime"
  while IFS= read -r -d '' extension; do
    set_python_extension_rpath "$extension"
  done < <(find "$TOOLCHAIN/python/lib" -type f -name '*.so' -print0 2>/dev/null)
  refresh_tcc_wrapper
fi

drop_global_ld_library_path

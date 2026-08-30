#!/usr/bin/env bash
# Compatibility entry point. The audited Linux release path is build-linux.sh.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$#" -ne 1 ]; then
  echo "usage: $0 <version>" >&2
  echo "the legacy runner-build argument is unsupported; use build-linux.sh options" >&2
  exit 2
fi
exec bash "$SCRIPT_DIR/build-linux.sh" --version "$1"

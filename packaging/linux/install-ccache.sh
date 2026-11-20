#!/bin/sh
# Adds ccache to the pinned Linux release toolchain image without touching the
# compiler. Fails the image build if the base is not the pinned toolchain
# (release-toolchain.sha256) or if installing ccache changed any installed
# package version or any file of the toolchain packages.
set -eu

PINNED=/usr/local/share/mph/release-toolchain.sha256
CCACHE_VERSION="${CCACHE_VERSION:-4.5.1-1}"
TOOLCHAIN_PACKAGES="cpp-11 gcc-11 g++-11 libgcc-11-dev libstdc++-11-dev \
  binutils binutils-x86-64-linux-gnu libbinutils libc6 libc6-dev \
  linux-libc-dev libstdc++6 libgcc-s1"

sha256sum --quiet -c "$PINNED" || {
  echo "ERROR: base image is not the pinned release toolchain ($PINNED)" >&2
  exit 1
}

package_versions() {
  dpkg-query -W -f='${binary:Package}\t${Version}\n' | LC_ALL=C sort
}
toolchain_files() {
  for p in $TOOLCHAIN_PACKAGES; do dpkg -L "$p"; done | LC_ALL=C sort -u |
    while IFS= read -r f; do
      if [ -f "$f" ] && [ ! -L "$f" ]; then sha256sum "$f"; fi
    done
}

package_versions > /tmp/packages.before
toolchain_files > /tmp/toolchain.before

apt-get update
apt-get install -y --no-install-recommends "ccache=$CCACHE_VERSION"
rm -rf /var/lib/apt/lists/*

package_versions > /tmp/packages.after
toolchain_files > /tmp/toolchain.after

# New packages (ccache and its libraries) are expected; a changed or removed
# pre-existing package is not.
changed="$(LC_ALL=C comm -23 /tmp/packages.before /tmp/packages.after)"
if [ -n "$changed" ]; then
  echo "ERROR: installing ccache changed existing packages:" >&2
  echo "$changed" >&2
  exit 1
fi
cmp -s /tmp/toolchain.before /tmp/toolchain.after || {
  echo "ERROR: installing ccache changed toolchain files" >&2
  diff /tmp/toolchain.before /tmp/toolchain.after >&2 || true
  exit 1
}
sha256sum --quiet -c "$PINNED"

echo "ccache layer added; new packages:"
LC_ALL=C comm -13 /tmp/packages.before /tmp/packages.after
echo "toolchain manifest: $(wc -l < /tmp/toolchain.after) files," \
  "sha256 $(sha256sum < /tmp/toolchain.after | cut -d' ' -f1)"
cp /tmp/toolchain.after /usr/local/share/mph/toolchain-manifest.sha256
rm -f /tmp/packages.before /tmp/packages.after /tmp/toolchain.before \
  /tmp/toolchain.after
ccache --version | head -1

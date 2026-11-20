# Linux release build image: the pinned release toolchain plus ccache.
#
# This is a thin layer FROM an already-built image of steamdeck.Dockerfile,
# pinned by digest, so rebuilding it never pulls a newer compiler. Rebuilding
# steamdeck.Dockerfile itself resolves ubuntu:22.04 and apt packages afresh
# and therefore produces a NEW toolchain; that is a deliberate release-toolchain
# change, after which BASE_IMAGE and release-toolchain.sha256 must be updated.
#
# install-ccache.sh refuses a base whose gcc/cc1/cc1plus/as/ld bytes differ
# from release-toolchain.sha256 and fails if adding ccache changed any
# installed package or toolchain file.
ARG BASE_IMAGE=mph-linux-release14-builder:ubuntu22.04@sha256:a1b72566cda16446328931505fcc596dcef6807837c95789c7fb8316ad0ccb1d
FROM ${BASE_IMAGE}

ARG CCACHE_VERSION=4.5.1-1
COPY release-toolchain.sha256 /usr/local/share/mph/release-toolchain.sha256
COPY install-ccache.sh /usr/local/share/mph/install-ccache.sh
RUN CCACHE_VERSION="${CCACHE_VERSION}" sh /usr/local/share/mph/install-ccache.sh
COPY --chmod=0755 ccache-run.sh /usr/local/bin/mph-ccache-run

# Defaults only; tools/linux-release-container.ps1 passes these explicitly and
# mounts the persistent host cache at /ccache. Sources are always mounted at
# the same /work paths, so entries are already independent of the host
# worktree path. base_dir is deliberately unset: it makes ccache hand gcc
# relative paths, which changes __FILE__ strings (libslirp g_warn_*) and so
# the runner bytes versus an uncached build.
ENV CCACHE_DIR=/ccache \
    CCACHE_NOHASHDIR=1 \
    CCACHE_MAXSIZE=40G

WORKDIR /work/mph

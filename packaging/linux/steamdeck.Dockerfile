FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ARG SDL3_VERSION=3.2.20

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    file \
    git \
    libasound2-dev \
    libdbus-1-dev \
    libdecor-0-dev \
    libdrm-dev \
    libegl-dev \
    libfribidi-dev \
    libfuse2 \
    libgbm-dev \
    libgles-dev \
    libgl1-mesa-dev \
    libibus-1.0-dev \
    libpulse-dev \
    libsdl2-dev \
    libudev-dev \
    libwayland-dev \
    libx11-dev \
    libxcursor-dev \
    libxext-dev \
    libxfixes-dev \
    libxi-dev \
    libxkbcommon-dev \
    libxrandr-dev \
    libxrender-dev \
    libxss-dev \
    libxtst-dev \
    ninja-build \
    pkg-config \
    python3 \
    python3-pip \
    squashfs-tools \
    wayland-protocols \
    xz-utils \
  && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL "https://www.libsdl.org/release/SDL3-${SDL3_VERSION}.tar.gz" \
      -o /tmp/SDL3.tar.gz \
  && mkdir -p /tmp/SDL3-src /tmp/SDL3-build \
  && tar -xzf /tmp/SDL3.tar.gz -C /tmp/SDL3-src --strip-components=1 \
  && cmake -S /tmp/SDL3-src -B /tmp/SDL3-build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DSDL_TESTS=OFF \
      -DSDL_EXAMPLES=OFF \
  && cmake --build /tmp/SDL3-build -j"$(nproc)" \
  && cmake --install /tmp/SDL3-build \
  && ldconfig \
  && rm -rf /tmp/SDL3.tar.gz /tmp/SDL3-src /tmp/SDL3-build

RUN python3 -m pip install --no-cache-dir \
    cmake==3.29.6 \
    ninja==1.11.1.1 \
    ndspy==4.2.0 \
    Pillow==12.3.0

WORKDIR /work/mph

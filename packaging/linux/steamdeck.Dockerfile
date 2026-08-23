FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    cmake \
    curl \
    file \
    git \
    libfuse2 \
    libgl1-mesa-dev \
    libsdl2-dev \
    ninja-build \
    pkg-config \
    python3 \
    python3-pip \
    squashfs-tools \
    xz-utils \
  && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir \
    cmake==3.29.6 \
    ninja==1.11.1.1 \
    ndspy==4.2.0 \
    Pillow==12.3.0

WORKDIR /work/mph

FROM alpine:3.22

# Common environment variables and mounts.
ENV GEN=ninja
VOLUME /build
WORKDIR /build
RUN git config --global --add safe.directory "*"

VOLUME /ccache
ENV CCACHE_DIR=/ccache

# Minimal C/C++ build dependencies.
RUN set -eux; \
    apk add --no-cache \
      bash \
      build-base \
      ca-certificates \
      ccache \
      cmake \
      curl \
      git \
      jq \
      libtool \
      ninja \
      tar \
      unzip \
      wget \
      xz \
      zip; \
    ccache --version

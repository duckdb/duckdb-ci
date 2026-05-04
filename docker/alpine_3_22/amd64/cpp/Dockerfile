FROM alpine:3.22
COPY docker/cpp_packages.txt /tmp/cpp_packages.txt

# Common environment variables and mounts.
ENV GEN=ninja DUCKDB_PLATFORM=linux_amd64_musl
VOLUME /build
WORKDIR /build

VOLUME /ccache
ENV CCACHE_DIR=/ccache

# Minimal C/C++ build dependencies.
RUN set -eux; \
    common_packages="$(awk ' \
      /^[[:space:]]*($|#)/ { next } \
      /#[[:space:]]*manylinux[[:space:]]*$$/ { next } \
      { sub(/[[:space:]]*#[[:space:]]*alpine[[:space:]]*$$/, ""); print } \
    ' /tmp/cpp_packages.txt | tr '\n' ' ')"; \
    apk add --no-cache \
      ${common_packages} \
      bash \
      build-base \
      ccache \
      cmake; \
    git config --global --add safe.directory "*"; \
    ccache --version

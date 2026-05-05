FROM alpine:3.22
COPY docker/cpp_packages.txt /tmp/cpp_packages.txt
COPY docker/filter_packages.sh /usr/local/bin/filter-packages

# Common environment variables and mounts.
ENV GEN=ninja DUCKDB_PLATFORM=linux_amd64_musl
VOLUME /build
WORKDIR /build

VOLUME /ccache
ENV CCACHE_DIR=/ccache

# Minimal C/C++ build dependencies.
RUN set -eux; \
    chmod +x /usr/local/bin/filter-packages; \
    common_packages="$(filter-packages alpine /tmp/cpp_packages.txt)"; \
    apk add --no-cache \
      ${common_packages} \
      bash \
      build-base \
      ccache \
      cmake; \
    ccache --version

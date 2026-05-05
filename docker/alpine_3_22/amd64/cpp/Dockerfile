FROM alpine:3.22
COPY docker/cpp_packages.txt /tmp/cpp_packages.txt
COPY docker/packages.py /usr/local/bin/packages.py

# Common environment variables and mounts.
ENV GEN=ninja DUCKDB_PLATFORM=linux_amd64_musl
VOLUME /build
WORKDIR /build

VOLUME /ccache
ENV CCACHE_DIR=/ccache

# Minimal C/C++ build dependencies.
RUN set -eux; \
    common_packages="$(python3 /usr/local/bin/packages.py list --distro alpine --packages-file /tmp/cpp_packages.txt)"; \
    apk add --no-cache \
      ${common_packages} \
      bash \
      build-base \
      ccache \
      cmake; \
    python3 /usr/local/bin/packages.py check --distro alpine --packages-file /tmp/cpp_packages.txt; \
    ccache --version

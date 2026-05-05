FROM alpine:3.22
COPY docker/cpp_packages.txt /tmp/cpp_packages.txt
COPY docker/packages.py /usr/local/bin/packages.py
ARG CMAKE_VERSION
ARG CCACHE_VERSION
ARG VCPKG_COMMIT

# Common environment variables and mounts.
ENV GEN=ninja DUCKDB_PLATFORM=linux_amd64_musl
VOLUME /build
WORKDIR /build

VOLUME /ccache
ENV CCACHE_DIR=/ccache

# Minimal C/C++ build dependencies.
RUN set -eux; \
    apk add --no-cache python3; \
    common_packages="$(python3 /usr/local/bin/packages.py list --distro alpine --packages-file /tmp/cpp_packages.txt)"; \
    apk add --no-cache \
      ${common_packages} \
      bash \
      build-base \
      ccache \
      cmake; \
    python3 /usr/local/bin/packages.py check --distro alpine --packages-file /tmp/cpp_packages.txt; \
    git clone "https://github.com/microsoft/vcpkg.git" /vcpkg; \
    git -C /vcpkg checkout --force "${VCPKG_COMMIT}"; \
    VCPKG_FORCE_SYSTEM_BINARIES=1 /vcpkg/bootstrap-vcpkg.sh; \
    ccache --version
ENV VCPKG_ROOT=/vcpkg
ENV VCPKG_TOOLCHAIN_PATH=/vcpkg/scripts/buildsystems/vcpkg.cmake

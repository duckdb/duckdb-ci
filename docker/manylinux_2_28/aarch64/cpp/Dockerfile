FROM quay.io/pypa/manylinux_2_28_aarch64
COPY docker/cpp_packages.txt /tmp/cpp_packages.txt
COPY docker/filter_packages.sh /usr/local/bin/filter-packages

ARG CMAKE_VERSION=4.3.2
ARG CCACHE_VERSION=4.13.5

# Common environment variables and mounts.
ENV GEN=ninja
VOLUME /build
WORKDIR /build

VOLUME /ccache
ENV CCACHE_DIR=/ccache

# Minimal C/C++ build dependencies.
RUN set -eux; \
    chmod +x /usr/local/bin/filter-packages; \
    common_packages="$(filter-packages manylinux /tmp/cpp_packages.txt)"; \
    dnf groupinstall -y "Development Tools"; \
    dnf install -y \
      ${common_packages}; \
    mkdir -p /tmp/ccache && cd /tmp/ccache; \
    wget -nv "https://github.com/ccache/ccache/releases/download/v${CCACHE_VERSION}/ccache-${CCACHE_VERSION}-linux-aarch64-musl-static.tar.xz"; \
    tar -xf "ccache-${CCACHE_VERSION}-linux-aarch64-musl-static.tar.xz"; \
    install -m 0755 "ccache-${CCACHE_VERSION}-linux-aarch64-musl-static/ccache" /usr/local/bin/ccache; \
    cd /; \
    rm -rf /tmp/ccache; \
    ccache --version; \
    ccache --version | awk 'NR==1 { split($3, v, "."); if (v[1] != 4) exit 1 }'; \
    dnf install -y gcc-toolset-14-gcc gcc-toolset-14-gcc-c++ gcc-toolset-14-binutils; \
    mkdir -p /tmp/cmake && cd /tmp/cmake; \
    wget -nv "https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/cmake-${CMAKE_VERSION}-linux-aarch64.sh"; \
    chmod +x "cmake-${CMAKE_VERSION}-linux-aarch64.sh"; \
    ./"cmake-${CMAKE_VERSION}-linux-aarch64.sh" --skip-license --prefix=/usr/local; \
    cmake --version; \
    rm -rf /tmp/cmake; \
    dnf clean all; \
    rm -rf /var/cache/dnf
ENV PATH="/opt/rh/gcc-toolset-14/root/usr/bin:${PATH}"
ENV LD_LIBRARY_PATH="/opt/rh/gcc-toolset-14/root/usr/lib64:${LD_LIBRARY_PATH}"

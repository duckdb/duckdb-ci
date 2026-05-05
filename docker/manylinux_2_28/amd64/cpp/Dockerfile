FROM quay.io/pypa/manylinux_2_28_x86_64
COPY docker/cpp_packages.txt /tmp/cpp_packages.txt
COPY docker/packages.py /usr/local/bin/packages.py

ARG CMAKE_VERSION
ARG CCACHE_VERSION
ARG VCPKG_COMMIT

# Common environment variables and mounts.
ENV GEN=ninja
VOLUME /build
WORKDIR /build

VOLUME /ccache
ENV CCACHE_DIR=/ccache

# Minimal C/C++ build dependencies.
RUN set -eux; \
    common_packages="$(python3 /usr/local/bin/packages.py list --distro manylinux --packages-file /tmp/cpp_packages.txt)"; \
    dnf groupinstall -y "Development Tools"; \
    dnf install -y \
      ${common_packages}; \
    alternatives --install /usr/bin/python3 python3 /usr/local/bin/python3.14 314; \
    alternatives --set python3 /usr/local/bin/python3.14; \
    python3 /usr/local/bin/packages.py check --distro manylinux --packages-file /tmp/cpp_packages.txt; \
    mkdir -p /tmp/ccache && cd /tmp/ccache; \
    wget -nv "https://github.com/ccache/ccache/releases/download/v${CCACHE_VERSION}/ccache-${CCACHE_VERSION}-linux-x86_64-musl-static.tar.xz"; \
    tar -xf "ccache-${CCACHE_VERSION}-linux-x86_64-musl-static.tar.xz"; \
    install -m 0755 "ccache-${CCACHE_VERSION}-linux-x86_64-musl-static/ccache" /usr/local/bin/ccache; \
    cd /; \
    rm -rf /tmp/ccache; \
    ccache --version; \
    ccache --version | awk 'NR==1 { split($3, v, "."); if (v[1] != 4) exit 1 }'; \
    dnf install -y gcc-toolset-14-gcc gcc-toolset-14-gcc-c++ gcc-toolset-14-binutils; \
    mkdir -p /tmp/cmake && cd /tmp/cmake; \
    wget -nv "https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/cmake-${CMAKE_VERSION}-linux-x86_64.sh"; \
    chmod +x "cmake-${CMAKE_VERSION}-linux-x86_64.sh"; \
    ./"cmake-${CMAKE_VERSION}-linux-x86_64.sh" --skip-license --prefix=/usr/local; \
    cmake --version; \
    cd /; \
    rm -rf /tmp/cmake; \
    git clone "https://github.com/microsoft/vcpkg.git" /vcpkg; \
    git -C /vcpkg checkout --force "${VCPKG_COMMIT}"; \
    VCPKG_FORCE_SYSTEM_BINARIES=1 /vcpkg/bootstrap-vcpkg.sh; \
    dnf clean all; \
    rm -rf /var/cache/dnf
ENV PATH="/opt/rh/gcc-toolset-14/root/usr/bin:${PATH}"
ENV LD_LIBRARY_PATH="/opt/rh/gcc-toolset-14/root/usr/lib64:${LD_LIBRARY_PATH}"
ENV VCPKG_ROOT=/vcpkg
ENV VCPKG_TOOLCHAIN_PATH=/vcpkg/scripts/buildsystems/vcpkg.cmake

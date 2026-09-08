FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG CMAKE_VERSION
ARG VCPKG_COMMIT

COPY docker/cpp_packages.txt /tmp/cpp_packages.txt
COPY docker/cpp_python_packages.txt /tmp/cpp_python_packages.txt
COPY docker/packages.py /usr/local/bin/packages.py

ENV GEN=ninja
ENV CC=gcc-11
ENV CXX=g++-11
ENV CCACHE_DIR=/ccache
ENV VCPKG_FORCE_SYSTEM_BINARIES=1
ENV PATH="/opt/duckdb-cpp-venv/bin:${PATH}"

VOLUME /build
VOLUME /ccache
WORKDIR /build

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends python3; \
    common_packages="$(python3 /usr/local/bin/packages.py list --distro ubuntu --packages-file /tmp/cpp_packages.txt)"; \
    apt-get install -y --no-install-recommends ${common_packages}; \
    update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-11 110; \
    update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-11 110; \
    update-alternatives --install /usr/bin/cc cc /usr/bin/gcc-11 110; \
    update-alternatives --install /usr/bin/c++ c++ /usr/bin/g++-11 110; \
    python3 -m venv /opt/duckdb-cpp-venv; \
    python -m pip install --no-cache-dir --upgrade pip; \
    python -m pip install --no-cache-dir -r /tmp/cpp_python_packages.txt; \
    python /usr/local/bin/packages.py check --distro ubuntu --packages-file /tmp/cpp_packages.txt; \
    python /usr/local/bin/packages.py check --distro ubuntu --packages-file /tmp/cpp_python_packages.txt; \
    python /usr/local/bin/packages.py install "cmake@${CMAKE_VERSION}"; \
    git clone "https://github.com/microsoft/vcpkg.git" /vcpkg; \
    git -C /vcpkg checkout --force "${VCPKG_COMMIT}"; \
    /vcpkg/bootstrap-vcpkg.sh; \
    printf %s "${VCPKG_COMMIT}" > /vcpkg/vcpkgLastBuiltCommitId; \
    rm -f /tmp/cpp_packages.txt /tmp/cpp_python_packages.txt; \
    rm -rf /var/lib/apt/lists/*

ENV VCPKG_ROOT=/vcpkg
ENV VCPKG_TOOLCHAIN_PATH=/vcpkg/scripts/buildsystems/vcpkg.cmake

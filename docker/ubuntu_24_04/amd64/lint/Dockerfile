FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG TYPOS_VERSION=1.45.1

COPY docker/lint_packages.txt /tmp/lint_packages.txt
COPY docker/lint_python_packages.txt /tmp/lint_python_packages.txt
COPY docker/packages.py /usr/local/bin/packages.py

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    install -d -m 0755 /etc/apt/keyrings; \
    curl --fail --location --silent --show-error \
      https://apt.llvm.org/llvm-snapshot.gpg.key \
      --output /etc/apt/keyrings/apt.llvm.org.asc; \
    echo "deb [signed-by=/etc/apt/keyrings/apt.llvm.org.asc] https://apt.llvm.org/noble/ llvm-toolchain-noble-20 main" \
      > /etc/apt/sources.list.d/apt.llvm.org.list; \
    apt-get update; \
    lint_packages="$(python3 /usr/local/bin/packages.py list --distro ubuntu --packages-file /tmp/lint_packages.txt)"; \
    apt-get install -y --no-install-recommends ${lint_packages}; \
    python3 /usr/local/bin/packages.py check --distro ubuntu --packages-file /tmp/lint_packages.txt; \
    python3 -m venv /opt/duckdb-lint-venv; \
    /opt/duckdb-lint-venv/bin/python -m pip install --no-cache-dir --upgrade pip; \
    /opt/duckdb-lint-venv/bin/python -m pip install --no-cache-dir -r /tmp/lint_python_packages.txt; \
    /opt/duckdb-lint-venv/bin/python -m pip check; \
    typos_archive="typos-v${TYPOS_VERSION}-x86_64-unknown-linux-musl.tar.gz"; \
    curl --fail --location --silent --show-error \
      "https://github.com/crate-ci/typos/releases/download/v${TYPOS_VERSION}/${typos_archive}" \
      --output "/tmp/${typos_archive}"; \
    mkdir /tmp/typos; \
    tar -xzf "/tmp/${typos_archive}" -C /tmp/typos; \
    typos_binary="$(find /tmp/typos -type f -name typos -print -quit)"; \
    test -n "${typos_binary}"; \
    install -m 0755 "${typos_binary}" /usr/local/bin/typos; \
    rm -rf /tmp/typos "/tmp/${typos_archive}"; \
    rm -f /tmp/lint_packages.txt /tmp/lint_python_packages.txt; \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/duckdb-lint-venv/bin:${PATH}"
ENV CC=gcc
ENV CXX=g++
ENV GEN=ninja
ENV CCACHE_DIR=/ccache
ENV FORMAT_VENV=/opt/duckdb-lint-venv
ENV CLANGD_TIDY_VENV=/opt/duckdb-lint-venv
ENV CLANGD_BINARY=clangd-20
ENV CLANGD_TIDY_QUERY_DRIVER=/usr/bin/**/g++*,/usr/bin/**/gcc*

VOLUME /ccache
VOLUME /build
WORKDIR /build

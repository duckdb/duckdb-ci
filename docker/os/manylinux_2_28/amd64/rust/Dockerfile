ARG MAIN_IMAGE=duckdb-ci/manylinux_2_28_amd64_main:v1
FROM ${MAIN_IMAGE}

# Configure Rust in shared system paths so non-root users can use the toolchain.
ENV RUSTUP_HOME="/usr/local/rustup"
ENV CARGO_HOME="/usr/local/cargo"
ENV PATH="${CARGO_HOME}/bin:${PATH}"
RUN set -eux; \
    mkdir -p "${RUSTUP_HOME}" "${CARGO_HOME}"; \
    chmod -R a+rX "${RUSTUP_HOME}" "${CARGO_HOME}"; \
    curl --silent --show-error --fail --location https://sh.rustup.rs | bash -s -- -y --default-toolchain stable; \
    rustup default stable; \
    rustc --version; \
    cargo --version

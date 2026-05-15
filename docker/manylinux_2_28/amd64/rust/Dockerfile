ARG MAIN_IMAGE=duckdb-ci/manylinux_2_28_amd64_main:v1
FROM ${MAIN_IMAGE}

# Configure Rust.
ENV PATH="/root/.cargo/bin:${PATH}"
RUN set -eux; \
    curl --silent --show-error --fail --location https://sh.rustup.rs | bash -s -- -y; \
    rustc --version; \
    cargo --version

ARG MAIN_IMAGE=duckdb-ci/alpine_3_22_aarch64_main:v1
FROM ${MAIN_IMAGE}

# Configure Rust.
ENV PATH="/root/.cargo/bin:${PATH}"
RUN set -eux; \
    curl --silent --show-error --fail --location https://sh.rustup.rs | sh -s -- -y; \
    rustc --version; \
    cargo --version

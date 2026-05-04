ARG CPP_IMAGE=duckdb-ci/alpine_3_22_amd64_cpp:v1
FROM ${CPP_IMAGE}

# Configure Rust.
ENV PATH="/root/.cargo/bin:${PATH}"
RUN set -eux; \
    curl https://sh.rustup.rs -sSf | sh -s -- -y; \
    rustc --version; \
    cargo --version

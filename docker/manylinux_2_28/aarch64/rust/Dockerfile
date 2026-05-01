ARG CPP_IMAGE=duckdb-ci/manylinux_2_28_aarch64_cpp:v1
FROM ${CPP_IMAGE}

# Configure Rust.
ENV PATH="/root/.cargo/bin:${PATH}"
RUN set -eux; \
    curl https://sh.rustup.rs -sSf | bash -s -- -y; \
    rustc --version; \
    cargo --version

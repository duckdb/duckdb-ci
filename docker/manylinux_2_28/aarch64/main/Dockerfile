ARG CPP_IMAGE=duckdb-ci/manylinux_2_28_aarch64_cpp:v1
FROM ${CPP_IMAGE}

COPY docker/main_packages.txt /tmp/main_packages.txt

RUN set -eux; \
    main_packages="$(awk ' \
      /^[[:space:]]*($|#)/ { next } \
      /#[[:space:]]*alpine[[:space:]]*$$/ { next } \
      { sub(/[[:space:]]*#[[:space:]]*manylinux[[:space:]]*$$/, ""); print } \
    ' /tmp/main_packages.txt | tr '\n' ' ')"; \
    dnf install -y \
      ${main_packages}; \
    dnf clean all; \
    rm -rf /var/cache/dnf

ARG CPP_IMAGE=duckdb-ci/alpine_3_22_amd64_cpp:v1
FROM ${CPP_IMAGE}

COPY docker/main_packages.txt /tmp/main_packages.txt

RUN set -eux; \
    main_packages="$(filter-packages alpine /tmp/main_packages.txt)"; \
    apk add --no-cache \
      ${main_packages}

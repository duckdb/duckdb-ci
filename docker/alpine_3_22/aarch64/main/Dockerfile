ARG CPP_IMAGE=duckdb-ci/alpine_3_22_aarch64_cpp:v1
FROM ${CPP_IMAGE}

COPY docker/main_packages.txt /tmp/main_packages.txt

RUN set -eux; \
    main_packages="$(python3 /usr/local/bin/packages.py list --distro alpine --packages-file /tmp/main_packages.txt)"; \
    apk add --no-cache \
      ${main_packages}; \
    python3 /usr/local/bin/packages.py check --distro alpine --packages-file /tmp/main_packages.txt

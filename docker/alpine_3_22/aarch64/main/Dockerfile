ARG CPP_IMAGE=duckdb-ci/alpine_3_22_aarch64_cpp:v1
FROM ${CPP_IMAGE}

COPY docker/main_packages.txt /tmp/main_packages.txt

ARG RCLONE_INSTALL_VERSION
ARG S5CMD_VERSION

RUN set -eux; \
    main_packages="$(python /usr/local/bin/packages.py list --distro alpine --packages-file /tmp/main_packages.txt)"; \
    apk add --no-cache \
      ${main_packages}; \
    python /usr/local/bin/packages.py check --distro alpine --packages-file /tmp/main_packages.txt; \
    python /usr/local/bin/packages.py install "s5cmd@${S5CMD_VERSION}" "rclone@${RCLONE_INSTALL_VERSION}"

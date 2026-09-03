ARG CPP_IMAGE=duckdb-ci/manylinux_2_28_aarch64_cpp:v1
FROM ${CPP_IMAGE}

COPY docker/main_packages.txt /tmp/main_packages.txt

ARG RCLONE_INSTALL_VERSION
ARG S5CMD_VERSION

RUN set -eux; \
    main_packages="$(python /usr/local/bin/packages.py list --distro manylinux --packages-file /tmp/main_packages.txt)"; \
    dnf install -y \
      ${main_packages}; \
    python /usr/local/bin/packages.py check --distro manylinux --packages-file /tmp/main_packages.txt; \
    python /usr/local/bin/packages.py install "s5cmd@${S5CMD_VERSION}" "rclone@${RCLONE_INSTALL_VERSION}"; \
    dnf clean all; \
    rm -rf /var/cache/dnf

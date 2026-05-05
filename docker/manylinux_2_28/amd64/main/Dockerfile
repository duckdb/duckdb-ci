ARG CPP_IMAGE=duckdb-ci/manylinux_2_28_amd64_cpp:v1
FROM ${CPP_IMAGE}

COPY docker/main_packages.txt /tmp/main_packages.txt

RUN set -eux; \
    main_packages="$(python3 /usr/local/bin/packages.py list --distro manylinux --packages-file /tmp/main_packages.txt)"; \
    dnf install -y \
      ${main_packages}; \
    python3 /usr/local/bin/packages.py check --distro manylinux --packages-file /tmp/main_packages.txt; \
    dnf clean all; \
    rm -rf /var/cache/dnf

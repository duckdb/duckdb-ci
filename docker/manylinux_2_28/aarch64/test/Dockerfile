FROM quay.io/pypa/manylinux_2_28_aarch64

COPY docker/test_packages.txt /tmp/test_packages.txt
COPY docker/packages.py /usr/local/bin/packages.py

RUN set -eux; \
    test_packages="$(python3 /usr/local/bin/packages.py list --distro manylinux --packages-file /tmp/test_packages.txt)"; \
    dnf install -y \
      ${test_packages}; \
    alternatives --install /usr/bin/python3 python3 /usr/local/bin/python3.14 314; \
    alternatives --set python3 /usr/local/bin/python3.14; \
    python3 /usr/local/bin/packages.py check --distro manylinux --packages-file /tmp/test_packages.txt; \
    dnf clean all; \
    rm -rf /var/cache/dnf

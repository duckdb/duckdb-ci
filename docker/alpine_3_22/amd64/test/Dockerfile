FROM alpine:3.22

COPY docker/test_packages.txt /tmp/test_packages.txt
COPY docker/packages.py /usr/local/bin/packages.py

RUN set -eux; \
    apk add --no-cache python3; \
    test_packages="$(python3 /usr/local/bin/packages.py list --distro alpine --packages-file /tmp/test_packages.txt)"; \
    apk add --no-cache \
      ${test_packages}; \
    python3 /usr/local/bin/packages.py check --distro alpine --packages-file /tmp/test_packages.txt

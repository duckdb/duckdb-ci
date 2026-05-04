FROM alpine:3.22
COPY docker/cpp_packages.txt /tmp/cpp_packages.txt

# Common environment variables and mounts.
ENV GEN=ninja
VOLUME /build
WORKDIR /build
RUN git config --global --add safe.directory "*"

VOLUME /ccache
ENV CCACHE_DIR=/ccache

# Minimal C/C++ build dependencies.
RUN set -eux; \
    common_packages="$(grep -vE '^\s*(#|$)' /tmp/cpp_packages.txt | tr '\n' ' ')"; \
    apk add --no-cache \
      ${common_packages} \
      bash \
      build-base \
      ccache \
      cmake \
      ninja; \
    ccache --version

# GitHub actions rejects alpine arm64 and we can workaround it by installing a
# custom gcompat library. See also:
# - https://github.com/actions/runner/issues/1637#issuecomment-4018551958
# - https://github.com/laverdet/alpine-arm64
FROM alpine:3.22 AS gcompat

ARG GCOMPAT_REF=06600632096b14e03e32b234ec0b02a9d4d045e9
ARG NODE_VERSION=24.15.0

COPY docker/alpine_3_22/aarch64/cpp/gcompat.patch /gcompat.patch
RUN <<DONE
  set -eux
  apk add build-base curl git
  curl --silent https://nodejs.org/download/release/v$NODE_VERSION/node-v$NODE_VERSION-linux-arm64.tar.gz | tar xz
  git clone https://git.adelielinux.org/adelie/gcompat.git/
  cd gcompat
  git checkout "$GCOMPAT_REF"
  git apply -p1 < /gcompat.patch
  make LINKER_PATH=/lib/ld-musl-aarch64.so.1 LOADER_NAME=ld-linux-aarch64.so.1 all install
  /node-v$NODE_VERSION-linux-arm64/bin/node -e 'console.log("Hello world.")'
DONE

FROM alpine:3.22
COPY --from=gcompat /lib/libgcompat.so.0 /lib/ld-linux-aarch64.so.1 /lib/

# Common environment variables and mounts.
ENV GEN=ninja DUCKDB_PLATFORM=linux_arm64_musl
VOLUME /build
WORKDIR /build

VOLUME /ccache
ENV CCACHE_DIR=/ccache

COPY docker/cpp_packages.txt /tmp/cpp_packages.txt
COPY docker/packages.py /usr/local/bin/packages.py

# Minimal C/C++ build dependencies.
RUN set -eux; \
    apk add --no-cache python3; \
    common_packages="$(python3 /usr/local/bin/packages.py list --distro alpine --packages-file /tmp/cpp_packages.txt)"; \
    apk add --no-cache \
      ${common_packages} \
      bash \
      build-base \
      ccache \
      cmake \
      libstdc++ \
    ; \
    python3 /usr/local/bin/packages.py check --distro alpine --packages-file /tmp/cpp_packages.txt; \
    sed -i "s:ID=alpine:ID=NotpineForGHA:" /etc/os-release; \
    ccache --version

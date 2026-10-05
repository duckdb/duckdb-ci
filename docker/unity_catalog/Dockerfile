# syntax=docker.io/docker/dockerfile:1.7-labs@sha256:b99fecfe00268a8b556fad7d9c37ee25d716ae08a5d7320e6d51c4dd83246894
# The line above must be the first line of the file: it loads the frontend that has `COPY --parents`.
#
# The stages `base` and `runtime` are the Dockerfile of unitycatalog, with three changes:
# the source comes from the stage `source` and not from the build context, COURSIER_CACHE is
# set, and the uid and gid of the user are fixed.
ARG HOME="/home/unitycatalog"

FROM alpine:3.20@sha256:a4f4213abb84c497377b8544c81b3564f313746700372ec4fe84653e4fb03805 AS source

ARG HOME
ARG UPSTREAM_VERSION

WORKDIR $HOME

RUN apk add --no-cache git \
    && git clone --depth 1 --branch "v${UPSTREAM_VERSION}" https://github.com/unitycatalog/unitycatalog . \
    && git rev-parse HEAD > /UC_REVISION

COPY patches/ /patches/

# A version without a patch has no directory. A patch that does not apply stops the build.
RUN set -eu; \
    for patch in /patches/${UPSTREAM_VERSION}/*.patch; do \
      [ -e "$patch" ] || continue; \
      echo "Applying $patch"; \
      git apply "$patch"; \
    done

# Build stage, using Amazon Corretto jdk 17 on alpine with arm64 support
FROM amazoncorretto:17-alpine3.20-jdk@sha256:c045f0537bc890f9e61924f33f35e9667f696b4f372dad4a73861a9396b5d0b5 AS base

# Dependencies are installed in $HOME/.cache by sbt
ARG HOME
ENV HOME=$HOME

# sbt runs as root, and coursier takes its cache directory from the home of the uid, not from
# HOME: without this the dependency jars go to /root/.cache, the runtime stage does not copy
# them, and the server stops at startup with NoClassDefFoundError.
ENV COURSIER_CACHE="${HOME}/.cache/coursier"

WORKDIR $HOME

COPY --from=source --parents \
    $HOME/dev/ \
    $HOME/build/ \
    $HOME/project/ \
    $HOME/examples/ \
    $HOME/server/ \
    $HOME/api/ \
    $HOME/clients/ \
    $HOME/version.sbt \
    $HOME/build.sbt \
    /

RUN apk add --no-cache bash && ./build/sbt -info clean package

# Small runtime image
FROM alpine:3.20@sha256:a4f4213abb84c497377b8544c81b3564f313746700372ec4fe84653e4fb03805 AS runtime

# Specific JAVA_HOME from Amazon Corretto
ARG JAVA_HOME="/usr/lib/jvm/default-jvm"
ARG USER="unitycatalog"
ARG HOME

# Copy Java from base
COPY --from=base $JAVA_HOME $JAVA_HOME

ENV HOME=$HOME \
    JAVA_HOME=$JAVA_HOME \
    PATH="${JAVA_HOME}/bin:${PATH}"

# Copy build artifacts from base stage
COPY --from=base --parents \
    $HOME/examples/ \
    $HOME/server/ \
    $HOME/api/ \
    $HOME/clients/ \
    $HOME/target/ \
    $HOME/.cache/ \
    /

# The uid and gid are fixed at 2008. A caller runs the container with `--user $(id -u):2008`:
# the process then writes a bind-mounted host directory as the host uid, so the host owns the
# files, and gid 2008 gives it the group permissions on this 550/770 $HOME that the server
# needs to write its etc/ (H2 metastore and config).
RUN <<EOT
set -eu
apk add --no-cache bash
addgroup -g 2008 $USER
adduser -S -u 2008 -G $USER $USER
chmod -R 550 $HOME
mkdir -p $HOME/etc/
chmod -R 770 $HOME/etc/
chown -R $USER:$USER $HOME
EOT

USER $USER

COPY --from=source --chown=$USER:$USER $HOME/bin/ $HOME/bin/
COPY --from=source --chown=$USER:$USER $HOME/etc/ $HOME/etc/

WORKDIR $HOME

CMD ["./bin/start-uc-server"]

# The test service: config, seeding entrypoint and tools on top of the upstream runtime.
# Only this stage changes when one of those files changes.
FROM runtime

USER root

COPY server.properties /home/unitycatalog/etc/conf/server.properties
COPY entrypoint.sh /home/unitycatalog/bin/ducktest-entrypoint.sh
COPY uctl /usr/local/bin/uctl
COPY --from=source /UC_REVISION /home/unitycatalog/UC_REVISION

RUN set -eux; \
    chmod 0755 /home/unitycatalog/bin/ducktest-entrypoint.sh /usr/local/bin/uctl; \
    # The entrypoint adds a passwd entry for the uid of `--user`, and runs with gid 2008.
    chgrp unitycatalog /etc/passwd; chmod g+w /etc/passwd; \
    # Start from an empty metastore: without the bundled H2 db (the sample catalog `unity`)
    # the entrypoint seeds the same state on every start.
    rm -f /home/unitycatalog/etc/db/h2db*.db; \
    # Remove the bundled sample table and volume data.
    rm -rf /home/unitycatalog/etc/data/managed /home/unitycatalog/etc/data/external; \
    mkdir -p /home/unitycatalog/etc/data/duck/cmt /home/unitycatalog/etc/data/duck/plain; \
    # A conf dir on the classpath of the CLI and of the server: the S3A writer loads the
    # core-site.xml that the entrypoint writes there when DUCKTEST_UC_S3_ENDPOINT is set.
    mkdir -p /home/unitycatalog/conf; \
    for cp in /home/unitycatalog/examples/cli/target/classpath /home/unitycatalog/server/target/classpath; do \
      [ -f "$cp" ] && printf ':/home/unitycatalog/conf' >> "$cp" || true; \
    done; \
    chown -R unitycatalog:unitycatalog /home/unitycatalog/etc /home/unitycatalog/conf; \
    chmod -R 0770 /home/unitycatalog/etc /home/unitycatalog/conf

LABEL org.opencontainers.image.source="https://github.com/duckdb/duckdb-ci"

USER unitycatalog
WORKDIR /home/unitycatalog

EXPOSE 8080
ENTRYPOINT ["./bin/ducktest-entrypoint.sh"]

#!/usr/bin/env bash
# Starts the UC server and seeds the catalog `duck` with the schemas `cmt` and `plain`.
#
# The data dir can be a bind mount, so everything that touches it happens here, at
# runtime, and not in the image build.
set -euo pipefail

UC_HOME=/home/unitycatalog
# UC records absolute file:// locations for tables. A client on the host can open them only
# when DUCKTEST_UC_DATA_DIR is a path that is bind-mounted at the same path on the host and in
# the container. The default is good only for a client inside the container.
# The H2 metastore is not under this dir: it stays at $UC_HOME/etc/db.
DATA_DIR="${DUCKTEST_UC_DATA_DIR:-$UC_HOME/etc/data}"
CMT_ROOT="$DATA_DIR/duck/cmt"
PLAIN_ROOT="$DATA_DIR/duck/plain"

cd "$UC_HOME"

# With `--user $(id -u):2008` the uid usually has no passwd entry, and the JVM in delta-kernel
# then stops with "Invalid UID, could not determine effective user". /etc/passwd is writable
# by gid 2008 for this.
uid="$(id -u)"
if ! awk -F: -v u="$uid" '$3==u{f=1} END{exit !f}' /etc/passwd; then
	echo "ducktest:x:${uid}:$(id -g):duck:${UC_HOME}:/sbin/nologin" >>/etc/passwd
fi

# A bind mount hides the dirs of the image behind an empty host dir.
mkdir -p "$CMT_ROOT" "$PLAIN_ROOT"

# An S3-compatible endpoint for the S3A writer of the CLI. The conf dir is on the classpath.
# Without DUCKTEST_UC_S3_ENDPOINT there is no file: local filesystem, or AWS S3 at its default
# endpoint. The static keys are enough for EXTERNAL tables; MANAGED tables on S3 also need
# the s3.* credential vending config in server.properties.
if [ -n "${DUCKTEST_UC_S3_ENDPOINT:-}" ]; then
	cat >"$UC_HOME/conf/core-site.xml" <<XML
<?xml version="1.0"?>
<configuration>
  <property><name>fs.s3a.endpoint</name><value>${DUCKTEST_UC_S3_ENDPOINT}</value></property>
  <property><name>fs.s3a.endpoint.region</name><value>${DUCKTEST_UC_S3_REGION:-us-east-1}</value></property>
  <property><name>fs.s3a.path.style.access</name><value>true</value></property>
  <property><name>fs.s3a.connection.ssl.enabled</name><value>${DUCKTEST_UC_S3_SSL:-false}</value></property>
  <property><name>fs.s3a.access.key</name><value>${DUCKTEST_UC_S3_KEY:-}</value></property>
  <property><name>fs.s3a.secret.key</name><value>${DUCKTEST_UC_S3_SECRET:-}</value></property>
  <property><name>fs.s3a.aws.credentials.provider</name><value>org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider</value></property>
</configuration>
XML
	echo "ducktest-entrypoint: wrote core-site.xml for S3 endpoint $DUCKTEST_UC_S3_ENDPOINT"
else
	rm -f "$UC_HOME/conf/core-site.xml"
fi

./bin/start-uc-server &
SERVER_PID=$!

# `docker stop` then shuts the JVM down cleanly.
term() { kill -TERM "$SERVER_PID" 2>/dev/null || true; }
trap term TERM INT

echo "ducktest-entrypoint: waiting for UC server..."
ready=
for _ in $(seq 1 90); do
	if ./bin/uc catalog list >/dev/null 2>&1; then
		ready=1
		break
	fi
	if ! kill -0 "$SERVER_PID" 2>/dev/null; then
		echo "ducktest-entrypoint: server exited before becoming ready" >&2
		wait "$SERVER_PID"
		exit 1
	fi
	sleep 1
done
if [ -z "$ready" ]; then
	echo "ducktest-entrypoint: server did not become ready in time" >&2
	term
	exit 1
fi

# Each seed step does `get` first, so a restart on a metastore that has the objects changes nothing.
uc() { ./bin/uc "$@"; }

if ! uc catalog get --name duck >/dev/null 2>&1; then
	uc catalog create --name duck --comment "DuckDB test catalog"
	echo "ducktest-entrypoint: created catalog 'duck'"
fi

# UC allocates the location of each MANAGED table, and its __unitystorage tree, under this storage_root.
if ! uc schema get --full_name duck.cmt >/dev/null 2>&1; then
	uc schema create --catalog duck --name cmt \
		--comment "catalog-managed (MANAGED) Delta tables" \
		--storage_root "$CMT_ROOT"
	echo "ducktest-entrypoint: created schema 'duck.cmt' -> $CMT_ROOT"
fi

# No storage_root: each EXTERNAL table brings its own location, and uctl puts it under $PLAIN_ROOT.
if ! uc schema get --full_name duck.plain >/dev/null 2>&1; then
	uc schema create --catalog duck --name plain \
		--comment "plain (EXTERNAL) Delta tables"
	echo "ducktest-entrypoint: created schema 'duck.plain' (plain tables under $PLAIN_ROOT)"
fi

echo "ducktest-entrypoint: ready. catalog 'duck' with schemas 'cmt' and 'plain'."

wait "$SERVER_PID"

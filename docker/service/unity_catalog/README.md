# Unity Catalog service image

[Unity Catalog](https://github.com/unitycatalog/unitycatalog) OSS, built from
source at the git tag `v<upstream>`, and set up for tests:

- managed tables on, authorization off, local filesystem;
- an empty metastore that the entrypoint seeds on each start with one catalog,
  `duck`, and two schemas;
- `uctl`, a script in the image that creates and drops tables.

| Schema | Table type | Result |
| --- | --- | --- |
| `duck.cmt` | `MANAGED` | catalog-managed Delta table (the `catalogManaged` feature), at a location that UC allocates |
| `duck.plain` | `EXTERNAL` | plain Delta log, at a location that the client gives; UC only registers it |

The table type (who owns the storage) and catalog-managed commits are two
separate properties, but the `uc` CLI of UC 0.5 has only these two
combinations: a `MANAGED` create always commits through the catalog, and an
`EXTERNAL` create always writes a plain log. The CLI writes the Delta log with
Delta Kernel, so both are real Delta tables.

## Run

```bash
dir="$(mktemp -d)"
docker run --rm -d --name ducktest-uc \
	--user "$(id -u):2008" \
	-p 8080:8080 \
	-v "${dir}:${dir}" \
	-e "DUCKTEST_UC_DATA_DIR=${dir}" \
	ghcr.io/duckdb/duckdb-ci/service/unity_catalog:0.5.1
```

- `-v "${dir}:${dir}"` with `DUCKTEST_UC_DATA_DIR=${dir}`: UC records an
  absolute `file://` location for each table. A client on the host can open
  that location only when the data dir has the same absolute path on the host
  and in the container. Without the variable the data dir is
  `/home/unitycatalog/etc/data`, which only a client inside the container can
  read.
- `--user "$(id -u):2008"`: the server writes the data dir as the host user, so
  the host can read and remove the files. Gid 2008 is the group of the image; it
  gives the process write access to the metastore and config in the image.

The REST API is at `http://localhost:8080/api/2.1/unity-catalog`. The server is
ready for tests when both schemas exist; the entrypoint makes `duck.plain`
last:

```bash
curl -s 'http://localhost:8080/api/2.1/unity-catalog/schemas?catalog_name=duck'
```

The H2 metastore is in the container, not in the data dir. Each new container
starts with an empty metastore and seeds it again, so a new container on a new
directory is isolated from the one before.

## Storage layout

```
$DUCKTEST_UC_DATA_DIR/
  duck/
    cmt/      storage_root of duck.cmt
      __unitystorage/schemas/<schema-uuid>/tables/<table-uuid>/_delta_log
    plain/    one directory per table
      <table>/_delta_log
```

`duck.plain` has no storage root. `uctl` gives each plain table the location
`$DUCKTEST_UC_DATA_DIR/duck/plain/<table>`. That is a sibling of `duck/cmt`, so
the overlap check of UC passes and no external location is registered.

## uctl

```bash
docker exec ducktest-uc uctl create cmt   id_name "id INT, name STRING"
docker exec ducktest-uc uctl create plain id_name "id INT, name STRING"
docker exec ducktest-uc uctl list cmt
docker exec ducktest-uc uctl get  cmt id_name
docker exec ducktest-uc uctl drop cmt id_name
docker exec ducktest-uc uctl uc schema list --catalog duck   # any `bin/uc` command
```

## S3

The image works on the local filesystem by default. To point the S3A writer of
the CLI at an S3-compatible server, set these on `docker run`:

| Variable | Default |
| --- | --- |
| `DUCKTEST_UC_S3_ENDPOINT` | unset: local filesystem, or AWS S3 at its default endpoint |
| `DUCKTEST_UC_S3_REGION` | `us-east-1` |
| `DUCKTEST_UC_S3_KEY`, `DUCKTEST_UC_S3_SECRET` | empty |
| `DUCKTEST_UC_S3_SSL` | `false` |

With the endpoint set, the entrypoint writes a `core-site.xml` into a conf dir
that is on the classpath of the CLI and of the server.

- `EXTERNAL` tables at `s3://` need only these variables.
  `patches/0.5.1/0001-deltakernel-ambient-s3-creds.patch` makes this possible:
  without it the CLI stops with a null pointer when UC vends no credentials.
- `MANAGED` tables at `s3://` also need credential vending in
  `server.properties` (`s3.bucketPath.0`, region, keys and a non-empty
  `sessionToken`).
- A client that reads the table needs the S3 endpoint from its own config:
  vended credentials do not carry one.

## Build

`../build.sh` builds the image like any other service. The Dockerfile clones
the UC source at `v<upstream>`, applies `patches/<upstream>/*.patch`, and runs
the sbt build of UC; a patch that does not apply stops the build. The commit of
the source is in `/home/unitycatalog/UC_REVISION`.

The stages `base` and `runtime` are the Dockerfile of UC. One change matters
for the build: `COURSIER_CACHE` is set to a directory under `$HOME/.cache`. sbt
runs as root, and coursier takes its cache directory from the home of the uid
(`/root`), not from `HOME`. The runtime stage copies only `$HOME/.cache`, so
without the variable the image has no dependency jars and the server stops at
startup with `NoClassDefFoundError: io/vertx/core/Verticle`.

The first build runs sbt and takes a long time. The config, the entrypoint and
`uctl` are in the last stage, so a change to them reuses the sbt layers.

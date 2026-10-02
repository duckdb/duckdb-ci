# Docker images

This directory defines two kinds of image, both published to
`ghcr.io/duckdb/duckdb-ci`.

## Toolchain images

Images that DuckDB is built and tested in. Each family has its own directory,
`docker/<family>/`, with a `build.sh` and one Dockerfile per architecture and
toolchain:

- [`alpine_3_22`](alpine_3_22/README.md)
- [`manylinux_2_28`](manylinux_2_28/README.md)
- [`ubuntu_24_04`](ubuntu_24_04/README.md)

An image is named `duckdb-ci/<family>_<arch>_<toolchain>` and tagged
`<yyyymmdd>-<sha8>`. Each architecture is a separate image.

The packages installed in these images are listed in `docker/*_packages.txt`;
`docker/packages.py` reads the lists and checks package versions. `docker/test`
holds the tests that run inside the built images.

`make images` builds all of them locally.

## Service images

Images that tests start as a service, such as a local S3 server. Each service
has a directory `docker/service/<name>/`; one `build.sh` builds all of them. See
[`service/README.md`](service/README.md).

An image is named `duckdb-ci/service/<name>` and is one multi-arch manifest. It
has two tags per upstream version: `<upstream>-<yyyymmdd>-<sha8>`, which never
moves, and `<upstream>`, which follows the newest build.

`make service-images` builds all of them locally.

## Dev images

Images that are not for release get the suffix `_dev` on the image name:
toolchain images built for a pull request, and service images built from any
ref but `main`.

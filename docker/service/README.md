# Service images

A service image is a docker image that a test starts as a service: a local S3
server, a local Azure blob server. They are published here so that tests pull
every service from one place, each as one multi-arch image (`linux/amd64` and
`linux/arm64`), and do not depend on the availability or the rate limits of
third-party registries.

- `duckdb-ci/service/rustfs`: [RustFS](https://github.com/rustfs/rustfs), from `rustfs/rustfs`
- `duckdb-ci/service/azurite`: [Azurite](https://github.com/Azure/Azurite), from `mcr.microsoft.com/azure-storage/azurite`

Each image is its upstream image with labels added. It starts with the same
command and environment as upstream.

## Layout

```
docker/service/build.sh           builds any service
docker/service/<name>/Dockerfile
docker/service/<name>/versions    upstream versions to publish, one per line
docker/service/<name>/smoke.sh    starts the image and waits until it answers
```

## Names and tags

The image is `<REPO_PREFIX>/service/<name><IMAGE_SUFFIX>`, for example
`ghcr.io/duckdb/duckdb-ci/service/rustfs`. Each publish sets two tags per
upstream version:

- `<upstream>-<IMAGE_VERSION>`, for example `1.0.0-20260101-0123abcd`: never moves.
- `<upstream>`, for example `1.0.0`: moves to the newest build of that version.

## Build and test locally

```bash
# Build every version in rustfs/versions for the host platform, into the local docker.
IMAGE_VERSION=local ./docker/service/build.sh rustfs
./docker/service/rustfs/smoke.sh duckdb-ci/service/rustfs:1.0.0

# Build one version, listed or not.
IMAGE_VERSION=local ./docker/service/build.sh azurite 3.37.0
./docker/service/azurite/smoke.sh duckdb-ci/service/azurite:3.37.0
```

`build.sh` prints the refs it built. It reads these variables:

| Variable | Default | |
| --- | --- | --- |
| `IMAGE_VERSION` | required | suffix of the tag that never moves |
| `REPO_PREFIX` | `duckdb-ci` | |
| `IMAGE_SUFFIX` | empty | `_dev` for images not built from `main` |
| `PLATFORMS` | host platform | for example `linux/amd64,linux/arm64` |
| `PUSH` | empty | set to `1` to push instead of loading into the local docker |
| `IMAGE_SOURCE` | `https://github.com/duckdb/duckdb-ci` | repository that ghcr links the package to |

A build of more than one platform must push, and needs a builder that can hold
more than one platform:

```bash
docker buildx create --use
docker login ghcr.io
IMAGE_VERSION=local REPO_PREFIX=ghcr.io/<owner>/duckdb-ci PLATFORMS=linux/amd64,linux/arm64 PUSH=1 \
	./docker/service/build.sh rustfs
docker buildx imagetools inspect ghcr.io/<owner>/duckdb-ci/service/rustfs:1.0.0
```

## CI

`.github/workflows/service-images.yml` builds the services whose directory
changed, or all of them when `build.sh` or the workflow changed. It runs
`smoke.sh` on the host-platform image and pushes the multi-arch image only when
that passes. Run it by hand (`workflow_dispatch`) to build one service or all.

Dev images of services are not pruned yet. `prune-dev-images.yml` keeps only the
newest version of a package, and a multi-arch image is several versions (the
index and one untagged manifest per platform), so it would delete parts of a
live image.

## Bump a version

Add the new version to `docker/service/<name>/versions`, and remove an old one
when it needs no more builds. Tags that are published stay.

## Add a service

1. Add `docker/service/<name>/Dockerfile`. It takes `ARG UPSTREAM_VERSION` and
   sets the `org.opencontainers.image.source` label.
2. Add `docker/service/<name>/versions`.
3. Add an executable `docker/service/<name>/smoke.sh <image-ref>` that starts a
   container from the ref, exits 0 when the service answers and 1 when it does
   not, and removes the container.

CI finds the service by its directory. After the first publish, make the new
package public in the ghcr package settings.

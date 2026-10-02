# Service images

A service image is a docker image that a test starts as a service: a local S3
server, a local Azure blob server. They are published here so that tests pull
every service from one place, each as one multi-arch image (`linux/amd64` and
`linux/arm64`), and do not depend on the availability or the rate limits of
third-party registries.

- `duckdb-ci/service/rustfs`: [RustFS](https://github.com/rustfs/rustfs), from `rustfs/rustfs`
- `duckdb-ci/service/azurite`: [Azurite](https://github.com/Azure/Azurite), from `mcr.microsoft.com/azure-storage/azurite`
- `duckdb-ci/service/unity_catalog`: [Unity Catalog](https://github.com/unitycatalog/unitycatalog), built from source; see [`unity_catalog/README.md`](unity_catalog/README.md)

The RustFS and Azurite images are the upstream image with labels added. They
start with the same command and environment as upstream.

## Layout

```
docker/service/build.sh           builds any service
docker/service/merge.sh           joins the images of the architectures under the two tags
docker/service/<name>/Dockerfile
docker/service/<name>/versions    upstream versions to publish, one per line
docker/service/<name>/smoke.sh    starts the image and waits until it answers
docker/service/<name>/...         other files that the Dockerfile copies
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
| `ARCH` | empty | `amd64` or `arm64`: build that one platform as a part for `merge.sh` |
| `PUSH` | empty | set to `1` to push instead of loading into the local docker |
| `IMAGE_SOURCE` | `https://github.com/duckdb/duckdb-ci` | repository that ghcr links the package to |

## Publish

Each architecture is built on a machine of that architecture, and `merge.sh`
joins the results. With `ARCH` set, `build.sh` builds `linux/<ARCH>` and sets
one tag, `<upstream>-<IMAGE_VERSION>-<ARCH>`. It does not set the moving tag.

```bash
docker buildx create --use
docker login ghcr.io
export IMAGE_VERSION=20260101-0123abcd REPO_PREFIX=ghcr.io/<owner>/duckdb-ci IMAGE_SUFFIX=_dev

# On an amd64 machine, and the same with ARCH=arm64 on an arm64 machine.
ARCH=amd64 ./docker/service/build.sh rustfs
./docker/service/rustfs/smoke.sh "${REPO_PREFIX}/service/rustfs_dev:1.0.0-${IMAGE_VERSION}-amd64"
ARCH=amd64 PUSH=1 ./docker/service/build.sh rustfs

# On any machine, when both are pushed.
./docker/service/merge.sh rustfs
```

`merge.sh` takes the same arguments as `build.sh` and reads `IMAGE_VERSION`,
`REPO_PREFIX` and `IMAGE_SUFFIX`. It makes `<upstream>-<IMAGE_VERSION>` and
`<upstream>` from the tags of the architectures, fails when a platform is
missing, and prints the two refs.

A build with `ARCH` reads the layer cache in the tag `buildcache-<ARCH>` of the
same package, and writes it when it pushes. A `_dev` build also reads the cache
of the package without the suffix. The cache holds the layers of all stages, so
a change to a late layer does not run an expensive early stage again. The
builder must be a `docker buildx create` one: the default docker driver cannot
write this cache.

An image with no `RUN` step can also be built for both platforms in one step:

```bash
IMAGE_VERSION=local REPO_PREFIX=ghcr.io/<owner>/duckdb-ci PLATFORMS=linux/amd64,linux/arm64 PUSH=1 \
	./docker/service/build.sh rustfs
docker buildx imagetools inspect ghcr.io/<owner>/duckdb-ci/service/rustfs:1.0.0
```

## CI

`.github/workflows/service-images.yml` builds the services whose directory
changed, or all of them when a script in `docker/service/` or the workflow
changed. Run it by hand (`workflow_dispatch`) to build one service or all.

- `build` runs per service and architecture, on a runner of that architecture:
  `build.sh` with `ARCH`, then `smoke.sh`, then the push of the tag of that
  architecture.
- `merge` runs per service: `merge.sh`. Only this job moves the tag
  `<upstream>`, so a build that fails on one architecture leaves it as it was.

A pull request from another repository, or from dependabot, cannot push: `build`
stops after the smoke test and `merge` does not run.

Dev images of services are not pruned yet. `prune-dev-images.yml` keeps only the
newest version of a package, and a multi-arch image is several versions (the
index, one manifest per platform, and the tags of the architectures and of the
cache), so it would delete parts of a live image.

## Bump a version

Add the new version to `docker/service/<name>/versions`, and remove an old one
when it needs no more builds. Tags that are published stay.

## Add a service

1. Add `docker/service/<name>/Dockerfile`. It takes `ARG UPSTREAM_VERSION` and
   sets the `org.opencontainers.image.source` label. The build context is the
   directory of the service, so the Dockerfile can copy config, scripts and
   patches from it. It must build with no input but the context and
   `UPSTREAM_VERSION`: an image that is built from source gets the source in a
   build stage.
2. Add `docker/service/<name>/versions`.
3. Add an executable `docker/service/<name>/smoke.sh <image-ref>` that starts a
   container from the ref, exits 0 when the service answers and 1 when it does
   not, and removes the container.

Put the steps that take long in early stages or layers and the files of the
service in late ones, so that the layer cache covers the long steps. A service
with more than the upstream image has a `README.md` in its directory.

CI finds the service by its directory. After the first publish, make the new
package public in the ghcr package settings.

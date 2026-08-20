# Ubuntu 24.04 images

This directory defines the AMD64 lint image used by DuckDB formatting,
generation, CI linting, and clangd-based tidy checks:

- `duckdb-ci/ubuntu_24_04_amd64_lint`

The image intentionally supports only AMD64 and uses Ubuntu 24.04 as its base.
It includes GCC, clangd 20, the Python lint and generation tools, shellcheck,
and typos.

## Build locally

```bash
IMAGE_VERSION=dev ./docker/ubuntu_24_04/build.sh amd64
```

The repository-level `make images` target builds this image together with the
other Docker image families.

# Ubuntu 24.04 images

This directory defines AMD64 images based on Ubuntu 24.04:

- `duckdb-ci/ubuntu_24_04_amd64_compat`
- `duckdb-ci/ubuntu_24_04_amd64_lint`

The `compat` image uses GCC 11 by default and contains the C++ build tools,
Python packages, CMake, ccache, and vcpkg used to build and test DuckDB. It is
intended to catch source compatibility regressions with older GCC versions.

The `lint` image includes GCC, clangd 20, the Python lint and generation tools,
shellcheck, and typos.

Both images intentionally support only AMD64.

## Build locally

```bash
IMAGE_VERSION=dev ./docker/ubuntu_24_04/build.sh amd64
```

Build only the compatibility image with:

```bash
IMAGE_VERSION=dev TOOLCHAINS=compat ./docker/ubuntu_24_04/build.sh amd64
```

The repository-level `make images` target builds these images together with the
other Docker image families.

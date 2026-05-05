# manylinux_2_28 images

This directory defines split DuckDB build images for two architectures:

- `duckdb-ci/manylinux_2_28_aarch64_cpp`
- `duckdb-ci/manylinux_2_28_aarch64_main`
- `duckdb-ci/manylinux_2_28_aarch64_rust`
- `duckdb-ci/manylinux_2_28_aarch64_cuda`
- `duckdb-ci/manylinux_2_28_amd64_cpp`
- `duckdb-ci/manylinux_2_28_amd64_main`
- `duckdb-ci/manylinux_2_28_amd64_rust`
- `duckdb-ci/manylinux_2_28_amd64_cuda`

For each architecture, `main`, `rust`, and `cuda` inherit from `cpp`.

## Build locally

```bash
./docker/manylinux_2_28/build.sh
```

The script always builds both `aarch64` and `amd64` image sets.

Image tags are generated automatically as `:YYYYMMDD-<gitsha>`.

## Notes

- CUDA version is fixed to `13` in the build script.
- vcpkg setup stays in CI (`lukka/run-vcpkg`), not in these images.

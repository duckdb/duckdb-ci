# alpine_3_22 images

This directory defines split DuckDB build images for two architectures:

- `duckdb-ci/alpine_3_22_aarch64_cpp`
- `duckdb-ci/alpine_3_22_aarch64_main`
- `duckdb-ci/alpine_3_22_aarch64_rust`
- `duckdb-ci/alpine_3_22_amd64_cpp`
- `duckdb-ci/alpine_3_22_amd64_main`
- `duckdb-ci/alpine_3_22_amd64_rust`

For each architecture, `main` and `rust` inherit from `cpp`.

## Build locally

```bash
./docker/alpine_3_22/build.sh
```

The script always builds both `aarch64` and `amd64` image sets.

Image tags are generated automatically as `:YYYYMMDD-<gitsha>`.

## Notes

- These images are based on Alpine 3.22 and target musl libc.
- vcpkg setup stays in CI (`lukka/run-vcpkg`), not in these images.

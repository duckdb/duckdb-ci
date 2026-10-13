# Extension build matrix

The `groups` input associates extension configuration files with build toolchains.
CUDA groups can optionally specify a semicolon-separated CMake architecture list:

```yaml
groups: |
  cuda12:
    config: .github/config/cuda12.cmake
    toolchain: cuda12
    cuda_archs: "70-real;80-real"
  cuda13:
    config: .github/config/cuda13.cmake
    toolchain: cuda13
    cuda_archs: "90a-real;120"
```

Each build row exposes `cuda_version` (`"12"` or `"13"`, derived from the
toolchain) and `cuda_archs`. Omit `cuda_archs` or set it to `""` to leave
architecture selection to the build toolchain. Lists accept semicolons or commas;
whitespace and duplicates are removed. Non-CUDA build rows have empty
values; a nonempty `cuda_archs` setting requires a CUDA toolchain. The matrix
passes architecture names through without checking toolkit support.

Consumers can forward these fields directly:

```yaml
env:
  CI_CUDA_VERSION: ${{ matrix.cuda_version }}
  CI_CUDA_ARCHS: ${{ matrix.cuda_archs }}
```

Test rows combine artifacts from multiple groups and do not expose these build
settings.

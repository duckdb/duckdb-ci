ARG CPP_IMAGE=duckdb-ci/manylinux_2_28_aarch64_cpp:v1
FROM ${CPP_IMAGE}

ARG CUDA_VERSION=13

# Install CUDA toolkit (nvcc, dev headers, runtime).
RUN set -eux; \
    dnf install -y dnf-plugins-core; \
    dnf config-manager --add-repo \
      https://developer.download.nvidia.com/compute/cuda/repos/rhel8/sbsa/cuda-rhel8.repo; \
    dnf install -y \
      cuda-nvcc-${CUDA_VERSION}-* \
      cuda-cudart-devel-${CUDA_VERSION}-* \
      cuda-driver-devel-${CUDA_VERSION}-* \
      cuda-nvml-devel-${CUDA_VERSION}-* \
      libcurand-devel-${CUDA_VERSION}-* \
      libnvjitlink-devel-${CUDA_VERSION}-* \
      cuda-nvrtc-devel-${CUDA_VERSION}-*; \
    dnf clean all; \
    rm -rf /var/cache/dnf
ENV PATH="/usr/local/cuda/bin:${PATH}"

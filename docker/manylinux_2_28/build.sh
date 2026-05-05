#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
	echo "Usage: $0 <aarch64|amd64>" >&2
	exit 1
fi

ARCH="$1"
case "${ARCH}" in
	aarch64|amd64) ;;
	*)
		echo "Unsupported arch: ${ARCH}" >&2
		exit 1
		;;
esac

if [[ -z "${IMAGE_VERSION:-}" ]]; then
	echo "IMAGE_VERSION must be set" >&2
	exit 1
fi

CUDA_VERSION="13"
BASE_IMAGE="manylinux_2_28"
CMAKE_VERSION="${CMAKE_VERSION:-4.3.2}"
CCACHE_VERSION="${CCACHE_VERSION:-4.13.5}"
VCPKG_COMMIT="${VCPKG_COMMIT:-84bab45d415d22042bd0b9081aea57f362da3f35}"
REPO_PREFIX="${REPO_PREFIX:-duckdb-ci}"
IMAGE_SUFFIX="${IMAGE_SUFFIX:-}"
TOOLCHAINS_INPUT="${TOOLCHAINS:-cpp main rust cuda}"
read -r -a TOOLCHAINS <<< "${TOOLCHAINS_INPUT}"

build_image() {
	local repo="$1"
	local dockerfile="$2"
	local context="$3"
	shift 3

	docker build \
		-f "$dockerfile" \
		-t "${repo}:${IMAGE_VERSION}" \
		"$@" \
		"$context"
}

build_toolchain() {
	local toolchain="$1"
	local root="docker/${BASE_IMAGE}/${ARCH}"
	local repo="${REPO_PREFIX}/${BASE_IMAGE}_${ARCH}_${toolchain}${IMAGE_SUFFIX}"
	local cpp_repo="${REPO_PREFIX}/${BASE_IMAGE}_${ARCH}_cpp${IMAGE_SUFFIX}"

	case "${toolchain}" in
		cpp)
			build_image "${repo}" "${root}/cpp/Dockerfile" "." \
				--build-arg "CMAKE_VERSION=${CMAKE_VERSION}" \
				--build-arg "CCACHE_VERSION=${CCACHE_VERSION}" \
				--build-arg "VCPKG_COMMIT=${VCPKG_COMMIT}"
			;;
		rust)
			build_image \
				"${repo}" \
				"${root}/rust/Dockerfile" \
				"." \
				--build-arg "CPP_IMAGE=${cpp_repo}:${IMAGE_VERSION}"
			;;
		main)
			build_image \
				"${repo}" \
				"${root}/main/Dockerfile" \
				"." \
				--build-arg "CPP_IMAGE=${cpp_repo}:${IMAGE_VERSION}"
			;;
		cuda)
			build_image \
				"${repo}" \
				"${root}/cuda/Dockerfile" \
				"." \
				--build-arg "CPP_IMAGE=${cpp_repo}:${IMAGE_VERSION}" \
				--build-arg "CUDA_VERSION=${CUDA_VERSION}"
			;;
		*)
			echo "Unknown toolchain: ${toolchain}" >&2
			exit 1
			;;
	esac

}

main() {
	set -x

	for toolchain in "${TOOLCHAINS[@]}"; do
		build_toolchain "${toolchain}"
	done

	echo "Built ${ARCH} images with version tag '${IMAGE_VERSION}'"
}

main

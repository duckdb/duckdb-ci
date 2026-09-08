#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
	echo "Usage: $0 <amd64>" >&2
	exit 1
fi

ARCH="$1"
if [[ "${ARCH}" != "amd64" ]]; then
	echo "Unsupported arch: ${ARCH}" >&2
	exit 1
fi

if [[ -z "${IMAGE_VERSION:-}" ]]; then
	echo "IMAGE_VERSION must be set" >&2
	exit 1
fi

BASE_IMAGE="ubuntu_24_04"
CMAKE_VERSION="${CMAKE_VERSION:-4.4.3}"
VCPKG_COMMIT="${VCPKG_COMMIT:-84bab45d415d22042bd0b9081aea57f362da3f35}"
REPO_PREFIX="${REPO_PREFIX:-duckdb-ci}"
IMAGE_SUFFIX="${IMAGE_SUFFIX:-}"
TYPOS_VERSION="${TYPOS_VERSION:-1.45.1}"
TOOLCHAINS_INPUT="${TOOLCHAINS:-compat lint}"
read -r -a TOOLCHAINS <<< "${TOOLCHAINS_INPUT}"

build_toolchain() {
	local toolchain="$1"
	local root="docker/${BASE_IMAGE}/${ARCH}"
	local repo="${REPO_PREFIX}/${BASE_IMAGE}_${ARCH}_${toolchain}${IMAGE_SUFFIX}"

	case "${toolchain}" in
		compat)
			docker build \
				--platform linux/amd64 \
				-f "${root}/compat/Dockerfile" \
				-t "${repo}:${IMAGE_VERSION}" \
				--build-arg "CMAKE_VERSION=${CMAKE_VERSION}" \
				--build-arg "VCPKG_COMMIT=${VCPKG_COMMIT}" \
				.
			;;
		lint)
			docker build \
				--platform linux/amd64 \
				-f "${root}/lint/Dockerfile" \
				-t "${repo}:${IMAGE_VERSION}" \
				--build-arg "TYPOS_VERSION=${TYPOS_VERSION}" \
				.
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

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
REPO_PREFIX="${REPO_PREFIX:-duckdb-ci}"
IMAGE_SUFFIX="${IMAGE_SUFFIX:-}"
TYPOS_VERSION="${TYPOS_VERSION:-1.45.1}"
REPO="${REPO_PREFIX}/${BASE_IMAGE}_${ARCH}_lint${IMAGE_SUFFIX}"

set -x
docker build \
	--platform linux/amd64 \
	-f "docker/${BASE_IMAGE}/${ARCH}/lint/Dockerfile" \
	-t "${REPO}:${IMAGE_VERSION}" \
	--build-arg "TYPOS_VERSION=${TYPOS_VERSION}" \
	.

echo "Built ${ARCH} lint image with version tag '${IMAGE_VERSION}'"

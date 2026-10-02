#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
	echo "Usage: $0 <service> [<upstream-version>]" >&2
	exit 1
fi

SERVICE="$1"
SERVICE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/${SERVICE}"
if [[ ! -f "${SERVICE_DIR}/Dockerfile" ]]; then
	echo "Unknown service: ${SERVICE}" >&2
	exit 1
fi

if [[ -z "${IMAGE_VERSION:-}" ]]; then
	echo "IMAGE_VERSION must be set" >&2
	exit 1
fi

REPO_PREFIX="${REPO_PREFIX:-duckdb-ci}"
IMAGE_SUFFIX="${IMAGE_SUFFIX:-}"
PLATFORMS="${PLATFORMS:-}"
ARCH="${ARCH:-}"
PUSH="${PUSH:-}"
IMAGE_SOURCE="${IMAGE_SOURCE:-}"
REPO="${REPO_PREFIX}/service/${SERVICE}${IMAGE_SUFFIX}"

if [[ -n "${ARCH}" ]]; then
	if [[ -n "${PLATFORMS}" ]]; then
		echo "Set ARCH or PLATFORMS, not both" >&2
		exit 1
	fi
	PLATFORMS="linux/${ARCH}"
fi

if [[ $# -eq 2 ]]; then
	VERSIONS=("$2")
else
	mapfile -t VERSIONS < <(sed -e 's/#.*//' -e 's/[[:space:]]//g' -e '/^$/d' "${SERVICE_DIR}/versions")
fi
if [[ ${#VERSIONS[@]} -eq 0 ]]; then
	echo "No versions in ${SERVICE_DIR}/versions" >&2
	exit 1
fi

if [[ -n "${PUSH}" ]]; then
	OUTPUT="--push"
elif [[ "${PLATFORMS}" == *,* ]]; then
	echo "The local docker holds one platform per image: set PUSH=1 to build ${PLATFORMS}" >&2
	exit 1
else
	OUTPUT="--load"
fi

REVISION="$(git -C "${SERVICE_DIR}" rev-parse HEAD 2>/dev/null || true)"

build_version() {
	local version="$1"
	local refs=("${REPO}:${version}-${IMAGE_VERSION}" "${REPO}:${version}")
	local cache
	local args=(
		"${OUTPUT}"
		# An attestation makes the pushed tag an index, with one more manifest of platform unknown/unknown.
		--provenance=false
		-f "${SERVICE_DIR}/Dockerfile"
		--build-arg "UPSTREAM_VERSION=${version}"
		--label "org.opencontainers.image.version=${version}-${IMAGE_VERSION}"
	)
	if [[ -n "${ARCH}" ]]; then
		# merge.sh makes the two real tags; the moving tag must not point at one platform.
		refs=("${REPO}:${version}-${IMAGE_VERSION}-${ARCH}")
		cache="${REPO}:buildcache-${ARCH}"
		args+=(--cache-from "type=registry,ref=${cache}")
		if [[ -n "${IMAGE_SUFFIX}" ]]; then
			args+=(--cache-from "type=registry,ref=${REPO_PREFIX}/service/${SERVICE}:buildcache-${ARCH}")
		fi
		if [[ -n "${PUSH}" ]]; then
			# mode=max also holds the layers of the stages that are not in the image.
			args+=(--cache-to "type=registry,ref=${cache},mode=max")
		fi
	fi
	local ref
	for ref in "${refs[@]}"; do
		args+=(-t "${ref}")
	done
	if [[ -n "${PLATFORMS}" ]]; then
		args+=(--platform "${PLATFORMS}")
	fi
	if [[ -n "${REVISION}" ]]; then
		args+=(--label "org.opencontainers.image.revision=${REVISION}")
	fi
	if [[ -n "${IMAGE_SOURCE}" ]]; then
		args+=(--label "org.opencontainers.image.source=${IMAGE_SOURCE}")
	fi

	# stdout carries only the refs, for a caller to read.
	(set -x; docker buildx build "${args[@]}" "${SERVICE_DIR}" >&2)
	printf '%s\n' "${refs[@]}"
}

main() {
	for version in "${VERSIONS[@]}"; do
		build_version "${version}"
	done
}

main

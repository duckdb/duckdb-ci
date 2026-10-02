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
PUSH="${PUSH:-}"
IMAGE_SOURCE="${IMAGE_SOURCE:-}"
REPO="${REPO_PREFIX}/service/${SERVICE}${IMAGE_SUFFIX}"

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
	local args=(
		"${OUTPUT}"
		# An attestation is one more manifest in the index, with platform unknown/unknown.
		--provenance=false
		-f "${SERVICE_DIR}/Dockerfile"
		-t "${REPO}:${version}-${IMAGE_VERSION}"
		-t "${REPO}:${version}"
		--build-arg "UPSTREAM_VERSION=${version}"
		--label "org.opencontainers.image.version=${version}-${IMAGE_VERSION}"
	)
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
	echo "${REPO}:${version}-${IMAGE_VERSION}"
	echo "${REPO}:${version}"
}

main() {
	for version in "${VERSIONS[@]}"; do
		build_version "${version}"
	done
}

main

#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
	echo "Usage: $0 <service> [<upstream-version>]" >&2
	exit 1
fi

SERVICE="$1"
SERVICE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/${SERVICE}"
# A service is a directory with a versions file; the toolchain families have none.
if [[ ! -f "${SERVICE_DIR}/versions" ]]; then
	echo "Unknown service: ${SERVICE}" >&2
	exit 1
fi

if [[ -z "${IMAGE_VERSION:-}" ]]; then
	echo "IMAGE_VERSION must be set" >&2
	exit 1
fi

REPO_PREFIX="${REPO_PREFIX:-duckdb-ci}"
IMAGE_SUFFIX="${IMAGE_SUFFIX:-}"
REPO="${REPO_PREFIX}/${SERVICE}${IMAGE_SUFFIX}"
read -r -a ARCHES <<<"${ARCHES:-amd64 arm64}"

if [[ $# -eq 2 ]]; then
	VERSIONS=("$2")
else
	mapfile -t VERSIONS < <(sed -e 's/#.*//' -e 's/[[:space:]]//g' -e '/^$/d' "${SERVICE_DIR}/versions")
fi
if [[ ${#VERSIONS[@]} -eq 0 ]]; then
	echo "No versions in ${SERVICE_DIR}/versions" >&2
	exit 1
fi

merge_version() {
	local version="$1"
	local fixed="${REPO}:${version}-${IMAGE_VERSION}"
	local moving="${REPO}:${version}"
	local sources=() want=() arch ref
	for arch in "${ARCHES[@]}"; do
		sources+=("${fixed}-${arch}")
		want+=("linux/${arch}")
	done

	# stdout carries only the refs, for a caller to read.
	(set -x; docker buildx imagetools create -t "${fixed}" -t "${moving}" "${sources[@]}" >&2)

	for ref in "${fixed}" "${moving}"; do
		if ! docker buildx imagetools inspect --format '{{json .Manifest}}' "${ref}" \
			| jq -e '[.manifests[]?.platform | "\(.os)/\(.architecture)"] as $have | $ARGS.positional - $have == []' \
				--args "${want[@]}" >/dev/null; then
			echo "${ref} does not hold all of ${want[*]}" >&2
			exit 1
		fi
		echo "${ref}"
	done
}

main() {
	for version in "${VERSIONS[@]}"; do
		merge_version "${version}"
	done
}

main

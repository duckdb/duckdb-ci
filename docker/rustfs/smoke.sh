#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
	echo "Usage: $0 <image-ref>" >&2
	exit 1
fi

IMAGE="$1"
NAME="smoke-rustfs-$$"
TIMEOUT="${TIMEOUT:-60}"
code=000

cleanup() {
	local status=$?
	if [[ ${status} -ne 0 ]]; then
		docker logs "${NAME}" >&2 || true
	fi
	docker rm -f "${NAME}" >/dev/null 2>&1 || true
	exit "${status}"
}
trap cleanup EXIT

docker run -d --name "${NAME}" \
	-p 127.0.0.1::9000 \
	-e RUSTFS_ACCESS_KEY=admin \
	-e RUSTFS_SECRET_KEY=password \
	-e RUSTFS_VOLUMES=/data \
	-e RUSTFS_ADDRESS=:9000 \
	-e RUSTFS_CONSOLE_ENABLE=false \
	"${IMAGE}" >/dev/null

port="$(docker port "${NAME}" 9000/tcp | head -n 1)"
url="http://127.0.0.1:${port##*:}/"

for ((i = 0; i < TIMEOUT; i++)); do
	if [[ "$(docker inspect -f '{{.State.Running}}' "${NAME}")" != "true" ]]; then
		echo "${IMAGE}: the container stopped" >&2
		exit 1
	fi
	# The server refuses an unsigned request, and that refusal is the answer; 000 is no answer.
	code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "${url}" || true)"
	if [[ "${code}" != "000" && "${code}" -lt 500 ]]; then
		echo "${IMAGE}: answers with HTTP ${code}"
		exit 0
	fi
	sleep 1
done

echo "${IMAGE}: no answer at ${url} in ${TIMEOUT}s (last HTTP code ${code})" >&2
exit 1

#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
	echo "Usage: $0 <image-ref>" >&2
	exit 1
fi

IMAGE="$1"
NAME="smoke-unity-catalog-$$"
TIMEOUT="${TIMEOUT:-120}"
DATA_DIR="$(mktemp -d)"

cleanup() {
	local status=$?
	if [[ ${status} -ne 0 ]]; then
		docker logs "${NAME}" >&2 || true
	fi
	docker rm -f "${NAME}" >/dev/null 2>&1 || true
	rm -rf "${DATA_DIR}"
	exit "${status}"
}
trap cleanup EXIT

fail() {
	echo "${IMAGE}: $*" >&2
	exit 1
}

uctl() {
	docker exec "${NAME}" uctl "$@"
}

has_delta_log() {
	find "$1" -name _delta_log -type d 2>/dev/null | grep -q .
}

# The same path on the host and in the container: UC records absolute file:// locations.
# The host uid owns what the server writes; gid 2008 is the group of the image.
docker run -d --name "${NAME}" \
	--user "$(id -u):2008" \
	-p 127.0.0.1::8080 \
	-v "${DATA_DIR}:${DATA_DIR}" \
	-e "DUCKTEST_UC_DATA_DIR=${DATA_DIR}" \
	"${IMAGE}" >/dev/null

seeded=
for ((i = 0; i < TIMEOUT; i++)); do
	if [[ "$(docker inspect -f '{{.State.Running}}' "${NAME}")" != "true" ]]; then
		fail "the container stopped"
	fi
	# The entrypoint makes duck.plain last.
	if uctl uc schema get --full_name duck.cmt >/dev/null 2>&1 \
		&& uctl uc schema get --full_name duck.plain >/dev/null 2>&1; then
		seeded=1
		break
	fi
	sleep 1
done
[[ -n "${seeded}" ]] || fail "no schemas duck.cmt and duck.plain in ${TIMEOUT}s"

port="$(docker port "${NAME}" 8080/tcp | head -n 1)"
url="http://127.0.0.1:${port##*:}/api/2.1/unity-catalog/schemas?catalog_name=duck"
curl -fsS -o /dev/null --max-time 10 "${url}" || fail "no answer at ${url}"

out="$(uctl create cmt id_name "id INT, name STRING")"
grep -q catalogManaged <<<"${out}" || fail "duck.cmt.id_name does not have the catalogManaged feature: ${out}"
has_delta_log "${DATA_DIR}/duck/cmt" || fail "no _delta_log under ${DATA_DIR}/duck/cmt on the host"

out="$(uctl create plain id_name "id INT, name STRING")"
if grep -q catalogManaged <<<"${out}"; then
	fail "duck.plain.id_name has the catalogManaged feature: ${out}"
fi
has_delta_log "${DATA_DIR}/duck/plain" || fail "no _delta_log under ${DATA_DIR}/duck/plain on the host"

uctl drop cmt id_name >/dev/null || fail "cannot drop duck.cmt.id_name"
uctl drop plain id_name >/dev/null || fail "cannot drop duck.plain.id_name"
if uctl get cmt id_name >/dev/null 2>&1; then
	fail "duck.cmt.id_name is still there after the drop"
fi

echo "${IMAGE}: seeds duck.cmt and duck.plain, creates and drops a table in each"

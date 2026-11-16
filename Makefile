.PHONY: images service-images prune

IMAGE_VERSION ?= $(shell date -u +%Y%m%d)-$$(git rev-parse --short=8 HEAD)

images:
	IMAGE_VERSION="$(IMAGE_VERSION)" ./docker/alpine_3_22/build.sh aarch64
	IMAGE_VERSION="$(IMAGE_VERSION)" ./docker/alpine_3_22/build.sh amd64
	IMAGE_VERSION="$(IMAGE_VERSION)" ./docker/manylinux_2_28/build.sh aarch64
	IMAGE_VERSION="$(IMAGE_VERSION)" ./docker/manylinux_2_28/build.sh amd64
	IMAGE_VERSION="$(IMAGE_VERSION)" ./docker/ubuntu_24_04/build.sh amd64

service-images:
	set -e; for versions in docker/*/versions; do \
		IMAGE_VERSION="$(IMAGE_VERSION)" ./docker/build_service.sh "$$(basename "$$(dirname "$$versions")")"; \
	done

prune:
	docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}}' \
	| awk '$$1 ~ /(^duckdb-ci\/|\/duckdb-ci\/)/ { print $$2 }' \
	| sort -u \
	| xargs -r docker rmi -f

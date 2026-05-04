.PHONY: images prune

IMAGE_VERSION ?= $(shell date -u +%Y%m%d)-$$(git rev-parse --short=8 HEAD)

images:
	IMAGE_VERSION="$(IMAGE_VERSION)" ./docker/manylinux_2_28/build.sh amd64
	IMAGE_VERSION="$(IMAGE_VERSION)" ./docker/manylinux_2_28/build.sh aarch64
	IMAGE_VERSION="$(IMAGE_VERSION)" ./docker/alpine_3_22/build.sh amd64
	IMAGE_VERSION="$(IMAGE_VERSION)" ./docker/alpine_3_22/build.sh aarch64

prune:
	docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}}' \
	| awk '$$1 ~ /(^duckdb-ci\/|\/duckdb-ci\/)/ { print $$2 }' \
	| sort -u \
	| xargs -r docker rmi -f

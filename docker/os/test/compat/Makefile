.PHONY: package install-deps smoke test clean

MAKEFLAGS += --no-print-directory

DUCKDB_DIR ?= duckdb
ARTIFACT_DIR ?= duckdb-static
BUILD_DIR ?= build
CC ?= cc

# Prefer canonical static lib location and fall back to first libduckdb*.a in release tree.
DUCKDB_STATIC_PRIMARY := $(DUCKDB_DIR)/build/release/src/libduckdb_static.a
DUCKDB_STATIC_FALLBACK := $(shell find "$(DUCKDB_DIR)/build/release" -name 'libduckdb*.a' 2>/dev/null | head -n1)
DUCKDB_STATIC_SRC := $(if $(wildcard $(DUCKDB_STATIC_PRIMARY)),$(DUCKDB_STATIC_PRIMARY),$(DUCKDB_STATIC_FALLBACK))

package:
	set -eu; \
	test -f "$(DUCKDB_DIR)/src/include/duckdb.h"; \
	test -n "$(DUCKDB_STATIC_SRC)"; \
	test -f "$(DUCKDB_STATIC_SRC)"; \
	mkdir -p "$(ARTIFACT_DIR)"; \
	cp "$(DUCKDB_DIR)/src/include/duckdb.h" "$(ARTIFACT_DIR)/duckdb.h"; \
	cp "$(DUCKDB_STATIC_SRC)" "$(ARTIFACT_DIR)/libduckdb.a"; \
	ls -lh "$(ARTIFACT_DIR)"

install-deps:
	set -eu; \
	if command -v apt-get >/dev/null 2>&1; then \
	  apt-get update; \
	  apt-get install -y --no-install-recommends build-essential ca-certificates; \
	elif command -v apk >/dev/null 2>&1; then \
	  apk add --no-cache build-base ca-certificates; \
	else \
	  echo "unsupported package manager" >&2; \
	  exit 1; \
	fi

smoke: $(BUILD_DIR)/compat_smoke
	./$(BUILD_DIR)/compat_smoke

$(BUILD_DIR)/compat_smoke: smoke.c
	set -eu; \
	test -f "$(ARTIFACT_DIR)/duckdb.h"; \
	test -f "$(ARTIFACT_DIR)/libduckdb.a"; \
	mkdir -p "$(BUILD_DIR)"; \
	$(CC) -I"$(ARTIFACT_DIR)" smoke.c "$(ARTIFACT_DIR)/libduckdb.a" -ldl -lpthread -lm -lstdc++ -o "$@"

test: install-deps smoke

clean:
	rm -rf "$(BUILD_DIR)"

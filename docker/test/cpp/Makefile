.PHONY: test test_clang test_gcc test_asan test_tsan clean

MAKEFLAGS += --no-print-directory
BUILD_DIR := build

test: test_clang test_gcc

test_clang:
	$(MAKE) -C asan test_clang BUILD_DIR="../$(BUILD_DIR)"
	$(MAKE) -C tsan test_clang BUILD_DIR="../$(BUILD_DIR)"

test_gcc:
	$(MAKE) -C asan test_gcc BUILD_DIR="../$(BUILD_DIR)"
	$(MAKE) -C tsan test_gcc BUILD_DIR="../$(BUILD_DIR)"

test_asan:
	$(MAKE) -C asan test BUILD_DIR="../$(BUILD_DIR)"

test_tsan:
	$(MAKE) -C tsan test BUILD_DIR="../$(BUILD_DIR)"

clean:
	$(MAKE) -C asan clean BUILD_DIR="../$(BUILD_DIR)"
	$(MAKE) -C tsan clean BUILD_DIR="../$(BUILD_DIR)"

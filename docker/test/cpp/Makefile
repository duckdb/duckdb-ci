.PHONY: test test_asan test_tsan clean

CXX ?= clang++
CXXFLAGS_COMMON := -std=c++17 -O1 -g -fno-omit-frame-pointer
ASAN_FLAGS := -fsanitize=address
TSAN_FLAGS := -fsanitize=thread -pthread

BUILD_DIR := build
ASAN_BIN := $(BUILD_DIR)/asan_smoke
TSAN_BIN := $(BUILD_DIR)/tsan_smoke

test: test_asan test_tsan

test_asan: $(ASAN_BIN)
	$(ASAN_BIN)
	runtime_dir="$$( $(CXX) --print-runtime-dir )"; \
	test -d "$$runtime_dir"; \
	ls "$$runtime_dir" | rg -q 'libclang_rt\.asan|asan' || (echo "ASAN runtime library not found in $$runtime_dir" && exit 1)

test_tsan: $(TSAN_BIN)
	$(TSAN_BIN)
	runtime_dir="$$( $(CXX) --print-runtime-dir )"; \
	test -d "$$runtime_dir"; \
	ls "$$runtime_dir" | rg -q 'libclang_rt\.tsan|tsan' || (echo "TSAN runtime library not found in $$runtime_dir" && exit 1)

$(ASAN_BIN): asan.cpp | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS_COMMON) $(ASAN_FLAGS) $< -o $@

$(TSAN_BIN): tsan.cpp | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS_COMMON) $(TSAN_FLAGS) $< -o $@

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

clean:
	rm -rf $(BUILD_DIR)

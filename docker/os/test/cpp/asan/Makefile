.PHONY: test test_clang test_gcc clean

CLANGXX := clang++
GXX := g++
CXXFLAGS_COMMON := -std=c++17 -O1 -g -fno-omit-frame-pointer
ASAN_FLAGS := -fsanitize=address

BUILD_DIR ?= ../build
SRC := asan.cpp
CLANG_BIN := $(BUILD_DIR)/asan_smoke_clang
GCC_BIN := $(BUILD_DIR)/asan_smoke_gcc

test: test_clang test_gcc

test_clang: $(CLANG_BIN)
	$(CLANG_BIN)

test_gcc: $(GCC_BIN)
	$(GCC_BIN)

$(CLANG_BIN): $(SRC)
	mkdir -p $(BUILD_DIR)
	$(CLANGXX) $(CXXFLAGS_COMMON) $(ASAN_FLAGS) $< -o $@

$(GCC_BIN): $(SRC)
	mkdir -p $(BUILD_DIR)
	$(GXX) $(CXXFLAGS_COMMON) $(ASAN_FLAGS) $< -o $@

clean:
	rm -f $(CLANG_BIN) $(GCC_BIN)

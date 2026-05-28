#include <atomic>
#include <iostream>
#include <thread>
#include <vector>

int main() {
    std::atomic<int> counter{0};
    std::vector<std::thread> threads;
    threads.reserve(4);

    for (int i = 0; i < 4; i++) {
        threads.emplace_back([&counter]() {
            for (int j = 0; j < 1000; j++) {
                counter.fetch_add(1, std::memory_order_relaxed);
            }
        });
    }

    for (auto &thread : threads) {
        thread.join();
    }

    const int result = counter.load(std::memory_order_relaxed);
    std::cout << "tsan_ok=" << result << std::endl;
    return result == 4000 ? 0 : 1;
}

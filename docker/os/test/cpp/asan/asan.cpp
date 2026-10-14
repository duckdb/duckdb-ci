#include <iostream>
#include <vector>

int main() {
    std::vector<int> values = {1, 2, 3, 4};
    int sum = 0;
    for (int value : values) {
        sum += value;
    }
    std::cout << "asan_ok=" << sum << std::endl;
    return sum == 10 ? 0 : 1;
}

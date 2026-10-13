#include <iostream>
using namespace std;

// 原创演示：累计和使用 long long，覆盖空数组、负数和整数边界。
int main() {
    int n;
    cin >> n;
    long long sum = 0;
    for (int i = 0; i < n; ++i) {
        long long value;
        cin >> value;
        sum += value;
    }
    cout << sum << '\n';
    return 0;
}

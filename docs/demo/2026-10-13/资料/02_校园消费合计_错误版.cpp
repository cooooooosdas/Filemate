#include <iostream>
using namespace std;

// 原创演示：故意使用 int 累计，展示大整数边界错误。
int main() {
    int n;
    cin >> n;
    int sum = 0;
    for (int i = 0; i < n; ++i) {
        int value;
        cin >> value;
        sum += value;
    }
    cout << sum << '\n';
    return 0;
}

"""原创 C++17 题目与确定性测试点。"""

from __future__ import annotations

from typing import Any

STARTER = "#include <iostream>\nusing namespace std;\n\nint main() {\n    // 从标准输入读取数据，将答案输出到标准输出。\n    return 0;\n}\n"


def _problem(identifier: str, title: str, difficulty: str, tags: list[str], statement: str,
             examples: list[dict[str, str]], tests: list[tuple[str, str, str]], hint: str) -> dict[str, Any]:
    return {
        "id": identifier, "version": 1, "title": title, "difficulty": difficulty,
        "tags": tags, "statement": statement, "examples": examples,
        "tests": [{"name": name, "input": data, "expected": expected}
                  for name, data, expected in tests],
        "hint": hint, "starter": STARTER, "language": "cpp17",
        "time_limit_ms": 1000, "memory_limit_mb": 256,
        "attribution": "FileMate 原创题目与测试数据（2026），项目内授权使用",
    }


PROBLEMS: list[dict[str, Any]] = [
    _problem("array-sum", "校园消费合计", "简单", ["数组", "整数边界"],
             "输入 n（0≤n≤100000），随后输入 n 个整数（每个在 -10^9 到 10^9 之间）。"
             "输出它们的和。n=0 时输出 0。答案可能超过 32 位整数范围。",
             [{"input": "3\n12 -2 5\n", "output": "15\n"}],
             [("普通账单", "3\n12 -2 5\n", "15"), ("空账单", "0\n", "0"),
              ("负数账单", "4\n-1 -2 -3 -4\n", "-10"),
              ("64 位边界", "4\n1000000000 1000000000 1000000000 1000000000\n", "4000000000"),
              ("相互抵消", "4\n-1000000000 1000000000 -7 7\n", "0")],
             "累计值使用 long long，空数组的初始和为 0。"),
    _problem("palindrome", "社团口令回文", "简单", ["字符串", "双指针"],
             "输入一行长度 0 到 100000 的 ASCII 字符串（可能包含空格）。"
             "逐字符区分大小写和空格判断是否回文，是则输出 YES，否则输出 NO。空串是回文。",
             [{"input": "level\n", "output": "YES\n"}],
             [("普通回文", "level\n", "YES"), ("非回文", "campus\n", "NO"),
              ("空串", "\n", "YES"), ("单字符", "a\n", "YES"),
              ("包含空格", "a a\n", "YES"), ("大小写", "Aa\n", "NO")],
             "使用 getline 保留空格；空字符串不要计算无符号的 size()-1。"),
    _problem("lower-bound", "成绩区间起点", "简单", ["二分", "数组"],
             "第一行输入 n 和 x（0≤n≤100000；x 和数组元素在 -10^9 到 10^9 之间），"
             "第二行输入 n 个非递减整数。输出第一个大于等于 x 的元素下标（从 0 开始），不存在输出 n。",
             [{"input": "5 3\n1 3 3 5 7\n", "output": "1\n"}],
             [("重复成绩", "5 3\n1 3 3 5 7\n", "1"), ("空数组", "0 2\n", "0"),
              ("大于全部", "3 9\n1 2 3\n", "3"), ("小于全部", "3 -3\n-2 0 5\n", "0"),
              ("单元素", "1 4\n4\n", "0")],
             "维护左闭右开区间 [l,r)，遇到相等值继续向左查找。"),
    _problem("brackets", "表达式括号校验", "中等", ["栈", "字符串"],
             "输入一行仅包含 ()[]{} 的字符串，长度 0 到 100000。"
             "所有括号按类型正确嵌套配对时输出 YES，否则输出 NO。空串合法。",
             [{"input": "([]{})\n", "output": "YES\n"}],
             [("正确嵌套", "([]{})\n", "YES"), ("交叉配对", "([)]\n", "NO"),
              ("未闭合", "((\n", "NO"), ("先右括号", ")\n", "NO"),
              ("空表达式", "\n", "YES"), ("并列括号", "()[]{}\n", "YES")],
             "右括号只与栈顶配对；处理完毕后栈也应为空。"),
    _problem("intervals", "活动室排期", "中等", ["贪心", "排序"],
             "输入 n（0≤n≤100000），随后 n 行每行输入开始时间 s 和结束时间 e"
             "（0≤s<e≤10^9）。同一时刻只能进行一项活动；前项结束时刻等于后项开始时刻允许衔接。"
             "输出最多可安排的活动数。",
             [{"input": "3\n1 3\n2 4\n3 5\n", "output": "2\n"}],
             [("普通冲突", "3\n1 3\n2 4\n3 5\n", "2"), ("空排期", "0\n", "0"),
              ("全部重叠", "3\n0 9\n1 8\n2 7\n", "1"),
              ("首尾衔接", "3\n0 1\n1 2\n2 3\n", "3"),
              ("不能按开始贪心", "4\n0 10\n1 2\n2 3\n3 4\n", "3")],
             "按结束时刻排序，每次选择与已选活动不冲突的最早结束活动。"),
    _problem("tree-depth", "课程依赖树高度", "中等", ["树", "队列"],
             "输入 n（0≤n≤100000）；n>0 时输入 n 个父节点编号 p_i，节点编号为 1 到 n。"
             "恰有一个 p_i=0 表示根，其余保证形成一棵树。输出最大深度，根深度为 1；n=0 输出 0。",
             [{"input": "5\n0 1 1 2 2\n", "output": "3\n"}],
             [("普通树", "5\n0 1 1 2 2\n", "3"), ("空树", "0\n", "0"),
              ("单节点", "1\n0\n", "1"), ("根不在首位", "3\n2 0 2\n", "2"),
              ("链式依赖", "5\n0 1 2 3 4\n", "5")],
             "使用显式队列或栈避免长链递归栈溢出，先找到父节点为 0 的根。"),
    _problem("shortest-path", "校区最短路线", "困难", ["图", "最短路", "优先队列"],
             "输入 n、m、s、t（1≤n≤100000，0≤m≤200000）。随后 m 行输入有向边 u v w"
             "（1≤u,v≤n，0≤w≤10^9）。输出 s 到 t 的最短距离；无法到达输出 -1。允许重边和自环。",
             [{"input": "3 3 1 3\n1 2 2\n2 3 3\n1 3 9\n", "output": "5\n"}],
             [("普通路线", "3 3 1 3\n1 2 2\n2 3 3\n1 3 9\n", "5"),
              ("不可达", "3 1 1 3\n1 2 1\n", "-1"), ("同一起终点", "1 0 1 1\n", "0"),
              ("零权重与重边", "3 4 1 3\n1 2 9\n1 2 0\n2 3 0\n3 3 0\n", "0"),
              ("64 位距离", "4 3 1 4\n1 2 1000000000\n2 3 1000000000\n3 4 1000000000\n", "3000000000")],
             "所有边权非负，可使用 Dijkstra；距离用 long long，优先队列跳过过期状态。"),
    _problem("knapsack", "竞赛资料装包", "困难", ["动态规划", "背包"],
             "输入 n 和容量 C（0≤n≤200，0≤C≤10000）。随后 n 行输入重量 w 和价值 v"
             "（1≤w≤10000，0≤v≤10^9）。每件资料最多选一次，输出总重量不超过 C 时的最大总价值。",
             [{"input": "3 5\n2 3\n3 4\n4 5\n", "output": "7\n"}],
             [("普通装包", "3 5\n2 3\n3 4\n4 5\n", "7"), ("无资料", "0 9\n", "0"),
              ("零容量", "2 0\n1 9\n2 3\n", "0"), ("禁止重复选择", "1 4\n2 3\n", "3"),
              ("全部过重", "2 1\n2 4\n3 5\n", "0"),
              ("64 位价值", "3 3\n1 1000000000\n1 1000000000\n1 1000000000\n", "3000000000")],
             "一维 0/1 背包按容量倒序更新；价值累计使用 long long。"),
]

_BOUNDARY_CASES = {
    "array-sum": ("100000\n" + "1000000000 " * 100000 + "\n", "100000000000000"),
    "palindrome": ("a" * 100000 + "\n", "YES"),
    "lower-bound": ("100000 1\n" + "0 " * 100000 + "\n", "100000"),
    "brackets": ("()" * 50000 + "\n", "YES"),
    "intervals": ("100000\n" + "".join(f"{i} {i+1}\n" for i in range(100000)), "100000"),
    "tree-depth": ("100000\n" + " ".join(str(i) for i in range(100000)) + "\n", "100000"),
    "shortest-path": ("100000 99999 1 100000\n" +
                      "".join(f"{i} {i+1} 1\n" for i in range(1, 100000)), "99999"),
    "knapsack": ("200 10000\n" + "50 1000000000\n" * 200, "200000000000"),
}
for _item in PROBLEMS:
    _input, _expected = _BOUNDARY_CASES[_item["id"]]
    _item["tests"].append({"name": "最大规模边界", "input": _input, "expected": _expected})


def get_problem(problem_id: str) -> dict[str, Any]:
    """取得固定版本的题目。"""
    for problem in PROBLEMS:
        if problem["id"] == problem_id:
            return problem
    raise KeyError(problem_id)


def public_problem(problem: dict[str, Any]) -> dict[str, Any]:
    """公开题面与资源限制，测试数据通过结果单独查看。"""
    return {key: value for key, value in problem.items() if key != "tests"} | {
        "test_count": len(problem["tests"]),
    }

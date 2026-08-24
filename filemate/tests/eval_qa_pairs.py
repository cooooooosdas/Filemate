"""评测集种子：30+ 道问答对，用于检索质量评估。"""
from __future__ import annotations

from typing import Any

# ──────────────────────────────────────────────
# 知识库语料（与 test_flow2.py 一致）
# ──────────────────────────────────────────────
CORPUS = """
进程是操作系统资源分配的基本单位。
线程是CPU调度的基本单位。
进程间通信方式包括：管道、消息队列、共享内存、信号量。
线程同步机制包括：互斥锁、条件变量、信号量、读写锁。
内存管理采用分页机制，页面置换算法有FIFO、LRU、OPT。
文件系统采用树形目录结构，支持绝对路径和相对路径。
死锁的四个必要条件是：互斥、持有并等待、不可剥夺、循环等待。
死锁处理策略包括：预防、避免、检测与解除。
进程调度算法包括：FCFS、SJF、优先级、RR、MLFQ。
虚拟内存允许程序使用比物理内存更大的地址空间。
分段存储管理将程序分成若干段，每段是一个逻辑单位。
分页和分段的主要区别：分页是物理视角，分段是逻辑视角。
TCP三次握手过程：SYN → SYN-ACK → ACK。
TCP四次挥手过程：FIN → ACK → FIN → ACK。
UDP是无连接协议，不保证可靠传输。
HTTP状态码200表示成功，404表示资源未找到，500表示服务器内部错误。
IP地址分为IPv4和IPv6，子网掩码用于划分网络地址和主机地址。
DNS协议将域名解析为IP地址，使用53端口。
HTTPS在HTTP基础上加入SSL/TLS加密，使用443端口。
关系数据库的ACID特性：原子性、一致性、隔离性、持久性。
SQL的JOIN操作包括：INNER JOIN、LEFT JOIN、RIGHT JOIN、FULL JOIN。
索引可以显著加快查询速度，但会降低写入性能。
事务的隔离级别包括：读未提交、读已提交、可重复读、串行化。
二叉搜索树的查找、插入、删除平均时间复杂度为O(log n)。
哈希表的平均查找时间复杂度为O(1)，最坏情况为O(n)。
快速排序的平均时间复杂度为O(n log n)，最坏情况为O(n^2)。
归并排序的时间复杂度稳定在O(n log n)，需要额外空间。
动态规划通过子问题重叠和最优子结构来优化计算。
贪心算法在每一步选择局部最优解，但不一定得到全局最优解。
栈是后进先出（LIFO）的数据结构，队列是先进先出（FIFO）的数据结构。
图的遍历算法有深度优先搜索（DFS）和广度优先搜索（BFS）。
最小生成树算法有Prim算法和Kruskal算法。
最短路径算法有Dijkstra算法和Floyd算法。
"""

# ──────────────────────────────────────────────
# 问答对定义
# ──────────────────────────────────────────────
QA_PAIRS: list[dict[str, Any]] = [
    # ── 操作系统基础 ──
    {
        "id": "os-001",
        "query": "进程是什么？它的主要特征是什么？",
        "expected_chunks": ["进程是操作系统资源分配的基本单位", "进程是资源分配的基本单位"],
        "category": "操作系统",
        "difficulty": "basic",
    },
    {
        "id": "os-002",
        "query": "线程和进程有什么区别？",
        "expected_chunks": ["线程是CPU调度的基本单位", "进程是操作系统资源分配的基本单位"],
        "category": "操作系统",
        "difficulty": "basic",
    },
    {
        "id": "os-003",
        "query": "进程间通信有哪些方式？",
        "expected_chunks": ["进程间通信方式包括", "管道、消息队列、共享内存、信号量"],
        "category": "操作系统",
        "difficulty": "basic",
    },
    {
        "id": "os-004",
        "query": "线程同步机制有哪些？",
        "expected_chunks": ["线程同步机制包括", "互斥锁、条件变量、信号量、读写锁"],
        "category": "操作系统",
        "difficulty": "basic",
    },
    {
        "id": "os-005",
        "query": "什么是死锁？产生死锁的四个必要条件是什么？",
        "expected_chunks": ["死锁的四个必要条件", "互斥、持有并等待、不可剥夺、循环等待"],
        "category": "操作系统",
        "difficulty": "intermediate",
    },
    {
        "id": "os-006",
        "query": "如何处理死锁？",
        "expected_chunks": ["死锁处理策略包括", "预防、避免、检测与解除"],
        "category": "操作系统",
        "difficulty": "intermediate",
    },
    {
        "id": "os-007",
        "query": "常见的进程调度算法有哪些？",
        "expected_chunks": ["进程调度算法包括", "FCFS、SJF、优先级、RR、MLFQ"],
        "category": "操作系统",
        "difficulty": "intermediate",
    },
    {
        "id": "os-008",
        "query": "内存管理采用什么机制？页面置换算法有哪些？",
        "expected_chunks": ["内存管理采用分页机制", "页面置换算法有FIFO、LRU、OPT"],
        "category": "操作系统",
        "difficulty": "basic",
    },
    {
        "id": "os-009",
        "query": "虚拟内存的作用是什么？",
        "expected_chunks": ["虚拟内存允许程序使用比物理内存更大的地址空间"],
        "category": "操作系统",
        "difficulty": "intermediate",
    },
    {
        "id": "os-010",
        "query": "分页存储和分段存储有什么区别？",
        "expected_chunks": ["分页和分段的主要区别", "分页是物理视角", "分段是逻辑视角"],
        "category": "操作系统",
        "difficulty": "intermediate",
    },
    # ── 计算机网络 ──
    {
        "id": "net-001",
        "query": "TCP三次握手的过程是什么？",
        "expected_chunks": ["TCP三次握手过程", "SYN → SYN-ACK → ACK"],
        "category": "计算机网络",
        "difficulty": "basic",
    },
    {
        "id": "net-002",
        "query": "TCP四次挥手的过程是怎样的？",
        "expected_chunks": ["TCP四次挥手过程", "FIN → ACK → FIN → ACK"],
        "category": "计算机网络",
        "difficulty": "basic",
    },
    {
        "id": "net-003",
        "query": "UDP协议有什么特点？",
        "expected_chunks": ["UDP是无连接协议", "不保证可靠传输"],
        "category": "计算机网络",
        "difficulty": "basic",
    },
    {
        "id": "net-004",
        "query": "HTTP状态码200、404、500分别表示什么？",
        "expected_chunks": ["HTTP状态码200表示成功", "404表示资源未找到", "500表示服务器内部错误"],
        "category": "计算机网络",
        "difficulty": "basic",
    },
    {
        "id": "net-005",
        "query": "子网掩码的作用是什么？",
        "expected_chunks": ["子网掩码用于划分网络地址和主机地址"],
        "category": "计算机网络",
        "difficulty": "intermediate",
    },
    {
        "id": "net-006",
        "query": "DNS协议的作用和端口号是什么？",
        "expected_chunks": ["DNS协议将域名解析为IP地址", "使用53端口"],
        "category": "计算机网络",
        "difficulty": "basic",
    },
    {
        "id": "net-007",
        "query": "HTTPS和HTTP有什么区别？",
        "expected_chunks": ["HTTPS在HTTP基础上加入SSL/TLS加密", "使用443端口"],
        "category": "计算机网络",
        "difficulty": "basic",
    },
    # ── 数据库 ──
    {
        "id": "db-001",
        "query": "关系数据库的ACID特性是什么？",
        "expected_chunks": ["ACID特性", "原子性、一致性、隔离性、持久性"],
        "category": "数据库",
        "difficulty": "basic",
    },
    {
        "id": "db-002",
        "query": "SQL的JOIN操作有哪些类型？",
        "expected_chunks": ["SQL的JOIN操作包括", "INNER JOIN、LEFT JOIN、RIGHT JOIN、FULL JOIN"],
        "category": "数据库",
        "difficulty": "basic",
    },
    {
        "id": "db-003",
        "query": "索引的优缺点是什么？",
        "expected_chunks": ["索引可以显著加快查询速度", "但会降低写入性能"],
        "category": "数据库",
        "difficulty": "intermediate",
    },
    {
        "id": "db-004",
        "query": "事务的隔离级别有哪些？",
        "expected_chunks": ["事务的隔离级别包括", "读未提交、读已提交、可重复读、串行化"],
        "category": "数据库",
        "difficulty": "intermediate",
    },
    # ── 数据结构 ──
    {
        "id": "ds-001",
        "query": "二叉搜索树的查找、插入、删除时间复杂度是多少？",
        "expected_chunks": ["二叉搜索树的查找、插入、删除平均时间复杂度为O(log n)"],
        "category": "数据结构",
        "difficulty": "basic",
    },
    {
        "id": "ds-002",
        "query": "哈希表的查找时间复杂度是多少？",
        "expected_chunks": ["哈希表的平均查找时间复杂度为O(1)", "最坏情况为O(n)"],
        "category": "数据结构",
        "difficulty": "basic",
    },
    {
        "id": "ds-003",
        "query": "快速排序和归并排序的时间复杂度分别是多少？",
        "expected_chunks": ["快速排序的平均时间复杂度为O(n log n)", "归并排序的时间复杂度稳定在O(n log n)"],
        "category": "数据结构",
        "difficulty": "intermediate",
    },
    {
        "id": "ds-004",
        "query": "栈和队列的区别是什么？",
        "expected_chunks": [
            "栈是后进先出（LIFO）的数据结构",
            "队列是先进先出（FIFO）的数据结构",
            "后进先出",
            "先进先出",
        ],
        "category": "数据结构",
        "difficulty": "basic",
    },
    {
        "id": "ds-005",
        "query": "图的遍历算法有哪些？",
        "expected_chunks": ["图的遍历算法有深度优先搜索（DFS）和广度优先搜索（BFS）"],
        "category": "数据结构",
        "difficulty": "basic",
    },
    {
        "id": "ds-006",
        "query": "最小生成树算法有哪些？",
        "expected_chunks": ["最小生成树算法有Prim算法和Kruskal算法"],
        "category": "数据结构",
        "difficulty": "intermediate",
    },
    {
        "id": "ds-007",
        "query": "最短路径算法有哪些？",
        "expected_chunks": ["最短路径算法有Dijkstra算法和Floyd算法"],
        "category": "数据结构",
        "difficulty": "intermediate",
    },
    # ── 算法 ──
    {
        "id": "algo-001",
        "query": "动态规划和贪心算法的区别是什么？",
        "expected_chunks": ["动态规划通过子问题重叠和最优子结构来优化计算", "贪心算法在每一步选择局部最优解"],
        "category": "算法",
        "difficulty": "intermediate",
    },
    {
        "id": "algo-002",
        "query": "快速排序的最坏情况时间复杂度是多少？",
        "expected_chunks": ["快速排序的平均时间复杂度为O(n log n)", "最坏情况为O(n^2)"],
        "category": "算法",
        "difficulty": "intermediate",
    },
    {
        "id": "algo-003",
        "query": "归并排序需要额外的空间吗？",
        "expected_chunks": ["归并排序的时间复杂度稳定在O(n log n)", "需要额外空间"],
        "category": "算法",
        "difficulty": "intermediate",
    },
    # ── 文件系统 ──
    {
        "id": "fs-001",
        "query": "文件系统采用什么目录结构？",
        "expected_chunks": ["文件系统采用树形目录结构", "支持绝对路径和相对路径"],
        "category": "文件系统",
        "difficulty": "basic",
    },
    # ── 综合 ──
    {
        "id": "gen-001",
        "query": "操作系统的核心功能有哪些？",
        "expected_chunks": ["进程是操作系统资源分配的基本单位", "内存管理采用分页机制", "文件系统采用树形目录结构"],
        "category": "综合",
        "difficulty": "basic",
    },
    {
        "id": "gen-002",
        "query": "网络协议中常用的端口号有哪些？",
        "expected_chunks": ["DNS使用53端口", "HTTPS使用443端口"],
        "category": "计算机网络",
        "difficulty": "basic",
    },
    {
        "id": "gen-003",
        "query": "IP地址的分类和子网划分是什么？",
        "expected_chunks": ["IP地址分为IPv4和IPv6", "子网掩码用于划分网络地址和主机地址"],
        "category": "计算机网络",
        "difficulty": "intermediate",
    },
    {
        "id": "gen-004",
        "query": "数据库索引为什么能加快查询？",
        "expected_chunks": ["索引可以显著加快查询速度"],
        "category": "数据库",
        "difficulty": "basic",
    },
    {
        "id": "gen-005",
        "query": "操作系统中的内存管理策略有哪些？",
        "expected_chunks": ["内存管理采用分页机制", "虚拟内存允许程序使用比物理内存更大的地址空间"],
        "category": "操作系统",
        "difficulty": "intermediate",
    },
]


def get_qa_pairs() -> list[dict[str, Any]]:
    """返回完整的问答对列表。"""
    return QA_PAIRS


def get_corpus() -> str:
    """返回知识库语料文本。"""
    return CORPUS.strip()


def get_queries() -> list[str]:
    """返回所有查询文本。"""
    return [qa["query"] for qa in QA_PAIRS]


if __name__ == "__main__":
    pairs = get_qa_pairs()
    print(f"评测集总数: {len(pairs)} 道问答对")
    from collections import Counter
    cats = Counter(qa["category"] for qa in pairs)
    for cat, count in cats.most_common():
        print(f"  {cat}: {count}")

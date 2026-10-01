"""只读投影岗位要求与现役训练证据。"""

from __future__ import annotations

from filemate.execution.storage import SQLiteStorage
from filemate.programming.problems import PROBLEMS, get_problem
from filemate.programming.repository import CodingRepository
from filemate.study.knowledge_graph import build_graph

ALIASES = {
    "数据结构": ["数据结构", "数组", "栈", "队列", "树", "链表", "堆"],
    "算法": ["算法", "二分", "排序", "搜索", "动态规划", "贪心", "图论"],
    "数据库": ["数据库", "SQL", "索引", "事务"],
    "计算机网络": ["计算机网络", "TCP", "HTTP", "网络编程"],
    "操作系统": ["操作系统", "进程", "线程", "内存管理"],
}


def related(label: str, text: str) -> bool:
    """公开词表按原文标签匹配，不把词法关联当作能力评价。"""
    return any(word.casefold() in text.casefold() for word in ALIASES.get(label, [label]))


def recommended_problems(position: dict) -> list[dict]:
    """从现有原创题映射训练主题，不宣称企业原题。"""
    labels = [r["label"] for r in position["requirements"]]
    supported = any(label in {"C++", "算法", "数据结构"} for label in labels)
    return (
        [
            {
                "id": p["id"],
                "title": p["title"],
                "tags": p["tags"],
                "difficulty": p["difficulty"],
                "version": p["version"],
                "reason": "岗位涉及C++/算法/数据结构；使用平台原创题练习",
            }
            for p in PROBLEMS[:3]
        ]
        if supported
        else []
    )


def compare(storage: SQLiteStorage, position_id: str, position: dict, revision: int) -> dict:
    """整合实际样本与引用，没有样本时返回待评测。"""
    graph = build_graph(storage)
    coding = [
        row
        for row in CodingRepository(storage).evidence()
        if row["result"]["verdict"] in {"AC", "WA", "TLE", "RE", "CE", "OLE"}
    ]
    sessions = []
    for row in storage._conn().execute(
        "SELECT t.training_id,t.interview_id FROM career_trainings t "
        "WHERE t.position_id=? AND t.interview_id IS NOT NULL",
        (position_id,),
    ):
        interview = storage.get_interview(row["interview_id"])
        if interview:
            sessions.append(
                {
                    "training_id": row["training_id"],
                    "interview_id": row["interview_id"],
                    "answered": len(interview["turns"]),
                    "assessed": interview["assessed_turn_count"],
                    "status": interview["status"],
                }
            )
    skills = []
    for requirement in position["requirements"]:
        label = requirement["label"]
        nodes = [n for n in graph["nodes"] if related(label, n["label"])]
        relevant = []
        for row in coding:
            problem = get_problem(row["problem_id"])
            if (
                label in {"C++", "算法"}
                or label == "数据结构"
                and related(label, " ".join(problem["tags"]))
                or related(label, " ".join(problem["tags"]))
            ):
                relevant.append(
                    {
                        "submission_id": row["submission_id"],
                        "problem_id": row["problem_id"],
                        "verdict": row["result"]["verdict"],
                        "created_at": row["created_at"],
                    }
                )
        samples = sum(node["metrics"]["recent_sample_count"] for node in nodes)
        notes = []
        if not samples and not relevant:
            notes.append("尚无相关作答证据，先确认资料并开始练习；不代表不会这项技能。")
        if nodes and not samples:
            notes.append("图谱已收录相关知识，但暂未采集关联作答。")
        if relevant:
            ac = sum(row["verdict"] == "AC" for row in relevant)
            notes.append(
                f"相关C++17练习有效完成提交{len(relevant)}次，其中AC {ac}次；同题可重复提交。"
            )
        if label in {"Python", "Java"}:
            notes.append("当前编程引擎仅支持C++17，这门语言暂不能通过该引擎评测。")
        if requirement["category"] in {"project", "communication"}:
            notes.append("项目与表达需要人工核对原回答；面试完成量不等于该项能力已达标。")
        skills.append(
            {
                **requirement,
                "status": "有训练记录" if samples or relevant else "待评测",
                "graph_nodes": [
                    {
                        "id": n["id"],
                        "label": n["label"],
                        "source_id": n["source_id"],
                        "metrics": n["metrics"],
                    }
                    for n in nodes
                ],
                "recent_graph_samples": samples,
                "coding_count": len(relevant),
                "coding_ac_count": sum(r["verdict"] == "AC" for r in relevant),
                "coding_evidence": relevant[:20],
                "notes": notes,
            }
        )
    return {
        "position_id": position_id,
        "position_revision": revision,
        "skills": skills,
        "interviews": sessions,
        "recommended_problems": recommended_problems(position),
        "mapping_method": "公开词表匹配岗位标签、图谱标签及原创题分类，需人工核对关联。图谱样本为各节点最近窗口之和，可重复关联，不是独立作答数。",
        "purpose": "只描述训练样本与来源，不计算岗位适配率、录用概率或能力总分。",
    }


# 原创基础题，不来自企业题库；稳定事实，不以LLM判分。
BASIC_QUESTIONS = [
    {
        "id": "stack",
        "skill": "数据结构",
        "question": "栈的典型访问顺序是什么？",
        "options": ["先进先出", "后进先出", "随机访问", "按大小排序"],
        "correct": 1,
        "explanation": "栈从栈顶入栈与出栈，遵循后进先出。",
    },
    {
        "id": "search",
        "skill": "算法",
        "question": "对有序数组进行二分查找，通常的时间复杂度是？",
        "options": ["O(n²)", "O(n)", "O(log n)", "O(2ⁿ)"],
        "correct": 2,
        "explanation": "每轮把候选区间约减半，轮数随输入规模呈对数增长。",
    },
    {
        "id": "cpp",
        "skill": "C++",
        "question": "在本平台C++17环境中，累计可能超出32位的整数时应优先使用？",
        "options": ["bool", "char", "long long", "只使用int"],
        "correct": 2,
        "explanation": "long long至少64位；仍需对照题目范围检查溢出。",
    },
    {
        "id": "database",
        "skill": "数据库",
        "question": "SQL中通常用什么关键字限定查询结果的排序？",
        "options": ["ORDER BY", "INSERT", "DROP", "GRANT"],
        "correct": 0,
        "explanation": "ORDER BY用于指定查询结果排序；没有指定时不应假定固定顺序。",
    },
    {
        "id": "network",
        "skill": "计算机网络",
        "question": "以下哪一个通常属于应用层协议？",
        "options": ["IP", "TCP", "HTTP", "以太网"],
        "correct": 2,
        "explanation": "HTTP是应用层协议；TCP提供传输服务，IP负责网络层寻址路由。",
    },
    {
        "id": "python",
        "skill": "Python",
        "question": "Python中字典主要用于哪类数据组织？",
        "options": ["只保存声音", "键与值的映射", "只能保存排序整数", "编译二进制"],
        "correct": 1,
        "explanation": "dict表示键值映射，键须满足可哈希要求。",
    },
    {
        "id": "os",
        "skill": "操作系统",
        "question": "一个进程内的多个线程通常共享什么？",
        "options": [
            "全部线程使用同一个栈",
            "该进程的地址空间",
            "所有进程的私有内存",
            "必须拥有同一线程ID",
        ],
        "correct": 1,
        "explanation": "同一进程的线程共享进程地址空间，同时各线程有自己的栈等执行状态。",
    },
]


def basic_questions(position: dict) -> list[dict]:
    labels = {r["label"] for r in position["requirements"]}
    return [q for q in BASIC_QUESTIONS if q["skill"] in labels][:5]


def interview_questions(position: dict) -> list[str]:
    skills = [r["label"] for r in position["requirements"]]
    return [
        f"针对{position['company']}的{position['title']}训练，请用一个项目说明你的具体贡献与验证结果。",
        f"请选一个与{'、'.join(skills[:3])}相关的概念，解释它的适用条件并给出例子。",
        f"围绕岗位要求“{skills[0]}”，说明你遇到的一个问题，以及如何定位和验证解决方案。",
        "请介绍一次协作中的技术分歧，按情境、任务、行动、结果组织回答。",
        "结合本次训练，请列出一个仍需补充证据的知识点，以及下一步的练习计划。",
    ]

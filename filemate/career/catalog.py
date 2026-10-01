"""少量官方岗位快照与原创训练映射。"""

from __future__ import annotations

import re

from .models import Position

COLLECTED = "2026-10-01T00:00:00+00:00"


def _position(company, region, title, employment, description, requirements, url, published):
    return Position.model_validate(
        {
            "company": company,
            "industry": "互联网与软件",
            "region": region,
            "title": title,
            "employment": employment,
            "description": description,
            "source": f"{company}官方招聘页面",
            "source_url": url,
            "source_kind": "official_snapshot",
            "collected_at": COLLECTED,
            "published_at": published,
            "requirements": [
                {"label": label, "category": category, "evidence": quote}
                for label, category, quote in requirements
            ],
        }
    ).model_dump(mode="json")


CATALOG = [
    _position(
        "百度",
        "上海",
        "搜索架构工程师（J100814）",
        "校招",
        "岗位要求摘要：深刻理解计算机数据结构和算法设计，精通C/C++等至少一门编程语言；"
        "熟悉网络编程、多线程、分布式编程技术，熟悉Linux系统知识；有一定项目经验。",
        [
            ("C++", "programming", "精通C/C++等至少一门编程语言"),
            ("数据结构", "knowledge", "深刻理解计算机数据结构和算法设计"),
            ("算法", "programming", "数据结构和算法设计"),
            ("Linux", "knowledge", "熟悉Linux系统知识"),
            ("计算机网络", "knowledge", "熟悉网络编程"),
            ("项目经历", "project", "有一定项目经验"),
        ],
        "https://talent.baidu.com/jobs/detail/GRADUATE/62597167-3972-42ef-98aa-162290f5e7e6",
        "2026-07-30",
    ),
    _position(
        "百度",
        "北京",
        "AI研发实习生（J97336）",
        "实习",
        "岗位要求摘要：熟练掌握Python/Golang/C++，精通数据结构与算法；"
        "具有较强的沟通能力。工作包括参与Prompt、RAG等优化工作及MCP协议链路搭建。",
        [
            ("Python", "programming", "熟练掌握Python/Golang/C++"),
            ("C++", "programming", "熟练掌握Python/Golang/C++"),
            ("数据结构", "knowledge", "精通数据结构与算法"),
            ("算法", "programming", "精通数据结构与算法"),
            ("RAG", "knowledge", "参与Prompt、RAG等优化工作"),
            ("沟通表达", "communication", "具有较强的沟通能力"),
        ],
        "https://talent.baidu.com/jobs/detail/INTERN/46efcb09-9461-4401-925f-8aaf611994d8",
        "2026-07-21",
    ),
    _position(
        "腾讯",
        "广州",
        "微信小店后台开发（治理方向）",
        "社招参考",
        "岗位要求摘要：熟悉数据结构和算法；熟悉Linux环境下的C/C++开发；"
        "熟练掌握分布式、高并发、性能优化、服务稳定性等后台开发知识。要求一年以上工作经验。",
        [
            ("C++", "programming", "熟悉Linux环境下的C/C++开发"),
            ("数据结构", "knowledge", "熟悉数据结构和算法"),
            ("算法", "programming", "熟悉数据结构和算法"),
            ("Linux", "knowledge", "熟悉Linux环境"),
            ("分布式系统", "knowledge", "熟练掌握分布式、高并发、性能优化、服务稳定性"),
        ],
        "https://careers.tencent.com/zh-cn/jobdesc.html?postId=1936827253514149888",
        "2026-09-28",
    ),
]

# 词表仅建议训练映射，原句和映射需由用户核对。
SKILLS = {
    "C++": "programming",
    "Python": "programming",
    "Java": "programming",
    "数据结构": "knowledge",
    "算法": "programming",
    "数据库": "knowledge",
    "计算机网络": "knowledge",
    "操作系统": "knowledge",
    "Linux": "knowledge",
    "机器学习": "knowledge",
    "深度学习": "knowledge",
    "大模型": "knowledge",
    "RAG": "knowledge",
    "Agent": "knowledge",
    "项目经历": "project",
    "沟通": "communication",
    "英语": "communication",
}


def extract_requirements(description: str) -> list[dict]:
    """从用户原文提取待核对词项，不推断未出现的要求。"""
    requirements = []
    for label, category in SKILLS.items():
        pattern = re.escape(label)
        if label.isascii():
            pattern = rf"(?<![A-Za-z]){pattern}(?![A-Za-z])"
        match = re.search(pattern, description, flags=re.IGNORECASE)
        if match:
            requirements.append({"label": label, "category": category, "evidence": match.group()})
    return requirements

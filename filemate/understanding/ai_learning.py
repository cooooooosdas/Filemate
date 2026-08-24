"""AI 辅助学习：语义检索 + 对话逻辑 + 总结生成。

设计原则：
- 不用外部向量库，BM25 粗召回 + LLM 查询扩展实现轻量语义检索
- 用户自带 API Key，不走项目默认配置
- 产物（总结文档）写入现有 artifacts 表，artifact_type = 'ai_summary'
"""

from __future__ import annotations

import logging
import math
import re
import uuid
from collections import Counter
from typing import Any

from filemate.execution.storage import SQLiteStorage
from filemate.llm_client import LLMClient

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 检索阈值
# ──────────────────────────────────────────────

_MIN_RELEVANCE_SCORE = 0.5  # BM25 得分低于此值的 chunk 视为不相关

# ──────────────────────────────────────────────
# 轻量 BM25 检索（自包含，不依赖 retrieval.py）
# ──────────────────────────────────────────────

_LATIN = re.compile(r"[a-zA-Z0-9_]+")
_HAN = re.compile(r"[一-鿿]+")


def _tokenize(text: str) -> list[str]:
    """中英文混合分词：英文词 + 中文双字/三字词（过滤单字噪音）。"""
    lowered = text.lower()
    tokens = _LATIN.findall(lowered)
    for run in _HAN.findall(lowered):
        # 跳过单字，保留双字及以上 n-gram
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
        tokens.extend(run[i : i + 3] for i in range(len(run) - 2))
    return tokens


def _bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """计算 BM25 得分。"""
    if not query_tokens or not doc_tokens:
        return 0.0
    doc_len = len(doc_tokens)
    avg_len = max(1.0, doc_len)  # 简化：单文档时即自身长度
    tf = Counter(doc_tokens)
    score = 0.0
    for qt in set(query_tokens):
        if qt not in tf:
            continue
        f = tf[qt]
        idf = math.log((1 + avg_len) / (1 + f)) + 1
        denom = f + k1 * (1 - b + b * doc_len / avg_len)
        score += idf * f * (k1 + 1) / max(1, denom)
    return score


def bm25_rank(
    query: str,
    chunks: list[dict[str, Any]],
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """对知识库 chunks 做 BM25 粗召回。"""
    qtokens = _tokenize(query)
    if not qtokens or not chunks:
        return []
    scored = []
    for chunk in chunks:
        dtokens = _tokenize(str(chunk.get("content", "")))
        s = _bm25_score(qtokens, dtokens)
        scored.append((s, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = []
    for s, c in scored[:limit]:
        chunk = dict(c)
        chunk["score"] = round(s, 6)
        ranked.append(chunk)
    return ranked


# ──────────────────────────────────────────────
# LLM 查询扩展
# ──────────────────────────────────────────────

_QUERY_EXPANSION_PROMPT = """\
生成3个检索查询（每行一个），覆盖同义词和相关术语，帮助从知识库找资料。

用户问题：{query}

只输出查询，每行一个："""


def expand_query(
    query: str,
    llm_client: LLMClient,
) -> list[str]:
    """用 LLM 扩展查询，生成多个检索角度。"""
    if len(query) < 4:
        return [query]
    prompt = _QUERY_EXPANSION_PROMPT.format(query=query)
    try:
        raw = llm_client.call(
            prompt=prompt,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.3,
        )
        queries = [line.strip() for line in raw.strip().split("\n") if line.strip()]
        return queries[:5] if queries else [query]
    except Exception:  # noqa: BLE001 - LLM 调用失败时降级为原查询
        return [query]


# ──────────────────────────────────────────────
# 语义重排
# ──────────────────────────────────────────────

_RERANK_PROMPT = """\
你是一个检索结果排序助手。给定用户问题和若干候选资料片段，
请只返回与问题最相关的片段的序号（从1开始），按相关性从高到低排序。
最多返回 {top_k} 个序号，用逗号分隔，不要其他内容。

用户问题：{query}

候选片段：
{chunks}
"""


def rerank_chunks(
    query: str,
    chunks: list[dict[str, Any]],
    llm_client: LLMClient,
    *,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """用 LLM 对 BM25 粗召回结果做语义重排。结果<=top_k时跳过。"""
    if len(chunks) <= top_k:
        return chunks
    chunk_texts = "\n\n".join(
        f"[{i+1}] {c.get('content', '')[:300]}"
        for i, c in enumerate(chunks)
    )
    prompt = _RERANK_PROMPT.format(
        query=query, chunks=chunk_texts, top_k=top_k
    )
    try:
        raw = llm_client.call(
            prompt=prompt,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=64,
            temperature=0.0,
        )
        indices = re.findall(r"\d+", raw)
        ranked = []
        for idx_str in indices[:top_k]:
            idx = int(idx_str) - 1
            if 0 <= idx < len(chunks):
                ranked.append(chunks[idx])
        if ranked:
            return ranked
    except Exception:
        logger.debug("LLM 重排失败，使用 BM25 原始顺序", exc_info=True)
    return chunks[:top_k]


# ──────────────────────────────────────────────
# 学习检索器
# ──────────────────────────────────────────────

class LearningRetriever:
    """AI 学习的知识库检索器：BM25 粗召回 + LLM 扩展 + 语义重排。"""

    def __init__(
        self,
        storage: SQLiteStorage,
        llm_client: LLMClient,
    ) -> None:
        self._storage = storage
        self._llm = llm_client

    def search(
        self,
        query: str,
        *,
        workspace_id: str = "local",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """检索知识库，返回带引用的 chunk 列表。

        检索范围：
        1. 用户上传的原始资料（document_chunks）
        2. AI 总结的学习笔记（artifacts, artifact_type = 'ai_summary'）
        """
        # 1. 获取所有资料源和 chunks
        sources = self._storage.list_sources(workspace_id=workspace_id, limit=200)
        all_chunks: list[dict[str, Any]] = []
        source_map: dict[str, dict[str, Any]] = {}
        for src in sources:
            sid = src["source_id"]
            source_map[sid] = src
            chunks = self._storage.list_source_chunks(sid)
            for ch in chunks:
                ch["source_id"] = sid
            all_chunks.extend(chunks)

        # 2. 补充 AI 总结（学习笔记）到知识库
        summaries = self._storage.list_artifacts(
            workspace_id=workspace_id,
            artifact_type="ai_summary",
            limit=100,
        )
        for art in summaries:
            aid = art.get("artifact_id", "")
            title = art.get("title", "未命名笔记")
            content = art.get("content", "")
            if isinstance(content, str) and content.strip():
                summary_chunk = {
                    "source_id": aid,
                    "source_name": f"[笔记] {title}",
                    "content": content,
                    "excerpt": content[:300],
                    "_is_summary": True,
                }
                all_chunks.append(summary_chunk)
                source_map[aid] = {
                    "source_id": aid,
                    "original_name": f"[笔记] {title}",
                }

        if not all_chunks:
            return []

        # 3. 查询扩展
        expanded = expand_query(query, self._llm)

        # 4. BM25 粗召回（多查询取并集，然后去重）
        seen: set[int] = set()
        merged: list[dict[str, Any]] = []
        for q in expanded:
            results = bm25_rank(q, all_chunks, limit=limit * 2)
            for r in results:
                idx = id(r)
                if idx not in seen:
                    seen.add(idx)
                    merged.append(r)
            if len(merged) >= limit * 3:
                break

        if not merged:
            return []

        # 5. 语义重排
        final = rerank_chunks(query, merged, self._llm, top_k=limit)

        # 5.5 过滤低分结果（低于阈值的视为不相关）
        final = [
            chunk for chunk in final
            if chunk.get("score", 0) >= _MIN_RELEVANCE_SCORE
        ]

        # 6. 补充来源名称
        for chunk in final:
            src = source_map.get(chunk.get("source_id", ""), {})
            chunk["source_name"] = src.get("original_name", "未知资料")
            chunk["excerpt"] = str(chunk.get("content", ""))[:300]

        return final


# ──────────────────────────────────────────────
# 对话系统提示词
# ──────────────────────────────────────────────

_EXPLORE_SYSTEM = "你是 AI 学习助手。帮助用户探索新领域：给出核心概念、学习路线、结构化讲解。用类比和例子，深入浅出。中文回答。"

_REINFORCE_SYSTEM = "你是 AI 学习助手。基于提供的知识库资料回答问题。引用时标注来源编号如[1]。知识库没有的内容明确告知用户，不要编造。简洁准确，中文回答。"

_SUMMARY_PROMPT = """\
请将以下对话内容整理成一份详尽的结构化学习笔记 Markdown 文档。

## 格式要求

1. **标题**：根据内容自拟一个精准的标题，直接写在最开头（用 # 一级标题）
2. **学习模式**：在标题下方标注本次笔记对应的学习模式（探索全新领域 / 加强已有知识）
3. **生成时间**：标注笔记生成日期

## 内容要求（必须包含以下全部章节）

### # 核心概念
将对话中涉及的核心概念逐条列出，每个概念包含：
- 概念名称（加粗）
- 清晰定义（2-3 句话）
- 与相关概念之间的关系

### ## 知识点详解
按逻辑分组展开每个知识点：
- 使用标题层级（## / ###）组织知识结构
- 每个知识点配 1-2 个具体例子或类比
- 公式、定理等用 LaTeX 格式书写（行内用 `$...$`，块级用 `$$...$$`）
- 关键术语首次出现时给出中英文对照

### ## 重要结论
将对话中得出的关键结论、规律、方法论单独列出：
- 每条结论用 > 引用块呈现
- 标注适用条件和局限性

### ## 易错点与注意事项
列出学习中容易混淆或出错的地方：
- 对比常见误解与正确理解
- 标注需要特别注意的前提条件

### ## 学习建议
基于本次对话内容给出下一步学习建议：
- 推荐的学习顺序
- 需要额外查阅的资料方向
- 自检问题（3-5 个，帮助检验理解程度）

### ## 拓展思考
提出 2-3 个与本次内容相关的延伸问题，引导深度思考

## 格式规范
- 总长度不少于对话内容的 60%，宁多勿少
- 善用 Markdown：标题层级、无序/有序列表、加粗、引用、代码块、表格
- 直接输出 Markdown 内容，不要额外说明

## 对话内容
{conversation}
"""


# ──────────────────────────────────────────────
# AI 学习对话引擎
# ──────────────────────────────────────────────

class AILearningChat:
    """AI 学习对话核心逻辑。"""

    def __init__(
        self,
        storage: SQLiteStorage,
        llm_client: LLMClient,
    ) -> None:
        self._storage = storage
        self._llm = llm_client
        self._retriever = LearningRetriever(storage, llm_client)

    def chat(
        self,
        session_id: str,
        user_message: str,
        mode: str,
        *,
        uploaded_file_text: str = "",
    ) -> dict[str, Any]:
        """发送一条消息并返回 AI 回复。

        返回格式：
        {
            "role": "assistant",
            "content": "AI 回复文本",
            "citations": [...],  # 引用来源
            "message_id": "...",
        }
        """
        # 1. 用户消息已由路由层持久化，此处只初始化引用列表
        citations: list[dict[str, Any]] = []

        # 2. 根据模式构建上下文
        if mode == "reinforce":
            # 检索知识库
            search_results = self._retriever.search(user_message)

            # 无依据拒答：知识库中无相关资料时，不调用 LLM
            if not search_results:
                reply = "知识库中没有找到相关资料，无法回答此问题。建议您先上传相关课程资料到知识库。"
                assistant_msg_id = uuid.uuid4().hex[:12]
                self._storage.add_ai_message(
                    message_id=assistant_msg_id,
                    session_id=session_id,
                    role="assistant",
                    content=reply,
                    citations=[],
                    mode=mode,
                )
                return {
                    "role": "assistant",
                    "content": reply,
                    "citations": [],
                    "message_id": assistant_msg_id,
                    "answerable": False,
                }

            citations = [
                {
                    "source_id": r.get("source_id", ""),
                    "source_name": r.get("source_name", ""),
                    "excerpt": r.get("excerpt", "")[:200],
                    "score": round(r.get("score", 0), 3),
                }
                for r in search_results
            ]
            context_parts = [
                f"[{i+1}] {r.get('source_name', '')}\n{r.get('content', '')[:500]}"
                for i, r in enumerate(search_results)
            ]
            context = "\n\n".join(context_parts) if context_parts else ""
        else:
            context = uploaded_file_text

        # 3. 构建消息列表
        # 注意：step-explore 等模型对 system 消息支持不佳，统一用 user 消息承载指令
        system_prompt = _REINFORCE_SYSTEM if mode == "reinforce" else _EXPLORE_SYSTEM
        messages: list[dict[str, str]] = [
            {"role": "user", "content": f"[系统指令]\n{system_prompt}"}
        ]

        if context:
            if mode == "reinforce":
                messages.append({
                    "role": "user",
                    "content": f"[知识库资料]\n{context}\n\n请基于以上资料回答问题。"
                })
            else:
                messages.append({
                    "role": "user",
                    "content": f"[用户上传的文件内容]\n{context[:8000]}"
                })

        # 加载历史（仅当前模式的消息，探索/巩固互不干扰）
        history = self._storage.get_ai_messages_by_mode(session_id, mode)
        for m in history[-10:]:
            messages.append({"role": m["role"], "content": m["content"]})

        messages.append({"role": "user", "content": user_message})

        # 4. 调用 LLM
        try:
            reply = self._llm.call(
                prompt="",
                messages=messages,
                max_tokens=8192,
                temperature=0.7,
            )
            if not reply:
                logger.warning("AI 返回空回复，原始 messages 长度=%d", len(messages))
                reply = "抱歉，AI 未返回有效回复，请重试。"
        except Exception as exc:  # noqa: BLE001 - LLM 调用失败时返回友好提示
            logger.error("AI 学习对话失败: %s", exc)
            reply = f"抱歉，AI 调用失败：{exc}"

        # 5. 持久化 AI 回复（带上模式）
        assistant_msg_id = uuid.uuid4().hex[:12]
        self._storage.add_ai_message(
            message_id=assistant_msg_id,
            session_id=session_id,
            role="assistant",
            content=reply,
            citations=citations,
            mode=mode,
        )

        return {
            "role": "assistant",
            "content": reply,
            "citations": citations,
            "message_id": assistant_msg_id,
        }

    def generate_summary(self, session_id: str) -> dict[str, Any]:
        """总结对话内容，生成 Markdown 文档并写入知识库。

        返回格式：
        {
            "artifact_id": "...",
            "title": "...",
            "content": "Markdown 内容",
        }
        """
        # 1. 获取会话信息
        session = self._storage.get_ai_session(session_id)
        if not session:
            raise ValueError(f"会话不存在: {session_id}")

        mode = session.get("mode", "explore")
        messages = self._storage.get_ai_messages_by_mode(session_id, mode)
        if not messages:
            raise ValueError("对话为空，无法总结")

        # 2. 构建对话文本
        conv_parts = []
        for m in messages:
            role_label = "用户" if m["role"] == "user" else "AI"
            conv_parts.append(f"### {role_label}\n{m['content']}")
        conversation = "\n\n".join(conv_parts)

        # 3. 生成总结
        prompt = _SUMMARY_PROMPT.format(conversation=conversation)
        try:
            summary_md = self._llm.call(
                prompt=prompt,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
                temperature=0.5,
            )
        except Exception as exc:
            logger.error("生成总结失败: %s", exc)
            raise RuntimeError(f"生成总结失败: {exc}") from exc

        # 4. 写入 artifacts
        title_prefix = "探索" if mode == "explore" else "巩固"
        title = f"{title_prefix}学习笔记 - {messages[0]['content'][:30]}"
        title = re.sub(r"[^\w\s一-鿿\-]", "", title).strip()
        if not title:
            title = f"{title_prefix}学习笔记"

        source_id = self._storage.get_ai_learning_source_id(workspace_id="local")

        artifact_id = self._storage.save_artifact(
            source_id=source_id,
            artifact_type="ai_summary",
            title=title,
            content=summary_md,
            metadata={
                "ai_session_id": session_id,
                "mode": mode,
                "message_count": len(messages),
            },
        )

        # 5. 更新会话的 summary_artifact_id
        self._storage.update_ai_session(
            session_id=session_id,
            summary_artifact_id=artifact_id,
        )

        return {
            "artifact_id": artifact_id,
            "title": title,
            "content": summary_md,
        }

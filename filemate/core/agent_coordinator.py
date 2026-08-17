"""AgentCoordinator - 多 Agent 协调器。

支持：
- 串行执行：按顺序执行多个 Agent
- 并行执行：同时执行多个 Agent
- 混合模式：根据条件选择执行路径
- 结果聚合：将多个 Agent 的结果合并

设计原则：
- 每个 Agent 有明确的输入输出契约
- 支持状态传递（上一个 Agent 的输出作为下一个的输入）
- 可配置重试和超时
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

from filemate.core.session import ProcessingSession, SessionStatus

logger = logging.getLogger(__name__)


class AgentMode(Enum):
    """Agent 执行模式。"""
    SERIAL = auto()    # 串行
    PARALLEL = auto()  # 并行
    CONDITIONAL = auto()  # 条件
    SERIAL_THEN_PARALLEL = auto()  # 先串行后并行


@dataclass
class AgentResult:
    """单个 Agent 的执行结果。"""
    agent_name: str
    success: bool
    output: Any = None
    error: str = ""
    duration: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class CoordinatorConfig:
    """协调器配置。"""
    name: str = "coordinator"
    mode: AgentMode = AgentMode.SERIAL
    max_workers: int = 4           # 并行模式的最大工作线程
    timeout: Optional[float] = None  # 全局超时
    continue_on_failure: bool = True  # 失败后是否继续


class Agent(Callable):
    """Agent 基类。

    用法::

        class MyAgent(Agent):
            def execute(self, session: ProcessingSession, context: dict) -> Any:
                # 处理逻辑
                return result
    """

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description

    def execute(self, session: ProcessingSession, context: dict) -> Any:
        """执行 Agent 逻辑。子类必须实现。"""
        raise NotImplementedError("子类必须实现 execute 方法")

    def __call__(self, session: ProcessingSession, context: dict = None) -> AgentResult:
        """包装执行，捕获异常和计时。"""
        import time
        start = time.time()
        context = context or {}

        try:
            output = self.execute(session, context)
            duration = time.time() - start
            return AgentResult(
                agent_name=self.name,
                success=True,
                output=output,
                duration=duration,
            )
        except Exception as exc:
            duration = time.time() - start
            logger.error("[Agent %s] 执行失败: %s", self.name, exc)
            return AgentResult(
                agent_name=self.name,
                success=False,
                error=str(exc),
                duration=duration,
            )


class AgentCoordinator:
    """多 Agent 协调器。

    用法::

        coordinator = AgentCoordinator()

        # 添加 Agent
        coordinator.add_agent(MyAgent("agent1"))
        coordinator.add_agent(MyAgent("agent2"))

        # 串行执行
        results = coordinator.run_serial(session)

        # 并行执行
        results = coordinator.run_parallel(session)
    """

    def __init__(self, config: Optional[CoordinatorConfig] = None) -> None:
        self.config = config or CoordinatorConfig()
        self._agents: list[Agent] = []
        self._agent_index: dict[str, Agent] = {}

    def add_agent(self, agent: Agent) -> "AgentCoordinator":
        """添加 Agent。"""
        self._agents.append(agent)
        self._agent_index[agent.name] = agent
        return self

    def remove_agent(self, name: str) -> bool:
        """移除 Agent。"""
        if name not in self._agent_index:
            return False
        agent = self._agent_index.pop(name)
        self._agents.remove(agent)
        return True

    def get_agent(self, name: str) -> Optional[Agent]:
        """获取 Agent。"""
        return self._agent_index.get(name)

    def list_agents(self) -> list[str]:
        """列出所有 Agent。"""
        return [a.name for a in self._agents]

    # =====================================================================
    # 执行模式
    # =====================================================================

    def run_serial(
        self,
        session: ProcessingSession,
        context: Optional[dict] = None,
    ) -> list[AgentResult]:
        """串行执行所有 Agent。

        每个 Agent 的输出会传递给下一个 Agent（通过 context）。
        """
        results = []
        context = context or {}

        for agent in self._agents:
            logger.info("[%s] Agent %s 开始执行", session.session_id, agent.name)
            result = agent(session, context)

            # 传递输出到 context（供下一个 Agent 使用）
            if result.success and result.output is not None:
                context[agent.name] = result.output

            results.append(result)

            # 失败处理
            if not result.success and not self.config.continue_on_failure:
                logger.warning("[%s] Agent %s 失败，停止执行", session.session_id, agent.name)
                break

        return results

    def run_parallel(
        self,
        session: ProcessingSession,
        context: Optional[dict] = None,
        max_workers: Optional[int] = None,
    ) -> list[AgentResult]:
        """并行执行所有 Agent。

        注意：并行模式下，Agent 之间的状态共享需要小心处理。
        建议只用于独立的、无状态的 Agent。
        """
        max_workers = max_workers or self.config.max_workers
        results = []
        context = context or {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(agent, session, context): agent
                for agent in self._agents
            }

            for future in as_completed(futures):
                agent = futures[future]
                try:
                    result = future.result(timeout=self.config.timeout)
                    results.append(result)
                    logger.info("[%s] Agent %s 完成: success=%s",
                                session.session_id, agent.name, result.success)
                except Exception as exc:
                    logger.error("[%s] Agent %s 异常: %s", session.session_id, agent.name, exc)
                    results.append(AgentResult(
                        agent_name=agent.name,
                        success=False,
                        error=str(exc),
                    ))

        # 按添加顺序排序结果
        results.sort(key=lambda r: self._agents.index(self._agent_index[r.agent_name]))
        return results

    def run_conditional(
        self,
        session: ProcessingSession,
        condition_fn: Callable[[ProcessingSession, dict], list[str]],
        context: Optional[dict] = None,
    ) -> list[AgentResult]:
        """条件执行：根据 session 状态选择要执行的 Agent。

        Parameters
        ----------
        session : ProcessingSession
            当前会话。
        condition_fn : callable
            函数，返回要执行的 Agent 名称列表。
            签名: (session, context) -> list[str]

        Returns
        -------
        list[AgentResult]
            执行结果列表。
        """
        context = context or {}

        # 获取要执行的 Agent 名称
        target_names = condition_fn(session, context)
        target_agents = [self._agent_index[name] for name in target_names if name in self._agent_index]

        # 串行执行选中的 Agent
        results = []
        for agent in target_agents:
            logger.info("[%s] Agent %s 开始执行（条件）", session.session_id, agent.name)
            result = agent(session, context)
            results.append(result)

            if result.success and result.output is not None:
                context[agent.name] = result.output

            if not result.success and not self.config.continue_on_failure:
                break

        return results

    # =====================================================================
    # 执行入口
    # =====================================================================

    def run(
        self,
        session: ProcessingSession,
        mode: Optional[AgentMode] = None,
        context: Optional[dict] = None,
    ) -> list[AgentResult]:
        """统一执行入口（根据配置选择模式）。"""
        mode = mode or self.config.mode

        if mode == AgentMode.SERIAL:
            return self.run_serial(session, context)
        elif mode == AgentMode.PARALLEL:
            return self.run_parallel(session, context)
        elif mode == AgentMode.CONDITIONAL:
            # 条件模式需要额外的 condition_fn 参数，这里简化处理
            return self.run_serial(session, context)
        elif mode == AgentMode.SERIAL_THEN_PARALLEL:
            # 需要额外参数，使用默认配置
            return self.run_serial(session, context)
        else:
            raise ValueError(f"未知执行模式: {mode}")

    def run_serial_then_parallel(
        self,
        session: ProcessingSession,
        serial_agents: list[Agent],
        parallel_agents: list[Agent],
        context: Optional[dict] = None,
        max_workers: Optional[int] = None,
    ) -> list[AgentResult]:
        """先串行执行一部分Agent，再并行执行其余Agent。

        执行流程：
        1. 串行执行 serial_agents（比如 [ParseAgent]）
        2. 将串行结果注入 context
        3. 并行执行 parallel_agents（比如 [ClassifyAgent, ExtractAgent, GenerateNameAgent]）

        Parameters
        ----------
        session : ProcessingSession
            当前会话。
        serial_agents : list[Agent]
            需要先串行执行的 Agent 列表。
        parallel_agents : list[Agent]
            需要后并行执行的 Agent 列表。
        context : dict, optional
            共享上下文。
        max_workers : int, optional
            并行执行的最大线程数。

        Returns
        -------
        list[AgentResult]
            所有 Agent 的执行结果（串行结果在前，并行结果在后）。
        """
        results = []
        context = context or {}

        # Step 1: 串行执行
        logger.info("[%s] 开始串行执行 %d 个 Agent",
                   session.session_id, len(serial_agents))
        for agent in serial_agents:
            result = agent(session, context)
            results.append(result)
            if result.success and result.output is not None:
                context[agent.name] = result.output
            if not result.success and not self.config.continue_on_failure:
                logger.warning("[%s] Agent %s 失败，停止执行",
                              session.session_id, agent.name)
                break

        # Step 2: 并行执行
        if not parallel_agents:
            return results

        max_workers = max_workers or self.config.max_workers
        logger.info("[%s] 开始并行执行 %d 个 Agent",
                    session.session_id, len(parallel_agents))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(agent, session, context): agent
                for agent in parallel_agents
            }

            for future in as_completed(futures):
                agent = futures[future]
                try:
                    result = future.result(timeout=self.config.timeout)
                    results.append(result)
                    logger.info("[%s] Agent %s 完成: success=%s, duration=%.2fs",
                                session.session_id, agent.name,
                                result.success, result.duration)
                except Exception as exc:
                    logger.error("[%s] Agent %s 异常: %s",
                                 session.session_id, agent.name, exc)
                    results.append(AgentResult(
                        agent_name=agent.name,
                        success=False,
                        error=str(exc),
                    ))

        # 按添加顺序排序结果（串行结果在前，并行结果按原顺序）
        serial_results = [r for r in results if r.agent_name in [a.name for a in serial_agents]]
        parallel_results = [r for r in results if r.agent_name in [a.name for a in parallel_agents]]
        results = serial_results + parallel_results
        return results

    # =====================================================================
    # 聚合结果
    # =====================================================================

    def aggregate_outputs(self, results: list[AgentResult]) -> dict[str, Any]:
        """聚合所有 Agent 的输出。"""
        aggregated = {}
        for r in results:
            if r.success:
                aggregated[r.agent_name] = r.output
            else:
                aggregated[f"{r.agent_name}_error"] = r.error
        return aggregated


# =====================================================================
# 预定义 Agent
# =====================================================================

class ParseAgent(Agent):
    """文件解析 Agent。"""

    def __init__(self) -> None:
        super().__init__("parse", "解析文件内容")

    def execute(self, session: ProcessingSession, context: dict) -> dict:
        from filemate.perception import FileParser

        parser = FileParser()
        parsed = parser.parse(session.source_path)
        session.entities["raw_text"] = parsed.get("raw_text", "")
        session.entities["metadata"] = parsed.get("metadata", {})
        return parsed


class ClassifyAgent(Agent):
    """分类 Agent。"""

    def __init__(self) -> None:
        super().__init__("classify", "分类文件")

    def execute(self, session: ProcessingSession, context: dict) -> dict:
        from filemate.understanding import Classifier
        from filemate.core.registry import get_registry
        from pathlib import Path

        llm = get_registry().get_llm()
        classifier = Classifier(llm)
        raw_text = session.entities.get("raw_text", "")
        filename = Path(session.source_path).name
        result = classifier.classify(raw_text, filename=filename)

        session.category = result.get("category", "待确认")
        session.confidence = float(result.get("confidence", 0.0))

        return result


class ExtractAgent(Agent):
    """实体抽取 Agent。"""

    def __init__(self) -> None:
        super().__init__("extract", "抽取实体")

    def execute(self, session: ProcessingSession, context: dict) -> dict:
        from filemate.understanding import EntityExtractor
        from filemate.core.registry import get_registry

        llm = get_registry().get_llm()
        extractor = EntityExtractor(llm)
        raw_text = session.entities.get("raw_text", "")
        entities = extractor.extract(raw_text)

        session.entities.update(entities)
        return entities


class GenerateNameAgent(Agent):
    """命名生成 Agent。"""

    def __init__(self) -> None:
        super().__init__("generate_name", "生成建议文件名")

    def execute(self, session: ProcessingSession, context: dict) -> str:
        from filemate.understanding import Namer
        from filemate.core.registry import get_registry
        from pathlib import Path

        llm = get_registry().get_llm()
        namer = Namer(llm)
        course = session.entities.get("course_name") or "未分类"
        task = session.entities.get("task_description") or "未命名"
        deadline = session.entities.get("deadline") or ""

        suggested = namer.generate(
            category=session.category,
            course=course,
            task=task,
            deadline=deadline,
            status="待处理",
        )
        session.suggested_name = suggested
        return suggested


# =====================================================================
# 便捷函数
# =====================================================================

def create_coordinator(
    mode: AgentMode = AgentMode.SERIAL,
    agents: Optional[list[Agent]] = None,
) -> AgentCoordinator:
    """创建预配置的协调器。"""
    config = CoordinatorConfig(mode=mode)
    coordinator = AgentCoordinator(config)

    if agents:
        for agent in agents:
            coordinator.add_agent(agent)

    return coordinator


def create_full_coordinator() -> AgentCoordinator:
    """创建完整的处理协调器（所有阶段）。"""
    return (
        create_coordinator(AgentMode.SERIAL)
        .add_agent(ParseAgent())
        .add_agent(ClassifyAgent())
        .add_agent(ExtractAgent())
        .add_agent(GenerateNameAgent())
    )


def create_parallel_coordinator(
    serial_agents: Optional[list[Agent]] = None,
    parallel_agents: Optional[list[Agent]] = None,
) -> tuple[AgentCoordinator, list[Agent], list[Agent]]:
    """创建支持"先串行后并行"模式的协调器。

    返回协调器实例，以及串行Agent列表和平行Agent列表，
    方便外部调用 run_serial_then_parallel 方法。

    Parameters
    ----------
    serial_agents : list[Agent], optional
        需要串行执行的 Agent 列表。默认为 [ParseAgent()]。
    parallel_agents : list[Agent], optional
        需要并行执行的 Agent 列表。
        默认为 [ClassifyAgent(), ExtractAgent(), GenerateNameAgent()]。

    Returns
    -------
    tuple[AgentCoordinator, list[Agent], list[Agent]]
        (协调器实例, 串行Agent列表, 并行Agent列表)

    Example
    -------
    >>> coordinator, serial, parallel = create_parallel_coordinator()
    >>> results = coordinator.run_serial_then_parallel(session, serial, parallel)
    """
    # 默认串行：仅 ParseAgent
    if serial_agents is None:
        serial_agents = [ParseAgent()]

    # 默认并行：Classify + Extract + GenerateName
    if parallel_agents is None:
        parallel_agents = [
            ClassifyAgent(),
            ExtractAgent(),
            GenerateNameAgent()
        ]

    config = CoordinatorConfig(mode=AgentMode.SERIAL_THEN_PARALLEL)
    coordinator = AgentCoordinator(config)

    # 添加所有 Agent（虽然执行顺序由 run_serial_then_parallel 控制）
    for agent in serial_agents:
        coordinator.add_agent(agent)
    for agent in parallel_agents:
        coordinator.add_agent(agent)

    return coordinator, serial_agents, parallel_agents
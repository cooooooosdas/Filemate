"""核心编排：Session + Pipeline + PipelineFactory + AgentCoordinator + ModuleRegistry。"""
from .categories import CATEGORIES
from .session import ProcessingSession, SessionStatus
from .pipeline import PipelineWorker
from .pipeline_factory import Pipeline, PipelineBuilder, PipelineConfig, StageCondition, create_full_pipeline, create_minimal_pipeline
from .agent_coordinator import AgentCoordinator, Agent, AgentResult, AgentMode, create_full_coordinator, create_parallel_coordinator
from .registry import ModuleRegistry, get_registry, get_llm, get_parser, get_storage
__all__ = [
    "CATEGORIES",
    "ProcessingSession",
    "SessionStatus",
    "PipelineWorker",
    "Pipeline",
    "PipelineBuilder",
    "PipelineConfig",
    "StageCondition",
    "create_full_pipeline",
    "create_minimal_pipeline",
    "AgentCoordinator",
    "Agent",
    "AgentResult",
    "AgentMode",
    "create_full_coordinator",
    "create_parallel_coordinator",
    "ModuleRegistry",
    "get_registry",
    "get_llm",
    "get_parser",
    "get_storage",
]

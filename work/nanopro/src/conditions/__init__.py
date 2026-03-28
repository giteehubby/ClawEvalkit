"""
Conditions 模块 - 导出所有 training-free recipes

T1 (Memory): Episodic memory
T2 (Control): Single-agent control mechanisms
T3 (Collaboration): Minimal two-agent collaboration
T4 (Procedure): Procedural skill cards with on-demand expansion
T5: Memory + Control (enabled by passing both T1 and T2 flags)
"""

from src.harness.agent.memory import MemoryConfig, EpisodicMemoryStore, WritePolicy, RetrievalPolicy
from src.harness.agent.control import ControlConfig, PlanFirstConfig, ReplanConfig, RetryConfig, ReflectionConfig
from src.harness.agent.collaboration import CollabConfig, HandoffPolicy, PlannerRole, ExecutorRole, VerifierRole, HandoffManager
from src.harness.agent.procedure import ProceduralConfig, ProceduralStore, ProceduralTrigger, ProceduralExpander

__all__ = [
    # Memory (T1)
    "MemoryConfig",
    "EpisodicMemoryStore",
    "WritePolicy",
    "RetrievalPolicy",
    # Control (T2)
    "ControlConfig",
    "PlanFirstConfig",
    "ReplanConfig",
    "RetryConfig",
    "ReflectionConfig",
    # Collaboration (T3)
    "CollabConfig",
    "HandoffPolicy",
    "PlannerRole",
    "ExecutorRole",
    "VerifierRole",
    "HandoffManager",
    # Procedure (T4)
    "ProceduralConfig",
    "ProceduralStore",
    "ProceduralTrigger",
    "ProceduralExpander",
]

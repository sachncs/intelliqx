"""Tier 1 agents: Planner, Orchestrator, Memory Manager, Knowledge/RAG, Tool Manager.

The Tier 1 agents together form the platform's coordination layer.
They have no domain knowledge of their own; they orchestrate
Tier 2 reasoning agents and Tier 3 execution agents. Each agent
in this tier is a thin wrapper over a well-understood algorithm:

* :class:`PlannerAgent` — deterministic template-based plan
  generation with cost-ceiling trimming and DAG validation.
* :class:`OrchestratorAgent` — Kahn-style topological scheduling
  with parallel execution, retries, and event emission.
* :class:`MemoryManagerAgent` — polymorphic dispatch over
  Put/Get/Search/Summarize/Forget operations.
* :class:`KnowledgeRAGAgent` — three-source hybrid retrieval
  (vector + KG + lexical).
* :class:`ToolManagerAgent` — MCP-compatible tool gateway with
  rate limiting.
"""

from agents.tier1.knowledge_rag import KnowledgeRAGAgent
from agents.tier1.memory_manager import MemoryManagerAgent
from agents.tier1.orchestrator import OrchestratorAgent
from agents.tier1.planner import PlannerAgent
from agents.tier1.tool_manager import ToolManagerAgent, default_tool_manager

__all__ = [
    "KnowledgeRAGAgent",
    "MemoryManagerAgent",
    "OrchestratorAgent",
    "PlannerAgent",
    "ToolManagerAgent",
    "default_tool_manager",
]

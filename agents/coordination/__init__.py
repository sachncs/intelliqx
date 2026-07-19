"""Coordination agents: Planner, Orchestrator, Knowledge/RAG, Tool Manager.

The Coordination agents together form the platform's coordination layer.
They have no domain knowledge of their own; they orchestrate
Intelligence reasoning agents and Execution execution agents. Each agent
in this category is a thin wrapper over a well-understood algorithm:

* :class:`PlannerAgent` — deterministic template-based plan
  generation with cost-ceiling trimming and DAG validation.
* :class:`OrchestratorAgent` — Kahn-style topological scheduling
  with parallel execution, retries, and event emission.
* :class:`KnowledgeRAGAgent` — three-source hybrid retrieval
  (index + KG + lexical) using reciprocal-rank fusion.
* :class:`ToolManagerAgent` — MCP-compatible tool gateway with
  rate limiting.

Per-run state lives in the process-transient :class:`RunContext`,
not in a durable memory manager.
"""

from agents.coordination.knowledge_rag import KnowledgeRAGAgent
from agents.coordination.orchestrator import OrchestratorAgent
from agents.coordination.planner import PlannerAgent
from agents.coordination.tool_manager import ToolManagerAgent, default_tool_manager

__all__ = [
    "KnowledgeRAGAgent",
    "OrchestratorAgent",
    "PlannerAgent",
    "ToolManagerAgent",
    "default_tool_manager",
]

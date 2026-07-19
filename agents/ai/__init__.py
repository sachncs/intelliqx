"""Pydantic AI agent role registry for IntelliqX."""

from intelliqx_ai.runtime import AgentConfig, build_agent

from .roles import ROLE_TABLE, AgentRole, RoleSpec, build_agent_for_role, build_roles

__all__ = [
    "ROLE_TABLE",
    "AgentConfig",
    "AgentRole",
    "RoleSpec",
    "build_agent",
    "build_agent_for_role",
    "build_roles",
]

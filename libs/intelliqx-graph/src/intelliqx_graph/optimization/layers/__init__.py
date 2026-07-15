from __future__ import annotations

from intelliqx_graph.layers import LayerBuilderRegistry
from intelliqx_graph.optimization.layers.call_graph import CallGraphBuilder
from intelliqx_graph.optimization.layers.control_flow import ControlFlowBuilder
from intelliqx_graph.optimization.layers.data_flow import DataFlowBuilder
from intelliqx_graph.optimization.layers.dependency_graph import DependencyGraphBuilder
from intelliqx_graph.optimization.layers.deployment_graph import DeploymentGraphBuilder
from intelliqx_graph.optimization.layers.resource_graph import ResourceGraphBuilder
from intelliqx_graph.optimization.layers.security_graph import SecurityGraphBuilder
from intelliqx_graph.optimization.layers.state_transition import StateTransitionBuilder


def create_default_registry() -> LayerBuilderRegistry:
    registry = LayerBuilderRegistry()
    registry.register(CallGraphBuilder())
    registry.register(DataFlowBuilder())
    registry.register(ControlFlowBuilder())
    registry.register(DependencyGraphBuilder())
    registry.register(StateTransitionBuilder())
    registry.register(ResourceGraphBuilder())
    registry.register(SecurityGraphBuilder())
    registry.register(DeploymentGraphBuilder())
    return registry

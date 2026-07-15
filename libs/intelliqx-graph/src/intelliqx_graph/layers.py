"""Graph layer definitions and builder registry.

Each of the eight graph layers has a builder that constructs the
``SGIRGraph`` for that layer from parsed AST data. Builders are
registered via the ``LayerBuilderRegistry`` and invoked by the
Semantic Graph Builder agent.
"""

from __future__ import annotations

import abc
from typing import Any

from intelliqx_graph.models import GraphLayer, SGIRGraph


class LayerBuilder(abc.ABC):
    """Abstract base for graph layer builders.

    Each concrete builder takes parsed repository data and produces
    an ``SGIRGraph`` for one semantic layer.
    """

    @property
    @abc.abstractmethod
    def layer(self) -> GraphLayer:
        """The graph layer this builder produces."""

    @abc.abstractmethod
    def build(self, parsed_data: dict[str, Any], existing: SGIRGraph | None = None) -> SGIRGraph:
        """Build the graph layer from parsed repository data.

        Args:
            parsed_data: Output from the language parsers — ASTs,
                file metadata, imports, etc.
            existing: An optional pre-existing graph to augment
                (used for incremental updates).

        Returns:
            The constructed ``SGIRGraph`` for this layer.
        """
        raise NotImplementedError


class LayerBuilderRegistry:
    """Registry of layer builders keyed by ``GraphLayer``."""

    def __init__(self) -> None:
        self.builders: dict[GraphLayer, LayerBuilder] = {}

    def register(self, builder: LayerBuilder) -> None:
        """Register a layer builder."""
        self.builders[builder.layer] = builder

    def get(self, layer: GraphLayer) -> LayerBuilder | None:
        """Return the builder for the given layer, or None."""
        return self.builders.get(layer)

    def build_all(
        self, parsed_data: dict[str, Any]
    ) -> dict[GraphLayer, SGIRGraph]:
        """Invoke every registered builder and return the results."""
        results: dict[GraphLayer, SGIRGraph] = {}
        for layer, builder in self.builders.items():
            results[layer] = builder.build(parsed_data, results.get(layer))
        return results

    @property
    def registered_layers(self) -> list[GraphLayer]:
        return list(self.builders.keys())

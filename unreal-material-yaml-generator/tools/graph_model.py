"""
graph_model.py

Defines the intermediate graph model used to represent a material graph
before it is passed to the Unreal Engine backend.

The model is intentionally decoupled from Unreal so that it can be created,
inspected, and unit-tested without an Unreal Engine environment.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphNode:
    """Represents a single node in the material graph.

    Attributes:
        name: Unique identifier for this node within the graph.
        type: The kind of Unreal material expression to create
              (e.g. 'TextureSample', 'Multiply', 'Constant').
        properties: Arbitrary key/value pairs forwarded to the backend
                    when the node is created (e.g. ``texture``, ``value``).
    """

    name: str
    type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphConnection:
    """Represents a directed edge between two nodes.

    Both ``source`` and ``destination`` are pin references in the form
    ``<node_name>.<pin_name>`` or just ``<node_name>`` when the default pin
    is implied.

    Attributes:
        source: Output pin reference (e.g. ``multiply_1.RGB``).
        destination: Input pin reference (e.g. ``add_1.A``).
    """

    source: str
    destination: str


@dataclass
class GraphOutput:
    """Binds a node output to a named material attribute.

    Attributes:
        property: The material property to drive
                  (e.g. ``BaseColor``, ``Normal``, ``Roughness``).
        source: Node (and optional pin) that provides the value.
    """

    property: str
    source: str


@dataclass
class GraphAsset:
    """Top-level container for an entire material graph.

    Attributes:
        class_name: The Unreal asset class (always ``Material`` for now).
        asset_name: The name of the asset to create (e.g. ``M_Example``).
        asset_path: Content-browser path under which the asset is saved
                    (e.g. ``/Game/Generated``).
        nodes: Ordered mapping from node name to :class:`GraphNode`.
        connections: List of :class:`GraphConnection` objects.
        outputs: List of :class:`GraphOutput` bindings.
    """

    class_name: str
    asset_name: str
    asset_path: str
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    connections: list[GraphConnection] = field(default_factory=list)
    outputs: list[GraphOutput] = field(default_factory=list)

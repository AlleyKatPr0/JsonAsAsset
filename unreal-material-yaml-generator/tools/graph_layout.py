"""
graph_layout.py

Deterministic, layered graph-layout algorithm for material graphs.

Assigns ``node_pos_x`` / ``node_pos_y`` coordinates to every
:class:`~graph_model.GraphNode` that does not already have explicit
positions.  The layout is computed without Unreal Engine and is
therefore safe to use in tests and CLI tools.

Algorithm
---------
Nodes are sorted into layers using a topological ordering:

* **Layer 0** – source nodes (no incoming edges): textures, parameters,
  constants.
* **Layer 1..N** – derived nodes whose inputs come from earlier layers.
* **Layer N+1** – nodes that drive material outputs.

Within each layer nodes are distributed evenly on the Y axis.  Layers
are spaced evenly on the X axis.

If a node already has ``node_pos_x`` **and** ``node_pos_y`` in its
``properties`` dict it is left untouched.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque

from graph_model import GraphAsset, GraphNode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Layout constants (pixels in the Unreal material graph viewport).
# ---------------------------------------------------------------------------
_LAYER_X_STRIDE: int = 300   # horizontal spacing between layers
_NODE_Y_STRIDE: int = 200    # vertical spacing between nodes in a layer
_ORIGIN_X: int = -900        # X coordinate of the leftmost layer
_ORIGIN_Y: int = 0           # Y centre-offset of the first node in each layer


def assign_layout(graph: GraphAsset) -> None:
    """Assign ``node_pos_x``/``node_pos_y`` to nodes that lack positions.

    Mutates the ``properties`` dict of each :class:`~graph_model.GraphNode`
    in *graph* in-place.

    Parameters
    ----------
    graph:
        The graph whose nodes should receive layout coordinates.
    """
    nodes = graph.nodes
    if not nodes:
        return

    # Identify nodes that already have explicit positions.
    positioned = {
        name
        for name, node in nodes.items()
        if "node_pos_x" in node.properties and "node_pos_y" in node.properties
    }

    # Build adjacency: dest → {sources}
    incoming: dict[str, set[str]] = defaultdict(set)
    for conn in graph.connections:
        src_name = conn.source.split(".", maxsplit=1)[0]
        dst_name = conn.destination.split(".", maxsplit=1)[0]
        if src_name in nodes and dst_name in nodes:
            incoming[dst_name].add(src_name)

    # Also consider output bindings: output-driving nodes are "sinks".
    output_node_names: set[str] = set()
    for out in graph.outputs:
        src_name = out.source.split(".", maxsplit=1)[0]
        if src_name in nodes:
            output_node_names.add(src_name)

    # Kahn's algorithm to assign layers (topological BFS).
    in_degree: dict[str, int] = {name: len(incoming[name]) for name in nodes}
    layer_of: dict[str, int] = {}
    queue: deque[str] = deque(
        name for name, deg in in_degree.items() if deg == 0
    )

    while queue:
        name = queue.popleft()
        # Layer = 1 + max layer of all predecessors (0 if no predecessors).
        preds = incoming.get(name, set())
        layer = (max((layer_of[p] for p in preds if p in layer_of), default=-1)
                 + 1)
        layer_of[name] = layer

        # Propagate to successors.
        for conn in graph.connections:
            src_name = conn.source.split(".", maxsplit=1)[0]
            dst_name = conn.destination.split(".", maxsplit=1)[0]
            if src_name == name and dst_name in nodes:
                in_degree[dst_name] -= 1
                if in_degree[dst_name] == 0:
                    queue.append(dst_name)

    # Any node not yet assigned (e.g. cycle) gets placed at layer 0.
    for name in nodes:
        if name not in layer_of:
            layer_of[name] = 0
            logger.warning(
                "Node '%s' was not reached in topological sort "
                "(possible cycle); placed at layer 0.",
                name,
            )

    # Group nodes by layer.
    layers: dict[int, list[str]] = defaultdict(list)
    for name, layer in layer_of.items():
        layers[layer].append(name)

    # Sort nodes within each layer for determinism.
    for layer_nodes in layers.values():
        layer_nodes.sort()

    # Assign coordinates to nodes that are not already positioned.
    max_layer = max(layers.keys(), default=0)
    for layer_idx in sorted(layers.keys()):
        layer_nodes = layers[layer_idx]
        x = _ORIGIN_X + layer_idx * _LAYER_X_STRIDE
        total_height = (len(layer_nodes) - 1) * _NODE_Y_STRIDE
        start_y = _ORIGIN_Y - total_height // 2

        for i, name in enumerate(layer_nodes):
            if name in positioned:
                continue  # respect explicit positions
            node = nodes[name]
            node.properties["node_pos_x"] = x
            node.properties["node_pos_y"] = start_y + i * _NODE_Y_STRIDE
            logger.debug(
                "  Layout: '%s' → layer=%d  x=%d  y=%d",
                name, layer_idx, x, node.properties["node_pos_y"],
            )

    logger.info(
        "Layout assigned to %d nodes across %d layers.",
        len(nodes) - len(positioned),
        max_layer + 1,
    )

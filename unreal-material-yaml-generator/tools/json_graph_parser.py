"""
json_graph_parser.py

Converts a JSON graph description (as exported by tools such as FModel or
JsonAsAsset) into the intermediate :class:`~graph_model.GraphAsset` model.

This allows the full pipeline to accept JSON input as an alternative to YAML::

    JSON → GraphAsset → Unreal backend → Unreal asset

Supported JSON schema
---------------------
The minimal required structure is:

.. code-block:: json

    {
      "asset": {
        "class": "Material",
        "name": "M_Example",
        "path": "/Game/Generated"
      },
      "nodes": [
        {"name": "base", "type": "TextureSample", "texture": "/Game/T_Base"},
        {"name": "mul",  "type": "Multiply"}
      ],
      "connections": [
        {"source": "base.RGB", "destination": "mul.A"}
      ],
      "outputs": {
        "BaseColor": "mul"
      }
    }

The ``connections`` and ``outputs`` sections are optional.

For **Material Instance** assets the JSON asset block accepts additional fields:

.. code-block:: json

    {
      "asset": {
        "class": "MaterialInstance",
        "name": "MI_Metal",
        "path": "/Game/Generated",
        "parent": "/Game/Materials/M_Master"
      },
      "parameters": {
        "Roughness": 0.2,
        "TintColor": [1, 0, 0]
      }
    }
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Union

from graph_model import GraphAsset, GraphConnection, GraphNode, GraphOutput

logger = logging.getLogger(__name__)


def parse_json(source: Union[str, Path, dict]) -> GraphAsset:
    """Parse a JSON graph description and return a :class:`~graph_model.GraphAsset`.

    Parameters
    ----------
    source:
        Either a filesystem path to a ``.json`` file, or a pre-loaded Python
        ``dict`` containing the graph data.

    Returns
    -------
    GraphAsset
        Fully populated graph model ready to pass to the Unreal backend.

    Raises
    ------
    FileNotFoundError
        If *source* is a path that does not exist.
    KeyError
        If a required section is missing from the JSON.
    ValueError
        If a node entry is missing a ``name`` or ``type`` field, or if a
        connection references an undeclared node.
    """
    if isinstance(source, dict):
        data = source
        logger.info("Parsing JSON graph from in-memory dict.")
    else:
        path = Path(source)
        logger.info("Parsing JSON graph from: %s", path)
        if not path.exists():
            raise FileNotFoundError(f"JSON graph file not found: {path}")
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)

    # -- asset section -------------------------------------------------------
    asset_data: dict = data["asset"]
    class_name: str = asset_data["class"]
    asset_name: str = asset_data["name"]
    asset_path: str = asset_data["path"]
    parent: str = asset_data.get("parent", "")

    # -- nodes section -------------------------------------------------------
    nodes: dict[str, GraphNode] = {}
    for node_data in data.get("nodes", []):
        _validate_node_entry(node_data)
        node_name: str = node_data["name"]
        node_type: str = node_data["type"]
        properties: dict[str, Any] = {
            k: v for k, v in node_data.items() if k not in ("name", "type")
        }
        nodes[node_name] = GraphNode(
            name=node_name,
            type=node_type,
            properties=properties,
        )
        logger.debug(
            "  Node %r: type=%r properties=%r", node_name, node_type, properties
        )

    # -- connections section (optional) --------------------------------------
    connections: list[GraphConnection] = []
    for conn_data in data.get("connections", []):
        if isinstance(conn_data, dict):
            source = conn_data.get("source", "")
            destination = conn_data.get("destination", "")
            if not source or not destination:
                raise ValueError(
                    f"Connection entry missing 'source' or 'destination': {conn_data!r}"
                )
        elif isinstance(conn_data, str):
            # Support arrow-string format same as YAML.
            if "->" not in conn_data:
                raise ValueError(
                    f"Invalid connection string (missing '->'): {conn_data!r}"
                )
            left, right = conn_data.split("->", maxsplit=1)
            source, destination = left.strip(), right.strip()
        else:
            raise ValueError(f"Unsupported connection entry type: {type(conn_data)!r}")

        connections.append(
            GraphConnection(source=source, destination=destination)
        )
        logger.debug("  Connection: %r -> %r", source, destination)

    # -- outputs section (optional) ------------------------------------------
    outputs: list[GraphOutput] = []
    for prop_name, source_ref in data.get("outputs", {}).items():
        output = GraphOutput(property=prop_name, source=str(source_ref).strip())
        outputs.append(output)
        logger.debug("  Output %r <- %r", prop_name, output.source)

    # -- parameters section (MaterialInstance only) --------------------------
    parameters: dict[str, Any] = dict(data.get("parameters", {}))

    # -- validate connections reference declared nodes -----------------------
    for conn in connections:
        src_node_name = conn.source.split(".", maxsplit=1)[0]
        dst_node_name = conn.destination.split(".", maxsplit=1)[0]
        if src_node_name not in nodes:
            available = ", ".join(sorted(nodes)) or "<none>"
            raise ValueError(
                f"Connection source node '{src_node_name}' is not defined in the "
                f"nodes section. Available nodes: {available}"
            )
        if dst_node_name not in nodes:
            available = ", ".join(sorted(nodes)) or "<none>"
            raise ValueError(
                f"Connection destination node '{dst_node_name}' is not defined in "
                f"the nodes section. Available nodes: {available}"
            )

    # -- validate outputs reference declared nodes ---------------------------
    for output in outputs:
        src_node_name = output.source.split(".", maxsplit=1)[0]
        if src_node_name not in nodes:
            available = ", ".join(sorted(nodes)) or "<none>"
            raise ValueError(
                f"Output '{output.property}' references undefined node "
                f"'{src_node_name}'. Available nodes: {available}"
            )

    return GraphAsset(
        class_name=class_name,
        asset_name=asset_name,
        asset_path=asset_path,
        nodes=nodes,
        connections=connections,
        outputs=outputs,
        parent=parent,
        parameters=parameters,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_node_entry(node_data: Any) -> None:
    """Raise :class:`ValueError` if *node_data* is missing required fields."""
    if not isinstance(node_data, dict):
        raise ValueError(
            f"Each entry in 'nodes' must be a JSON object, got: {type(node_data)!r}"
        )
    if "name" not in node_data:
        raise ValueError(f"Node entry missing required 'name' field: {node_data!r}")
    if "type" not in node_data:
        raise ValueError(
            f"Node entry '{node_data.get('name', '?')}' missing required 'type' field."
        )

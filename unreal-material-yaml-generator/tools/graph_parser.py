"""
graph_parser.py

Parses YAML material-graph files and converts them into the intermediate
:class:`~graph_model.GraphAsset` model.

The parser is intentionally kept separate from both the YAML I/O layer
(handled here) and the Unreal backend (handled in
``unreal_material_backend.py``).

Supported YAML schema
---------------------
asset:
  class: Material
  name: M_Example
  path: /Game/Generated

nodes:
  <node_name>:
    type: <ExpressionType>
    <property>: <value>
    ...

connections:          # optional
  - <src_node>[.<pin>] -> <dst_node>[.<pin>]

outputs:
  <MaterialProperty>: <node>[.<pin>]
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

import yaml

from graph_model import GraphAsset, GraphConnection, GraphNode, GraphOutput

logger = logging.getLogger(__name__)


def _parse_pin_ref(ref: str) -> str:
    """Return the pin reference string as-is after basic validation.

    Pin references are strings of the form ``node_name`` or
    ``node_name.pin_name``.  The backend is responsible for splitting the
    node name from the pin name when wiring connections.
    """
    return ref.strip()


def _parse_connection_string(connection_str: str) -> GraphConnection:
    """Parse a connection string of the form ``src -> dst``.

    Parameters
    ----------
    connection_str:
        E.g. ``"base_tex.RGB -> multiply_1.A"``

    Returns
    -------
    GraphConnection
        Populated with the parsed source and destination pin references.

    Raises
    ------
    ValueError
        If the connection string does not contain the ``->`` separator.
    """
    if "->" not in connection_str:
        raise ValueError(
            f"Invalid connection string (missing '->'): {connection_str!r}"
        )
    left, right = connection_str.split("->", maxsplit=1)
    return GraphConnection(
        source=_parse_pin_ref(left),
        destination=_parse_pin_ref(right),
    )


def parse_yaml(source: Union[str, Path]) -> GraphAsset:
    """Load a YAML file and return a :class:`~graph_model.GraphAsset`.

    Parameters
    ----------
    source:
        Filesystem path to the ``.yaml`` file.

    Returns
    -------
    GraphAsset
        Fully populated graph model ready to pass to the Unreal backend.

    Raises
    ------
    FileNotFoundError
        If *source* does not exist.
    KeyError
        If a required top-level section is missing from the YAML.
    ValueError
        If a connection string cannot be parsed.
    """
    path = Path(source)
    logger.info("Parsing YAML from: %s", path)

    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    # -- asset section -------------------------------------------------------
    asset_data: dict = data["asset"]
    class_name: str = asset_data["class"]
    asset_name: str = asset_data["name"]
    asset_path: str = asset_data["path"]

    # -- nodes section -------------------------------------------------------
    nodes: dict[str, GraphNode] = {}
    for node_name, node_data in data.get("nodes", {}).items():
        node_type: str = node_data["type"]
        # Everything except 'type' is treated as a node property.
        properties: dict = {k: v for k, v in node_data.items() if k != "type"}
        nodes[node_name] = GraphNode(
            name=node_name,
            type=node_type,
            properties=properties,
        )
        logger.debug("  Node %r: type=%r properties=%r", node_name, node_type, properties)

    # -- connections section (optional) --------------------------------------
    connections: list[GraphConnection] = []
    for conn_str in data.get("connections", []):
        conn = _parse_connection_string(str(conn_str))
        connections.append(conn)
        logger.debug("  Connection: %r -> %r", conn.source, conn.destination)

    # -- outputs section -----------------------------------------------------
    outputs: list[GraphOutput] = []
    for prop_name, source_ref in data.get("outputs", {}).items():
        output = GraphOutput(property=prop_name, source=_parse_pin_ref(str(source_ref)))
        outputs.append(output)
        logger.debug("  Output %r <- %r", prop_name, output.source)

    return GraphAsset(
        class_name=class_name,
        asset_name=asset_name,
        asset_path=asset_path,
        nodes=nodes,
        connections=connections,
        outputs=outputs,
    )

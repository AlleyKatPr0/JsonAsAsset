"""
node_discovery.py

Automatic discovery of all ``MaterialExpression`` classes available in
the current Unreal Engine Python environment.

This module replaces the static ``NODE_TYPE_MAP`` dictionary with a
dynamically generated mapping that supports every material expression
registered in the engine, including custom plugins and UE5.7+ Substrate
expressions.

Usage
-----
Called at module-load time inside the Unreal backend to build the node map::

    from node_discovery import discover_material_nodes
    NODE_TYPE_MAP = discover_material_nodes()

Fallback
--------
If ``unreal`` is unavailable (e.g. during unit tests), the function returns
the provided *fallback* mapping unchanged, allowing tests to run without an
Unreal Engine installation.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def discover_material_nodes(
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a mapping of short node-type names to Unreal expression classes.

    Iterates over all names exposed by the ``unreal`` Python module and
    collects every name that starts with ``MaterialExpression``.  The short
    name (with ``MaterialExpression`` prefix stripped) is used as the YAML
    ``type`` value, e.g. ``"TextureSample"`` maps to
    ``unreal.MaterialExpressionTextureSample``.

    Parameters
    ----------
    fallback:
        Optional static mapping to return when ``unreal`` is not importable.
        Defaults to an empty dict.

    Returns
    -------
    dict[str, Any]
        Mapping from short node-type name (e.g. ``"Multiply"``) to the
        corresponding Unreal class object.

    Examples
    --------
    Inside Unreal Python::

        from node_discovery import discover_material_nodes
        node_map = discover_material_nodes()
        print(list(node_map.keys())[:5])
        # ['Abs', 'Add', 'AntiAliasedTextureMask', ...]
    """
    if fallback is None:
        fallback = {}

    try:
        import unreal  # type: ignore[import]
    except ImportError:
        logger.debug(
            "unreal module not available; returning fallback node map "
            "with %d entries.",
            len(fallback),
        )
        return fallback

    prefix = "MaterialExpression"
    node_map: dict[str, Any] = {}

    for name in dir(unreal):
        if name.startswith(prefix):
            short = name[len(prefix):]  # strip 'MaterialExpression' prefix
            cls = getattr(unreal, name)
            node_map[short] = cls

    logger.info(
        "Discovered %d MaterialExpression classes from the Unreal module.",
        len(node_map),
    )
    return node_map


def get_expression_class(
    node_type: str,
    node_map: dict[str, Any],
) -> Any:
    """Return the Unreal expression class for *node_type*.

    Looks up *node_type* in *node_map* (produced by
    :func:`discover_material_nodes`).  Raises a descriptive
    :class:`ValueError` when the type is not found so that callers
    receive a useful error message.

    Parameters
    ----------
    node_type:
        Short expression type name as used in YAML (e.g. ``"TextureSample"``).
    node_map:
        Mapping returned by :func:`discover_material_nodes`.

    Returns
    -------
    Any
        The Unreal expression class.

    Raises
    ------
    ValueError
        If *node_type* is not present in *node_map*.
    """
    cls = node_map.get(node_type)
    if cls is None:
        available = ", ".join(sorted(node_map.keys())) or "<none>"
        raise ValueError(
            f"Unknown node type '{node_type}'. "
            f"No MaterialExpression class named 'MaterialExpression{node_type}' "
            f"was found in the Unreal module. "
            f"Available types: {available}"
        )
    return cls

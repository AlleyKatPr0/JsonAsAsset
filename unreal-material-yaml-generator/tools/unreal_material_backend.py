"""
unreal_material_backend.py

Translates a :class:`~graph_model.GraphAsset` into a live Unreal Engine
``Material`` asset using the Unreal Python API.

This module must be executed inside Unreal Engine (i.e. via the Unreal
Python interpreter or the Unreal Editor console).

Pipeline
--------
1. Create the ``Material`` asset via ``AssetToolsHelpers`` + ``MaterialFactoryNew``.
2. Iterate over graph nodes and call
   ``MaterialEditingLibrary.create_material_expression`` for each one.
3. Apply per-node property assignments (texture, value, etc.).
4. Wire connections using ``MaterialEditingLibrary.connect_material_expressions``.
5. Bind output nodes using ``MaterialEditingLibrary.connect_material_property``.
6. Recompile and save the material.
"""

from __future__ import annotations

import logging
from typing import Any

# ---------------------------------------------------------------------------
# Unreal Engine imports – these are only available inside Unreal Python.
# ---------------------------------------------------------------------------
import unreal  # type: ignore[import]

from graph_model import GraphAsset, GraphConnection, GraphNode, GraphOutput

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mapping: YAML node type  →  Unreal expression class name
# ---------------------------------------------------------------------------
# Each value is the string passed to unreal.load_class / used to look up the
# expression class under the ``unreal`` module.
NODE_TYPE_MAP: dict[str, str] = {
    "TextureSample":     "MaterialExpressionTextureSample",
    "Multiply":          "MaterialExpressionMultiply",
    "Add":               "MaterialExpressionAdd",
    "Constant":          "MaterialExpressionConstant",
    "Constant3Vector":   "MaterialExpressionConstant3Vector",
    "ScalarParameter":   "MaterialExpressionScalarParameter",
    "VectorParameter":   "MaterialExpressionVectorParameter",
    # TODO: Add MaterialExpressionMaterialFunctionCall for Material Functions
    # TODO: Add MaterialExpressionStaticSwitchParameter for Static Switches
    # TODO: Add MaterialExpressionComponentMask for Component Masks
    # TODO: Add MaterialExpressionTextureCoordinate for Texture Coordinate Nodes
}

# ---------------------------------------------------------------------------
# Mapping: output property name  →  unreal.MaterialProperty enum value
# ---------------------------------------------------------------------------
OUTPUT_PROPERTY_MAP: dict[str, unreal.MaterialProperty] = {
    "BaseColor": unreal.MaterialProperty.MP_BASE_COLOR,
    "Normal":    unreal.MaterialProperty.MP_NORMAL,
    "Roughness": unreal.MaterialProperty.MP_ROUGHNESS,
    "Metallic":  unreal.MaterialProperty.MP_METALLIC,
    "Emissive":  unreal.MaterialProperty.MP_EMISSIVE_COLOR,
    "Opacity":   unreal.MaterialProperty.MP_OPACITY,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_pin_ref(ref: str) -> tuple[str, str]:
    """Split a pin reference into ``(node_name, pin_name)``.

    If no pin is specified (i.e. the string contains no ``.``), an empty
    string is returned for the pin name so that the caller can decide on a
    sensible default.
    """
    if "." in ref:
        node_name, pin_name = ref.split(".", maxsplit=1)
        return node_name.strip(), pin_name.strip()
    return ref.strip(), ""


def _get_expression_class(node_type: str) -> Any:
    """Return the Unreal expression class for *node_type*.

    Parameters
    ----------
    node_type:
        The ``type`` field from the YAML node definition.

    Raises
    ------
    KeyError
        If *node_type* is not present in :data:`NODE_TYPE_MAP`.
    AttributeError
        If the mapped class name does not exist in the ``unreal`` module.
    """
    class_name = NODE_TYPE_MAP[node_type]
    return getattr(unreal, class_name)


# ---------------------------------------------------------------------------
# Asset creation
# ---------------------------------------------------------------------------

def _create_material_asset(
    asset_name: str,
    asset_path: str,
) -> unreal.Material:
    """Create and return a new empty ``Material`` asset.

    Uses ``AssetToolsHelpers`` and ``MaterialFactoryNew`` as required by the
    Unreal Python API.

    Parameters
    ----------
    asset_name:
        The asset name without the package path (e.g. ``M_Example``).
    asset_path:
        The content-browser directory (e.g. ``/Game/Generated``).

    Returns
    -------
    unreal.Material
        The newly created material object.
    """
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.MaterialFactoryNew()
    material = asset_tools.create_asset(
        asset_name=asset_name,
        package_path=asset_path,
        asset_class=unreal.Material,
        factory=factory,
    )
    if material is None:
        raise RuntimeError(
            f"Failed to create material asset '{asset_name}' at '{asset_path}'."
        )
    logger.info("Created material asset: %s/%s", asset_path, asset_name)
    return material


# ---------------------------------------------------------------------------
# Node creation
# ---------------------------------------------------------------------------

def _create_nodes(
    material: unreal.Material,
    nodes: dict[str, GraphNode],
) -> dict[str, Any]:
    """Create Unreal material expressions for every node in *nodes*.

    Parameters
    ----------
    material:
        The parent material asset.
    nodes:
        Mapping from node name to :class:`~graph_model.GraphNode`.

    Returns
    -------
    dict[str, Any]
        Registry mapping node name → created Unreal expression object.
    """
    mel = unreal.MaterialEditingLibrary
    node_registry: dict[str, Any] = {}

    for node_name, node in nodes.items():
        expr_class = _get_expression_class(node.type)
        # create_material_expression places the node inside the material graph.
        expression = mel.create_material_expression(
            material,
            expr_class,
            node_pos_x=0,
            node_pos_y=0,
        )
        node_registry[node_name] = expression
        logger.debug("  Created expression %r -> %r", node_name, expr_class.__name__)

        # Apply node-specific properties.
        _apply_node_properties(expression, node)

    return node_registry


def _apply_node_properties(expression: Any, node: GraphNode) -> None:
    """Assign YAML properties onto an Unreal material expression.

    Currently handled properties:
    - ``texture`` – loads a :class:`unreal.Texture` object and assigns it.
    - ``value``   – sets the ``r`` (float) or ``constant`` field.
    - ``vector``  – sets the ``constant`` (linear color) field.

    Parameters
    ----------
    expression:
        The Unreal expression object to modify.
    node:
        The graph node containing property data.
    """
    props = node.properties

    if "texture" in props:
        # Load the texture asset and assign it to the expression.
        texture_path: str = props["texture"]
        texture_obj = unreal.load_asset(texture_path)
        if texture_obj is None:
            logger.warning(
                "  Texture not found at '%s' for node '%s'.", texture_path, node.name
            )
        else:
            expression.set_editor_property("texture", texture_obj)
            logger.debug("  Set texture '%s' on '%s'.", texture_path, node.name)

    if "value" in props:
        # Constant node: single float value stored in the 'r' property.
        float_val = float(props["value"])
        try:
            expression.set_editor_property("r", float_val)
        except (AttributeError, RuntimeError):
            # Some constant types use a different property name.
            expression.set_editor_property("constant", float_val)
        logger.debug("  Set value %s on '%s'.", float_val, node.name)

    if "vector" in props:
        # Constant3Vector node: list of [r, g, b] or [r, g, b, a].
        vec = props["vector"]
        color = unreal.LinearColor(
            r=float(vec[0]),
            g=float(vec[1]),
            b=float(vec[2]),
            a=float(vec[3]) if len(vec) > 3 else 1.0,
        )
        expression.set_editor_property("constant", color)
        logger.debug("  Set vector %s on '%s'.", vec, node.name)

    if "parameter_name" in props:
        # Scalar/Vector parameter nodes need a unique parameter name.
        expression.set_editor_property("parameter_name", props["parameter_name"])

    if "default_value" in props:
        float_val = float(props["default_value"])
        expression.set_editor_property("default_value", float_val)


# ---------------------------------------------------------------------------
# Connection wiring
# ---------------------------------------------------------------------------

def _connect_nodes(
    connections: list[GraphConnection],
    node_registry: dict[str, Any],
) -> None:
    """Wire expression nodes together using the connection list.

    Uses ``MaterialEditingLibrary.connect_material_expressions``.

    Parameters
    ----------
    connections:
        List of :class:`~graph_model.GraphConnection` objects.
    node_registry:
        Mapping of node name → Unreal expression object.
    """
    mel = unreal.MaterialEditingLibrary

    for conn in connections:
        src_node_name, src_pin = _split_pin_ref(conn.source)
        dst_node_name, dst_pin = _split_pin_ref(conn.destination)

        src_expr = node_registry.get(src_node_name)
        dst_expr = node_registry.get(dst_node_name)

        if src_expr is None:
            logger.warning("  Source node '%s' not found; skipping.", src_node_name)
            continue
        if dst_expr is None:
            logger.warning("  Destination node '%s' not found; skipping.", dst_node_name)
            continue

        # connect_material_expressions(from_expr, from_output_name,
        #                               to_expr,   to_input_name)
        mel.connect_material_expressions(src_expr, src_pin, dst_expr, dst_pin)
        logger.debug(
            "  Connected %s.%s -> %s.%s",
            src_node_name, src_pin, dst_node_name, dst_pin,
        )


# ---------------------------------------------------------------------------
# Output binding
# ---------------------------------------------------------------------------

def _bind_outputs(
    material: unreal.Material,
    outputs: list[GraphOutput],
    node_registry: dict[str, Any],
) -> None:
    """Bind material expression outputs to named material properties.

    Uses ``MaterialEditingLibrary.connect_material_property``.

    Parameters
    ----------
    material:
        The parent material asset.
    outputs:
        List of :class:`~graph_model.GraphOutput` objects.
    node_registry:
        Mapping of node name → Unreal expression object.
    """
    mel = unreal.MaterialEditingLibrary

    for output in outputs:
        prop = OUTPUT_PROPERTY_MAP.get(output.property)
        if prop is None:
            logger.warning(
                "  Unknown material property '%s'; skipping.", output.property
            )
            continue

        src_node_name, src_pin = _split_pin_ref(output.source)
        src_expr = node_registry.get(src_node_name)

        if src_expr is None:
            logger.warning(
                "  Output source node '%s' not found; skipping.", src_node_name
            )
            continue

        # connect_material_property(from_expr, from_output_name, property)
        mel.connect_material_property(src_expr, src_pin, prop)
        logger.debug(
            "  Bound %s.%s -> material.%s",
            src_node_name, src_pin, output.property,
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_from_graph(graph: GraphAsset) -> unreal.Material:
    """Create a complete Unreal material from an intermediate graph model.

    This is the main entry point called by :mod:`material_builder`.

    Parameters
    ----------
    graph:
        Fully populated :class:`~graph_model.GraphAsset`.

    Returns
    -------
    unreal.Material
        The compiled and saved material asset.
    """
    logger.info("Building material '%s' at '%s'.", graph.asset_name, graph.asset_path)

    # 1. Create the Material asset.
    material = _create_material_asset(graph.asset_name, graph.asset_path)

    # 2. Create all expression nodes.
    node_registry = _create_nodes(material, graph.nodes)

    # 3. Wire node-to-node connections.
    _connect_nodes(graph.connections, node_registry)

    # 4. Bind material outputs.
    _bind_outputs(material, graph.outputs, node_registry)

    # 5. Recompile the material so the graph is validated.
    unreal.MaterialEditingLibrary.recompile_material(material)
    logger.info("Recompiled material '%s'.", graph.asset_name)

    # 6. Save the asset to disk.
    unreal.EditorAssetLibrary.save_loaded_asset(material)
    logger.info("Saved material '%s'.", graph.asset_name)

    return material

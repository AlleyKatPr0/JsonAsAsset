"""
Unit tests for graph_parser.py.

These tests run without an Unreal Engine installation because graph_parser
and graph_model are engine-agnostic.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Make sure the tools directory is importable regardless of how pytest is
# invoked (from the repo root or from this directory).
# ---------------------------------------------------------------------------
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from graph_model import GraphAsset, GraphConnection, GraphNode, GraphOutput  # noqa: E402
from graph_parser import _parse_connection_string, parse_yaml  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(content: str) -> Path:
    """Write *content* to a temporary YAML file and return its path."""
    fh = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    fh.write(content)
    fh.close()
    return Path(fh.name)


# ---------------------------------------------------------------------------
# _parse_connection_string
# ---------------------------------------------------------------------------

class TestParseConnectionString:
    def test_simple_node_names(self):
        conn = _parse_connection_string("node_a -> node_b")
        assert conn.source == "node_a"
        assert conn.destination == "node_b"

    def test_pin_references(self):
        conn = _parse_connection_string("base_tex.RGB -> multiply_1.A")
        assert conn.source == "base_tex.RGB"
        assert conn.destination == "multiply_1.A"

    def test_whitespace_is_stripped(self):
        conn = _parse_connection_string("  tex.RGB  ->  mul.B  ")
        assert conn.source == "tex.RGB"
        assert conn.destination == "mul.B"

    def test_missing_arrow_raises_value_error(self):
        with pytest.raises(ValueError, match="->"):
            _parse_connection_string("node_a node_b")


# ---------------------------------------------------------------------------
# parse_yaml – basic structure
# ---------------------------------------------------------------------------

class TestParseYamlBasic:
    def test_minimal_material(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  tex:
    type: TextureSample
    texture: /Game/T_Test

outputs:
  BaseColor: tex.RGB
"""
        )
        try:
            graph = parse_yaml(path)
            assert isinstance(graph, GraphAsset)
            assert graph.asset_name == "M_Test"
            assert graph.asset_path == "/Game/Generated"
            assert graph.class_name == "Material"
            assert "tex" in graph.nodes
            node = graph.nodes["tex"]
            assert node.type == "TextureSample"
            assert node.properties["texture"] == "/Game/T_Test"
            assert len(graph.outputs) == 1
            assert graph.outputs[0].property == "BaseColor"
            assert graph.outputs[0].source == "tex.RGB"
        finally:
            os.unlink(path)

    def test_connections_are_parsed(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  base_tex:
    type: TextureSample
    texture: /Game/T_Base
  multiply_1:
    type: Multiply

connections:
  - base_tex.RGB -> multiply_1.A

outputs:
  BaseColor: multiply_1
"""
        )
        try:
            graph = parse_yaml(path)
            assert len(graph.connections) == 1
            conn = graph.connections[0]
            assert conn.source == "base_tex.RGB"
            assert conn.destination == "multiply_1.A"
        finally:
            os.unlink(path)

    def test_connections_section_optional(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  tex:
    type: TextureSample
    texture: /Game/T_Test

outputs:
  BaseColor: tex.RGB
"""
        )
        try:
            graph = parse_yaml(path)
            assert graph.connections == []
        finally:
            os.unlink(path)

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_yaml("/nonexistent/path/material.yaml")

    def test_missing_asset_section_raises(self):
        path = _write_yaml(
            """
nodes:
  tex:
    type: TextureSample

outputs:
  BaseColor: tex.RGB
"""
        )
        try:
            with pytest.raises(KeyError):
                parse_yaml(path)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# parse_yaml – node layout positions
# ---------------------------------------------------------------------------

class TestNodePositions:
    def test_node_pos_stored_in_properties(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  tex:
    type: TextureSample
    texture: /Game/T_Test
    node_pos_x: -400
    node_pos_y: 100

outputs:
  BaseColor: tex.RGB
"""
        )
        try:
            graph = parse_yaml(path)
            props = graph.nodes["tex"].properties
            assert props["node_pos_x"] == -400
            assert props["node_pos_y"] == 100
        finally:
            os.unlink(path)

    def test_node_pos_defaults_absent(self):
        """Nodes without layout keys should simply not have them in properties."""
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  tex:
    type: TextureSample
    texture: /Game/T_Test

outputs:
  BaseColor: tex.RGB
"""
        )
        try:
            graph = parse_yaml(path)
            props = graph.nodes["tex"].properties
            assert "node_pos_x" not in props
            assert "node_pos_y" not in props
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# parse_yaml – ScalarParameter / VectorParameter metadata
# ---------------------------------------------------------------------------

class TestParameterMetadata:
    def test_scalar_parameter_full_metadata(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  roughness:
    type: ScalarParameter
    parameter_name: Roughness
    default_value: 0.5
    group: Surface
    sort_priority: 0
    slider_min: 0.0
    slider_max: 1.0

outputs:
  Roughness: roughness
"""
        )
        try:
            graph = parse_yaml(path)
            props = graph.nodes["roughness"].properties
            assert props["parameter_name"] == "Roughness"
            assert props["default_value"] == 0.5
            assert props["group"] == "Surface"
            assert props["sort_priority"] == 0
            assert props["slider_min"] == 0.0
            assert props["slider_max"] == 1.0
        finally:
            os.unlink(path)

    def test_vector_parameter_with_group(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  tint:
    type: VectorParameter
    parameter_name: TintColor
    vector: [1.0, 1.0, 1.0, 1.0]
    group: Surface
    sort_priority: 1

outputs:
  BaseColor: tint.RGB
"""
        )
        try:
            graph = parse_yaml(path)
            props = graph.nodes["tint"].properties
            assert props["group"] == "Surface"
            assert props["sort_priority"] == 1
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# parse_yaml – new node types
# ---------------------------------------------------------------------------

class TestNewNodeTypes:
    def test_component_mask_channels_parsed(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  mask:
    type: ComponentMask
    r: true
    g: false
    b: false
    a: false
  tex:
    type: TextureSample
    texture: /Game/T_Test

connections:
  - tex -> mask

outputs:
  Roughness: mask
"""
        )
        try:
            graph = parse_yaml(path)
            props = graph.nodes["mask"].properties
            assert props["r"] is True
            assert props["g"] is False
            assert props["b"] is False
            assert props["a"] is False
        finally:
            os.unlink(path)

    def test_texture_coordinate_properties_parsed(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  uv:
    type: TextureCoordinate
    coordinate_index: 1
    u_tiling: 2.0
    v_tiling: 3.0
  tex:
    type: TextureSample
    texture: /Game/T_Test

connections:
  - uv -> tex.UVs

outputs:
  BaseColor: tex.RGB
"""
        )
        try:
            graph = parse_yaml(path)
            props = graph.nodes["uv"].properties
            assert props["coordinate_index"] == 1
            assert props["u_tiling"] == 2.0
            assert props["v_tiling"] == 3.0
        finally:
            os.unlink(path)

    def test_static_switch_parameter_parsed(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  sw:
    type: StaticSwitchParameter
    parameter_name: UseDetail
    default_value: false
    group: Options
  tex:
    type: TextureSample
    texture: /Game/T_Test

outputs:
  BaseColor: sw
"""
        )
        try:
            graph = parse_yaml(path)
            props = graph.nodes["sw"].properties
            assert props["parameter_name"] == "UseDetail"
            assert props["default_value"] is False
            assert props["group"] == "Options"
        finally:
            os.unlink(path)

    def test_function_call_parsed(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  func:
    type: FunctionCall
    material_function: /Game/MaterialFunctions/MF_Blend

outputs:
  BaseColor: func
"""
        )
        try:
            graph = parse_yaml(path)
            assert graph.nodes["func"].type == "FunctionCall"
            assert (
                graph.nodes["func"].properties["material_function"]
                == "/Game/MaterialFunctions/MF_Blend"
            )
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# parse_yaml – validation errors
# ---------------------------------------------------------------------------

class TestValidationErrors:
    def test_connection_source_node_undefined_raises(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  tex:
    type: TextureSample
    texture: /Game/T_Test

connections:
  - ghost_node.RGB -> tex.UVs

outputs:
  BaseColor: tex.RGB
"""
        )
        try:
            with pytest.raises(ValueError, match="ghost_node"):
                parse_yaml(path)
        finally:
            os.unlink(path)

    def test_connection_destination_node_undefined_raises(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  tex:
    type: TextureSample
    texture: /Game/T_Test

connections:
  - tex.RGB -> missing_node.A

outputs:
  BaseColor: tex.RGB
"""
        )
        try:
            with pytest.raises(ValueError, match="missing_node"):
                parse_yaml(path)
        finally:
            os.unlink(path)

    def test_output_references_undefined_node_raises(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  tex:
    type: TextureSample
    texture: /Game/T_Test

outputs:
  BaseColor: nowhere_node.RGB
"""
        )
        try:
            with pytest.raises(ValueError, match="nowhere_node"):
                parse_yaml(path)
        finally:
            os.unlink(path)

    def test_error_message_lists_available_nodes(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  real_node:
    type: Multiply

outputs:
  BaseColor: bad_node
"""
        )
        try:
            with pytest.raises(ValueError, match="real_node"):
                parse_yaml(path)
        finally:
            os.unlink(path)

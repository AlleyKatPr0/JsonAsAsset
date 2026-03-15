"""
Unit tests for new engine-agnostic modules:
  - json_graph_parser.py
  - graph_layout.py
  - node_discovery.py  (fallback / non-Unreal path)
  - graph_parser.py    (MaterialInstance fields)

These tests run without an Unreal Engine installation.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure the tools directory is importable.
# ---------------------------------------------------------------------------
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from graph_model import GraphAsset, GraphConnection, GraphNode, GraphOutput  # noqa: E402
from json_graph_parser import parse_json  # noqa: E402
from graph_layout import assign_layout  # noqa: E402
from node_discovery import discover_material_nodes, get_expression_class  # noqa: E402

import os
import tempfile


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


def _make_graph(**kwargs) -> GraphAsset:
    """Return a minimal GraphAsset with optional overrides."""
    defaults = dict(
        class_name="Material",
        asset_name="M_Test",
        asset_path="/Game/Generated",
    )
    defaults.update(kwargs)
    return GraphAsset(**defaults)


def _make_node(name: str, node_type: str = "TextureSample", **props) -> GraphNode:
    return GraphNode(name=name, type=node_type, properties=dict(props))


# ===========================================================================
# json_graph_parser.py
# ===========================================================================

class TestParseJsonBasic:
    def test_minimal_dict(self):
        data = {
            "asset": {
                "class": "Material",
                "name": "M_Test",
                "path": "/Game/Generated",
            },
            "nodes": [
                {"name": "tex", "type": "TextureSample", "texture": "/Game/T_Test"},
            ],
            "outputs": {"BaseColor": "tex.RGB"},
        }
        graph = parse_json(data)
        assert isinstance(graph, GraphAsset)
        assert graph.asset_name == "M_Test"
        assert graph.class_name == "Material"
        assert "tex" in graph.nodes
        assert graph.nodes["tex"].type == "TextureSample"
        assert graph.nodes["tex"].properties["texture"] == "/Game/T_Test"
        assert len(graph.outputs) == 1
        assert graph.outputs[0].property == "BaseColor"
        assert graph.outputs[0].source == "tex.RGB"

    def test_connections_dict_format(self):
        data = {
            "asset": {"class": "Material", "name": "M", "path": "/Game"},
            "nodes": [
                {"name": "a", "type": "TextureSample"},
                {"name": "b", "type": "Multiply"},
            ],
            "connections": [
                {"source": "a.RGB", "destination": "b.A"},
            ],
            "outputs": {"BaseColor": "b"},
        }
        graph = parse_json(data)
        assert len(graph.connections) == 1
        assert graph.connections[0].source == "a.RGB"
        assert graph.connections[0].destination == "b.A"

    def test_connections_arrow_string_format(self):
        data = {
            "asset": {"class": "Material", "name": "M", "path": "/Game"},
            "nodes": [
                {"name": "a", "type": "TextureSample"},
                {"name": "b", "type": "Multiply"},
            ],
            "connections": ["a.RGB -> b.A"],
            "outputs": {"BaseColor": "b"},
        }
        graph = parse_json(data)
        assert graph.connections[0].source == "a.RGB"

    def test_no_connections_section(self):
        data = {
            "asset": {"class": "Material", "name": "M", "path": "/Game"},
            "nodes": [{"name": "c", "type": "Constant", "value": 1.0}],
            "outputs": {"Roughness": "c"},
        }
        graph = parse_json(data)
        assert graph.connections == []

    def test_material_instance_fields(self):
        data = {
            "asset": {
                "class": "MaterialInstance",
                "name": "MI_Metal",
                "path": "/Game/Generated",
                "parent": "/Game/Materials/M_Master",
            },
            "parameters": {
                "Roughness": 0.2,
                "TintColor": [1, 0, 0],
            },
        }
        graph = parse_json(data)
        assert graph.class_name == "MaterialInstance"
        assert graph.parent == "/Game/Materials/M_Master"
        assert graph.parameters["Roughness"] == 0.2
        assert graph.parameters["TintColor"] == [1, 0, 0]

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_json("/nonexistent/graph.json")

    def test_missing_asset_section_raises(self):
        with pytest.raises(KeyError):
            parse_json({"nodes": []})

    def test_node_missing_name_raises(self):
        data = {
            "asset": {"class": "Material", "name": "M", "path": "/Game"},
            "nodes": [{"type": "Multiply"}],
        }
        with pytest.raises(ValueError, match="name"):
            parse_json(data)

    def test_node_missing_type_raises(self):
        data = {
            "asset": {"class": "Material", "name": "M", "path": "/Game"},
            "nodes": [{"name": "mul"}],
        }
        with pytest.raises(ValueError, match="type"):
            parse_json(data)

    def test_connection_references_undefined_node_raises(self):
        data = {
            "asset": {"class": "Material", "name": "M", "path": "/Game"},
            "nodes": [{"name": "a", "type": "TextureSample"}],
            "connections": [{"source": "ghost.RGB", "destination": "a.UVs"}],
            "outputs": {"BaseColor": "a"},
        }
        with pytest.raises(ValueError, match="ghost"):
            parse_json(data)

    def test_output_references_undefined_node_raises(self):
        data = {
            "asset": {"class": "Material", "name": "M", "path": "/Game"},
            "nodes": [{"name": "a", "type": "TextureSample"}],
            "outputs": {"BaseColor": "missing"},
        }
        with pytest.raises(ValueError, match="missing"):
            parse_json(data)

    def test_parse_json_file(self, tmp_path):
        import json

        payload = {
            "asset": {"class": "Material", "name": "M_File", "path": "/Game"},
            "nodes": [{"name": "n", "type": "Constant", "value": 0.5}],
            "outputs": {"Roughness": "n"},
        }
        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps(payload), encoding="utf-8")

        graph = parse_json(json_file)
        assert graph.asset_name == "M_File"
        assert "n" in graph.nodes


# ===========================================================================
# graph_layout.py
# ===========================================================================

class TestAssignLayout:
    def _linear_graph(self) -> GraphAsset:
        """tex → mul → result, output: BaseColor = result"""
        nodes = {
            "tex": _make_node("tex", "TextureSample"),
            "mul": _make_node("mul", "Multiply"),
            "result": _make_node("result", "Add"),
        }
        connections = [
            GraphConnection(source="tex", destination="mul"),
            GraphConnection(source="mul", destination="result"),
        ]
        outputs = [GraphOutput(property="BaseColor", source="result")]
        return _make_graph(nodes=nodes, connections=connections, outputs=outputs)

    def test_positions_assigned_to_all_nodes(self):
        graph = self._linear_graph()
        assign_layout(graph)
        for node in graph.nodes.values():
            assert "node_pos_x" in node.properties
            assert "node_pos_y" in node.properties

    def test_upstream_nodes_have_smaller_x(self):
        graph = self._linear_graph()
        assign_layout(graph)
        # tex (layer 0) → mul (layer 1) → result (layer 2)
        x_tex = graph.nodes["tex"].properties["node_pos_x"]
        x_mul = graph.nodes["mul"].properties["node_pos_x"]
        x_result = graph.nodes["result"].properties["node_pos_x"]
        assert x_tex < x_mul < x_result

    def test_explicit_positions_not_overwritten(self):
        graph = self._linear_graph()
        graph.nodes["tex"].properties["node_pos_x"] = 9999
        graph.nodes["tex"].properties["node_pos_y"] = 8888
        assign_layout(graph)
        assert graph.nodes["tex"].properties["node_pos_x"] == 9999
        assert graph.nodes["tex"].properties["node_pos_y"] == 8888

    def test_empty_graph_no_crash(self):
        graph = _make_graph()
        assign_layout(graph)  # Should not raise

    def test_single_node_gets_origin(self):
        nodes = {"solo": _make_node("solo")}
        graph = _make_graph(nodes=nodes)
        assign_layout(graph)
        assert "node_pos_x" in graph.nodes["solo"].properties
        assert "node_pos_y" in graph.nodes["solo"].properties

    def test_parallel_nodes_have_different_y(self):
        """Two source nodes should share X but differ in Y."""
        nodes = {
            "tex_a": _make_node("tex_a", "TextureSample"),
            "tex_b": _make_node("tex_b", "TextureSample"),
            "mul": _make_node("mul", "Multiply"),
        }
        connections = [
            GraphConnection(source="tex_a", destination="mul"),
            GraphConnection(source="tex_b", destination="mul"),
        ]
        outputs = [GraphOutput(property="BaseColor", source="mul")]
        graph = _make_graph(nodes=nodes, connections=connections, outputs=outputs)
        assign_layout(graph)
        assert (
            graph.nodes["tex_a"].properties["node_pos_x"]
            == graph.nodes["tex_b"].properties["node_pos_x"]
        )
        assert (
            graph.nodes["tex_a"].properties["node_pos_y"]
            != graph.nodes["tex_b"].properties["node_pos_y"]
        )

    def test_layout_is_deterministic(self):
        """Running assign_layout twice on the same graph gives identical results."""
        graph1 = self._linear_graph()
        graph2 = self._linear_graph()
        assign_layout(graph1)
        assign_layout(graph2)
        for name in graph1.nodes:
            assert (
                graph1.nodes[name].properties["node_pos_x"]
                == graph2.nodes[name].properties["node_pos_x"]
            )
            assert (
                graph1.nodes[name].properties["node_pos_y"]
                == graph2.nodes[name].properties["node_pos_y"]
            )


# ===========================================================================
# node_discovery.py  (fallback / no-Unreal path)
# ===========================================================================

class TestNodeDiscovery:
    def test_returns_fallback_when_unreal_unavailable(self):
        fallback = {"Multiply": object(), "Add": object()}
        result = discover_material_nodes(fallback=fallback)
        # Without real Unreal, should return the fallback unchanged.
        assert result == fallback

    def test_empty_fallback_returns_empty_dict(self):
        result = discover_material_nodes(fallback={})
        assert isinstance(result, dict)

    def test_none_fallback_returns_empty_dict(self):
        result = discover_material_nodes(fallback=None)
        assert isinstance(result, dict)

    def test_get_expression_class_found(self):
        sentinel = object()
        node_map = {"TextureSample": sentinel}
        cls = get_expression_class("TextureSample", node_map)
        assert cls is sentinel

    def test_get_expression_class_not_found_raises(self):
        node_map = {"TextureSample": object()}
        with pytest.raises(ValueError, match="Unknown node type 'Multiply'"):
            get_expression_class("Multiply", node_map)

    def test_get_expression_class_error_lists_available(self):
        node_map = {"A": object(), "B": object()}
        with pytest.raises(ValueError, match="A"):
            get_expression_class("Missing", node_map)


# ===========================================================================
# graph_parser.py – MaterialInstance fields
# ===========================================================================

class TestParseYamlMaterialInstance:
    def test_material_instance_parsed(self):
        path = _write_yaml(
            """
asset:
  class: MaterialInstance
  name: MI_Metal
  path: /Game/Generated
  parent: /Game/Materials/M_Master

parameters:
  Roughness: 0.2
  TintColor: [1.0, 0.0, 0.0]
"""
        )
        try:
            from graph_parser import parse_yaml  # noqa: PLC0415

            graph = parse_yaml(path)
            assert graph.class_name == "MaterialInstance"
            assert graph.parent == "/Game/Materials/M_Master"
            assert graph.parameters["Roughness"] == pytest.approx(0.2)
            assert graph.parameters["TintColor"] == [1.0, 0.0, 0.0]
        finally:
            os.unlink(path)

    def test_material_without_parent_defaults_empty(self):
        path = _write_yaml(
            """
asset:
  class: Material
  name: M_Test
  path: /Game/Generated

nodes:
  c:
    type: Constant
    value: 0.5

outputs:
  Roughness: c
"""
        )
        try:
            from graph_parser import parse_yaml  # noqa: PLC0415

            graph = parse_yaml(path)
            assert graph.parent == ""
            assert graph.parameters == {}
        finally:
            os.unlink(path)

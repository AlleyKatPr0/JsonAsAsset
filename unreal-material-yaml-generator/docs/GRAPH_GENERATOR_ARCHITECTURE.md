# Graph Generator Architecture

## Overview

The Universal Unreal Graph Generator (Material version) converts human-readable
YAML files into fully wired Unreal Engine `Material` assets. The system is split
into three clearly separated layers:

```
 ┌─────────────────────┐
 │   YAML source file  │  Human-readable graph description
 └────────┬────────────┘
          │  graph_parser.py
          ▼
 ┌─────────────────────┐
 │  Intermediate Graph │  Language & engine agnostic data model
 │       Model         │  (graph_model.py)
 └────────┬────────────┘
          │  unreal_material_backend.py
          ▼
 ┌─────────────────────┐
 │  Unreal Asset       │  MaterialFactoryNew + MaterialEditingLibrary
 │  Factory            │
 └─────────────────────┘
```

This separation means the YAML layer and graph model can be developed and
tested without an Unreal Engine installation.

---

## Human Readable Source

Material graphs are described as YAML files with four top-level sections:

| Section       | Required | Purpose |
|---------------|----------|---------|
| `asset`       | Yes      | Asset metadata (class, name, path) |
| `nodes`       | Yes      | Expression nodes to create |
| `connections` | No       | Directed edges between node pins |
| `outputs`     | Yes      | Mapping of material properties to node outputs |

### YAML Schema

```yaml
asset:
  class: Material          # Unreal asset class (always Material for now)
  name: M_Example          # Asset name inside the Content Browser
  path: /Game/Generated    # Content Browser directory

nodes:
  <node_name>:             # Unique identifier for this node
    type: <ExpressionType> # See supported types below
    <property>: <value>    # Type-specific properties (texture, value, vector, …)

connections:               # Optional – omit if no explicit wiring is needed
  - <src_node>[.<pin>] -> <dst_node>[.<pin>]

outputs:
  <MaterialProperty>: <node>[.<pin>]
```

#### Supported Node Types

| YAML type                | Unreal expression class                             |
|--------------------------|-----------------------------------------------------|
| `TextureSample`          | `MaterialExpressionTextureSample`                   |
| `Multiply`               | `MaterialExpressionMultiply`                        |
| `Add`                    | `MaterialExpressionAdd`                             |
| `Constant`               | `MaterialExpressionConstant`                        |
| `Constant3Vector`        | `MaterialExpressionConstant3Vector`                 |
| `ScalarParameter`        | `MaterialExpressionScalarParameter`                 |
| `VectorParameter`        | `MaterialExpressionVectorParameter`                 |
| `FunctionCall`           | `MaterialExpressionMaterialFunctionCall`            |
| `StaticSwitchParameter`  | `MaterialExpressionStaticSwitchParameter`           |
| `ComponentMask`          | `MaterialExpressionComponentMask`                   |
| `TextureCoordinate`      | `MaterialExpressionTextureCoordinate`               |

#### Supported Material Output Properties

`BaseColor`, `Normal`, `Roughness`, `Metallic`, `Emissive`, `Opacity`

---

## Intermediate Graph Model

`tools/graph_model.py` defines four plain Python dataclasses:

### `GraphAsset`

Top-level container.

| Field          | Type                        | Description |
|----------------|-----------------------------|-------------|
| `class_name`   | `str`                       | Unreal asset class |
| `asset_name`   | `str`                       | Asset name |
| `asset_path`   | `str`                       | Content Browser path |
| `nodes`        | `dict[str, GraphNode]`      | All expression nodes |
| `connections`  | `list[GraphConnection]`     | Node-to-node wiring |
| `outputs`      | `list[GraphOutput]`         | Material property bindings |

### `GraphNode`

Represents a single expression node.

| Field        | Type             | Description |
|--------------|------------------|-------------|
| `name`       | `str`            | Unique name |
| `type`       | `str`            | YAML type string |
| `properties` | `dict[str, Any]` | Type-specific properties |

### `GraphConnection`

A directed edge between two pin references.

| Field         | Type  | Description |
|---------------|-------|-------------|
| `source`      | `str` | `node[.pin]` reference |
| `destination` | `str` | `node[.pin]` reference |

### `GraphOutput`

Binds a node to a named material property.

| Field      | Type  | Description |
|------------|-------|-------------|
| `property` | `str` | Material property name |
| `source`   | `str` | `node[.pin]` reference |

---

## Unreal Asset Factory

`tools/unreal_material_backend.py` implements asset creation:

```python
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
factory = unreal.MaterialFactoryNew()
material = asset_tools.create_asset(
    asset_name=asset_name,
    package_path=asset_path,
    asset_class=unreal.Material,
    factory=factory,
)
```

This creates a blank `Material` asset in the Content Browser before any nodes
are added.

---

## Node Creation

For each `GraphNode` in the graph:

```python
expression = unreal.MaterialEditingLibrary.create_material_expression(
    material,
    expr_class,   # e.g. unreal.MaterialExpressionTextureSample
    node_pos_x=0,
    node_pos_y=0,
)
```

After creation, node properties are applied via
`expression.set_editor_property(key, value)`.

A `node_registry` dictionary maps `node_name → expression` for use during
connection wiring and output binding.

---

## Connection Wiring

Each `GraphConnection` is translated into:

```python
unreal.MaterialEditingLibrary.connect_material_expressions(
    from_expression,  # source node object
    from_output_name, # source pin name (may be empty string for default)
    to_expression,    # destination node object
    to_input_name,    # destination pin name (may be empty string for default)
)
```

Pin references in the YAML follow the format `node_name.pin_name`; missing
pin names default to the empty string which Unreal treats as the primary
output/input.

---

## Output Binding

Each `GraphOutput` is bound with:

```python
unreal.MaterialEditingLibrary.connect_material_property(
    from_expression,  # source node object
    from_output_name, # source pin name
    material_property # e.g. unreal.MaterialProperty.MP_BASE_COLOR
)
```

The mapping from YAML property name to `unreal.MaterialProperty` is defined
in `OUTPUT_PROPERTY_MAP` inside the backend module.

---

## Future Extensions

The following extensions are planned but not yet implemented:

- **Blueprint Graph Support** – Extend the pipeline to generate Blueprint
  event graphs from YAML.
- **Niagara Graph Support** – Extend the pipeline to generate Niagara
  particle-system graphs from YAML.

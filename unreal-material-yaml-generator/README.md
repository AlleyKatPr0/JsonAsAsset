# unreal-material-yaml-generator

A **Universal Unreal Graph Generator** (Material version) that converts
human-readable YAML files into fully wired Unreal Engine `Material` assets
using the Unreal Python API.

---

## Table of Contents

- [Project Purpose](#project-purpose)
- [Architecture](#architecture)
- [Pipeline Diagram](#pipeline-diagram)
- [Repository Structure](#repository-structure)
- [YAML Schema](#yaml-schema)
- [How to Run Inside Unreal Engine](#how-to-run-inside-unreal-engine)
- [Examples](#examples)

---

## Project Purpose

Writing material graphs by hand inside Unreal Engine is repetitive and
difficult to version-control. This project lets you describe a material graph
in a plain YAML file and then generate the corresponding Unreal asset
automatically – ideal for procedural workflows, CI pipelines, and asset
porting tools.

---

## Architecture

The system is split into three clearly separated layers:

| Layer | Module | Responsibility |
|-------|--------|----------------|
| YAML Source | *(your `.yaml` files)* | Human-readable graph description |
| Intermediate Graph Model | `tools/graph_model.py` | Engine-agnostic data model |
| YAML Parser | `tools/graph_parser.py` | Converts YAML → graph model |
| Unreal Backend | `tools/unreal_material_backend.py` | Creates assets via Unreal Python API |
| Entry Script | `tools/material_builder.py` | Orchestrates the full pipeline |

See [`docs/GRAPH_GENERATOR_ARCHITECTURE.md`](docs/GRAPH_GENERATOR_ARCHITECTURE.md)
for a detailed description of each layer.

---

## Pipeline Diagram

```
 ┌──────────────────┐
 │  YAML file       │  Write your material graph in plain text
 └────────┬─────────┘
          │  graph_parser.py  (parse_yaml)
          ▼
 ┌──────────────────┐
 │  Graph Model     │  GraphAsset / GraphNode / GraphConnection / GraphOutput
 │  (in-memory)     │
 └────────┬─────────┘
          │  unreal_material_backend.py  (build_from_graph)
          ▼
 ┌──────────────────────────────────────┐
 │  Unreal Asset Factory                │
 │  AssetToolsHelpers + MaterialFactory │  → creates Material asset
 ├──────────────────────────────────────┤
 │  Node Creation                       │
 │  MaterialEditingLibrary              │  → creates expression nodes
 ├──────────────────────────────────────┤
 │  Node Wiring                         │
 │  connect_material_expressions        │  → wires pin-to-pin connections
 ├──────────────────────────────────────┤
 │  Output Binding                      │
 │  connect_material_property           │  → binds BaseColor, Normal, …
 ├──────────────────────────────────────┤
 │  Save Material                       │
 │  recompile_material + save_asset     │  → persists to Content Browser
 └──────────────────────────────────────┘
```

---

## Repository Structure

```
unreal-material-yaml-generator/
│
├── docs/
│   └── GRAPH_GENERATOR_ARCHITECTURE.md   Detailed architecture description
│
├── examples/
│   └── materials/
│       ├── simple_texture.yaml           Single texture → BaseColor
│       ├── pbr_material.yaml             Full PBR material
│       └── multiply_example.yaml         Texture × tint color
│
├── tools/
│   ├── graph_model.py                    Intermediate graph dataclasses
│   ├── graph_parser.py                   YAML → GraphAsset parser
│   ├── unreal_material_backend.py        Unreal Python API integration
│   └── material_builder.py              Entry script / public API
│
├── README.md
└── requirements.txt
```

---

## YAML Schema

```yaml
asset:
  class: Material          # Unreal asset class (always Material for now)
  name: M_Example          # Asset name in the Content Browser
  path: /Game/Generated    # Content Browser directory

nodes:
  <node_name>:             # Unique identifier used in connections/outputs
    type: <ExpressionType> # See table below
    <property>: <value>    # Type-specific properties

connections:               # Optional
  - <src_node>[.<pin>] -> <dst_node>[.<pin>]

outputs:
  <MaterialProperty>: <node>[.<pin>]
```

### Supported Node Types

| YAML `type`        | Unreal Expression Class                     |
|--------------------|---------------------------------------------|
| `TextureSample`    | `MaterialExpressionTextureSample`           |
| `Multiply`         | `MaterialExpressionMultiply`                |
| `Add`              | `MaterialExpressionAdd`                     |
| `Constant`         | `MaterialExpressionConstant`                |
| `Constant3Vector`  | `MaterialExpressionConstant3Vector`         |
| `ScalarParameter`  | `MaterialExpressionScalarParameter`         |
| `VectorParameter`  | `MaterialExpressionVectorParameter`         |

### Node Properties

| Property         | Applicable Types          | Description |
|------------------|---------------------------|-------------|
| `texture`        | `TextureSample`           | Content Browser path to a texture asset |
| `value`          | `Constant`, `ScalarParameter` | Float value |
| `vector`         | `Constant3Vector`, `VectorParameter` | `[r, g, b]` or `[r, g, b, a]` |
| `parameter_name` | `ScalarParameter`, `VectorParameter` | Parameter name exposed on instances |
| `default_value`  | `ScalarParameter`         | Default parameter value |

### Supported Material Output Properties

`BaseColor`, `Normal`, `Roughness`, `Metallic`, `Emissive`, `Opacity`

---

## How to Run Inside Unreal Engine

### Prerequisites

1. Unreal Engine 5.x with the **Python Editor Script Plugin** enabled.
2. PyYAML available to Unreal's bundled Python interpreter:

   ```bash
   # From Unreal's bundled pip (path varies by platform)
   UE_Python/python -m pip install PyYAML
   ```

   Alternatively, install PyYAML system-wide if Unreal is configured to use
   the system Python.

### Running a build

Open the **Output Log** inside Unreal Editor, switch the input mode to
**Python**, then run:

```python
import sys
sys.path.append("/absolute/path/to/unreal-material-yaml-generator/tools")

import material_builder
material_builder.build_material("/absolute/path/to/examples/materials/simple_texture.yaml")
```

After a successful run the generated material appears at the `path` specified
in the YAML file inside the **Content Browser**.

### Running from the Unreal Command Line

```bash
UnrealEditor MyProject.uproject -ExecutePythonScript="/path/to/tools/material_builder.py /path/to/material.yaml"
```

---

## Examples

### Simple Texture (`examples/materials/simple_texture.yaml`)

Creates a material that samples a single texture and uses its RGB output as
`BaseColor`.

```yaml
asset:
  class: Material
  name: M_SimpleTexture
  path: /Game/Generated

nodes:
  base_tex:
    type: TextureSample
    texture: /Game/Textures/T_BaseColor

outputs:
  BaseColor: base_tex.RGB
```

### PBR Material (`examples/materials/pbr_material.yaml`)

Full physically-based material with albedo, normal, roughness, and metallic
channels.

```yaml
asset:
  class: Material
  name: M_PBRExample
  path: /Game/Generated

nodes:
  base_tex:
    type: TextureSample
    texture: /Game/Textures/T_BaseColor
  normal_tex:
    type: TextureSample
    texture: /Game/Textures/T_Normal
  roughness:
    type: Constant
    value: 0.6
  metallic:
    type: Constant
    value: 1.0

outputs:
  BaseColor: base_tex.RGB
  Normal: normal_tex.RGB
  Roughness: roughness
  Metallic: metallic
```

### Multiply Example (`examples/materials/multiply_example.yaml`)

Multiplies a texture by a solid tint colour before sending the result to
`BaseColor`.

```yaml
asset:
  class: Material
  name: M_MultiplyExample
  path: /Game/Generated

nodes:
  base_tex:
    type: TextureSample
    texture: /Game/Textures/T_BaseColor
  tint_color:
    type: Constant3Vector
    vector: [0.8, 0.4, 0.2]
  multiply_1:
    type: Multiply

connections:
  - base_tex.RGB -> multiply_1.A
  - tint_color.RGB -> multiply_1.B

outputs:
  BaseColor: multiply_1
```

---

## Future Extensions

See [`docs/GRAPH_GENERATOR_ARCHITECTURE.md`](docs/GRAPH_GENERATOR_ARCHITECTURE.md#future-extensions)
for a full list of planned features, including Material Functions, Static
Switches, Component Masks, Texture Coordinates, Blueprint graphs, and Niagara
graphs.

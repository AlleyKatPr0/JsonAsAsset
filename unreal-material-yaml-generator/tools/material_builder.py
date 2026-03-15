"""
material_builder.py

Entry script for the Universal Unreal Material Graph Generator.

Run this module inside Unreal Engine Python to generate a material asset
from a YAML description file.

Usage inside Unreal Engine Python console
-----------------------------------------
>>> import sys
>>> sys.path.append("path/to/unreal-material-yaml-generator/tools")
>>> import material_builder
>>> material_builder.build_material("path/to/material.yaml")
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the tools directory is on sys.path so relative imports work whether
# the script is launched from inside or outside Unreal's Python interpreter.
# ---------------------------------------------------------------------------
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from graph_model import GraphAsset  # noqa: E402  (after sys.path setup)
from graph_parser import parse_yaml  # noqa: E402
from unreal_material_backend import build_from_graph  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="[MaterialBuilder] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def build_material(yaml_path: str) -> None:
    """Generate an Unreal Engine material asset from a YAML file.

    This function orchestrates the full pipeline:

    1. Load the YAML file from *yaml_path*.
    2. Parse it into an intermediate :class:`~graph_model.GraphAsset`.
    3. Pass the graph to the Unreal backend which:

       a. Creates the ``Material`` asset.
       b. Creates every expression node.
       c. Wires node-to-node connections.
       d. Binds the material outputs.
       e. Recompiles the material.
       f. Saves the asset to disk.

    Parameters
    ----------
    yaml_path:
        Absolute or relative path to the YAML material description file.

    Examples
    --------
    Run from the Unreal Python console::

        import material_builder
        material_builder.build_material("/path/to/simple_texture.yaml")
    """
    path = Path(yaml_path)
    logger.info("=== Starting material build from: %s ===", path)

    # Step 1 & 2 – Load YAML and parse into the graph model.
    logger.info("Parsing YAML graph description...")
    graph: GraphAsset = parse_yaml(path)
    logger.info(
        "Parsed graph: asset=%r, nodes=%d, connections=%d, outputs=%d",
        graph.asset_name,
        len(graph.nodes),
        len(graph.connections),
        len(graph.outputs),
    )

    # Step 3 – Hand off to the Unreal backend.
    logger.info("Creating Unreal material asset...")
    build_from_graph(graph)

    logger.info("=== Material build complete: %s/%s ===", graph.asset_path, graph.asset_name)


# ---------------------------------------------------------------------------
# Allow the module to be run directly for quick testing outside Unreal.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python material_builder.py <path_to_yaml>")
        sys.exit(1)
    build_material(sys.argv[1])

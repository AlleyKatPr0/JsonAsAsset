"""
cli.py

Command-line interface for the Universal Unreal Graph Compiler.

This script is the single entry point for all CLI operations.  It must be
run from within an Unreal Engine Python environment for the ``build`` and
``build-dir`` commands (which create Unreal assets).  The ``visualize``
command does **not** require Unreal and can be run from any Python
environment that has ``graphviz`` installed.

Commands
--------
build <yaml_path>
    Build a single material from a YAML file.

    Example::

        python cli.py build ./materials/M_Metal.yaml

build-dir <directory_path>
    Recursively build all ``*.yaml`` files in a directory.

    Example::

        python cli.py build-dir ./materials

visualize <yaml_or_json_path> [--output <path>] [--no-png]
    Render a graph as a DOT file (and optionally a PNG image).

    Example::

        python cli.py visualize ./materials/M_Metal.yaml
        python cli.py visualize ./materials/M_Metal.yaml --output /tmp/graph
        python cli.py visualize ./materials/M_Metal.json --no-png
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the tools directory is on sys.path so sibling modules are importable.
# ---------------------------------------------------------------------------
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="[CLI] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _cmd_build(args: argparse.Namespace) -> int:
    """Handle the ``build`` command."""
    from material_builder import build_material  # noqa: PLC0415

    try:
        build_material(args.yaml_path)
        return 0
    except Exception as exc:  # noqa: BLE001
        logger.error("Build failed: %s", exc)
        return 1


def _cmd_build_dir(args: argparse.Namespace) -> int:
    """Handle the ``build-dir`` command."""
    from material_builder import build_directory  # noqa: PLC0415

    try:
        results = build_directory(args.directory_path)
    except NotADirectoryError as exc:
        logger.error("%s", exc)
        return 1

    failures = {p: msg for p, msg in results.items() if msg != "ok"}
    if failures:
        for path, msg in failures.items():
            logger.error("FAILED: %s – %s", path, msg)
        return 1
    return 0


def _cmd_visualize(args: argparse.Namespace) -> int:
    """Handle the ``visualize`` command."""
    source = Path(args.source)
    if not source.exists():
        logger.error("Source file not found: %s", source)
        return 1

    # Determine output path: default to source stem alongside source file.
    output_path = args.output or str(source.with_suffix(""))

    # Parse the source file into a GraphAsset.
    try:
        if source.suffix.lower() == ".json":
            from json_graph_parser import parse_json  # noqa: PLC0415

            graph = parse_json(source)
        else:
            from graph_parser import parse_yaml  # noqa: PLC0415

            graph = parse_yaml(source)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to parse '%s': %s", source, exc)
        return 1

    # Render the graph.
    try:
        from graph_visualizer import visualize_graph  # noqa: PLC0415

        dot_path = visualize_graph(
            graph,
            output_path=output_path,
            render_png=not args.no_png,
        )
        logger.info("DOT file: %s", dot_path)
        if not args.no_png:
            png_path = dot_path.with_suffix(".png")
            if png_path.exists():
                logger.info("PNG file: %s", png_path)
    except ImportError as exc:
        logger.error("%s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.error("Visualisation failed: %s", exc)
        return 1

    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Universal Unreal Graph Compiler – CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- build ---------------------------------------------------------------
    p_build = sub.add_parser(
        "build",
        help="Build a single material from a YAML file (requires Unreal).",
    )
    p_build.add_argument("yaml_path", help="Path to the .yaml material file.")

    # -- build-dir -----------------------------------------------------------
    p_build_dir = sub.add_parser(
        "build-dir",
        help="Recursively build all *.yaml files in a directory (requires Unreal).",
    )
    p_build_dir.add_argument(
        "directory_path", help="Path to the directory to scan."
    )

    # -- visualize -----------------------------------------------------------
    p_vis = sub.add_parser(
        "visualize",
        help="Render a graph as DOT/PNG (does not require Unreal).",
    )
    p_vis.add_argument(
        "source",
        help="Path to a .yaml or .json graph file.",
    )
    p_vis.add_argument(
        "--output",
        default=None,
        metavar="PATH",
        help=(
            "Output path without extension.  Defaults to the source file "
            "path without its extension."
        ),
    )
    p_vis.add_argument(
        "--no-png",
        action="store_true",
        default=False,
        help="Only write the DOT file; skip PNG rendering.",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Parse *argv* and dispatch to the appropriate command handler.

    Returns the exit code (0 = success, non-zero = failure).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    dispatch = {
        "build": _cmd_build,
        "build-dir": _cmd_build_dir,
        "visualize": _cmd_visualize,
    }
    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())

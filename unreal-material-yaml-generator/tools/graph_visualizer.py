"""
graph_visualizer.py

Generates a GraphViz DOT representation and optional PNG image from a
:class:`~graph_model.GraphAsset`.

Requires the ``graphviz`` Python package (``pip install graphviz``) and
the ``graphviz`` system binaries (``dot`` command) for PNG rendering.

Usage
-----
From Python::

    from graph_visualizer import visualize_graph
    visualize_graph(graph, output_path="mymaterial")
    # Produces: mymaterial.dot  and  mymaterial.png

From the CLI (via ``tools/cli.py``)::

    python cli.py visualize mymaterial.yaml
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from graph_model import GraphAsset

logger = logging.getLogger(__name__)


def visualize_graph(
    graph: GraphAsset,
    output_path: str = "material_graph",
    render_png: bool = True,
    view: bool = False,
) -> Path:
    """Render *graph* as a GraphViz DOT file (and optionally a PNG image).

    Parameters
    ----------
    graph:
        The material graph to visualise.
    output_path:
        Destination path **without** extension.  A ``.dot`` file and
        (optionally) a ``.png`` file are written to this location.
    render_png:
        When *True* (default) the GraphViz ``dot`` command is invoked to
        produce a PNG image alongside the DOT file.  Set to *False* to only
        produce the DOT source.
    view:
        When *True* the rendered image is opened with the system viewer
        immediately after rendering.  Requires *render_png=True*.

    Returns
    -------
    Path
        Path to the DOT file that was written.

    Raises
    ------
    ImportError
        If the ``graphviz`` Python package is not installed.
    graphviz.ExecutableNotFound
        If ``render_png=True`` but the ``dot`` executable is not on ``PATH``.
    """
    try:
        import graphviz  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "The 'graphviz' package is required for graph visualisation. "
            "Install it with: pip install graphviz"
        ) from exc

    dot = graphviz.Digraph(
        name=graph.asset_name,
        comment=f"{graph.class_name}: {graph.asset_path}/{graph.asset_name}",
    )
    dot.attr(rankdir="LR", fontname="Helvetica", fontsize="10")
    dot.attr("node", shape="box", style="filled", fillcolor="#ddeeff",
             fontname="Helvetica", fontsize="9")
    dot.attr("edge", fontname="Helvetica", fontsize="8")

    # -- nodes ---------------------------------------------------------------
    for node_name, node in graph.nodes.items():
        label = f"{node_name}\\n({node.type})"
        # Highlight Substrate nodes.
        if node.type.startswith("Substrate"):
            dot.node(node_name, label=label, fillcolor="#ffe0cc")
        else:
            dot.node(node_name, label=label)

    # -- connections ---------------------------------------------------------
    for conn in graph.connections:
        src_node = conn.source.split(".", maxsplit=1)[0]
        dst_node = conn.destination.split(".", maxsplit=1)[0]
        src_pin = conn.source.split(".", maxsplit=1)[1] if "." in conn.source else ""
        dst_pin = (
            conn.destination.split(".", maxsplit=1)[1]
            if "." in conn.destination
            else ""
        )
        edge_label = ""
        if src_pin and dst_pin:
            edge_label = f"{src_pin}→{dst_pin}"
        elif src_pin:
            edge_label = src_pin
        elif dst_pin:
            edge_label = dst_pin
        dot.edge(src_node, dst_node, label=edge_label)

    # -- outputs -------------------------------------------------------------
    # Create a virtual "Output" node.
    if graph.outputs:
        dot.node("__OUTPUT__", label="Material\\nOutputs", shape="ellipse",
                 fillcolor="#ccffcc")
        for out in graph.outputs:
            src_node = out.source.split(".", maxsplit=1)[0]
            src_pin = out.source.split(".", maxsplit=1)[1] if "." in out.source else ""
            edge_label = f"{src_pin}→{out.property}" if src_pin else out.property
            dot.edge(src_node, "__OUTPUT__", label=edge_label)

    # -- write DOT file ------------------------------------------------------
    out_path = Path(output_path)
    dot_path = out_path.with_suffix(".dot")
    dot_path.write_text(dot.source, encoding="utf-8")
    logger.info("DOT file written: %s", dot_path)

    # -- render PNG ----------------------------------------------------------
    if render_png:
        try:
            rendered = dot.render(
                filename=str(out_path),
                format="png",
                cleanup=False,
                view=view,
            )
            png_path = Path(rendered)
            logger.info("PNG rendered: %s", png_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "PNG rendering failed (%s). DOT file is still available at %s.",
                exc,
                dot_path,
            )

    return dot_path

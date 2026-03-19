"""Optional PyODM client for post-flight orthophoto/DEM validation."""

from __future__ import annotations

from typing import Any

try:
    from pyodm import Node
    HAS_PYODM = True
except ImportError:
    HAS_PYODM = False


def run_odm_task(
    host: str = "localhost",
    port: int = 3000,
    images: list[str] | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run ODM task on NodeODM for orthophoto generation and GSD validation.

    Requires NodeODM running (e.g. docker run -p 3000:3000 opendronemap/nodeodm).
    Install with: pip install gorzen[odm]
    """
    if not HAS_PYODM:
        return {"error": "PyODM not installed. Install with: pip install gorzen[odm]"}

    node = Node(host, port)
    opts = options or {}
    if "dsm" not in opts:
        opts["dsm"] = True
    task = node.create_task(images or [], opts)
    return {
        "uuid": task.uuid,
        "status": task.status(),
    }

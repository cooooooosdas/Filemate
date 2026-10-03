"""Keep the FileMate Vite development server attached to a stable process tree."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def main() -> int:
    """Run Vite with the repository-local entry point."""
    project_root = Path(__file__).resolve().parents[1]
    web_root = project_root / "filemate" / "web"
    vite_entry = web_root / "node_modules" / "vite" / "bin" / "vite.js"
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js was not found on PATH")
    if not vite_entry.is_file():
        raise FileNotFoundError(f"Vite entry was not found: {vite_entry}")
    return subprocess.call(
        [node, str(vite_entry), "--host", "127.0.0.1"],
        cwd=web_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())

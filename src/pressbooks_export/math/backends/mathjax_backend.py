from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .base import MathBackend, MathConversionError


class MathJaxNodeBackend(MathBackend):
    """MathJax backend that mirrors the Pressbooks webbook rendering engine."""

    def __init__(self, script_path: Path | None = None, node_binary: str = "node") -> None:
        self.script_path = script_path or Path(__file__).with_name("node").joinpath("mathjax_convert.mjs")
        self.node_binary = node_binary

    def convert(self, latex: str, *, display: bool = False) -> str:
        if shutil.which(self.node_binary) is None:
            raise MathConversionError("Node.js is required for the MathJax backend.")

        payload = json.dumps({"latex": latex, "display": display})
        try:
            completed = subprocess.run(
                [self.node_binary, str(self.script_path)],
                check=True,
                text=True,
                input=payload,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:  # pragma: no cover - subprocess wrapper
            raise MathConversionError(exc.stderr.strip() or "MathJax conversion failed") from exc

        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
            raise MathConversionError("MathJax backend returned invalid JSON") from exc
        if result.get("error"):
            raise MathConversionError(result["error"])
        return str(result["mathml"])

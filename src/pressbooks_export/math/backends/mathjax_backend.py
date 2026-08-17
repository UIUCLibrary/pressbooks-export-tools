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

    def _check_node(self) -> None:
        if shutil.which(self.node_binary) is None:
            raise MathConversionError("Node.js is required for the MathJax backend.")

    def _run_script(self, payload: str) -> str:
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
        return completed.stdout

    def convert(self, latex: str, *, display: bool = False) -> str:
        """Convert a single LaTeX expression to MathML."""
        self._check_node()
        payload = json.dumps({"latex": latex, "display": display})
        stdout = self._run_script(payload)
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
            raise MathConversionError("MathJax backend returned invalid JSON") from exc
        if result.get("error"):
            raise MathConversionError(result["error"])
        return str(result["mathml"])

    def convert_batch(self, items: list[tuple[str, bool]]) -> list[str | MathConversionError]:
        """Convert a list of (latex, display) pairs to MathML in a single Node.js call.

        Returns a list of the same length as *items*.  Each entry is either a
        MathML string (success) or a :class:`MathConversionError` instance
        (per-equation failure).  The caller decides how to handle failures.
        """
        self._check_node()
        payload = json.dumps([{"latex": latex, "display": display} for latex, display in items])
        stdout = self._run_script(payload)
        try:
            results = json.loads(stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
            raise MathConversionError("MathJax backend returned invalid JSON") from exc
        if not isinstance(results, list):  # pragma: no cover - defensive guard
            raise MathConversionError("MathJax batch mode expected a JSON array")
        out: list[str | MathConversionError] = []
        for item in results:
            if item.get("error"):
                out.append(MathConversionError(item["error"]))
            else:
                out.append(str(item["mathml"]))
        return out

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class SpeechConversionError(RuntimeError):
    """Raised when the SRE backend cannot produce a spoken description."""


class SreNodeBackend:
    """Convert LaTeX to plain-English speech via Speech Rule Engine (Node.js).

    The backend shells out to ``sre_convert.mjs``, which runs MathJax
    (LaTeX → MathML) followed by Speech Rule Engine (MathML → spoken English)
    in a single Node.js process.

    Requirements:
        - Node.js (``node`` on PATH)
        - ``npm install`` run inside the ``node/`` sibling directory
    """

    def __init__(
        self,
        script_path: Path | None = None,
        node_binary: str = "node",
    ) -> None:
        self.script_path = script_path or Path(__file__).with_name("node") / "sre_convert.mjs"
        self.node_binary = node_binary

    def to_speech(self, latex: str, *, display: bool = False) -> str:
        """Return a plain-English spoken description of *latex*.

        Parameters
        ----------
        latex:
            A LaTeX math expression (without surrounding ``$`` or ``\\[``).
        display:
            *True* for a block (display-mode) equation, *False* for inline.

        Raises
        ------
        SpeechConversionError
            If Node.js is not available or the conversion fails.
        """
        if shutil.which(self.node_binary) is None:
            raise SpeechConversionError(
                "Node.js is required for the SRE speech backend. "
                "Install Node.js and run `npm install` in the node/ directory."
            )

        payload = json.dumps({"latex": latex, "display": display})
        try:
            completed = subprocess.run(
                [self.node_binary, str(self.script_path)],
                check=True,
                text=True,
                input=payload,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            raise SpeechConversionError(
                exc.stderr.strip() or "SRE conversion failed"
            ) from exc

        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise SpeechConversionError("SRE backend returned invalid JSON") from exc

        if result.get("error"):
            raise SpeechConversionError(result["error"])
        return str(result["speech"])

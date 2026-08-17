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

    def _check_node(self) -> None:
        """Raise :class:`SpeechConversionError` if Node.js is not on PATH."""
        if shutil.which(self.node_binary) is None:
            raise SpeechConversionError(
                "Node.js is required for the SRE speech backend. "
                "Install Node.js and run `npm install` in the node/ directory."
            )

    def _run_script(self, payload: str) -> str:
        """Run the Node script with *payload* on stdin and return stdout."""
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
        return completed.stdout

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
        self._check_node()

        payload = json.dumps({"latex": latex, "display": display})
        stdout = self._run_script(payload)

        try:
            result = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise SpeechConversionError("SRE backend returned invalid JSON") from exc

        if result.get("error"):
            raise SpeechConversionError(result["error"])
        return str(result["speech"])

    def to_speech_batch(self, items: list[tuple[str, bool]]) -> list[str]:
        """Convert many LaTeX expressions in a single Node.js process.

        Sends all *items* to ``sre_convert.mjs`` in one subprocess call,
        paying the Node.js / MathJax / SRE startup cost only once.

        Parameters
        ----------
        items:
            Sequence of ``(latex, display)`` pairs.

        Returns
        -------
        list[str]
            Speech description for each input item, in the same order.
            Items whose per-item conversion fails are returned as empty
            strings; a :class:`SpeechConversionError` is raised after
            collecting all results so that the caller learns which items
            failed.

        Raises
        ------
        SpeechConversionError
            If Node.js is unavailable, the subprocess fails, the response
            cannot be parsed, or any individual item fails conversion.
        """
        self._check_node()

        if not items:
            return []

        payload = json.dumps(
            [{"latex": latex, "display": display} for latex, display in items]
        )
        stdout = self._run_script(payload)

        try:
            results = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise SpeechConversionError("SRE backend returned invalid JSON") from exc

        if not isinstance(results, list):
            raise SpeechConversionError(
                "SRE backend returned unexpected response (expected a JSON array)"
            )
        if len(results) != len(items):
            raise SpeechConversionError(
                f"SRE backend returned {len(results)} results for {len(items)} inputs"
            )

        speeches: list[str] = []
        errors: list[str] = []
        for result in results:
            if result.get("error"):
                speeches.append("")
                errors.append(result["error"])
            else:
                speeches.append(str(result.get("speech", "")))

        if errors:
            raise SpeechConversionError(
                f"{len(errors)} item(s) failed conversion: " + "; ".join(errors[:5])
            )

        return speeches

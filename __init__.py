"""
cli-code-format plugin — auto-format code blocks for CLI mode.

Wires one behaviour:

* ``transform_llm_output`` hook — scans the LLM's final response text for
  markdown fenced code blocks (```...```) and, when the platform is ``"cli"``,
  rewrites them into Hermes box-drawing format:

    ╭─ python ─────────────────────────────

      print("hello")

    ╰─────────────────────────────────────

  On gateway platforms (telegram, discord, etc.) the text is left untouched
  so native syntax highlighting and shaded backgrounds work normally.

  The first registered ``transform_llm_output`` plugin to return a string
  wins — this plugin returns None when not on CLI to yield to other plugins.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ── Box-drawing constants ──────────────────────────────────────────────────
TOP_RAIL_LEFT = "\u256d\u2500"  # ╭─
BOTTOM_RAIL_LEFT = "\u2570\u2500"  # ╰─
RAIL_CHAR = "\u2500"  # ─
BOX_WIDTH = 60

# ── Language → label mapping ────────────────────────────────────────────────
LANG_LABELS: dict[str, str] = {
    "python": "python",
    "py": "python",
    "bash": "bash",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
    "yaml": "yaml",
    "yml": "yaml",
    "json": "json",
    "toml": "toml",
    "ini": "config",
    "cfg": "config",
    "conf": "config",
    "diff": "diff",
    "patch": "diff",
    "git": "git",
    "javascript": "js",
    "js": "js",
    "typescript": "ts",
    "ts": "ts",
    "jsx": "jsx",
    "tsx": "tsx",
    "html": "html",
    "css": "css",
    "sql": "sql",
    "xml": "xml",
    "markdown": "md",
    "md": "md",
    "dockerfile": "docker",
    "docker": "docker",
    "go": "go",
    "rust": "rust",
    "rs": "rust",
    "ruby": "ruby",
    "rb": "ruby",
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "h": "c",
    "hpp": "cpp",
    "java": "java",
    "swift": "swift",
    "kotlin": "kotlin",
    "kt": "kotlin",
    "scala": "scala",
    "lua": "lua",
    "r": "r",
    "perl": "perl",
    "pl": "perl",
    "php": "php",
    "haskell": "haskell",
    "hs": "haskell",
    "elixir": "elixir",
    "ex": "elixir",
    "solidity": "solidity",
    "sol": "solidity",
    "graphql": "graphql",
    "gql": "graphql",
    "makefile": "make",
    "make": "make",
    "cmake": "cmake",
    "nginx": "nginx",
    "regex": "regex",
    "csv": "csv",
    "text": "output",
    "txt": "output",
    "output": "output",
    "stdout": "output",
    "stderr": "output",
    "console": "output",
    "log": "output",
    "copy": "copy",
}

DEFAULT_LABEL = "code"


def _rail(*, label: str | None = None) -> str:
    """Build a box-drawing rail line.

    Top rail: ``╭─ label ──...``  (no right corner)
    Bottom:   ``╰─────────...``   (no right corner)
    """
    if label:
        prefix = f"{TOP_RAIL_LEFT} {label} "
        return prefix + RAIL_CHAR * max(0, BOX_WIDTH - len(prefix))
    return BOTTOM_RAIL_LEFT + RAIL_CHAR * (BOX_WIDTH - 1)


def _format_code_block(code: str, lang: str | None) -> str:
    """Wrap ``code`` in box-drawing rails.

    The code is indented 2 spaces for breathing room.
    """
    label = LANG_LABELS.get((lang or "").strip().lower(), lang or DEFAULT_LABEL)
    lines = code.split("\n")
    # Strip a single leading/trailing blank line for clean spacing
    if lines and lines[0].strip() == "":
        lines = lines[1:]
    if lines and lines[-1].strip() == "":
        lines = lines[:-1]
    indented = "\n".join("  " + l for l in lines)
    return f"{_rail(label=label)}\n\n{indented}\n\n{_rail()}"


# Regex: ```lang? \n content \n ```
_FENCE_RE = re.compile(
    r"^```([^\n]*)\n(.*?)\n```$",
    re.MULTILINE | re.DOTALL,
)


def _transform_cli(text: str) -> str:
    """Replace all fenced code blocks with box-drawing format."""
    def _replacer(m: re.Match) -> str:
        lang = m.group(1).strip()
        code = m.group(2)
        return _format_code_block(code, lang if lang else None)
    return _FENCE_RE.sub(_replacer, text)


def _on_transform_llm_output(
    response_text: str,
    session_id: str | None = None,
    model: str | None = None,
    platform: str = "",
    **kwargs,
) -> str | None:
    """Hook callback — transform code blocks when on CLI, otherwise pass."""
    if platform != "cli":
        return None  # yield to other plugins; gateways keep standard markdown
    try:
        transformed = _transform_cli(response_text)
        if transformed != response_text:
            logger.debug(
                "Transformed code blocks for platform=%r (session=%s)",
                platform,
                session_id,
            )
            return transformed
    except Exception as exc:
        logger.warning("cli-code-format transform failed: %s", exc)
    return None


def register(ctx) -> None:
    """Register the transform_llm_output hook."""
    ctx.register_hook("transform_llm_output", _on_transform_llm_output)
    logger.info("cli-code-format plugin registered (CLI box-drawing for code blocks)")

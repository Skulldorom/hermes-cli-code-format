"""
cli-code-format plugin — auto-format code blocks for CLI mode.

Wires two strategies so box-drawing code blocks render in both streaming
and non-streaming paths:

1. ``_stream_delta`` monkey-patch — intercepts real-time token deltas
   and replaces markdown fenced code blocks with Hermes box-drawing
   format *before* the CLI strips/displays them.  Uses a stateful
   buffer so partial fences that span multiple deltas are handled
   correctly.

2. ``transform_llm_output`` hook — fallback for the Rich Panel
   (non-streaming) path.  Scans the final LLM response, transforms
   any remaining fence blocks the stream patch may have missed.


Output format (both paths):

    ╭─ python ─────────────────────────────

      print("hello")

    ╰─────────────────────────────────────

On gateway platforms the text is left untouched so native syntax
highlighting and shaded backgrounds work normally.
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
    "python": "python", "py": "python",
    "bash": "bash", "sh": "bash", "shell": "bash", "zsh": "bash",
    "yaml": "yaml", "yml": "yaml",
    "json": "json", "toml": "toml",
    "ini": "config", "cfg": "config", "conf": "config",
    "diff": "diff", "patch": "diff",
    "git": "git",
    "javascript": "js", "js": "js",
    "typescript": "ts", "ts": "ts",
    "jsx": "jsx", "tsx": "tsx",
    "html": "html", "css": "css", "sql": "sql",
    "xml": "xml",
    "markdown": "md", "md": "md",
    "dockerfile": "docker", "docker": "docker",
    "go": "go", "rust": "rust", "rs": "rust",
    "ruby": "ruby", "rb": "ruby",
    "c": "c", "cpp": "cpp", "c++": "cpp", "h": "c", "hpp": "cpp",
    "java": "java", "swift": "swift",
    "kotlin": "kotlin", "kt": "kotlin",
    "scala": "scala",
    "lua": "lua", "r": "r",
    "perl": "perl", "pl": "perl",
    "php": "php",
    "haskell": "haskell", "hs": "haskell",
    "elixir": "elixir", "ex": "elixir",
    "solidity": "solidity", "sol": "solidity",
    "graphql": "graphql", "gql": "graphql",
    "makefile": "make", "make": "make",
    "cmake": "cmake",
    "nginx": "nginx",
    "regex": "regex", "csv": "csv",
    "text": "output", "txt": "output", "output": "output",
    "stdout": "output", "stderr": "output", "console": "output", "log": "output",
    "copy": "copy",
}

DEFAULT_LABEL = "code"

# Cached original method reference (set in register())
_original_stream_delta = None

# Regex: ```lang? \n content \n ```
_FENCE_RE = re.compile(
    r"^```([^\n]*)\n(.*?)\n```$",
    re.MULTILINE | re.DOTALL,
)


def _rail(*, label: str | None = None) -> str:
    """Build a box-drawing rail line."""
    if label:
        prefix = f"{TOP_RAIL_LEFT} {label} "
        return prefix + RAIL_CHAR * max(0, BOX_WIDTH - len(prefix))
    return BOTTOM_RAIL_LEFT + RAIL_CHAR * (BOX_WIDTH - 2)


def _format_code_block(code: str, lang: str | None) -> str:
    """Wrap ``code`` in box-drawing rails."""
    label = LANG_LABELS.get((lang or "").strip().lower(), lang or DEFAULT_LABEL)
    lines = code.split("\n")
    if lines and lines[0].strip() == "":
        lines = lines[1:]
    if lines and lines[-1].strip() == "":
        lines = lines[:-1]
    indented = "\n".join("  " + l for l in lines)
    return f"{_rail(label=label)}\n\n{indented}\n\n{_rail()}"


def _transform_cli(text: str) -> str:
    """Replace all fenced code blocks with box-drawing format."""
    def _replacer(m: re.Match) -> str:
        lang = m.group(1).strip()
        code = m.group(2)
        return _format_code_block(code, lang if lang else None)
    return _FENCE_RE.sub(_replacer, text)


# ── Streaming intercept ────────────────────────────────────────────────────

def _patched_stream_delta(self, text) -> None:
    """Intercept ``HermesCLI._stream_delta`` to transform fences during streaming.

    Maintains per-instance fence state.  When a `` ``` `` opening fence is
    detected, subsequent text is buffered until the closing fence arrives.
    The complete block is then emitted as box-drawing format.  Non-fence
    text is forwarded immediately.
    """
    if text is None:
        return _original_stream_delta(self, text)

    # ── Initialise per-instance fence state ────────────────────────────
    if not hasattr(self, "_ccf_buf"):
        self._ccf_buf = ""
        self._ccf_in_fence = False
        self._ccf_fence_lang = ""

    # ── Pass through non-fence text immediately ────────────────────────
    if not self._ccf_in_fence:
        stripped = text.lstrip("\n").lstrip()
        if not stripped.startswith("```") or stripped.startswith("````"):
            # If text contains a fence further in, split at the fence
            fence_at = text.find("\n```")
            if fence_at >= 0:
                pre = text[:fence_at + 1]  # include the \n before ```
                _original_stream_delta(self, pre)
                _patched_stream_delta(self, text[fence_at + 1:])
                return
            # No fence in this text — just forward
            if self._ccf_buf:
                residual = self._ccf_buf
                self._ccf_buf = ""
                _original_stream_delta(self, residual)
            return _original_stream_delta(self, text)

        # ── Fence opening detected ─────────────────────────────────
        idx = text.find("```")
        if idx > 0:
            # Text before the fence — forward it
            pre = text[:idx]
            _original_stream_delta(self, pre)

        # Extract the fence line and any following content
        after_fence = text[idx:]  # starts with ```
        lines = after_fence.split("\n", 1)
        fence_line = lines[0].strip()
        lang = fence_line[3:].strip()
        self._ccf_in_fence = True
        self._ccf_fence_lang = lang
        self._ccf_buf = lines[1] if len(lines) > 1 else ""

        # If the closing fence is already in the buffer (single-delta case),
        # close the fence immediately
        close_marker = "\n```"
        if close_marker in self._ccf_buf:
            close_idx = self._ccf_buf.rfind(close_marker)
            code = self._ccf_buf[:close_idx]
            after = self._ccf_buf[close_idx + len(close_marker):]
            formatted = _format_code_block(code, self._ccf_fence_lang)
            if after:
                formatted += "\n"
            _original_stream_delta(self, formatted)
            self._ccf_in_fence = False
            self._ccf_buf = ""
            self._ccf_fence_lang = ""
            if after:
                _patched_stream_delta(self, after)
        return

    # ── We're inside a fence — buffer content ──────────────────────────
    self._ccf_buf += text

    # Check for closing fence
    close_marker = "\n```"
    if close_marker in self._ccf_buf:
        close_idx = self._ccf_buf.rfind(close_marker)
        code = self._ccf_buf[:close_idx]
        after = self._ccf_buf[close_idx + len(close_marker):]

        # Format and emit through original
        formatted = _format_code_block(code, self._ccf_fence_lang)
        if after:
            formatted += "\n"
        _original_stream_delta(self, formatted)

        # Reset fence state and handle trailing text
        self._ccf_in_fence = False
        self._ccf_buf = ""
        self._ccf_fence_lang = ""
        if after:
            _patched_stream_delta(self, after)


# ── Hooks ───────────────────────────────────────────────────────────────────

def _on_transform_llm_output(
    response_text: str,
    session_id: str | None = None,
    model: str | None = None,
    platform: str = "",
    **kwargs,
) -> str | None:
    """Hook callback — transform code blocks when on CLI, otherwise pass."""
    if platform != "cli":
        return None
    try:
        transformed = _transform_cli(response_text)
        if transformed != response_text:
            logger.debug(
                "Transformed code blocks for platform=%r (session=%s)",
                platform, session_id,
            )
            return transformed
    except Exception as exc:
        logger.warning("cli-code-format transform failed: %s", exc)
    return None


def register(ctx) -> None:
    """Register the transform_llm_output hook and the streaming monkey-patch."""
    global _original_stream_delta

    # ── Hook for the Rich Panel (non-streaming) path ───────────────────
    ctx.register_hook("transform_llm_output", _on_transform_llm_output)

    # ── Monkey-patch for the streaming path ────────────────────────────
    try:
        from cli import HermesCLI
        if _original_stream_delta is None:
            _original_stream_delta = HermesCLI._stream_delta
            HermesCLI._stream_delta = _patched_stream_delta
            logger.info(
                "cli-code-format: patched HermesCLI._stream_delta "
                "for streaming fence→box transform"
            )
    except ImportError:
        logger.debug("cli-code-format: cli module not loaded; streaming patch deferred")
    except Exception as exc:
        logger.warning("cli-code-format: streaming patch failed: %s", exc)

    logger.info("cli-code-format plugin registered")

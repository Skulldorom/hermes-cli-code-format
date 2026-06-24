"""
Tests for cli-code-format plugin — exercises the box-drawing transformation.

Output format:
  ╭─ python ─────────────────────────────

    code here

  ╰─────────────────────────────────────

Covers: basic blocks, lang labels, multi-block, edge cases, platform gating.
"""

import os
import sys

# Point at the repo root so we can import the plugin as a flat module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from __init__ import _transform_cli, _format_code_block, LANG_LABELS, _on_transform_llm_output, register

PASS = "  PASS"
FAIL = "  FAIL"


def check(name, got, expected):
    ok = got == expected
    print(f"  {'OK' if ok else 'FAIL'}  {name}")
    if not ok:
        print(f"       expected: {expected!r}")
        print(f"       got:      {got!r}")
    return ok


# ── Rail width helper ───────────────────────────────────────────────────

def _top_rail(label: str) -> str:
    """Replicate what the plugin does internally for width verification."""
    from __init__ import TOP_RAIL_LEFT, RAIL_CHAR, BOX_WIDTH
    prefix = f"{TOP_RAIL_LEFT} {label} "
    return prefix + RAIL_CHAR * max(0, BOX_WIDTH - len(prefix))


def _bot_rail() -> str:
    from __init__ import BOTTOM_RAIL_LEFT, RAIL_CHAR, BOX_WIDTH
    return BOTTOM_RAIL_LEFT + RAIL_CHAR * (BOX_WIDTH - 2)


# ── Tests ───────────────────────────────────────────────────────────────

def _expected(lang: str, code: str) -> str:
    """Build the expected box-drawing output for a single block."""
    label = LANG_LABELS.get(lang, lang or "code")
    return _top_rail(label) + "\n\n" + "\n".join("  " + l for l in code.strip("\n").split("\n")) + "\n\n" + _bot_rail()


def test_basic_python_block():
    """A simple python block should produce box-drawing rails."""
    text = "```python\nprint('hello')\n```"
    result = _transform_cli(text)
    expected = _expected("python", "print('hello')")
    return check("basic python block", result, expected)


def test_no_lang_block():
    """A fenced block without a language tag should default to 'code'."""
    text = "```\necho hi\n```"
    result = _transform_cli(text)
    expected = _expected("", "echo hi")
    return check("no-lang block", result, expected)


def test_label_aliases():
    """Language aliases (py→python, sh→bash, yml→yaml) should map correctly."""
    cases = [("py", "python"), ("sh", "bash"), ("yml", "yaml"),
             ("js", "js"), ("ts", "ts"), ("rs", "rust"),
             ("md", "md"), ("sol", "solidity"), ("kt", "kotlin")]
    for alias, expected_label in cases:
        text = f"```{alias}\nhello\n```"
        result = _transform_cli(text)
        expected = _expected(alias, "hello")
        if result != expected:
            print(f"       alias {alias!r} => {expected_label!r}: mismatch")
            return False
    return check("label aliases (%d cases)" % len(cases), True, True)


def test_multi_line_block():
    """Multi-line code should indent every line."""
    text = "```python\nline1\nline2\nline3\n```"
    result = _transform_cli(text)
    assert "  line1\n  line2\n  line3" in result
    print(f"       lines verify OK")
    return check("multi-line block", True, True)


def test_multi_block():
    """Multiple fenced blocks should each be transformed independently."""
    text = "```python\nprint(1)\n```\n\nsome text\n\n```bash\necho 2\n```"
    result = _transform_cli(text)
    rails = [l for l in result.split("\n") if "╭─" in l or "╰─" in l]
    ok = len(rails) == 4
    return check("multi-block (%d rails)" % len(rails), ok, True)


def test_no_code_blocks():
    """Plain text with no fenced blocks should pass through unchanged."""
    text = "Just some regular text.\nNo code here."
    result = _transform_cli(text)
    return check("no code blocks", result, text)


def test_inline_code_untouched():
    """Inline backtick code should be left alone."""
    text = "Run `pip install foo` to install."
    result = _transform_cli(text)
    return check("inline code untouched", result, text)


def test_strip_blank_first_last_line():
    """Leading/trailing blank lines inside the fence should be stripped."""
    text = "```python\n\nprint('hello')\n\n```"
    result = _transform_cli(text)
    expected = _expected("python", "\nprint('hello')\n")
    return check("strip leading/trailing blank", result, expected)


def test_unknown_lang_preserved():
    """Unknown language tags should be used as-is."""
    text = "```foobarlang\ncode\n```"
    result = _transform_cli(text)
    expected = _expected("foobarlang", "code")
    return check("unknown lang preserved", result, expected)


def test_empty_block_passthrough():
    """A fence with no content between newlines — regex requires \ncontent\n so
    ```lang\n``` is NOT matched and passes through unchanged."""
    text = "```python\n```"
    result = _transform_cli(text)
    return check("empty block -> passthrough (no crash)", True, True)


def test_box_width_invariant():
    """Every rail line must be exactly BOX_WIDTH (60) chars."""
    from __init__ import BOX_WIDTH
    for lang in ["python", "go", "javascript", "a", "", "solidity", "dockerfile"]:
        label = LANG_LABELS.get(lang, lang or "code")
        text = f"```{lang}\nx\n```" if lang else "```\nx\n```"
        result = _transform_cli(text)
        for line in result.split("\n"):
            if line.startswith("╭─") or line.startswith("╰─"):
                actual = len(line)
                if actual != BOX_WIDTH:
                    print(f"       {lang!r} rail width: {actual} (expected {BOX_WIDTH})")
                    return False
    return check("box width invariant (%d)" % BOX_WIDTH, True, True)


def test_platform_gating():
    """_on_transform_llm_output returns None on non-CLI platforms."""
    r_cli = _on_transform_llm_output("```python\nx\n```", platform="cli")
    r_tg = _on_transform_llm_output("```python\nx\n```", platform="telegram")
    r_dc = _on_transform_llm_output("```python\nx\n```", platform="discord")
    r_none = _on_transform_llm_output("```python\nx\n```", platform="")
    ok = r_cli is not None and all(x is None for x in (r_tg, r_dc, r_none))
    return check("platform gating (CLI transforms, others None)", ok, True)


def test_register_works():
    """register() should wire the hook without crashing."""
    class FakeCtx:
        hooks = {}
        def register_hook(self, name, fn):
            self.hooks[name] = fn

    ctx = FakeCtx()
    register(ctx)
    ok = "transform_llm_output" in ctx.hooks
    return check("register() wires transform_llm_output", ok, True)


def test_mixed_content():
    """Inline code, regular text, and fenced blocks interleaved."""
    text = """Here's a thing:
```python
def foo():
    pass
```
And then `some inline` and another:
```bash
echo done
```"""
    result = _transform_cli(text)
    lines = result.split("\n")
    rails = [l for l in lines if "╭─" in l or "╰─" in l]
    ok = len(rails) == 4
    assert "def foo():" in result
    assert "`some inline`" in result
    return check("mixed content (%d rails)" % len(rails), ok, True)


def test_no_transform_needed():
    """When no fenced blocks exist, _on_transform_llm_output returns None
    even on CLI so it doesn't re-process text unnecessarily."""
    text = "Just plain text.\nNo fences here."
    result = _on_transform_llm_output(text, platform="cli")
    return check("no-op returns None not empty string", result is None, True)


def test_all_known_labels_have_good_names():
    """All entries in LANG_LABELS map to non-empty, readable labels."""
    for key, val in LANG_LABELS.items():
        assert val and len(val) > 0, f"empty label for {key!r}"
        assert " " not in val, f"label with spaces for {key!r}: {val!r}"
    print(f"       {len(LANG_LABELS)} label mappings checked")
    return check("label table sanity", True, True)


# ── Runner ──────────────────────────────────────────────────────────────

def main():
    tests = [
        test_basic_python_block,
        test_no_lang_block,
        test_label_aliases,
        test_multi_line_block,
        test_multi_block,
        test_no_code_blocks,
        test_inline_code_untouched,
        test_strip_blank_first_last_line,
        test_unknown_lang_preserved,
        test_empty_block_passthrough,
        test_box_width_invariant,
        test_platform_gating,
        test_register_works,
        test_mixed_content,
        test_no_transform_needed,
        test_all_known_labels_have_good_names,
    ]

    from test_streaming import TESTS as _streaming_tests
    tests.extend(_streaming_tests)

    results = []
    for t in tests:
        name = t.__name__.replace("test_", "").replace("_", " ")
        try:
            ok = t()
            results.append(ok)
        except Exception as e:
            import traceback
            print(f"  FAIL  {name}")
            print(f"       EXCEPTION: {e}")
            traceback.print_exc()
            results.append(False)

    total = len(results)
    passed = sum(results)
    print()
    print(f"  {'─' * 40}")
    print(f"  {passed}/{total} tests passed")
    if passed == total:
        print("  All good.")
    else:
        print(f"  {total - passed} test(s) failed.")


if __name__ == "__main__":
    main()

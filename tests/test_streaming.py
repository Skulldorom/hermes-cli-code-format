"""
Tests for the streaming monkey-patch (_patched_stream_delta).

Verifies that the stateful fence buffering correctly transforms
``` fences into box-drawing format when text arrives in a single
delta or split across multiple deltas.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from test_format import check, _expected
from __init__ import _patched_stream_delta, _format_code_block


class FakeCLI:
    """Minimal fake that captures streamed output."""
    def __init__(self):
        self.output = ""
        self._ccf_buf = ""
        self._ccf_in_fence = False
        self._ccf_fence_lang = ""

    def _stream_delta(self, text):
        """Simulate what the original _stream_delta does: forward to display."""
        if text:
            self.output += text


import __init__ as plugin
_original_ref = plugin._original_stream_delta


def _setup():
    plugin._original_stream_delta = FakeCLI._stream_delta


def _teardown():
    plugin._original_stream_delta = _original_ref


def _run_stream(cli, deltas):
    for text in deltas:
        _patched_stream_delta(cli, text)


def test_single_delta_basic():
    _setup()
    cli = FakeCLI()
    _run_stream(cli, ["```python\nprint('hello')\n```\n"])
    _teardown()
    ok = ("\u256d\u2500 python" in cli.output and "\u2570\u2500" in cli.output and "print('hello')" in cli.output)
    return check("single delta basic", ok, True)


def test_split_across_deltas():
    _setup()
    cli = FakeCLI()
    _run_stream(cli, ["```bash\n", "echo hello\n", "echo world\n", "```\n"])
    _teardown()
    ok = ("\u256d\u2500 bash" in cli.output and "\u2570\u2500" in cli.output and "echo hello" in cli.output and "echo world" in cli.output)
    return check("split across deltas", ok, True)


def test_non_fence_passthrough():
    _setup()
    cli = FakeCLI()
    _run_stream(cli, ["Here is some prose.\n", "More prose.\n"])
    _teardown()
    ok = "Here is some prose." in cli.output and "More prose." in cli.output
    return check("non-fence passthrough", ok, True)


def test_mixed_prose_and_fence():
    _setup()
    cli = FakeCLI()
    _run_stream(cli, ["Check this out:\n", "```python\n", "x = 1\n", "```\n", "Isn't that cool?\n"])
    _teardown()
    ok = ("Check this out:" in cli.output and "\u256d\u2500 python" in cli.output and "\u2570\u2500" in cli.output and "x = 1" in cli.output and "Isn't that cool?" in cli.output)
    return check("mixed prose and fence", ok, True)


def test_consecutive_fences():
    _setup()
    cli = FakeCLI()
    _run_stream(cli, ["```python\nprint(1)\n```\n", "```bash\necho 2\n```\n"])
    _teardown()
    rails = cli.output.count("\u256d\u2500") + cli.output.count("\u2570\u2500")
    ok = rails == 4
    return check("consecutive fences (%d rails)" % rails, ok, True)


def test_fence_with_leading_text():
    _setup()
    cli = FakeCLI()
    _run_stream(cli, ["Pre text\n```python\ncode\n```\n"])
    _teardown()
    ok = ("Pre text" in cli.output and "\u256d\u2500 python" in cli.output and "\u2570\u2500" in cli.output)
    return check("fence with leading text", ok, True)


def test_no_lang_fence():
    _setup()
    cli = FakeCLI()
    _run_stream(cli, ["```\nplain code\n```\n"])
    _teardown()
    ok = ("\u256d\u2500 code" in cli.output and "\u2570\u2500" in cli.output and "plain code" in cli.output)
    return check("no-lang fence", ok, True)


def test_none_delta_forwarded():
    _setup()
    cli = FakeCLI()
    _patched_stream_delta(cli, None)
    _teardown()
    return check("None delta forwarded", True, True)


TESTS = [
    test_single_delta_basic,
    test_split_across_deltas,
    test_non_fence_passthrough,
    test_mixed_prose_and_fence,
    test_consecutive_fences,
    test_fence_with_leading_text,
    test_no_lang_fence,
    test_none_delta_forwarded,
]

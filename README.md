# cli-code-format

A Hermes Agent plugin that transforms markdown fenced code blocks into
box-drawing format when running in CLI mode — cleaner, more readable code
blocks in your terminal.

Gateways (Telegram, Discord, Slack, etc.) get standard markdown untouched
so native syntax highlighting works normally.

## What it does

**Before** (standard markdown in your terminal):

    ```python
    def hello():
        print("world")
    ```

**After** (box-drawing format on CLI):

    ╭─ python ───────────────────────────────

      def hello():
          print("world")

    ╰────────────────────────────────────────

Code is indented 2 spaces for breathing room, and leading/trailing blank
lines are stripped for compact display. 50+ language tags are mapped to
short labels (python, bash, yaml, json, diff, js, ts, rust, go, etc.).
Unknown tags default to `code`.

## Installation

```bash
# Clone into your Hermes plugins directory
git clone https://github.com/Skulldorom/hermes-cli-code-format.git \
  ~/.hermes/plugins/cli-code-format/

# Restart Hermes or /reset your session
```

After installing, restart your Hermes session (`/reset` in interactive mode,
or start a new `hermes` invocation). The plugin auto-registers via the
`transform_llm_output` hook — no configuration needed.

## How it works

- Hooks into `transform_llm_output`, which fires once per turn after the
  LLM produces its final response
- Checks `platform == "cli"` — on gateways it yields and leaves markdown
  alone
- Regex-replaces every ` ```lang\n...\n``` ` block with box-drawing format
- The first registered `transform_llm_output` plugin to return a string
  wins — this plugin returns `None` on gateways to yield to other plugins

## Requirements

- Hermes Agent (any recent version with plugin support)
- Python 3.10+ (standard Hermes dependency)
- Nothing else — zero external dependencies

## Files

```
cli-code-format/
├── plugin.yaml     # Plugin manifest — declares hook: transform_llm_output
├── __init__.py     # The logic
├── LICENSE         # MIT
└── README.md       # This file
```

## License

MIT — see [LICENSE](LICENSE).

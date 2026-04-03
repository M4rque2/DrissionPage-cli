# DrissionPage-cli
Token-efficient browser automation CLI for coding agents, powered by [DrissionPage](https://DrissionPage.cn).

Mirrors the architecture of [playwright-cli](https://github.com/microsoft/playwright-cli) but uses DrissionPage as the backend — pure Python, no Node.js required.

## Why use drissionpage-cli

If you know, you know. If you don't, go use playwright-cli.


## Why CLI + Skills over MCP

Modern coding agents (Claude Code, GitHub Copilot, etc.) increasingly favour CLI-based workflows exposed as **SKILLs** over MCP because CLI invocations are more token-efficient: they avoid loading large tool schemas and verbose accessibility trees into the model context. This makes CLI + SKILLs better suited for high-throughput agents that must balance browser automation with large codebases within limited context windows.

## Requirements

- Python 3.8+
- Chrome / Chromium browser installed

## Installation

### From PyPI (recommended)

```bash
pip install drissionpage-cli
```

### From source (development)

```bash
git clone https://github.com/nicekate/DrissionPage-MCP.git
cd DrissionPage-MCP/DrissionPage-cli
pip install -e .
```

After installation the `drissionpage-cli` command is available globally:

```bash
drissionpage-cli --version
drissionpage-cli --help
```

### Install skills for Claude Code

```bash
drissionpage-cli install --skills
```

This copies the SKILL.md and reference guides into `.claude/skills/drissionpage-cli/` so that Claude Code (or any compatible agent) can discover them automatically.

**One-liner** — install the package and set up Claude Code skills in a single command:

```bash
pip install drissionpage-cli && drissionpage-cli install --skills
```

#### What gets installed

The `install --skills` command copies the following into `.claude/skills/drissionpage-cli/`:

| File | Purpose |
|------|---------|
| `SKILL.md` | Skill definition & quick-start guide for the agent |
| `references/element-locators.md` | CSS, XPath, text, and attribute locator syntax |
| `references/running-code.md` | Custom DrissionPage Python code execution |
| `references/session-management.md` | Multiple concurrent browser sessions |
| `references/storage-state.md` | Cookies, localStorage, sessionStorage management |
| `references/screenshots-pdf.md` | Visual capture and PDF generation |
| `references/network-listening.md` | Network request monitoring |
| `references/dual-mode.md` | Browser + HTTP request mode switching |

Once installed, Claude Code automatically discovers the skill and can use `drissionpage-cli` commands for browser automation tasks.

## Quick Start

```bash
# Open a browser (headless by default)
drissionpage-cli open https://example.com

# Take a snapshot of the page
drissionpage-cli snapshot

# Interact with elements using DrissionPage locators
drissionpage-cli click "@id=submit"
drissionpage-cli fill "css:input[name=email]" "user@example.com" --submit

# Evaluate JavaScript
drissionpage-cli eval "return document.title"

# Take a screenshot
drissionpage-cli screenshot --filename=result.png

# Close the browser
drissionpage-cli close
```

### Headed mode

```bash
drissionpage-cli open https://example.com --headed
```

## Commands

### Core

| Command | Description |
|---------|-------------|
| `open [url]` | Open browser, optionally navigate to URL |
| `goto <url>` | Navigate to a URL |
| `click <ref>` | Click an element |
| `dblclick <ref>` | Double-click an element |
| `right-click <ref>` | Right-click an element |
| `type <text> [ref]` | Type text into element |
| `fill <ref> <text> [--submit]` | Clear and fill text (optionally press Enter) |
| `hover <ref>` | Hover over element |
| `drag <startRef> <endRef>` | Drag element to another |
| `select <ref> <value>` | Select dropdown option |
| `check <ref>` / `uncheck <ref>` | Check / uncheck a checkbox |
| `upload <ref> <file>` | Upload a file |
| `snapshot [ref] [--filename=f]` | Capture page or element snapshot |
| `eval <expr> [ref]` | Evaluate JavaScript on page or element |
| `run-code <code> [--filename=f]` | Run arbitrary DrissionPage Python code |
| `screenshot [ref] [--filename=f]` | Take a screenshot |
| `pdf [--filename=f]` | Save page as PDF |
| `resize <w> <h>` | Resize the browser window |
| `dialog-accept [text]` | Accept a dialog |
| `dialog-dismiss` | Dismiss a dialog |
| `close` | Close the browser |

### Navigation

| Command | Description |
|---------|-------------|
| `go-back` | Go back |
| `go-forward` | Go forward |
| `reload` | Reload page |

### Keyboard & Mouse

| Command | Description |
|---------|-------------|
| `press <key>` | Press a key (Enter, ArrowDown, Tab, etc.) |
| `mousemove <x> <y>` | Move mouse to coordinates |
| `mousedown [button]` | Press mouse button |
| `mouseup [button]` | Release mouse button |
| `scroll <dx> <dy>` | Scroll the page |

### Tabs

| Command | Description |
|---------|-------------|
| `tab-list` | List all tabs |
| `tab-new [url]` | Create new tab |
| `tab-close [index]` | Close a tab |
| `tab-select <index>` | Select a tab |

### Cookies & Storage

| Command | Description |
|---------|-------------|
| `cookie-list [--domain=d]` | List cookies |
| `cookie-get <name>` | Get a cookie |
| `cookie-set <name> <val> [opts]` | Set a cookie |
| `cookie-delete <name>` | Delete a cookie |
| `cookie-clear` | Clear all cookies |
| `localstorage-list\|get\|set\|delete\|clear` | Manage localStorage |
| `sessionstorage-list\|get\|set\|delete\|clear` | Manage sessionStorage |
| `state-save [filename]` | Save cookies + storage to JSON |
| `state-load <filename>` | Restore cookies + storage from JSON |

### Session Management

| Command | Description |
|---------|-------------|
| `list` | List all active sessions |
| `close` | Close current session's browser |
| `close-all` | Close all sessions |
| `kill-all` | Kill all browser processes |
| `delete-data` | Delete user data for a session |

## Targeting Elements

DrissionPage supports rich locator syntax:

```bash
# CSS selector
drissionpage-cli click "css:#main > button.submit"

# XPath
drissionpage-cli click "xpath://button[@id='submit']"

# Text content
drissionpage-cli click "text:Submit"

# Tag name
drissionpage-cli click "tag:button"

# Attribute matching
drissionpage-cli click "@id=submit"
drissionpage-cli click "@class:btn"          # contains
drissionpage-cli click "@name^=user"         # starts with
drissionpage-cli click "@data-testid=login"

# Combined (AND)
drissionpage-cli click "@@tag()=button@@text()=Submit"

# Combined (OR)
drissionpage-cli click "@|id=btn1@id=btn2"
```

## Named Sessions

Run multiple isolated browser instances concurrently:

```bash
drissionpage-cli -s=auth open https://app.example.com/login
drissionpage-cli -s=scrape open https://data.example.com
drissionpage-cli list
drissionpage-cli close-all
```

Or set a default session via environment variable:

```bash
DRISSIONPAGE_CLI_SESSION=myproject drissionpage-cli open https://example.com
```

## Running Custom Code

Execute arbitrary DrissionPage Python code with `run-code`. The `page` variable is the active `ChromiumPage` instance. Set `result` to output a return value.

```bash
drissionpage-cli run-code "result = page.title"
drissionpage-cli run-code "
eles = page.eles('tag:a')
result = [{'text': a.text, 'href': a.link} for a in eles if a.link]
"
drissionpage-cli run-code --filename=myscript.py
```

## Testing

The project includes two test suites:

### Unit tests (no browser required)

92 tests covering the argument parser, session management, snapshot formatting, skill installation, state save/load, and all command handlers via mocks.

```bash
cd DrissionPage-cli
pip install pytest
python3 -m pytest tests/test_unit.py -v
```

### Integration tests (browser required)

30+ end-to-end tests that launch a real browser, navigate `data:` URLs, click elements, manage storage, take screenshots, etc.

```bash
python3 -m pytest tests/test_integration.py -v
```

To skip integration tests in CI (no browser available):

```bash
SKIP_INTEGRATION=1 python3 -m pytest tests/ -v
```

### Run all tests

```bash
python3 -m pytest tests/ -v
```

## Project Structure

```
DrissionPage-cli/
  drissionpage_cli/                  # Main package
    __init__.py                      # CLI entry point (59 commands)
    skills/drissionpage-cli/         # Bundled skill files
      SKILL.md
      references/
        element-locators.md
        running-code.md
        session-management.md
        storage-state.md
        screenshots-pdf.md
        network-listening.md
        dual-mode.md
  pyproject.toml                     # Python packaging
  requirements.txt                   # DrissionPage>=4.0.0
  pytest.ini                         # Test configuration
  README.md
  LICENSE
  scripts/
    update.py                        # Skill update script
  tests/
    conftest.py                      # Shared fixtures
    test_unit.py                     # 92 unit tests (mocked, no browser)
    test_integration.py              # 30+ integration tests (real browser)
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DRISSIONPAGE_CLI_SESSION` | Default session name (default: `default`) |
| `DRISSIONPAGE_CLI_DIR` | CLI data directory (default: `.drissionpage-cli`) |
| `DRISSIONPAGE_CLI_DEBUG` | Set to `1` for full tracebacks on errors |
| `SKIP_INTEGRATION` | Set to `1` to skip browser integration tests |

## License

Apache-2.0

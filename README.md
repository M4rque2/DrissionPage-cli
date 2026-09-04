# DrissionPage-cli
Token-efficient browser automation CLI for coding agents, powered by [DrissionPage](https://DrissionPage.cn).

Mirrors the architecture of [playwright-cli](https://github.com/microsoft/playwright-cli) but uses DrissionPage as the backend — pure Python, no Node.js required.

## Recommended use: Agent-controlled browser with human in the loop

The intended workflow is **agent drives, human assists**:

1. The agent opens a visible (headed) browser and starts the task.
2. The human watches the browser window. When the agent hits a wall — login page, CAPTCHA, 2FA prompt, cookie consent — the human steps in, completes it manually, and tells the agent to continue.
3. Login state is saved permanently in `~/.drissionpage-cli/profile`. Log in once and every future session picks up where you left off — no re-authentication needed.

```
Agent:  drissionpage-cli open https://github.com/settings
         → browser opens, hits sign-in page
         → reports: "I need you to log in — complete it in the browser window, then let me know"
Human: [logs in, solves any CAPTCHA/2FA in the browser]
Human: "done, continue"
Agent:  drissionpage-cli snapshot
         → now sees the settings page, carries on autonomously
         → login is saved; next run skips this step entirely
```

This design handles the real-world friction that fully-headless automation cannot: sites that require human verification, SSO flows, or browser fingerprint checks.

## Why CLI + Skills over MCP

Modern coding agents (Claude Code, GitHub Copilot, etc.) increasingly favour CLI-based workflows exposed as **SKILLs** over MCP because CLI invocations are more token-efficient: they avoid loading large tool schemas and verbose accessibility trees into the model context. This makes CLI + SKILLs better suited for high-throughput agents that must balance browser automation with large codebases within limited context windows.

## Requirements

- Python 3.8+
- Chrome / Chromium browser installed
- DrissionPage 4.0+ (installed automatically)

### Chrome 147+ users: DrissionPage 5.0.0b0 or newer

Chrome 147 exposes `chrome://newtab-footer/` as a separate CDP target, which older DrissionPage releases can pick as the default tab — pages then render squished into a ~100px strip at the bottom of the window. The fix landed upstream in [DrissionPage PR #665](https://github.com/g1879/DrissionPage/pull/665) and ships in **5.0.0b0 and newer**; the 4.1.x line does not carry it.

drissionpage-cli checks both versions when it connects and warns once per run **only if** your Chrome is 147+ *and* your DrissionPage is too old. On Chrome 146 or older the bug cannot occur, so there is no warning and nothing to do. If you do see the warning:

```bash
pip install --upgrade --pre "DrissionPage>=5.0.0b0"
```

`DRISSIONPAGE_CLI_NO_VERSION_WARN=1` silences it. See [docs/chrome146_compatibility_fix.md](docs/chrome146_compatibility_fix.md) for the full investigation.

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

After installation both `drissionpage-cli` and the shortcut `dp-cli` are available globally:

```bash
dp-cli --version
dp-cli --help
```

`dp-cli` and `drissionpage-cli` are identical — use whichever you prefer.

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
# Open a headed browser (default) — user can see and interact with it
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

### Headless mode (no visible window)

```bash
drissionpage-cli open https://example.com --headless
```

Use headless when running in CI or when no human oversight is needed and the site doesn't require interactive login.

## Persistent Profile

By default, every session uses a single persistent Chrome profile stored at:

```
~/.drissionpage-cli/profile
```

This profile accumulates cookies, localStorage, and login tokens across all sessions. The practical effect:

- **Log in once** to any site — the agent never needs to authenticate again on subsequent runs.
- Works across different working directories — the profile is home-based, not project-local.
- Both headed and headless mode share the same profile.

To reset all login state (start fresh):

```bash
drissionpage-cli delete-data --reset-profile
```

For a fully isolated throwaway session (no persistent state):

```bash
drissionpage-cli open --sandbox
```

### Capture mode (network traffic recording)

Append `--capture` to any interaction command to record all network traffic triggered by that action:

```bash
# Capture during navigation
drissionpage-cli open https://example.com --capture
drissionpage-cli goto https://example.com --capture

# Capture traffic triggered by a click (e.g. form submit, XHR, SPA navigation)
drissionpage-cli click "#submit" --capture

# Also supported on: dblclick, right-click, type, fill, hover, drag, select, check, uncheck
drissionpage-cli fill "css:input[name=q]" "search term" --submit --capture
drissionpage-cli hover "@id=lazy-load-trigger" --capture
```

Creates a timestamped folder `capture-<ts>/` in the current directory containing:

| File | Contents |
|------|----------|
| `snapshot.html` | Page HTML after the action completes |
| `traffic.json` | Manifest of all requests (url, method, status, content_type, file) |
| `0001_*.{ext}` … | Every response body saved as an individual file |

Captured file types include: HTML, CSS, JS, JSON, images (jpg, png, webp, gif, svg, avif, bmp, ico), audio (mp3, ogg, wav, aac, flac), and video (mp4, webm, ogv, mov).

```
[capture] folder   → /project/capture-2026-04-14T16-06-30
[capture] snapshot → snapshot.html
[capture] traffic  → traffic.json  (125 requests)
[capture] media    → 63 files (images/audio/video)
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

All commands above (except `upload`) accept `--capture` to record network traffic triggered by the action.
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
| `delete-data [--reset-profile]` | Close session; optionally wipe the persistent profile |

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

## Browser Connection Lifecycle

### How `open` connects

`open` uses a lazy, connection-first strategy — it never kills a browser it didn't launch:

1. **Reconnect to previous session** — if a session record exists in `~/.drissionpage-cli/sessions.json` and the browser is still alive, `open` reconnects to it. It does not kill and relaunch. Calling `open <url>` on a running session simply navigates to the new URL.
2. **Launch a new browser** — if no session record exists and port 9222 is free, `open` starts a fresh Chrome instance with the CLI-managed profile.
3. **Adopt an existing browser** — if port 9222 is already occupied (e.g. by an orphaned Chrome from a crashed session, or a manually launched `chrome --remote-debugging-port=9222`), `open` attempts a CDP connection. If it succeeds, the browser is adopted as the current session — no restart needed.
4. **Report an error** — if the port is occupied by something that isn't a controllable Chrome (e.g. another server), `open` reports a clear error with options (`--port=<other>`, `kill-all`). It never auto-kills the process.

### How `close` works

`close` only shuts down browsers that have a session record. If you run `close` and there is no matching session in the registry, it prints `"Session 'X' not found. Nothing to close."` — it does not probe the port or kill unknown processes. To forcefully clean up all Chrome instances (including orphans), use `kill-all`.

### Two processes controlling the same Chrome

Chrome DevTools Protocol (CDP) allows multiple clients to connect simultaneously. If two dp-cli processes (or any two CDP clients) attach to the same Chrome on port 9222:

- **Both send commands independently.** Chrome executes them in arrival order with no coordination — navigation, clicks, and JS evaluation from one client can interleave unpredictably with the other.
- **Both receive all events.** DOM changes, navigations, and network events triggered by one client appear to the other as spontaneous activity.
- **`close` from either side kills Chrome for both.** CDP's `Browser.close` terminates the entire browser process; the other client's WebSocket disconnects immediately.
- **Neither client can detect the other.** CDP has no API to list connected clients or receive "another client connected" events.

**Recommendation:** avoid sharing a single Chrome instance between concurrent automations. Use named sessions on different ports instead:

```bash
dp-cli -s=task1 open --port=9222 https://site-a.com
dp-cli -s=task2 open --port=9223 https://site-b.com
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

```bash
python3 -m pytest tests/test_unit.py -v
```

### Integration tests (browser required)

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
    test_unit.py                     # Unit tests (mocked, no browser)
    test_integration.py              # Integration tests (real browser)
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DRISSIONPAGE_CLI_SESSION` | Default session name (default: `default`) |
| `DRISSIONPAGE_CLI_DIR` | Override CLI data/profile directory (default: `~/.drissionpage-cli`) |
| `DRISSIONPAGE_CLI_DEBUG` | Set to `1` for full tracebacks on errors |
| `SKIP_INTEGRATION` | Set to `1` to skip browser integration tests |

## License

Apache-2.0

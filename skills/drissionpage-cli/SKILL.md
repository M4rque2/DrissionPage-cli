---
name: drissionpage-cli
description: Automate browser interactions, scrape web pages and test with DrissionPage.
allowed-tools: Bash(drissionpage-cli:*) Bash(python:*) Bash(pip:*)
---

# Browser Automation with drissionpage-cli

## How this works: agent drives, human assists

drissionpage-cli opens a **visible (headed) browser** by default. The human can see the browser window and step in whenever needed — to log in, solve a CAPTCHA, complete a 2FA prompt, or accept a cookie banner. Once the human is done, the agent continues from where it left off.

**Login state persists permanently** in `~/.drissionpage-cli/profile`. After the human logs in once, every future session is already authenticated — the agent never needs to ask again.

### Typical flow

```
Agent:  drissionpage-cli open https://some-site.com/dashboard
         → browser opens visibly; site redirects to login page
         → "I need you to log in — complete it in the browser window, then let me know"
Human: [logs in, handles any CAPTCHA or 2FA in the browser window]
Human: "done"
Agent:  drissionpage-cli snapshot
         → now sees the dashboard; continues autonomously
         → next run: already logged in, skips this entirely
```

**When to ask the human for help:**
- Login / sign-in pages
- CAPTCHA or bot-detection challenges
- Two-factor authentication prompts
- OAuth / SSO flows that open popup windows
- Cookie consent dialogs that block interaction

## Quick start

```bash
# open browser (headed by default — human can see and interact)
drissionpage-cli open
# navigate to a page
drissionpage-cli goto https://example.com
# interact with the page using CSS/XPath/text locators
drissionpage-cli click "#submit-button"
drissionpage-cli type "search query"
drissionpage-cli press Enter
# take a screenshot
drissionpage-cli screenshot
# close the browser
drissionpage-cli close
```

## Commands

### Core

```bash
drissionpage-cli open
# open and navigate right away
drissionpage-cli open https://example.com/
drissionpage-cli goto https://example.com
drissionpage-cli type "search query"
drissionpage-cli click "#submit"
drissionpage-cli dblclick "@id=item"
drissionpage-cli right-click "tag:div"
# --submit presses Enter after filling the element
drissionpage-cli fill "css:input[name=email]" "user@example.com" --submit
drissionpage-cli drag "@id=source" "@id=target"
drissionpage-cli hover "tag:button"
drissionpage-cli select "tag:select" "option-text"
drissionpage-cli upload "css:input[type=file]" ./document.pdf
drissionpage-cli check "@type=checkbox"
drissionpage-cli uncheck "@type=checkbox"
drissionpage-cli snapshot
drissionpage-cli eval "document.title"
drissionpage-cli eval "return this.id" "#element"
drissionpage-cli dialog-accept
drissionpage-cli dialog-accept "confirmation text"
drissionpage-cli dialog-dismiss
drissionpage-cli resize 1920 1080
drissionpage-cli close
```

### Navigation

```bash
drissionpage-cli go-back
drissionpage-cli go-forward
drissionpage-cli reload
```

### Keyboard

```bash
drissionpage-cli press Enter
drissionpage-cli press ArrowDown
drissionpage-cli press Tab
```

### Mouse

```bash
drissionpage-cli mousemove 150 300
drissionpage-cli mousedown
drissionpage-cli mousedown right
drissionpage-cli mouseup
drissionpage-cli scroll 0 100
```

### Save as

```bash
drissionpage-cli screenshot
drissionpage-cli screenshot "#element"
drissionpage-cli screenshot --filename=page.png
drissionpage-cli pdf --filename=page.pdf
```

### Tabs

```bash
drissionpage-cli tab-list
drissionpage-cli tab-new
drissionpage-cli tab-new https://example.com/page
drissionpage-cli tab-close
drissionpage-cli tab-close 2
drissionpage-cli tab-select 0
```

### Storage

```bash
drissionpage-cli state-save
drissionpage-cli state-save auth.json
drissionpage-cli state-load auth.json

# Cookies
drissionpage-cli cookie-list
drissionpage-cli cookie-list --domain=example.com
drissionpage-cli cookie-get session_id
drissionpage-cli cookie-set session_id abc123
drissionpage-cli cookie-set session_id abc123 --domain=example.com --httpOnly --secure
drissionpage-cli cookie-delete session_id
drissionpage-cli cookie-clear

# LocalStorage
drissionpage-cli localstorage-list
drissionpage-cli localstorage-get theme
drissionpage-cli localstorage-set theme dark
drissionpage-cli localstorage-delete theme
drissionpage-cli localstorage-clear

# SessionStorage
drissionpage-cli sessionstorage-list
drissionpage-cli sessionstorage-get step
drissionpage-cli sessionstorage-set step 3
drissionpage-cli sessionstorage-delete step
drissionpage-cli sessionstorage-clear
```

### DevTools

```bash
drissionpage-cli console
drissionpage-cli console warning
drissionpage-cli network
drissionpage-cli run-code "result = page.title"
drissionpage-cli run-code --filename=script.py
```

## Open parameters

```bash
# Default: headed browser with persistent profile (~/.drissionpage-cli/profile)
drissionpage-cli open

# Run headless (no visible window) — use for CI or sites that don't need human help
drissionpage-cli open --headless

# Sandbox mode: isolated temporary profile, no persistent state
drissionpage-cli open --sandbox

# Use a custom profile directory
drissionpage-cli open --profile=/path/to/profile

# Use a specific CDP port (default: 9222)
drissionpage-cli open --port=9333

# Close the browser
drissionpage-cli close

# Reset all login state (wipes ~/.drissionpage-cli/profile)
drissionpage-cli delete-data --reset-profile
```

### --capture (network traffic recording)

Append `--capture` to any interaction command to record all network traffic triggered by that action.

Supported commands: `open`, `goto`, `click`, `dblclick`, `right-click`, `type`, `fill`, `hover`, `drag`, `select`, `check`, `uncheck`.

```bash
# Capture during navigation
drissionpage-cli open https://example.com --capture
drissionpage-cli goto https://example.com --capture

# Capture traffic triggered by a click (e.g. form submit, XHR, SPA navigation)
drissionpage-cli click "#submit" --capture

# Combine with other flags
drissionpage-cli fill "css:input[name=q]" "search term" --submit --capture
drissionpage-cli hover "@id=lazy-load-trigger" --capture
```

Creates a timestamped folder `capture-<ts>/` in the current working directory:

```
capture-2026-04-14T16-06-30/
  snapshot.html        ← page HTML after the action completes
  traffic.json         ← manifest: [{url, method, status, content_type, file}, ...]
  0001_index.html      ← each network response body as its own file
  0002_styles.css
  0004_logo.png
  0017_hero.jpg
  0063_promo.mp4
  ...
```

Saves all response types: HTML, CSS, JS, JSON, images (jpg/png/webp/gif/svg/avif/bmp/ico), audio (mp3/ogg/wav/aac/flac), video (mp4/webm/ogv/mov).

Output:
```
[capture] folder   → /project/capture-2026-04-14T16-06-30
[capture] snapshot → snapshot.html
[capture] traffic  → traffic.json  (125 requests)
[capture] media    → 63 files (images/audio/video)
```

## Snapshots

After each command, drissionpage-cli provides a snapshot of the current page state.

```bash
> drissionpage-cli goto https://example.com
### Page
- Page URL: https://example.com/
- Page Title: Example Domain
### Snapshot
[Snapshot](~/.drissionpage-cli/snapshots/page-2026-02-14T19-22-42.html)
```

## Targeting elements

DrissionPage supports multiple locator strategies:

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
drissionpage-cli click "@class:btn"          # class contains 'btn'
drissionpage-cli click "@name^=user"         # name starts with 'user'
drissionpage-cli click "@data-testid=login"

# Combined attributes (AND)
drissionpage-cli click "@@tag()=button@@text()=Submit"

# Combined attributes (OR)
drissionpage-cli click "@|id=btn1@id=btn2"
```

## Browser Sessions

```bash
# create a named session
drissionpage-cli -s=mysession open https://example.com
drissionpage-cli -s=mysession click "#button"
drissionpage-cli -s=mysession close

drissionpage-cli list
# Close all browsers
drissionpage-cli close-all
# Forcefully kill all browser processes
drissionpage-cli kill-all
```

## Running custom code

Use `run-code` to execute arbitrary DrissionPage Python code:

```bash
drissionpage-cli run-code "result = page.title"
drissionpage-cli run-code "page.get('https://example.com'); result = page.html[:100]"
drissionpage-cli run-code --filename=myscript.py
```

The `page` variable is the active `ChromiumPage` instance. Set `result` to output a value.

## Installation

```bash
pip install drissionpage-cli
```

Or install skills for Claude Code:

```bash
drissionpage-cli install --skills
```

### DrissionPage version warning

If a command prints:

```
[warn] Chrome <N> exposes the chrome://newtab-footer target, and DrissionPage <x.y.z> is missing the fix for it ...
```

this Chrome is 147 or newer and the installed DrissionPage predates [upstream PR #665](https://github.com/g1879/DrissionPage/pull/665). Pages may render squished into a ~100px strip at the bottom of the window, so screenshots and viewport-dependent interactions will be wrong. Fix it by upgrading:

```bash
pip install --upgrade --pre "DrissionPage>=5.0.0b0"
```

The warning only appears on Chrome 147+ with an old DrissionPage — on Chrome 146 or older the bug cannot occur and nothing is printed. Export `DRISSIONPAGE_CLI_NO_VERSION_WARN=1` to silence it.

## Specific tasks

* **Element locator strategies** [references/element-locators.md](references/element-locators.md)
* **Running custom code** [references/running-code.md](references/running-code.md)
* **Browser session management** [references/session-management.md](references/session-management.md)
* **Storage state (cookies, localStorage)** [references/storage-state.md](references/storage-state.md)
* **Screenshots and PDF** [references/screenshots-pdf.md](references/screenshots-pdf.md)
* **Network listening** [references/network-listening.md](references/network-listening.md)
* **Dual-mode (browser + requests)** [references/dual-mode.md](references/dual-mode.md)

## Feishu → Markdown (`md` command)

```bash
drissionpage-cli md https://<company>.feishu.cn/docx/<token> [out_dir]
drissionpage-cli md https://<company>.feishu.cn/wiki/<token> ./output
drissionpage-cli md https://<company>.feishu.cn/docx/<token> --save-html
```

Converts a Feishu document to Markdown. Captures full network traffic on page
load — the complete document block tree is embedded in Feishu's SSR HTML as
`window.DATA.clientVars.data.block_map`. No scrolling or DOM scraping needed.

Output layout:
```
out_dir/
  Title/
    Title.md        ← Markdown with local references
    images/
      img_001.png   ← document images and file cover thumbnails
    files/
      report.pdf    ← file attachments if captured in traffic
```

### Supported block types

| Block | Feishu name | Markdown output |
|---|---|---|
| `heading1`–`heading9` | 标题1–9 | `#`–`######` (H7–H9 map to H6) |
| `text` | 正文 | paragraph |
| `bullet` | 无序列表 | `- item` |
| `ordered` | 有序列表 | `1. item` |
| `todo` | 任务列表 | `- [ ] item` / `- [x] item` |
| `code` | 代码块 | fenced ` ``` ` block |
| `quote_container` | 引用块 | `> blockquote` |
| `callout` | 高亮块 | `> highlighted text` |
| `divider` | 分隔线 | `---` |
| `image` | 图片 | `![alt](images/img_NNN.ext)` — saved locally |
| `file` | 文件 | `> 📎 [name](files/name)` if captured; metadata + cover thumbnail if not |
| `table` | 表格 | GFM pipe table |
| `grid` / `grid_column` | 分栏 | columns rendered inline (no visual columns) |
| `bookmark` | 链接 | `[title](url)` inline link |
| `synced_source` | 同步块 | content rendered inline (same as regular blocks) |
| `whiteboard` | 绘图/思维导图/流程图/UML图 | `![diagram](images/whiteboard_NNN.png)` — screenshot of rendered canvas |
| `page` | 子页面引用 | `> 📄 title` |

### Inline formatting

**bold**, *italic*, ***bold italic***, `code`, ~~strikethrough~~, [links](url) — all decoded from Quill/Etherpad attributed text.

### Known limitations

| Block | Feishu name | Reason |
|---|---|---|
| `whiteboard` | 绘图/思维导图/流程图/UML | Screenshotted via live browser (WASM renderer). Fallback `> 🎨 [not captured]` if the element was not rendered (empty whiteboard or scroll timing). |
| `equation` | 公式 | `$$\nlatex\n$$` block math; inline `$latex$` in text paragraphs |
| `button` | 按钮 | Interactive UI element; no text equivalent |
| `comment` | 评论/划线 | Annotation layer; not in block_map |
| Old DOC format | `wikcn…` wiki URLs | Different flat-text structure; not supported |
| Large docs (>239 blocks) | — | Feishu SSR caps initial payload; truncation warning added |

### File attachments

Files in traffic are saved to `files/`. Cover thumbnails (PNG previews) are
always captured and shown as inline images. The actual file is only captured
if the browser downloaded it (small files may be auto-fetched; large PDFs usually are not).

Options:
- `out_dir` — output directory (default: `.`)
- `--save-html` — also save the raw SSR HTML alongside the Markdown

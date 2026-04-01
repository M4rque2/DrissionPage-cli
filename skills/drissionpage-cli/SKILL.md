---
name: drissionpage-cli
description: Automate browser interactions, scrape web pages and test with DrissionPage.
allowed-tools: Bash(drissionpage-cli:*) Bash(python:*) Bash(pip:*)
---

# Browser Automation with drissionpage-cli

## Quick start

```bash
# open new browser
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
# Run in headed mode (browser window visible)
drissionpage-cli open --headed
# Use persistent user profile
drissionpage-cli open --profile=/path/to/profile
# Use specific CDP port
drissionpage-cli open --port=9222
# Close the browser
drissionpage-cli close
# Delete user data for the default session
drissionpage-cli delete-data
```

## Snapshots

After each command, drissionpage-cli provides a snapshot of the current page state.

```bash
> drissionpage-cli goto https://example.com
### Page
- Page URL: https://example.com/
- Page Title: Example Domain
### Snapshot
[Snapshot](.drissionpage-cli/snapshots/page-2026-02-14T19-22-42.html)
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

## Specific tasks

* **Element locator strategies** [references/element-locators.md](references/element-locators.md)
* **Running custom code** [references/running-code.md](references/running-code.md)
* **Browser session management** [references/session-management.md](references/session-management.md)
* **Storage state (cookies, localStorage)** [references/storage-state.md](references/storage-state.md)
* **Screenshots and PDF** [references/screenshots-pdf.md](references/screenshots-pdf.md)
* **Network listening** [references/network-listening.md](references/network-listening.md)
* **Dual-mode (browser + requests)** [references/dual-mode.md](references/dual-mode.md)

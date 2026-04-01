# Dual-Mode Operation

DrissionPage's unique feature: seamlessly switch between browser mode and HTTP requests mode.

## Overview

DrissionPage's `WebPage` class can operate in two modes:
- **`d` mode** (driver): Full Chromium browser with JavaScript support
- **`s` mode** (session): Lightweight HTTP requests (faster, no browser needed)

This is useful for workflows where you need browser interaction for some steps (e.g., login) and fast HTTP requests for others (e.g., bulk data fetching).

## Switching Modes via run-code

```bash
# Check current mode
drissionpage-cli run-code "
from DrissionPage import WebPage
wp = WebPage()
result = f'Current mode: {wp.mode}'
"

# Login in browser mode, then switch to session mode for scraping
drissionpage-cli run-code "
from DrissionPage import WebPage
wp = WebPage()

# Browser mode: handle login with JS
wp.get('https://example.com/login')
wp.ele('@name=username').input('admin')
wp.ele('@name=password').input('secret')
wp.ele('tag:button').click()

# Transfer cookies to session mode
wp.change_mode('s', go=False, copy_cookies=True)

# Session mode: fast scraping without browser overhead
results = []
for i in range(1, 10):
    wp.get(f'https://example.com/api/data?page={i}')
    results.append(wp.json)

result = f'Scraped {len(results)} pages'
"
```

## Cookie Synchronization

```bash
# Sync cookies from browser to session
drissionpage-cli run-code "
from DrissionPage import WebPage
wp = WebPage()
wp.get('https://example.com')
# ... do browser interactions ...
wp.cookies_to_session()
result = 'cookies synced to session'
"

# Sync cookies from session to browser
drissionpage-cli run-code "
from DrissionPage import WebPage
wp = WebPage()
wp.change_mode('s')
wp.get('https://example.com')
wp.cookies_to_browser()
wp.change_mode('d')
result = 'cookies synced to browser'
"
```

## Use Cases

### 1. Login + API Scraping

Browser for login (handles CAPTCHA, JS challenges), then session for fast API calls.

### 2. Dynamic + Static Content

Browser for pages requiring JavaScript rendering, session for static HTML pages.

### 3. Performance Optimization

Session mode is significantly faster for bulk requests since it doesn't render pages.

## Notes

- `WebPage` is different from `ChromiumPage`. The CLI primarily uses `ChromiumPage`.
- For dual-mode workflows, use `run-code` with explicit `WebPage` instantiation.
- Cookie transfer between modes preserves authentication state.
- Session mode does not support JavaScript execution or element interaction beyond HTML parsing.

# Chrome 147+ Compatibility Fix: Wrong Tab Target

## Problem

On Chrome 147 (Windows), pages appeared squished into a ~100px strip at the bottom of the browser window.

## Root Cause

Chrome 147 on Windows started exposing `chrome://newtab-footer/` as a separate CDP `page` type target. This is a small sub-page rendered at the bottom of Chrome's New Tab page.

When DrissionPage enumerated available page targets to connect to, `chrome://newtab-footer/` appeared alongside `chrome://newtab/` in the target list. Depending on the order returned by the `/json` endpoint, DrissionPage could pick the footer sub-page as its default tab.

When the footer target was navigated to a real URL (e.g. `https://www.example.com`), the page content rendered inside the footer's tiny area (~100px at the bottom), while the main New Tab page continued to fill the rest of the window.

## How we found it

1. Initial hypothesis was that Chrome 147 broke the CDP viewport (`innerHeight` collapsed to ~56px when DevTools connected). We tried many `Emulation.setDeviceMetricsOverride` workarounds and even Win32 window resize hacks.
2. CDP screenshots always looked correct because `setDeviceMetricsOverride` overrides the **virtual** viewport used by CDP, not the actual window rendering.
3. Capturing the **real screen** (via `PIL.ImageGrab`) revealed the New Tab page was still showing in the main area with the target page squished at the bottom.
4. Checking which target DrissionPage connected to revealed `chrome://newtab-footer/` instead of `chrome://newtab/`.

## Fix (upstream)

Fixed in DrissionPage itself by [PR #665](https://github.com/g1879/DrissionPage/pull/665) (merged 2026-04-21), which filters the footer sub-page out of the candidate target list:

```python
tabs = [(i[_id], i['url']) for i in tabs
        if i['type'] in ('page', 'webview') and not i['url'].startswith('devtools://')
        and not i['url'].startswith('chrome://newtab-footer')]
```

### Which DrissionPage versions carry the fix

| Version | Has fix |
|---------|---------|
| 4.1.1.4 (latest stable) | No |
| 4.1.1.3 and older | No |
| 5.0.0b0, 5.0.0b1 and newer | Yes |

The 4.1.x line never received the backport; the fix only ships in the 5.0 pre-releases and later, where the code now lives in `DrissionPage/_browsers/chromium.py`.

### What drissionpage-cli does about it

drissionpage-cli previously monkey-patched `ChromiumBase._connect_browser` to replicate this filtering. That patch has been **removed** — the fix belongs upstream.

Instead, `drissionpage_cli/_compat.py` warns — once per run, on stderr — only when **both** conditions hold:

1. the running browser is Chrome `MIN_AFFECTED_CHROME_MAJOR` (147) or newer, and
2. the installed DrissionPage is older than `MIN_VERSION` (`5.0.0b0`).

Chrome 146 and older never expose the footer target, so those users see nothing. Because condition 1 needs a live browser, the check runs just after `_get_page()` connects, reading `page.browser_version` (`Browser.getVersion`'s `product` string, e.g. `Chrome/147.0.7300.0`) — no extra process spawn.

```
[warn] Chrome 152 exposes the chrome://newtab-footer target, and DrissionPage
4.1.1.2 is missing the fix for it (upstream PR #665) — the page may render
squished into a ~100px strip. Upgrade with
'pip install --upgrade --pre "DrissionPage>=5.0.0b0"'.
Set DRISSIONPAGE_CLI_NO_VERSION_WARN=1 to silence this.
```

If either version cannot be determined, the check stays silent rather than guessing.

Set `DRISSIONPAGE_CLI_NO_VERSION_WARN=1` to suppress the warning — appropriate on a platform where the footer target does not appear despite a new-enough Chrome.

When the fix reaches a stable DrissionPage release, lower `MIN_VERSION` in `drissionpage_cli/_compat.py` to that release.

## How Playwright avoids this

Playwright never picks from existing targets. It creates a fresh page via `Target.createTarget(url: 'about:blank')` and manages window sizing explicitly through `Browser.setWindowBounds` + `Emulation.setDeviceMetricsOverride` with platform-specific chrome insets (see `crPage.ts:_updateViewport()`).

## References

- [Chromium Issue 422318935](https://issues.chromium.org/issues/422318935) — Virtual screen change report

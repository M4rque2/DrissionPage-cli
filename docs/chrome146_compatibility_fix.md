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

## Fix

In `DrissionPage/_pages/chromium_base.py`, method `_connect_browser()`, filter out the footer sub-page from the target list:

```python
tabs = [(i[_id], i['url']) for i in tabs
        if i['type'] in ('page', 'webview') and not i['url'].startswith('devtools://')
        and not i['url'].startswith('chrome://newtab-footer')]
```

## How Playwright avoids this

Playwright never picks from existing targets. It creates a fresh page via `Target.createTarget(url: 'about:blank')` and manages window sizing explicitly through `Browser.setWindowBounds` + `Emulation.setDeviceMetricsOverride` with platform-specific chrome insets (see `crPage.ts:_updateViewport()`).

## References

- [Chromium Issue 422318935](https://issues.chromium.org/issues/422318935) — Virtual screen change report

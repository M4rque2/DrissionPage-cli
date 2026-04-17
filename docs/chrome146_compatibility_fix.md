# Chrome 146+ Compatibility Fixes

## Issue 1: Headless Virtual Screen (Chrome 135-138+)

### Problem

Chrome/Chromium switched headless mode from using the host system's physical screen parameters to a virtual headless screen (800x600, DPR 1.0). This was rolled out across platforms:

| Platform | Chrome Version |
|----------|---------------|
| Linux    | 135           |
| Windows  | 136           |
| macOS    | 138           |

Symptoms: pages rendering at 800x600, `Page.captureScreenshot` hanging, `--window-size` ignored in headless.

### Fix

In `DrissionPage/_pages/chromium_base.py`, method `_driver_init()`, add after `Emulation.setFocusEmulationEnabled`:

```python
self._driver.run('Emulation.setDeviceMetricsOverride',
                 width=0, height=0, deviceScaleFactor=1, mobile=False)
```

- `deviceScaleFactor=1` bypasses the `captureScreenshot` hang bug
- `width=0, height=0` tells Chrome to use the actual window dimensions
- Only needed for **headless** mode; headed mode is unaffected by this issue

### Alternative: `--screen-info` (Chrome 142+)

```
--screen-info={1920x1080}
```

---

## Issue 2: Wrong Tab Target on Chrome 147+ Windows (the real viewport bug)

### Problem

On Chrome 147 (Windows), pages appeared squished into a ~100px strip at the bottom of the browser window. This was initially misdiagnosed as a viewport/`setDeviceMetricsOverride` issue but turned out to be a **target selection bug**.

### Root Cause

Chrome 147 on Windows started exposing `chrome://newtab-footer/` as a separate CDP `page` type target. This is a small sub-page rendered at the bottom of Chrome's New Tab page.

When DrissionPage enumerated available page targets to connect to, `chrome://newtab-footer/` appeared alongside `chrome://newtab/` in the target list. Depending on the order returned by the `/json` endpoint, DrissionPage could pick the footer sub-page as its default tab.

When the footer target was navigated to a real URL (e.g. `https://www.toutiao.com`), the page content rendered inside the footer's tiny area (~100px at the bottom), while the main New Tab page continued to fill the rest of the window.

### How we found it

1. Initial hypothesis was that Chrome 147 broke the CDP viewport (`innerHeight` collapsed to ~56px when DevTools connected). We tried many `Emulation.setDeviceMetricsOverride` workarounds and even Win32 window resize hacks.
2. CDP screenshots always looked correct because `setDeviceMetricsOverride` overrides the **virtual** viewport used by CDP, not the actual window rendering.
3. Capturing the **real screen** (via `PIL.ImageGrab`) revealed the New Tab page was still showing in the main area with the target page squished at the bottom.
4. Checking which target DrissionPage connected to revealed `chrome://newtab-footer/` instead of `chrome://newtab/`.

### Fix

In `DrissionPage/_pages/chromium_base.py`, method `_connect_browser()`, filter out the footer sub-page from the target list:

```python
tabs = [(i[_id], i['url']) for i in tabs
        if i['type'] in ('page', 'webview') and not i['url'].startswith('devtools://')
        and i['url'] != 'chrome://newtab-footer/'
        and i['url'] != 'chrome://newtab-footer']
```

No changes to `_driver_init()` are needed for this issue. The `setDeviceMetricsOverride` call is **not required** for headed mode on any platform.

### Why the Linux patch appeared to work

On Linux with Chromium 147, the `setDeviceMetricsOverride` patch happened to work because Chromium on Linux either doesn't expose `chrome://newtab-footer/` as a separate page target, or the `/json` endpoint returns targets in a different order so DrissionPage picked the correct tab by luck.

### How Playwright avoids this

Playwright never picks from existing targets. It creates a fresh page via `Target.createTarget(url: 'about:blank')` and manages window sizing explicitly through `Browser.setWindowBounds` + `Emulation.setDeviceMetricsOverride` with platform-specific chrome insets (see `crPage.ts:_updateViewport()`).

## References

- [Chromium Issue 422318935](https://issues.chromium.org/issues/422318935) — Virtual screen change report
- [Chromium Issue 40534755](https://issues.chromium.org/issues/40534755) — `captureScreenshot` hangs with `deviceScaleFactor=0`
- [CDP Protocol: setDeviceMetricsOverride](https://chromedevtools.github.io/devtools-protocol/tot/Emulation/#method-setDeviceMetricsOverride)
- [Headless `--screen-info` Documentation](https://chromium.googlesource.com/chromium/src/+/main/components/headless/screen_info/README.md)

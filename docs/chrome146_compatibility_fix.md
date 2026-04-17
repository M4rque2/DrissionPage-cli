# Chrome 146+ Compatibility Issue: `Emulation.setDeviceMetricsOverride`

## Problem

DrissionPage fails or renders incorrectly with Chrome/Chromium versions 135+ (Linux), 136+ (Windows), and 138+ (macOS). Common symptoms include:

- Pages rendering at 800x600 regardless of window size configuration
- `Page.captureScreenshot` hanging indefinitely
- Grey/blank page content area
- `--window-size` flag being ignored in headless mode

## Root Cause

This is **not** a single breaking change, but the result of a multi-version architectural overhaul of Chromium's headless mode (Chrome 128-142).

### What Changed

Starting from Chrome 135 (Linux), Chromium's headless mode switched from using the **host system's physical screen parameters** to a **virtual headless screen** that is completely independent of any physical display.

| Platform | Chrome Version | Virtual Screen Activated |
|----------|---------------|--------------------------|
| Linux    | 135           | Yes                      |
| Windows  | 136           | Yes                      |
| macOS    | 138           | Yes                      |

The virtual headless screen defaults to:

- **Resolution:** 800x600 pixels
- **Device Scale Factor:** 1.0
- **Color Depth:** 24 bits
- **Work Area:** Entire display

### Before (Chrome <= 134 on Linux)

- Headless Chrome inherited the host system's physical screen parameters
- `window.devicePixelRatio` reflected the actual display's DPI
- `--window-size=1920,1080` worked as expected
- `deviceScaleFactor: 0` in CDP's `setDeviceMetricsOverride` meant "don't override, use system default" — which was the physical display's scale factor

### After (Chrome >= 135 on Linux)

- Headless Chrome uses a virtual screen (800x600, DPR=1.0)
- `--window-size` is **ignored** in headless mode
- Browser chrome (toolbar, ~124px) is rendered even in headless, reducing effective viewport
- `deviceScaleFactor: 0` still means "don't override" but now refers to the virtual screen's default, interacting poorly with the changed geometry

### Why It Breaks

DrissionPage did not previously call `Emulation.setDeviceMetricsOverride`, relying on implicit screen parameters. With the virtual screen change:

1. The "system default" that tools relied on fundamentally changed (from physical display to 800x600 virtual)
2. A long-standing Chromium bug ([issue 40534755](https://issues.chromium.org/issues/40534755)) causes `Page.captureScreenshot` to **hang** when `deviceScaleFactor` is 0
3. Race conditions in rendering ([issue 426958509](https://issues.chromium.org/issues/426958509)) become more likely with mismatched emulation dimensions

## The Fix

In `DrissionPage/_pages/chromium_base.py`, method `_driver_init()`, add after `Emulation.setFocusEmulationEnabled`:

```python
self._driver.run('Emulation.setDeviceMetricsOverride',
                 width=0, height=0, deviceScaleFactor=1, mobile=False)
```

### Why This Works

- **`deviceScaleFactor=1`** (instead of 0) actively engages the device metrics override, bypassing the `captureScreenshot` hang bug and establishing a deterministic rendering context
- **`width=0, height=0`** tells Chrome to use the actual window dimensions rather than overriding them
- **`mobile=False`** keeps desktop rendering mode

## Alternative Approaches

### 1. `--screen-info` Command Line Switch (Chrome 142+)

Configure the virtual headless screen at launch:

```
--screen-info={1920x1080}
```

Or with custom DPI:

```
--screen-info={3840x2160 devicePixelRatio=2.0}
```

### 2. Full Viewport Override via CDP

For explicit control over the rendering viewport:

```python
page.run_cdp('Emulation.setDeviceMetricsOverride',
             width=1920, height=1080, deviceScaleFactor=1, mobile=False)
```

## Impact on Other Tools

This is not DrissionPage-specific. The same issue affects:

- **Selenium** — Workaround: `executeCdpCommand("Emulation.setDeviceMetricsOverride", ...)` with explicit `deviceScaleFactor: 1`
- **Puppeteer** — Users relying on `--window-size` or default viewport broken; `page.setViewport()` with explicit dimensions works
- **Playwright** — Less affected (always sets explicit viewport defaulting to 1280x720), but `deviceScaleFactor: 0` users impacted
- **Robot Framework / WebDriverIO** — Multiple reports of 800x600 viewport in CI/CD after Chrome upgrades

## Chromium Team Position

The Chromium team considers this **intended behavior** (Won't Fix). The official recommendation is to use `--screen-info` or explicit `setDeviceMetricsOverride` calls.

## References

- [Chromium Issue 422318935](https://issues.chromium.org/issues/422318935) — Main report, official explanation from Chromium team
- [Chromium Issue 364514022](https://issues.chromium.org/issues/364514022) — Viewport dimensions problem, confirmed "intended behavior"
- [Chromium Issue 362522328](https://issues.chromium.org/issues/362522328) — `--window-size` ignored in headless
- [Chromium Issue 40534755](https://issues.chromium.org/issues/40534755) — `captureScreenshot` hangs with `deviceScaleFactor=0`
- [Chromium Issue 40535224](https://issues.chromium.org/issues/40535224) — `setDeviceMetricsOverride` doesn't ignore `deviceScaleFactor=0`
- [CDP Protocol: setDeviceMetricsOverride](https://chromedevtools.github.io/devtools-protocol/tot/Emulation/#method-setDeviceMetricsOverride)
- [Headless `--screen-info` Documentation](https://chromium.googlesource.com/chromium/src/+/main/components/headless/screen_info/README.md)
- [Chromium Headless Default Commit](https://chromium.googlesource.com/chromium/src/+/b9b39a430f71c710d16aafcc67278ef77440c18d)

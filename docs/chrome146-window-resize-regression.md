# Chrome 146: Browser.getWindowForTarget / setWindowBounds Broken on Windows

## Summary

Chrome 146 on Windows introduced a regression that breaks all CDP window-management
commands. The `resize` CLI command fails on Chrome 146 and 147 (current stable as of
April 2026). Chrome 127 is confirmed working.

---

## Affected Commands

| drissionpage-cli command | DrissionPage API | Broken CDP call |
|---|---|---|
| `resize <width> <height>` | `page.set.window.size()` | `Browser.getWindowForTarget` |
| (internal) | `page.set.window.max()` | `Browser.getWindowForTarget` |
| (internal) | `page.set.window.mini()` | `Browser.getWindowForTarget` |
| (internal) | `page.set.window.full()` | `Browser.getWindowForTarget` |
| (internal) | `page.set.window.normal()` | `Browser.getWindowForTarget` |

---

## Error Observed

```
Error: 获取窗口信息失败 (Failed to get window info)
Version: 4.1.1.2
Traceback:
  File "...setter.py", line 480, in _get_info
    raise RuntimeError(_S._lang.join(_S._lang.GET_WINDOW_SIZE_FAILED))
```

The underlying CDP error returned by Chrome 146:

```
Browser window not found
Command: Browser.getWindowForTarget
```

Both `Browser.getWindowForTarget` (with and without explicit `targetId`) and
`Browser.getWindowBounds` return `"Browser window not found"` unconditionally, even
though Chrome is running in headed mode with a visible window.

`Browser.setWindowBounds` is equally broken since it depends on a `windowId` obtained
from `getWindowForTarget`.

---

## Root Cause

Two Chromium changes collided in Chrome 146:

**1. "Bedrock" BrowserList migration**
Chromium is migrating from the old `BrowserList` to a new
`BrowserWindowInterface` / `ForEachCurrentBrowserWindowInterfaceOrderedByActivation`
abstraction. The new iterator only enumerates fully-registered, active windows and
excludes windows in certain startup or WebUI states. In Chrome 146 on Windows, the
CDP handler's window lookup via this new iterator fails to locate the tab's
`WebContents`, even for normal `data:` and `https:` pages.

The relevant `browser_handler.cc` code (commit `10be28b`, Apr 8 2026):
```cpp
ForEachCurrentBrowserWindowInterfaceOrderedByActivation(
    [web_contents, &found_browser](BrowserWindowInterface* bwi) {
        int tab_index = bwi->GetTabStripModel()
                           ->GetIndexOfWebContents(web_contents);
        if (tab_index != TabStripModel::kNoTab) {
            found_browser = bwi;
            return false;
        }
        return true;
    });
if (!found_browser)
    return Response::ServerError("Browser window not found");
```

**2. `--user-data-dir` security enforcement (Chrome 136+, hardened in 146)**
Chrome 136 started blocking `--remote-debugging-port` when using the default OS
profile path. In the resulting "degraded" remote-debugging mode the initial tab may
land in a WebUI/NTP host whose `WebContents` is not registered in the `TabStripModel`,
compounding the Bedrock lookup failure.

---

## Confirmed Version Matrix

| Chrome version | `Browser.getWindowForTarget` | `resize` command |
|---|---|---|
| 127 | ✅ Works | ✅ Passes |
| 145 | ✅ Works (reported by others) | ✅ Should pass |
| 146 | ❌ "Browser window not found" | ❌ Fails |
| 147 (stable, Apr 7 2026) | ❌ Not fixed | ❌ Fails |

---

## What Still Works

These CDP commands are unaffected and can be used as viewport-only alternatives:

| CDP command | Effect |
|---|---|
| `Emulation.setVisibleSize` | Resizes the rendering viewport (not the OS window frame) |
| `Emulation.setDeviceMetricsOverride` | Overrides device metrics including viewport size |

Note: these resize the *viewport* (what CSS media queries and `window.innerWidth` see),
not the actual OS window. For most web-automation scenarios this is sufficient.

---

## Chromium Bug

- **Issue:** [#499572769](https://issues.chromium.org/issues/499572769)
- **Status:** Duplicate (merged into a parent tracking bug), Priority P2
- **Filed:** April 9, 2026 (two days after Chrome 147 shipped — not in scope for 147)
- **Fix shipped:** Not yet as of April 13, 2026

---

## Workaround Options (for future implementation)

### Option A — CLI-only try/except in `cmd_resize` (recommended)
Try `page.set.window.size()` first; catch `RuntimeError`; fall back to
`page._run_cdp('Emulation.setVisibleSize', width=w, height=h)`. Zero maintenance
burden — once Chrome fixes the regression the fallback silently stops being used.

### Option B — Fork DrissionPage
Patch `WindowSetter._get_info()` and `_perform()` in `_units/setter.py` with the same
try/fallback logic. Fixes the full `page.set.window.*` API surface, but requires
maintaining a forked package and reapplying patches on DrissionPage updates.

### Option C — Pin Chrome version
Use Chrome 127 or Chrome for Testing 145 (explicitly exempted from the
`--user-data-dir` enforcement). Not viable long-term.

---

## Related Documentation

- [`chrome136-remote-debugging-restriction.md`](chrome136-remote-debugging-restriction.md) — the `--user-data-dir` enforcement that contributed to this regression

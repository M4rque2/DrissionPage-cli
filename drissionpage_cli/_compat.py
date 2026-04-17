"""Runtime patches for DrissionPage compatibility with newer Chrome versions.

DrissionPage-cli does not own the DrissionPage codebase.  Rather than forking
or modifying installed files via post-install scripts, we apply targeted
monkey-patches at import time.  Each patch:

  - wraps (not replaces) the original method so upstream changes pass through,
  - is guarded by a version or feature check when possible,
  - is documented with the upstream issue link so it can be removed once fixed.

Call ``apply_patches()`` once, early in the process (e.g. at package import).
"""

_PATCHES_APPLIED = False

# ── Chrome 147+ newtab-footer target ─────────────────────────────────────
#
# Chrome 147 on Windows exposes ``chrome://newtab-footer/`` as a separate
# CDP ``page`` target.  DrissionPage's ``_connect_browser`` can pick it as
# the default tab, causing all subsequent page content to render inside the
# footer's tiny area (~100 px at the bottom of the window).
#
# Fix: wrap ``_connect_browser`` so that when it would auto-select a target,
# we do the selection ourselves (filtering out the footer) and hand the
# correct target_id to the original method, which then skips its own
# selection entirely.

_NEWTAB_FOOTER_URLS = frozenset((
    'chrome://newtab-footer/',
    'chrome://newtab-footer',
))


def _patch_connect_browser():
    from DrissionPage._pages.chromium_base import ChromiumBase

    _original = ChromiumBase._connect_browser

    def _patched(self, target_id=None):
        if target_id is None:
            target_id = _select_target(self)
        return _original(self, target_id)

    ChromiumBase._connect_browser = _patched


def _select_target(page_obj):
    """Replicate DrissionPage's default target selection with extra filtering.

    Returns the target_id of the best user-facing tab, skipping known
    Chrome-internal sub-pages.
    """
    browser = page_obj.browser

    if browser._ws_only:
        tabs = page_obj._run_cdp('Target.getTargets')['targetInfos']
        _id = 'targetId'
    else:
        tabs = browser._driver.get(
            f'http://{browser.address}/json').json()
        _id = 'id'

    tabs = [
        (i[_id], i['url']) for i in tabs
        if i['type'] in ('page', 'webview')
        and not i['url'].startswith('devtools://')
        and i['url'] not in _NEWTAB_FOOTER_URLS
    ]

    if not tabs:
        # Nothing matched after filtering; fall back to letting the
        # original method handle it (it will re-fetch and pick whatever
        # is available).
        return None

    target_id = None
    dialog = None

    if len(tabs) > 1:
        for k, t in enumerate(tabs):
            if t[1] == 'chrome://privacy-sandbox-dialog/notice':
                dialog = k
            elif target_id is None:
                target_id = t[0]
            if target_id and dialog is not None:
                break

        if dialog is not None:
            from DrissionPage._pages.chromium_base import close_privacy_dialog
            close_privacy_dialog(page_obj, tabs[dialog][0])
    else:
        target_id = tabs[0][0]

    return target_id


# ── Public entry point ────────────────────────────────────────────────────

def apply_patches():
    """Apply all runtime patches (idempotent)."""
    global _PATCHES_APPLIED
    if _PATCHES_APPLIED:
        return
    _PATCHES_APPLIED = True
    _patch_connect_browser()

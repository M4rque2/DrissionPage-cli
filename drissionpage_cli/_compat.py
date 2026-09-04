"""DrissionPage version compatibility checks.

DrissionPage-cli does not own the DrissionPage codebase, so browser
compatibility fixes belong upstream.  Instead of monkey-patching the installed
package, we detect versions that predate a known upstream fix and tell the
user to upgrade.

Call ``check_drissionpage_version(page)`` once a browser is connected, so the
running Chrome version can be taken into account.
"""

import os
import sys

# ── Chrome 147+ newtab-footer target ─────────────────────────────────────
#
# Chrome 147 (first seen on Windows) exposes ``chrome://newtab-footer/`` as a
# separate CDP ``page`` target.  Older DrissionPage releases can pick it as
# the default tab, causing all subsequent page content to render inside the
# footer's tiny area (~100 px at the bottom of the window).
#
# Fixed upstream by https://github.com/g1879/DrissionPage/pull/665, which
# filters the footer target out of the candidate tab list.  The fix ships in
# DrissionPage 5.0.0b0 and later; the 4.1.x line does not carry it.
#
# See docs/chrome146_compatibility_fix.md for the full investigation.

# DrissionPage release that first carries the fix.
MIN_VERSION = '5.0.0b0'

# First Chrome major version that exposes the footer target.  Chrome 146 and
# older cannot hit the bug, so there is nothing to warn about there.
MIN_AFFECTED_CHROME_MAJOR = 147

_WARNED = False


def _parse_version(text):
    """Parse a PEP 440-ish version into a sortable tuple.

    Handles the shapes DrissionPage actually publishes: ``4.1.1.4`` and
    ``5.0.0b1``.  A final release sorts after any pre-release of the same
    release number.  Returns ``None`` if *text* cannot be parsed.
    """
    import re

    m = re.match(r'^\s*v?(\d+(?:\.\d+)*)(?:(a|b|rc)(\d+))?', str(text))
    if not m:
        return None

    release = tuple(int(p) for p in m.group(1).split('.'))
    # Pad so 4.1 and 4.1.0.0 compare equal.
    release += (0,) * (4 - len(release)) if len(release) < 4 else ()

    if m.group(2) is None:
        # No pre-release marker: sorts after every pre-release.
        return release, (1,)
    stage = {'a': 0, 'b': 1, 'rc': 2}[m.group(2)]
    return release, (0, stage, int(m.group(3)))


def installed_version():
    """Return the installed DrissionPage version string, or None if unknown.

    Reads package metadata so we do not pay for importing DrissionPage, and
    falls back to ``DrissionPage.__version__`` if the metadata is missing
    (e.g. a source checkout on ``sys.path``).
    """
    try:
        from importlib.metadata import version, PackageNotFoundError
    except ImportError:  # Python 3.7 and older
        version = None

    if version is not None:
        try:
            return version('DrissionPage')
        except PackageNotFoundError:
            pass
        except Exception:
            pass

    try:
        import DrissionPage
        return getattr(DrissionPage, '__version__', None)
    except Exception:
        return None


def chrome_major_version(page):
    """Return the connected browser's major version as an int, or None.

    DrissionPage reports ``Browser.getVersion``'s ``product`` string, e.g.
    ``'Chrome/147.0.7300.0'``.
    """
    import re

    product = None
    for get in (lambda: page.browser_version, lambda: page.browser.version):
        try:
            product = get()
        except Exception:
            continue
        if product:
            break

    if not product:
        return None

    m = re.search(r'/(\d+)\.', str(product))
    return int(m.group(1)) if m else None


def check_drissionpage_version(page):
    """Warn once if this Chrome needs a newer DrissionPage than is installed.

    Only warns when the running browser is Chrome
    ``MIN_AFFECTED_CHROME_MAJOR`` or newer *and* the installed DrissionPage
    predates the upstream fix.  Emits a single line on stderr; set
    ``DRISSIONPAGE_CLI_NO_VERSION_WARN=1`` to silence it.
    """
    global _WARNED
    if _WARNED or os.environ.get('DRISSIONPAGE_CLI_NO_VERSION_WARN'):
        return
    _WARNED = True

    found = installed_version()
    if found is None:
        return

    parsed = _parse_version(found)
    minimum = _parse_version(MIN_VERSION)
    if parsed is None or parsed >= minimum:
        return

    chrome_major = chrome_major_version(page)
    if chrome_major is None or chrome_major < MIN_AFFECTED_CHROME_MAJOR:
        return

    print(
        f"[warn] Chrome {chrome_major} exposes the chrome://newtab-footer "
        f"target, and DrissionPage {found} is missing the fix for it "
        f"(upstream PR #665) — the page may render squished into a ~100px "
        f"strip. Upgrade with "
        f"'pip install --upgrade --pre \"DrissionPage>={MIN_VERSION}\"'. "
        f"Set DRISSIONPAGE_CLI_NO_VERSION_WARN=1 to silence this.",
        file=sys.stderr,
    )

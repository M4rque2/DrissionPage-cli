#!/usr/bin/env python3
"""
DrissionPage CLI - Command-line interface for browser automation with DrissionPage.

Mirrors the architecture of playwright-cli but uses DrissionPage as the backend.
Designed for token-efficient browser automation by coding agents.
"""

import argparse
import functools
import json
import os
import re
import shutil
import signal
import sys
import time
import traceback
from pathlib import Path
from urllib.parse import urlparse

from importlib.metadata import version as _pkg_version, PackageNotFoundError as _PackageNotFoundError
try:
    __version__ = _pkg_version("drissionpage-cli")
except _PackageNotFoundError:
    __version__ = "unknown"

# Apply runtime patches for Chrome compatibility before any DrissionPage usage.
from drissionpage_cli._compat import apply_patches as _apply_patches
_apply_patches()

# Session storage directory — home-based so profile and state persist across
# different working directories.
CLI_DIR = Path(os.environ.get("DRISSIONPAGE_CLI_DIR", str(Path.home() / ".drissionpage-cli")))
SESSIONS_FILE = CLI_DIR / "sessions.json"

# Default CDP port — drissionpage-cli owns this port exclusively
DEFAULT_PORT = int(os.environ.get("DRISSIONPAGE_CLI_PORT", "9222"))

_BROWSER_CANDIDATES = {
    "chrome": [
        "google-chrome-stable",
        "google-chrome",
        "chrome",
    ],
    "chromium": [
        "chromium-browser",
        "chromium",
    ],
    "edge": [
        "microsoft-edge-stable",
        "microsoft-edge",
        "msedge",
    ],
}

_BROWSER_SEARCH_ORDER = ["chrome", "chromium", "edge"]


def _find_browser_path(browser=None):
    """Return the path to a Chromium-family binary.

    *browser* can be ``"chrome"``, ``"chromium"``, or ``"edge"``.
    When *None*, tries all families in order and returns the first hit.
    """
    if browser:
        key = browser.lower()
        candidates = _BROWSER_CANDIDATES.get(key)
        if not candidates:
            raise RuntimeError(
                f"Unknown browser '{browser}'. "
                f"Choose from: {', '.join(_BROWSER_CANDIDATES)}"
            )
        for name in candidates:
            p = shutil.which(name)
            if p:
                return p
        raise RuntimeError(
            f"Browser '{browser}' not found on PATH. "
            f"Looked for: {', '.join(candidates)}"
        )
    for key in _BROWSER_SEARCH_ORDER:
        for name in _BROWSER_CANDIDATES[key]:
            p = shutil.which(name)
            if p:
                return p
    return None


def ensure_cli_dir():
    CLI_DIR.mkdir(parents=True, exist_ok=True)


def _load_sessions():
    """Load session registry from disk."""
    if SESSIONS_FILE.exists():
        try:
            return json.loads(SESSIONS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_sessions(sessions):
    """Persist session registry to disk."""
    ensure_cli_dir()
    SESSIONS_FILE.write_text(json.dumps(sessions, indent=2))


def _get_session_name(args):
    """Resolve the session name from args or env."""
    return getattr(args, "session", None) or os.environ.get(
        "DRISSIONPAGE_CLI_SESSION", "default"
    )


def _kill_session(sessions, session_name):
    """Try to kill a stale session's browser process."""
    info = sessions.get(session_name)
    if not info:
        return
    pid = info.get("pid")
    if pid:
        try:
            if sys.platform == "win32":
                import subprocess
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                )
            else:
                os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    del sessions[session_name]
    _save_sessions(sessions)


def _try_connect_existing(port, is_headless=False):
    """Try to connect to an existing Chrome on the given port via CDP.

    Returns a ChromiumPage if successful, or None if the port is not a
    controllable Chrome browser.  Never kills anything.
    """
    from DrissionPage import ChromiumOptions, ChromiumPage
    from DrissionPage._functions.settings import Settings
    from DrissionPage.errors import BrowserConnectError

    co = ChromiumOptions()
    co.set_address(f"127.0.0.1:{port}")
    co.existing_only(True)
    co.headless(is_headless)

    saved = Settings.browser_connect_timeout
    Settings.browser_connect_timeout = 3
    try:
        return ChromiumPage(addr_or_opts=co)
    except (BrowserConnectError, Exception):
        return None
    finally:
        Settings.browser_connect_timeout = saved


def _snap_name(path):
    """Return the snap package name if *path* is a snap binary, else None.

    Snap binaries live under ``/snap/bin/<name>`` (symlink to ``/usr/bin/snap``)
    or ``/snap/<name>/...``.  We check the original path (not resolved) because
    resolve() follows the symlink to ``/usr/bin/snap``.
    """
    if not path:
        return None
    p = str(Path(path))
    # /snap/bin/<name>
    if p.startswith("/snap/bin/"):
        return Path(p).name
    # /snap/<name>/current/... or /snap/<name>/<rev>/...
    parts = Path(p).parts
    if len(parts) >= 3 and parts[1] == "snap" and parts[2] != "bin":
        return parts[2]
    return None


def _cli_profile_path(browser_path=None):
    """Return the persistent profile directory managed by drissionpage-cli.

    Snap-packaged browsers cannot write to arbitrary home-directory paths due
    to AppArmor confinement, so we use ``~/snap/<name>/common/drissionpage-cli``
    instead.
    """
    name = _snap_name(browser_path)
    if name:
        return Path.home() / "snap" / name / "common" / "drissionpage-cli"
    return CLI_DIR / "profile"


def _get_page(session_name, create=False, options=None):
    """Get or create a ChromiumPage for the given session.

    Default behaviour: launch headed Chrome on port 9222 using the CLI-managed
    profile at ~/.drissionpage-cli/profile, so login state persists across runs.

    Pass options={"sandbox": True} for an isolated one-shot session.
    """
    from DrissionPage import ChromiumPage, ChromiumOptions
    from DrissionPage._functions.tools import port_is_using

    sessions = _load_sessions()
    info = sessions.get(session_name)

    if info:
        address = info["address"]
        ip, port_str = address.split(":")
        if port_is_using(ip, port_str):
            # Browser is alive — reconnect to it.
            co = ChromiumOptions()
            co.set_address(address)
            co.headless(info.get("headless", False))
            try:
                page = ChromiumPage(addr_or_opts=co)
                return page
            except Exception:
                _kill_session(sessions, session_name)
                sessions = _load_sessions()
                if not create:
                    raise RuntimeError(
                        f"Session '{session_name}' is no longer running. "
                        f"Use 'open' to start a new one."
                    )
        else:
            # Port not in use — browser is dead, clean up.
            _kill_session(sessions, session_name)
            sessions = _load_sessions()
            if not create:
                raise RuntimeError(
                    f"Session '{session_name}' is no longer running. "
                    f"Use 'open' to start a new one."
                )

    if not create:
        raise RuntimeError(
            f"No active session '{session_name}'. Use 'open' to start one."
        )

    # --- Create new session ---
    sandbox = options and options.get("sandbox", False)
    explicit_port = options and options.get("port")
    is_headless = options.get("headless", False) if options else False

    # Resolve browser binary first — profile path depends on whether it's a
    # snap package (AppArmor confinement restricts writable paths).
    browser_path = (options and options.get("browser_path")) or None
    if not browser_path:
        browser_path = _find_browser_path(
            options.get("browser") if options else None
        )

    co = ChromiumOptions()

    if browser_path:
        co.set_browser_path(browser_path)

    if sandbox:
        # Isolated profile: random port + temporary user data dir managed by DrissionPage.
        # State is not persisted — the temp dir is cleaned up when Chrome exits.
        co.auto_port()
    else:
        # Persistent profile: fixed port + CLI-managed profile.
        port = explicit_port or DEFAULT_PORT
        if port_is_using("127.0.0.1", str(port)):
            # Port occupied, no session record — try to connect via CDP.
            page = _try_connect_existing(port, is_headless)
            if page is not None:
                sessions[session_name] = {
                    "address": page.address,
                    "pid": page.process_id,
                    "started": time.time(),
                    "headless": is_headless,
                    "sandbox": False,
                }
                _save_sessions(sessions)
                return page
            raise RuntimeError(
                f"Port {port} is already in use but is not a controllable browser.\n"
                f"Options:\n"
                f"  - Stop whatever is using port {port}\n"
                f"  - Use a different port: drissionpage-cli open --port=<other>\n"
                f"  - Force-kill all CLI browsers: drissionpage-cli kill-all"
            )
        co.set_local_port(port)

        if options and options.get("user_data_path"):
            profile_path = options["user_data_path"]
        else:
            profile_path = str(_cli_profile_path(browser_path))
        Path(profile_path).mkdir(parents=True, exist_ok=True)
        co.set_user_data_path(profile_path)

    if options:
        if options.get("headless") is not None:
            co.headless(options["headless"])
        if options.get("proxy"):
            co.set_proxy(options["proxy"])
        if options.get("user_agent"):
            co.set_user_agent(options["user_agent"])
        if options.get("args"):
            for arg in options["args"]:
                co.set_argument(arg)

    page = ChromiumPage(addr_or_opts=co)

    # Record session info
    sessions[session_name] = {
        "address": page.address,
        "pid": page.process_id,
        "started": time.time(),
        "headless": options.get("headless", False) if options else False,
        "sandbox": sandbox,
    }
    _save_sessions(sessions)
    return page


def _format_snapshot(page, element=None, save=True):
    """Produce a text snapshot of the current page state, similar to playwright-cli's snapshot."""
    lines = []
    lines.append("### Page")
    lines.append(f"- Page URL: {page.url}")
    lines.append(f"- Page Title: {page.title}")
    lines.append("")

    if element:
        lines.append("### Element Snapshot")
        lines.append(f"- Tag: {element.tag}")
        lines.append(f"- Text: {element.text[:200]}")
        if element.attrs:
            for k, v in list(element.attrs.items())[:10]:
                lines.append(f"  @{k}={v}")
    else:
        lines.append("### Snapshot")
        if save:
            timestamp = time.strftime("%Y-%m-%dT%H-%M-%S")
            snap_file = Path.cwd() / f"page-{timestamp}.html"
            try:
                snap_file.write_text(page.html, encoding="utf-8")
                lines.append(f"[Snapshot]({snap_file})")
            except Exception:
                lines.append(f"- HTML length: {len(page.html):,} chars")
        else:
            lines.append(f"- HTML length: {len(page.html):,} chars")

    return "\n".join(lines)


def _ct_to_ext(ct: str) -> str:
    """Map a Content-Type value to a file extension."""
    ct = ct.lower().split(";")[0].strip()
    return {
        "text/html":                "html",
        "text/plain":               "txt",
        "text/css":                 "css",
        "text/javascript":          "js",
        "application/javascript":   "js",
        "application/x-javascript":"js",
        "application/json":         "json",
        "application/xml":          "xml",
        "text/xml":                 "xml",
        "image/png":                "png",
        "image/jpeg":               "jpg",
        "image/webp":               "webp",
        "image/gif":                "gif",
        "image/svg+xml":            "svg",
        "image/avif":               "avif",
        "image/bmp":                "bmp",
        "image/x-icon":             "ico",
        "image/vnd.microsoft.icon": "ico",
        "audio/mpeg":               "mp3",
        "audio/mp3":                "mp3",
        "audio/ogg":                "ogg",
        "audio/wav":                "wav",
        "audio/x-wav":              "wav",
        "audio/webm":               "webm",
        "audio/aac":                "aac",
        "audio/flac":               "flac",
        "audio/x-flac":             "flac",
        "video/mp4":                "mp4",
        "video/webm":               "webm",
        "video/ogg":                "ogv",
        "video/x-msvideo":          "avi",
        "video/quicktime":          "mov",
        "application/pdf":          "pdf",
        "font/woff":                "woff",
        "font/woff2":               "woff2",
        "application/font-woff":    "woff",
        "application/font-woff2":   "woff2",
        "application/octet-stream": "bin",
    }.get(ct, "bin")


def _response_filename(counter: int, url: str, ct: str) -> str:
    """Build a short, readable filename for a captured response."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    # Use last non-empty path segment, falling back to hostname
    segments = [s for s in parsed.path.split("/") if s]
    name = segments[-1] if segments else parsed.netloc
    # Strip existing extension so we control it via content-type
    name = re.sub(r"\.[^.]{1,6}$", "", name)
    # Sanitize: keep alphanum, dot, hyphen; collapse everything else to _
    name = re.sub(r"[^\w.\-]", "_", name)[:50].strip("_") or "response"
    ext = _ct_to_ext(ct)
    return f"{counter:04d}_{name}.{ext}"


def _collect_traffic(page, settle: float = 1.0, out_dir: Path = None) -> list:
    """
    Drain the network listener queue started before page.get().

    Call after page.get() returns.  ``settle`` gives async XHR/fetch calls
    a moment to complete before we declare the queue exhausted.

    If ``out_dir`` is given every response body is written as an individual
    file inside that directory and each record gets a ``"file"`` field with
    the relative filename.

    Returns a list of dicts (the traffic manifest), one per request/response.
    """
    _TEXT_TYPES = (
        "text/", "application/json", "application/javascript",
        "application/xml", "application/x-www-form-urlencoded",
    )

    time.sleep(settle)   # let in-flight async requests finish
    records = []
    counter = 0

    for packet in page.listen.steps(timeout=2):
        url = getattr(packet, "url", "") or ""

        # Only keep real HTTP(S) traffic — skip chrome://, data:, etc.
        if not url.startswith(("http://", "https://")):
            continue

        counter += 1
        resp   = getattr(packet, "response", None)
        method = getattr(packet, "method", "GET") or "GET"
        status = getattr(resp, "status", None) if resp else None

        ct = ""
        try:
            ct = (resp.headers.get("content-type") or "") if resp else ""
        except Exception:
            pass

        rec = {"url": url, "method": method, "status": status, "content_type": ct}

        # Request headers
        try:
            req = getattr(packet, "request", None)
            if req and getattr(req, "headers", None):
                rec["request_headers"] = dict(req.headers)
        except Exception:
            pass

        # Request body (POST etc.)
        try:
            req = getattr(packet, "request", None)
            post = getattr(req, "postData", None) or getattr(req, "body", None) if req else None
            if post:
                rec["request_body"] = post if isinstance(post, str) else post.decode("utf-8", errors="replace")
        except Exception:
            pass

        # Response headers
        try:
            if resp and getattr(resp, "headers", None):
                rec["response_headers"] = dict(resp.headers)
        except Exception:
            pass

        # Response body
        body = getattr(resp, "body", None) if resp else None
        if body is not None:
            if isinstance(body, (bytes, bytearray)):
                data: bytes = bytes(body)
            elif isinstance(body, str):
                data = body.encode("utf-8", errors="replace")
            elif isinstance(body, (dict, list)):
                # DrissionPage auto-parses JSON responses into Python objects
                data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            else:
                data = str(body).encode("utf-8", errors="replace")
            rec["size"] = len(data)

            if out_dir is not None:
                # Save every response as its own file
                fname = _response_filename(counter, url, ct)
                try:
                    (out_dir / fname).write_bytes(data)
                    rec["file"] = fname
                except Exception as e:
                    rec["file_error"] = str(e)
            else:
                # Inline text bodies only (no out_dir → old compact behaviour)
                is_text = any(t in ct.lower() for t in _TEXT_TYPES)
                if is_text:
                    rec["body"] = data.decode("utf-8", errors="replace")

        records.append(rec)

    return records


def _find_element(page, ref):
    """Find an element by reference. Supports CSS, XPath, DrissionPage locator syntax."""
    if not ref:
        return None
    # DrissionPage native locator syntax
    return page.ele(ref)


# ---------------------------------------------------------------------------
# Capture decorator
# ---------------------------------------------------------------------------

_MEDIA_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif", ".bmp", ".ico",
    ".mp3", ".mp4", ".ogg", ".ogv", ".wav", ".webm", ".aac", ".flac", ".avi", ".mov",
}


def _save_capture(page):
    """Drain the network listener and save traffic + HTML snapshot to disk."""
    timestamp = time.strftime("%Y-%m-%dT%H-%M-%S")
    capture_dir = Path.cwd() / f"capture-{timestamp}"
    capture_dir.mkdir(parents=True, exist_ok=True)

    try:
        (capture_dir / "snapshot.html").write_text(page.html, encoding="utf-8")
    except Exception as e:
        print(f"[warn] could not save snapshot HTML: {e}", file=sys.stderr)

    records = _collect_traffic(page, out_dir=capture_dir)

    try:
        (capture_dir / "traffic.json").write_text(
            json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8",
        )
    except Exception as e:
        print(f"[warn] could not save traffic manifest: {e}", file=sys.stderr)

    n_media = sum(
        1 for r in records
        if r.get("file") and Path(r["file"]).suffix.lower() in _MEDIA_EXTS
    )
    print(f"[capture] folder   → {capture_dir}")
    print(f"[capture] snapshot → snapshot.html")
    print(f"[capture] traffic  → traffic.json  ({len(records)} requests)")
    if n_media:
        print(f"[capture] media    → {n_media} files (images/audio/video)")


def _with_capture(fn):
    """Decorator: start network listener before, save capture after.

    Applied to commands that operate on an *existing* page (not ``open``).
    When ``args.capture`` is truthy the decorator brackets the handler
    with ``page.listen.start()`` / ``_save_capture(page)``.
    """

    @functools.wraps(fn)
    def wrapper(args):
        capture = getattr(args, "capture", False)
        if capture:
            session = _get_session_name(args)
            page = _get_page(session)
            page.listen.start()

        fn(args)

        if capture:
            _save_capture(page)

    return wrapper


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

_CONSOLE_CAPTURE_JS = """
if (!window.__dp_console_capture_installed) {
    window.__dp_console_logs = window.__dp_console_logs || [];
    ['log', 'info', 'warn', 'error', 'debug'].forEach(function(t) {
        var orig = console[t];
        console[t] = function() {
            var text = Array.prototype.slice.call(arguments).map(function(a) {
                try { return (typeof a === 'object') ? JSON.stringify(a) : String(a); }
                catch(e) { return String(a); }
            }).join(' ');
            window.__dp_console_logs.push({type: t === 'warn' ? 'warning' : t, text: text});
            orig.apply(console, arguments);
        };
    });
    window.__dp_console_capture_installed = true;
}
"""


def _inject_console_capture(page):
    """Inject console capture script into the page if not already installed."""
    try:
        page.run_js(_CONSOLE_CAPTURE_JS)
    except Exception:
        pass


def cmd_open(args):
    """Open a browser, optionally navigate to a URL."""
    session = _get_session_name(args)
    options = {
        "headless": getattr(args, "headless", False),
        "user_data_path": getattr(args, "profile", None),
        "port": getattr(args, "port", None),
        "sandbox": getattr(args, "sandbox", False),
        "browser": getattr(args, "browser", None),
    }
    page = _get_page(session, create=True, options=options)

    url = getattr(args, "url", None)
    capture = getattr(args, "capture", False)

    if url:
        if capture:
            page.listen.start()
        page.get(url)
        if capture:
            _save_capture(page)
    elif capture:
        print("[warn] --capture requires a URL to be useful; listener not started.",
              file=sys.stderr)

    _inject_console_capture(page)
    print(_format_snapshot(page, save=not capture))


@_with_capture
def cmd_goto(args):
    """Navigate to a URL."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.get(args.url)
    _inject_console_capture(page)
    print(_format_snapshot(page, save=not getattr(args, "capture", False)))


@_with_capture
def cmd_click(args):
    """Click an element."""
    session = _get_session_name(args)
    page = _get_page(session)
    ele = _find_element(page, args.ref)
    if not ele:
        print(f"Error: element not found: {args.ref}", file=sys.stderr)
        sys.exit(1)
    ele.click()
    print(_format_snapshot(page, save=not getattr(args, "capture", False)))


@_with_capture
def cmd_dblclick(args):
    """Double-click an element."""
    session = _get_session_name(args)
    page = _get_page(session)
    ele = _find_element(page, args.ref)
    if not ele:
        print(f"Error: element not found: {args.ref}", file=sys.stderr)
        sys.exit(1)
    ele.click(times=2)
    print(_format_snapshot(page, save=not getattr(args, "capture", False)))


@_with_capture
def cmd_right_click(args):
    """Right-click an element."""
    session = _get_session_name(args)
    page = _get_page(session)
    ele = _find_element(page, args.ref)
    if not ele:
        print(f"Error: element not found: {args.ref}", file=sys.stderr)
        sys.exit(1)
    ele.click(button="right")
    print(_format_snapshot(page, save=not getattr(args, "capture", False)))


@_with_capture
def cmd_type(args):
    """Type text into the focused or specified element."""
    session = _get_session_name(args)
    page = _get_page(session)
    if hasattr(args, "ref") and args.ref:
        ele = _find_element(page, args.ref)
        if not ele:
            print(f"Error: element not found: {args.ref}", file=sys.stderr)
            sys.exit(1)
        ele.input(args.text)
    else:
        page.actions.type(args.text)
    print(_format_snapshot(page, save=not getattr(args, "capture", False)))


@_with_capture
def cmd_fill(args):
    """Clear and fill text into an element."""
    session = _get_session_name(args)
    page = _get_page(session)
    ele = _find_element(page, args.ref)
    if not ele:
        print(f"Error: element not found: {args.ref}", file=sys.stderr)
        sys.exit(1)
    ele.clear()
    ele.input(args.text)
    if getattr(args, "submit", False):
        ele.input("\n")
    print(_format_snapshot(page, save=not getattr(args, "capture", False)))


@_with_capture
def cmd_hover(args):
    """Hover over an element."""
    session = _get_session_name(args)
    page = _get_page(session)
    ele = _find_element(page, args.ref)
    if not ele:
        print(f"Error: element not found: {args.ref}", file=sys.stderr)
        sys.exit(1)
    ele.hover()
    print(_format_snapshot(page, save=not getattr(args, "capture", False)))


@_with_capture
def cmd_drag(args):
    """Drag one element to another."""
    session = _get_session_name(args)
    page = _get_page(session)
    src = _find_element(page, args.start_ref)
    dst = _find_element(page, args.end_ref)
    if not src or not dst:
        print("Error: source or destination element not found", file=sys.stderr)
        sys.exit(1)
    src.drag_to(dst)
    print(_format_snapshot(page, save=not getattr(args, "capture", False)))


@_with_capture
def cmd_select(args):
    """Select an option in a dropdown."""
    session = _get_session_name(args)
    page = _get_page(session)
    ele = _find_element(page, args.ref)
    if not ele:
        print(f"Error: element not found: {args.ref}", file=sys.stderr)
        sys.exit(1)
    ele.select.by_text(args.value)
    print(_format_snapshot(page, save=not getattr(args, "capture", False)))


@_with_capture
def cmd_check(args):
    """Check a checkbox."""
    session = _get_session_name(args)
    page = _get_page(session)
    ele = _find_element(page, args.ref)
    if not ele:
        print(f"Error: element not found: {args.ref}", file=sys.stderr)
        sys.exit(1)
    if not ele.states.is_checked:
        ele.click()
    print(_format_snapshot(page, save=not getattr(args, "capture", False)))


@_with_capture
def cmd_uncheck(args):
    """Uncheck a checkbox."""
    session = _get_session_name(args)
    page = _get_page(session)
    ele = _find_element(page, args.ref)
    if not ele:
        print(f"Error: element not found: {args.ref}", file=sys.stderr)
        sys.exit(1)
    if ele.states.is_checked:
        ele.click()
    print(_format_snapshot(page, save=not getattr(args, "capture", False)))


def cmd_upload(args):
    """Upload a file."""
    session = _get_session_name(args)
    page = _get_page(session)
    ele = _find_element(page, args.ref)
    if not ele:
        print(f"Error: file input element not found: {args.ref}", file=sys.stderr)
        sys.exit(1)
    ele.input(args.file)
    print(_format_snapshot(page))


def cmd_snapshot(args):
    """Take a page or element snapshot."""
    session = _get_session_name(args)
    page = _get_page(session)
    ref = getattr(args, "ref", None)
    if ref:
        ele = _find_element(page, ref)
        if not ele:
            print(f"Error: element not found: {ref}", file=sys.stderr)
            sys.exit(1)
        print(_format_snapshot(page, element=ele))
    else:
        filename = getattr(args, "filename", None)
        if filename:
            Path(filename).write_text(page.html)
            print(f"Snapshot saved to {filename}")
        else:
            print(_format_snapshot(page))


def cmd_eval(args):
    """Evaluate JavaScript on the page or an element."""
    session = _get_session_name(args)
    page = _get_page(session)
    ref = getattr(args, "ref", None)
    if ref:
        ele = _find_element(page, ref)
        if not ele:
            print(f"Error: element not found: {ref}", file=sys.stderr)
            sys.exit(1)
        result = ele.run_js(args.expression)
    else:
        result = page.run_js(args.expression)
    if result is not None:
        if isinstance(result, (dict, list)):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(result)


def cmd_run_code(args):
    """Run a DrissionPage Python code snippet."""
    session = _get_session_name(args)
    page = _get_page(session)

    if getattr(args, "filename", None):
        code = Path(args.filename).read_text()
    else:
        code = args.code

    # Execute code with page in scope
    local_vars = {"page": page, "result": None}
    exec(code, {"__builtins__": __builtins__}, local_vars)
    if local_vars.get("result") is not None:
        result = local_vars["result"]
        if isinstance(result, (dict, list)):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(result)
    else:
        print(_format_snapshot(page))


def cmd_screenshot(args):
    """Take a screenshot."""
    session = _get_session_name(args)
    page = _get_page(session)

    filename = getattr(args, "filename", None)
    if not filename:
        timestamp = time.strftime("%Y-%m-%dT%H-%M-%S")
        ensure_cli_dir()
        filename = str(CLI_DIR / f"screenshot-{timestamp}.png")

    ref = getattr(args, "ref", None)
    if ref:
        ele = _find_element(page, ref)
        if not ele:
            print(f"Error: element not found: {ref}", file=sys.stderr)
            sys.exit(1)
        ele.get_screenshot(path=filename)
    else:
        page.get_screenshot(path=filename)

    print(f"Screenshot saved to {filename}")


def cmd_pdf(args):
    """Save page as PDF."""
    session = _get_session_name(args)
    page = _get_page(session)

    filename = getattr(args, "filename", None)
    if not filename:
        timestamp = time.strftime("%Y-%m-%dT%H-%M-%S")
        ensure_cli_dir()
        filename = str(CLI_DIR / f"page-{timestamp}.pdf")

    # Use CDP directly to avoid DrissionPage bug: open(..., 'wb', newline='\n')
    # is invalid since binary mode doesn't accept a newline argument.
    from base64 import b64decode
    r = page._run_cdp('Page.printToPDF', transferMode='ReturnAsBase64', printBackground=True)
    pdf_bytes = b64decode(r['data'])
    with open(filename, 'wb') as f:
        f.write(pdf_bytes)
    print(f"PDF saved to {filename}")


# --- Navigation ---


def cmd_go_back(args):
    """Go back."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.back()
    print(_format_snapshot(page))


def cmd_go_forward(args):
    """Go forward."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.forward()
    print(_format_snapshot(page))


def cmd_reload(args):
    """Reload the page."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.refresh()
    print(_format_snapshot(page))


# --- Keyboard ---


def cmd_press(args):
    """Press a key."""
    session = _get_session_name(args)
    page = _get_page(session)
    from DrissionPage.common import Keys

    key_map = {
        "enter": Keys.ENTER,
        "tab": Keys.TAB,
        "escape": Keys.ESCAPE,
        "backspace": Keys.BACKSPACE,
        "delete": Keys.DELETE,
        "arrowup": Keys.UP,
        "arrowdown": Keys.DOWN,
        "arrowleft": Keys.LEFT,
        "arrowright": Keys.RIGHT,
        "home": Keys.HOME,
        "end": Keys.END,
        "pageup": Keys.PAGE_UP,
        "pagedown": Keys.PAGE_DOWN,
        "space": Keys.SPACE,
        "f1": Keys.F1,
        "f2": Keys.F2,
        "f3": Keys.F3,
        "f4": Keys.F4,
        "f5": Keys.F5,
        "f6": Keys.F6,
        "f7": Keys.F7,
        "f8": Keys.F8,
        "f9": Keys.F9,
        "f10": Keys.F10,
        "f11": Keys.F11,
        "f12": Keys.F12,
    }
    key_name = args.key.lower()
    key = key_map.get(key_name, args.key)
    page.actions.key_down(key).key_up(key)
    print(_format_snapshot(page))


# --- Mouse ---


def cmd_mousemove(args):
    """Move mouse to coordinates."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.actions.move_to((args.x, args.y))
    print("Mouse moved to", args.x, args.y)


def cmd_mousedown(args):
    """Press mouse button down."""
    session = _get_session_name(args)
    page = _get_page(session)
    button = getattr(args, "button", "left") or "left"
    page.actions.hold(button)
    print(f"Mouse {button} button down")


def cmd_mouseup(args):
    """Release mouse button."""
    session = _get_session_name(args)
    page = _get_page(session)
    button = getattr(args, "button", "left") or "left"
    page.actions.release(button)
    print(f"Mouse {button} button up")


def cmd_scroll(args):
    """Scroll the page."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.scroll.down(args.dy)
    print(f"Scrolled by ({args.dx}, {args.dy})")


# --- Tabs ---


def cmd_tab_list(args):
    """List all tabs."""
    session = _get_session_name(args)
    page = _get_page(session)
    tab_ids = page.tab_ids
    print(f"Tabs ({len(tab_ids)}):")
    for i, tid in enumerate(tab_ids):
        tab = page.get_tab(tid)
        marker = " *" if tid == page.tab_id else ""
        print(f"  [{i}] {tab.title} - {tab.url}{marker}")


def cmd_tab_new(args):
    """Open a new tab."""
    session = _get_session_name(args)
    page = _get_page(session)
    url = getattr(args, "url", None) or ""
    tab = page.new_tab(url=url if url else None)
    print(f"New tab opened: {tab.url if hasattr(tab, 'url') else url}")


def cmd_tab_close(args):
    """Close a tab."""
    session = _get_session_name(args)
    page = _get_page(session)
    index = getattr(args, "index", None)
    if index is not None:
        tab_ids = page.tab_ids
        if 0 <= index < len(tab_ids):
            page.close_tabs(tab_ids[index])
        else:
            print(f"Error: tab index {index} out of range", file=sys.stderr)
            sys.exit(1)
    else:
        page.close_tabs(page.tab_id)
    print("Tab closed")


def cmd_tab_select(args):
    """Select a tab by index."""
    session = _get_session_name(args)
    page = _get_page(session)
    tab_ids = page.tab_ids
    if 0 <= args.index < len(tab_ids):
        tab = page.get_tab(tab_ids[args.index])
        print(_format_snapshot(tab))
    else:
        print(f"Error: tab index {args.index} out of range", file=sys.stderr)
        sys.exit(1)


# --- Resize ---


def cmd_resize(args):
    """Resize the browser window."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.set.window.size(args.width, args.height)
    print(f"Window resized to {args.width}x{args.height}")


# --- Dialog ---


def cmd_dialog_accept(args):
    """Accept a dialog."""
    session = _get_session_name(args)
    page = _get_page(session)
    text = getattr(args, "text", None)
    page.handle_alert(accept=True, send=text)
    print("Dialog accepted")


def cmd_dialog_dismiss(args):
    """Dismiss a dialog."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.handle_alert(accept=False)
    print("Dialog dismissed")


# --- Cookies ---


def cmd_cookie_list(args):
    """List cookies."""
    session = _get_session_name(args)
    page = _get_page(session)
    cookies = page.cookies(all_info=True)
    domain = getattr(args, "domain", None)
    if domain:
        cookies = [c for c in cookies if domain in c.get("domain", "")]
    for c in cookies:
        print(json.dumps(c, indent=2, ensure_ascii=False))


def cmd_cookie_get(args):
    """Get a cookie by name."""
    session = _get_session_name(args)
    page = _get_page(session)
    cookies = page.cookies(all_info=True)
    for c in cookies:
        if c.get("name") == args.name:
            print(json.dumps(c, indent=2, ensure_ascii=False))
            return
    print(f"Cookie '{args.name}' not found")


def cmd_cookie_set(args):
    """Set a cookie."""
    session = _get_session_name(args)
    page = _get_page(session)
    cookie = {"name": args.name, "value": args.value}
    if getattr(args, "domain", None):
        cookie["domain"] = args.domain
    if getattr(args, "path", None):
        cookie["path"] = args.path
    if getattr(args, "secure", False):
        cookie["secure"] = True
    if getattr(args, "httpOnly", False):
        cookie["httpOnly"] = True
    page.set.cookies(cookie)
    print(f"Cookie '{args.name}' set")


def cmd_cookie_delete(args):
    """Delete a cookie by name."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.set.cookies.remove(args.name)
    print(f"Cookie '{args.name}' deleted")


def cmd_cookie_clear(args):
    """Clear all cookies."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.set.cookies.clear()
    print("All cookies cleared")


# --- LocalStorage ---


def cmd_localstorage_list(args):
    """List localStorage entries."""
    session = _get_session_name(args)
    page = _get_page(session)
    result = page.run_js(
        "return JSON.stringify(Object.entries(localStorage))"
    )
    entries = json.loads(result) if result else []
    for key, value in entries:
        print(f"  {key}: {value}")


def cmd_localstorage_get(args):
    """Get a localStorage value."""
    session = _get_session_name(args)
    page = _get_page(session)
    result = page.run_js(f"return localStorage.getItem('{args.key}')")
    if result is not None:
        print(result)
    else:
        print(f"Key '{args.key}' not found in localStorage")


def cmd_localstorage_set(args):
    """Set a localStorage value."""
    session = _get_session_name(args)
    page = _get_page(session)
    value_escaped = args.value.replace("'", "\\'")
    page.run_js(f"localStorage.setItem('{args.key}', '{value_escaped}')")
    print(f"localStorage['{args.key}'] = '{args.value}'")


def cmd_localstorage_delete(args):
    """Delete a localStorage entry."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.run_js(f"localStorage.removeItem('{args.key}')")
    print(f"localStorage['{args.key}'] deleted")


def cmd_localstorage_clear(args):
    """Clear all localStorage."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.run_js("localStorage.clear()")
    print("localStorage cleared")


# --- SessionStorage ---


def cmd_sessionstorage_list(args):
    """List sessionStorage entries."""
    session = _get_session_name(args)
    page = _get_page(session)
    result = page.run_js(
        "return JSON.stringify(Object.entries(sessionStorage))"
    )
    entries = json.loads(result) if result else []
    for key, value in entries:
        print(f"  {key}: {value}")


def cmd_sessionstorage_get(args):
    """Get a sessionStorage value."""
    session = _get_session_name(args)
    page = _get_page(session)
    result = page.run_js(f"return sessionStorage.getItem('{args.key}')")
    if result is not None:
        print(result)
    else:
        print(f"Key '{args.key}' not found in sessionStorage")


def cmd_sessionstorage_set(args):
    """Set a sessionStorage value."""
    session = _get_session_name(args)
    page = _get_page(session)
    value_escaped = args.value.replace("'", "\\'")
    page.run_js(f"sessionStorage.setItem('{args.key}', '{value_escaped}')")
    print(f"sessionStorage['{args.key}'] = '{args.value}'")


def cmd_sessionstorage_delete(args):
    """Delete a sessionStorage entry."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.run_js(f"sessionStorage.removeItem('{args.key}')")
    print(f"sessionStorage['{args.key}'] deleted")


def cmd_sessionstorage_clear(args):
    """Clear all sessionStorage."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.run_js("sessionStorage.clear()")
    print("sessionStorage cleared")


# --- Network ---


def cmd_console(args):
    """List console messages."""
    session = _get_session_name(args)
    page = _get_page(session)
    # Ensure the interceptor is installed (no-op if already installed)
    _inject_console_capture(page)
    result = page.run_js("""
        return JSON.stringify(
            (window.__dp_console_logs || []).map(e => ({
                type: e.type, text: e.text
            }))
        )
    """)
    logs = json.loads(result) if result else []
    min_level = getattr(args, "level", None)
    levels = ["error", "warning", "info", "debug"]
    if min_level and min_level in levels:
        allowed = set(levels[: levels.index(min_level) + 1])
        logs = [l for l in logs if l.get("type", "info") in allowed]
    if logs:
        for log in logs:
            print(f"[{log.get('type', 'info')}] {log.get('text', '')}")
    else:
        print("No console messages captured yet. Console interceptor is now active — any future console.log/warn/error calls will be recorded.")


def cmd_network(args):
    """Show network requests (requires listener to be started)."""
    session = _get_session_name(args)
    page = _get_page(session)
    print("Network monitoring requires starting a listener first.")
    print("Use: drissionpage-cli run-code \"page.listen.start()\"")
    print("Then perform actions and use: drissionpage-cli run-code \"...")


# --- Session management ---


def cmd_list(args):
    """List all sessions."""
    sessions = _load_sessions()
    if not sessions:
        print("No active sessions")
        return
    print(f"Sessions ({len(sessions)}):")
    for name, info in sessions.items():
        started = time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(info.get("started", 0))
        )
        print(f"  {name}: address={info.get('address')} pid={info.get('pid')} started={started}")


def cmd_close(args):
    """Close the browser for a session."""
    session = _get_session_name(args)
    sessions = _load_sessions()

    if session not in sessions:
        print(f"Session '{session}' not found. Nothing to close.")
        return

    try:
        page = _get_page(session)
        page.quit()
    except Exception:
        pass

    del sessions[session]
    _save_sessions(sessions)
    print(f"Session '{session}' closed")


def cmd_close_all(args):
    """Close all browser sessions."""
    sessions = _load_sessions()
    for name in list(sessions.keys()):
        try:
            from DrissionPage import ChromiumPage, ChromiumOptions

            co = ChromiumOptions()
            co.set_address(sessions[name]["address"])
            page = ChromiumPage(addr_or_opts=co)
            page.quit()
        except Exception:
            pass
    _save_sessions({})
    print("All sessions closed")


def cmd_kill_all(args):
    """Kill all browser processes.

    Tries a graceful CDP quit first so Chrome can remove its SingletonLock and
    other profile lock files. Falls back to SIGTERM then SIGKILL only for
    processes that don't respond.
    """
    import subprocess

    sessions = _load_sessions()
    pids = [info["pid"] for info in sessions.values() if info.get("pid")]

    # Phase 1: graceful CDP quit — Chrome runs its own cleanup (removes SingletonLock etc.)
    for name, info in sessions.items():
        try:
            from DrissionPage import ChromiumPage, ChromiumOptions

            co = ChromiumOptions()
            co.set_address(info["address"])
            page = ChromiumPage(addr_or_opts=co)
            page.quit()
        except Exception:
            pass

    # Give Chrome up to 3 s to finish its cleanup after CDP close
    end = time.time() + 3
    alive = list(pids)
    while alive and time.time() < end:
        alive = [p for p in alive if _pid_alive(p)]
        if alive:
            time.sleep(0.1)

    # Phase 2: forcefully terminate any that are still alive
    if sys.platform == "win32":
        for pid in alive:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                )
            except Exception:
                pass
    else:
        for pid in alive:
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        time.sleep(1)
        # Phase 3: SIGKILL any that still didn't exit
        alive = [p for p in alive if _pid_alive(p)]
        for pid in alive:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    _save_sessions({})

    # Also clean up any orphaned chrome/chromium with remote debugging
    _kill_orphaned_browsers()
    print("All browser processes killed")


def _pid_alive(pid):
    """Return True if the process with the given PID is still running."""
    if sys.platform == "win32":
        import subprocess
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True,
            )
            return str(pid) in result.stdout
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _kill_orphaned_browsers():
    """Kill orphaned Chrome/Chromium processes with remote debugging ports.

    Works on macOS, Linux, and Windows.
    """
    import subprocess

    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["wmic", "process", "where",
                 "commandline like '%--remote-debugging-port%' and (name like '%chrome%' or name like '%chromium%')",
                 "get", "processid"],
                capture_output=True, text=True,
            )
            for line in result.stdout.strip().splitlines()[1:]:
                pid = line.strip()
                if pid.isdigit():
                    subprocess.run(
                        ["taskkill", "/F", "/PID", pid],
                        capture_output=True,
                    )
        except Exception:
            pass
    else:
        try:
            subprocess.run(
                ["pkill", "-TERM", "-f", "[Cc]hrome.*--remote-debugging-port"],
                capture_output=True,
            )
        except Exception:
            pass
        time.sleep(1)
        try:
            subprocess.run(
                ["pkill", "-KILL", "-f", "[Cc]hrome.*--remote-debugging-port"],
                capture_output=True,
            )
        except Exception:
            pass


def cmd_delete_data(args):
    """Delete user data for a session.

    For sandbox sessions: deletes the temporary profile.
    For CLI-profile sessions: closes the browser; use --reset-profile to also
    wipe ~/.drissionpage-cli/profile (this resets login state for ALL sessions).
    """
    import shutil

    session = _get_session_name(args)
    sessions = _load_sessions()
    info = sessions.get(session, {})

    # Close the browser first
    try:
        page = _get_page(session)
        sandbox_user_data = page.user_data_path if info.get("sandbox") else None
        page.quit()
    except Exception:
        sandbox_user_data = None

    if session in sessions:
        del sessions[session]
        _save_sessions(sessions)

    if info.get("sandbox") and sandbox_user_data and Path(sandbox_user_data).exists():
        shutil.rmtree(sandbox_user_data, ignore_errors=True)
        print(f"Deleted sandbox profile for '{session}' at {sandbox_user_data}")
        return

    # CLI-managed profile (default sessions)
    cli_profile = _cli_profile_path()
    if getattr(args, "reset_profile", False):
        if cli_profile.exists():
            shutil.rmtree(cli_profile, ignore_errors=True)
            print(f"CLI profile deleted: {cli_profile}")
            print("All login state has been reset. You will need to log in again.")
        else:
            print("No CLI profile found — nothing to delete.")
    else:
        print(f"Session '{session}' closed.")
        print(f"Login state retained at: {cli_profile}")
        print("To reset all login state: drissionpage-cli delete-data --reset-profile")


# --- State save/load ---


def cmd_state_save(args):
    """Save browser state (cookies + localStorage) to JSON."""
    session = _get_session_name(args)
    page = _get_page(session)

    filename = getattr(args, "filename", None)
    if not filename:
        timestamp = time.strftime("%Y-%m-%dT%H-%M-%S")
        ensure_cli_dir()
        filename = str(CLI_DIR / f"state-{timestamp}.json")

    cookies = page.cookies(all_info=True)
    local_storage = page.run_js(
        "return JSON.stringify(Object.entries(localStorage))"
    )
    session_storage = page.run_js(
        "return JSON.stringify(Object.entries(sessionStorage))"
    )

    state = {
        "url": page.url,
        "cookies": cookies if isinstance(cookies, list) else [],
        "localStorage": json.loads(local_storage) if local_storage else [],
        "sessionStorage": json.loads(session_storage) if session_storage else [],
    }

    Path(filename).write_text(json.dumps(state, indent=2, ensure_ascii=False))
    print(f"State saved to {filename}")


def cmd_state_load(args):
    """Load browser state from JSON."""
    session = _get_session_name(args)
    page = _get_page(session)

    state = json.loads(Path(args.filename).read_text())

    # Restore cookies
    for cookie in state.get("cookies", []):
        try:
            page.set.cookies(cookie)
        except Exception:
            pass

    # Restore localStorage
    for key, value in state.get("localStorage", []):
        value_escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        page.run_js(f"localStorage.setItem('{key}', '{value_escaped}')")

    # Restore sessionStorage
    for key, value in state.get("sessionStorage", []):
        value_escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        page.run_js(f"sessionStorage.setItem('{key}', '{value_escaped}')")

    print(f"State loaded from {args.filename}")

    # Navigate to saved URL if present
    url = state.get("url")
    if url and url != page.url:
        page.get(url)
        print(_format_snapshot(page))


# --- Install skills ---


def _detect_site(url: str):
    """Detect which converter to use for a URL.  Returns 'feishu', 'xhs', or None."""
    parsed = urlparse(url.split("?")[0])
    if (parsed.netloc.endswith(".feishu.cn")
            and ("/wiki/" in parsed.path or "/docx/" in parsed.path)):
        return "feishu"
    if ("xiaohongshu.com" in parsed.netloc
            and ("/explore/" in parsed.path or "/search_result/" in parsed.path)):
        return "xhs"
    return None


def cmd_md(args):
    """Convert a web page to Markdown with locally saved images."""
    url = getattr(args, "url", None)
    session = _get_session_name(args)

    try:
        page = _get_page(session)
    except RuntimeError:
        page = _get_page(session, create=True, options={"headless": False})

    if not url:
        url = page.url

    site = _detect_site(url)
    if not site:
        print(f"Error: '{url}' is not a supported page.", file=sys.stderr)
        print("Supported sites:", file=sys.stderr)
        print("  Feishu:       https://<company>.feishu.cn/wiki/<id>  or  /docx/<id>", file=sys.stderr)
        print("  Xiaohongshu:  https://www.xiaohongshu.com/explore/<note_id>", file=sys.stderr)
        print("Or omit the URL to convert the currently open page.", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    save_html = getattr(args, "save_html", False)

    if site == "feishu":
        from drissionpage_cli._feishu import convert
    else:
        from drissionpage_cli._xiaohongshu import convert

    convert(page, url=url, out_dir=out_dir, save_html=save_html)


def cmd_install(args):
    """Install skills for Claude Code or other agents."""
    if not getattr(args, "skills", False):
        print("Use --skills to install Claude Code skills")
        return

    # Install to .claude/skills/drissionpage-cli
    target = Path(".claude") / "skills" / "drissionpage-cli"
    source = Path(__file__).parent / "skills" / "drissionpage-cli"

    if not source.exists():
        print(f"Error: skills not found at {source}", file=sys.stderr)
        sys.exit(1)

    import shutil

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    print(f"Skills installed to {target}")


# --- Version ---


def cmd_version(args):
    """Print version."""
    print(f"drissionpage-cli v{__version__}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser():
    parser = argparse.ArgumentParser(
        prog="drissionpage-cli",
        description="DrissionPage CLI - Browser automation from the command line",
    )
    parser.add_argument("--version", action="store_true", help="Print version")
    parser.add_argument(
        "-s", "--session", default=None, help="Named browser session"
    )

    subparsers = parser.add_subparsers(dest="command")

    # open
    p = subparsers.add_parser("open", help="Open browser, optionally navigate to URL")
    p.add_argument("url", nargs="?", help="URL to navigate to")
    p.add_argument("--headless", action="store_true", help="Run in headless mode")
    p.add_argument("--profile", help="Custom user data directory (overrides system profile)")
    p.add_argument("--sandbox", action="store_true",
                   help="Isolated session: random port + temporary profile, no persistent state")
    p.add_argument("--port", type=int, help=f"CDP debugging port (default: {DEFAULT_PORT})")
    p.add_argument("--capture", action="store_true",
                   help="Capture full network traffic during page load; saves paired "
                        "page-<ts>.html and page-<ts>.traffic.json to the snapshots dir")
    p.add_argument("--browser", choices=["chrome", "chromium", "edge"],
                   help="Browser to use (default: auto-detect)")
    p.set_defaults(func=cmd_open)

    # goto
    p = subparsers.add_parser("goto", help="Navigate to a URL")
    p.add_argument("url", help="URL to navigate to")
    p.add_argument("--capture", action="store_true",
                   help="Capture network traffic triggered by this action")
    p.set_defaults(func=cmd_goto)

    # click
    p = subparsers.add_parser("click", help="Click an element")
    p.add_argument("ref", help="Element locator")
    p.add_argument("--capture", action="store_true",
                   help="Capture network traffic triggered by this action")
    p.set_defaults(func=cmd_click)

    # dblclick
    p = subparsers.add_parser("dblclick", help="Double-click an element")
    p.add_argument("ref", help="Element locator")
    p.add_argument("--capture", action="store_true",
                   help="Capture network traffic triggered by this action")
    p.set_defaults(func=cmd_dblclick)

    # right-click
    p = subparsers.add_parser("right-click", help="Right-click an element")
    p.add_argument("ref", help="Element locator")
    p.add_argument("--capture", action="store_true",
                   help="Capture network traffic triggered by this action")
    p.set_defaults(func=cmd_right_click)

    # type
    p = subparsers.add_parser("type", help="Type text")
    p.add_argument("text", help="Text to type")
    p.add_argument("ref", nargs="?", help="Element locator (optional)")
    p.add_argument("--capture", action="store_true",
                   help="Capture network traffic triggered by this action")
    p.set_defaults(func=cmd_type)

    # fill
    p = subparsers.add_parser("fill", help="Clear and fill text into element")
    p.add_argument("ref", help="Element locator")
    p.add_argument("text", help="Text to fill")
    p.add_argument("--submit", action="store_true", help="Press Enter after filling")
    p.add_argument("--capture", action="store_true",
                   help="Capture network traffic triggered by this action")
    p.set_defaults(func=cmd_fill)

    # hover
    p = subparsers.add_parser("hover", help="Hover over element")
    p.add_argument("ref", help="Element locator")
    p.add_argument("--capture", action="store_true",
                   help="Capture network traffic triggered by this action")
    p.set_defaults(func=cmd_hover)

    # drag
    p = subparsers.add_parser("drag", help="Drag element to another")
    p.add_argument("start_ref", help="Source element locator")
    p.add_argument("end_ref", help="Target element locator")
    p.add_argument("--capture", action="store_true",
                   help="Capture network traffic triggered by this action")
    p.set_defaults(func=cmd_drag)

    # select
    p = subparsers.add_parser("select", help="Select dropdown option")
    p.add_argument("ref", help="Select element locator")
    p.add_argument("value", help="Option text to select")
    p.add_argument("--capture", action="store_true",
                   help="Capture network traffic triggered by this action")
    p.set_defaults(func=cmd_select)

    # check / uncheck
    p = subparsers.add_parser("check", help="Check a checkbox")
    p.add_argument("ref", help="Checkbox element locator")
    p.add_argument("--capture", action="store_true",
                   help="Capture network traffic triggered by this action")
    p.set_defaults(func=cmd_check)

    p = subparsers.add_parser("uncheck", help="Uncheck a checkbox")
    p.add_argument("ref", help="Checkbox element locator")
    p.add_argument("--capture", action="store_true",
                   help="Capture network traffic triggered by this action")
    p.set_defaults(func=cmd_uncheck)

    # upload
    p = subparsers.add_parser("upload", help="Upload a file")
    p.add_argument("ref", help="File input element locator")
    p.add_argument("file", help="File path to upload")
    p.set_defaults(func=cmd_upload)

    # snapshot
    p = subparsers.add_parser("snapshot", help="Take page snapshot")
    p.add_argument("ref", nargs="?", help="Element locator (optional)")
    p.add_argument("--filename", help="Save snapshot to file")
    p.set_defaults(func=cmd_snapshot)

    # eval
    p = subparsers.add_parser("eval", help="Evaluate JavaScript")
    p.add_argument("expression", help="JavaScript expression")
    p.add_argument("ref", nargs="?", help="Element locator (optional)")
    p.set_defaults(func=cmd_eval)

    # run-code
    p = subparsers.add_parser("run-code", help="Run DrissionPage Python code")
    p.add_argument("code", nargs="?", help="Python code to run")
    p.add_argument("--filename", help="Python file to run")
    p.set_defaults(func=cmd_run_code)

    # screenshot
    p = subparsers.add_parser("screenshot", help="Take screenshot")
    p.add_argument("ref", nargs="?", help="Element locator (optional)")
    p.add_argument("--filename", help="Output filename")
    p.set_defaults(func=cmd_screenshot)

    # pdf
    p = subparsers.add_parser("pdf", help="Save page as PDF")
    p.add_argument("--filename", help="Output filename")
    p.set_defaults(func=cmd_pdf)

    # Navigation
    subparsers.add_parser("go-back", help="Go back").set_defaults(func=cmd_go_back)
    subparsers.add_parser("go-forward", help="Go forward").set_defaults(
        func=cmd_go_forward
    )
    subparsers.add_parser("reload", help="Reload page").set_defaults(func=cmd_reload)

    # Keyboard
    p = subparsers.add_parser("press", help="Press a key")
    p.add_argument("key", help="Key name (Enter, ArrowDown, etc.)")
    p.set_defaults(func=cmd_press)

    # Mouse
    p = subparsers.add_parser("mousemove", help="Move mouse")
    p.add_argument("x", type=int, help="X coordinate")
    p.add_argument("y", type=int, help="Y coordinate")
    p.set_defaults(func=cmd_mousemove)

    p = subparsers.add_parser("mousedown", help="Press mouse button")
    p.add_argument("button", nargs="?", default="left", help="Button (left/right)")
    p.set_defaults(func=cmd_mousedown)

    p = subparsers.add_parser("mouseup", help="Release mouse button")
    p.add_argument("button", nargs="?", default="left", help="Button (left/right)")
    p.set_defaults(func=cmd_mouseup)

    p = subparsers.add_parser("scroll", help="Scroll the page")
    p.add_argument("dx", type=int, help="Horizontal scroll")
    p.add_argument("dy", type=int, help="Vertical scroll")
    p.set_defaults(func=cmd_scroll)

    # Resize
    p = subparsers.add_parser("resize", help="Resize window")
    p.add_argument("width", type=int, help="Width in pixels")
    p.add_argument("height", type=int, help="Height in pixels")
    p.set_defaults(func=cmd_resize)

    # Dialog
    p = subparsers.add_parser("dialog-accept", help="Accept dialog")
    p.add_argument("text", nargs="?", help="Prompt text (optional)")
    p.set_defaults(func=cmd_dialog_accept)

    subparsers.add_parser("dialog-dismiss", help="Dismiss dialog").set_defaults(
        func=cmd_dialog_dismiss
    )

    # Tabs
    subparsers.add_parser("tab-list", help="List tabs").set_defaults(
        func=cmd_tab_list
    )

    p = subparsers.add_parser("tab-new", help="Open new tab")
    p.add_argument("url", nargs="?", help="URL to open")
    p.set_defaults(func=cmd_tab_new)

    p = subparsers.add_parser("tab-close", help="Close a tab")
    p.add_argument("index", nargs="?", type=int, help="Tab index")
    p.set_defaults(func=cmd_tab_close)

    p = subparsers.add_parser("tab-select", help="Select a tab")
    p.add_argument("index", type=int, help="Tab index")
    p.set_defaults(func=cmd_tab_select)

    # Cookies
    p = subparsers.add_parser("cookie-list", help="List cookies")
    p.add_argument("--domain", help="Filter by domain")
    p.set_defaults(func=cmd_cookie_list)

    p = subparsers.add_parser("cookie-get", help="Get a cookie")
    p.add_argument("name", help="Cookie name")
    p.set_defaults(func=cmd_cookie_get)

    p = subparsers.add_parser("cookie-set", help="Set a cookie")
    p.add_argument("name", help="Cookie name")
    p.add_argument("value", help="Cookie value")
    p.add_argument("--domain", help="Cookie domain")
    p.add_argument("--path", help="Cookie path")
    p.add_argument("--secure", action="store_true", help="Secure flag")
    p.add_argument("--httpOnly", action="store_true", help="HttpOnly flag")
    p.set_defaults(func=cmd_cookie_set)

    p = subparsers.add_parser("cookie-delete", help="Delete a cookie")
    p.add_argument("name", help="Cookie name")
    p.set_defaults(func=cmd_cookie_delete)

    subparsers.add_parser("cookie-clear", help="Clear all cookies").set_defaults(
        func=cmd_cookie_clear
    )

    # LocalStorage
    subparsers.add_parser("localstorage-list", help="List localStorage").set_defaults(
        func=cmd_localstorage_list
    )

    p = subparsers.add_parser("localstorage-get", help="Get localStorage value")
    p.add_argument("key", help="Key name")
    p.set_defaults(func=cmd_localstorage_get)

    p = subparsers.add_parser("localstorage-set", help="Set localStorage value")
    p.add_argument("key", help="Key name")
    p.add_argument("value", help="Value")
    p.set_defaults(func=cmd_localstorage_set)

    p = subparsers.add_parser("localstorage-delete", help="Delete localStorage entry")
    p.add_argument("key", help="Key name")
    p.set_defaults(func=cmd_localstorage_delete)

    subparsers.add_parser(
        "localstorage-clear", help="Clear localStorage"
    ).set_defaults(func=cmd_localstorage_clear)

    # SessionStorage
    subparsers.add_parser(
        "sessionstorage-list", help="List sessionStorage"
    ).set_defaults(func=cmd_sessionstorage_list)

    p = subparsers.add_parser("sessionstorage-get", help="Get sessionStorage value")
    p.add_argument("key", help="Key name")
    p.set_defaults(func=cmd_sessionstorage_get)

    p = subparsers.add_parser("sessionstorage-set", help="Set sessionStorage value")
    p.add_argument("key", help="Key name")
    p.add_argument("value", help="Value")
    p.set_defaults(func=cmd_sessionstorage_set)

    p = subparsers.add_parser(
        "sessionstorage-delete", help="Delete sessionStorage entry"
    )
    p.add_argument("key", help="Key name")
    p.set_defaults(func=cmd_sessionstorage_delete)

    subparsers.add_parser(
        "sessionstorage-clear", help="Clear sessionStorage"
    ).set_defaults(func=cmd_sessionstorage_clear)

    # Console / Network
    p = subparsers.add_parser("console", help="Show console messages")
    p.add_argument("level", nargs="?", help="Minimum level (error/warning/info/debug)")
    p.set_defaults(func=cmd_console)

    subparsers.add_parser("network", help="Show network requests").set_defaults(
        func=cmd_network
    )

    # Session management
    subparsers.add_parser("list", help="List all sessions").set_defaults(
        func=cmd_list
    )
    subparsers.add_parser("close", help="Close browser session").set_defaults(
        func=cmd_close
    )
    subparsers.add_parser("close-all", help="Close all sessions").set_defaults(
        func=cmd_close_all
    )
    subparsers.add_parser(
        "kill-all", help="Kill all browser processes"
    ).set_defaults(func=cmd_kill_all)
    p = subparsers.add_parser(
        "delete-data", help="Delete user data for session"
    )
    p.add_argument(
        "--reset-profile", action="store_true",
        help=f"Also wipe the CLI Chrome profile at ~/.drissionpage-cli/profile (resets all login state)"
    )
    p.set_defaults(func=cmd_delete_data)

    # State
    p = subparsers.add_parser("state-save", help="Save browser state")
    p.add_argument("filename", nargs="?", help="Output filename")
    p.set_defaults(func=cmd_state_save)

    p = subparsers.add_parser("state-load", help="Load browser state")
    p.add_argument("filename", help="State file to load")
    p.set_defaults(func=cmd_state_load)

    # Install
    p = subparsers.add_parser("install", help="Install skills or dependencies")
    p.add_argument("--skills", action="store_true", help="Install Claude Code skills")
    p.set_defaults(func=cmd_install)

    # md - Convert a web page to Markdown (Feishu, Xiaohongshu)
    p = subparsers.add_parser("md", help="Convert a web page to Markdown (Feishu, Xiaohongshu)")
    p.add_argument("url", nargs="?", help="Page URL (omit to use the currently open page)")
    p.add_argument("-o", "--out-dir", default=".", help="Output directory (default: .)")
    p.add_argument("--save-html", action="store_true", help="Also save the raw SSR HTML")
    p.set_defaults(func=cmd_md)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.version:
        cmd_version(args)
        return

    if not args.command:
        parser.print_help()
        return

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if os.environ.get("DRISSIONPAGE_CLI_DEBUG"):
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

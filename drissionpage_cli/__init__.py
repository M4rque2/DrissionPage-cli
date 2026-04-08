#!/usr/bin/env python3
"""
DrissionPage CLI - Command-line interface for browser automation with DrissionPage.

Mirrors the architecture of playwright-cli but uses DrissionPage as the backend.
Designed for token-efficient browser automation by coding agents.
"""

import argparse
import json
import os
import signal
import sys
import time
import traceback
from pathlib import Path

__version__ = "0.1.2"

# Session storage directory
CLI_DIR = Path(os.environ.get("DRISSIONPAGE_CLI_DIR", ".drissionpage-cli"))
SESSIONS_FILE = CLI_DIR / "sessions.json"


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
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
        except (ProcessLookupError, PermissionError):
            pass
    del sessions[session_name]
    _save_sessions(sessions)


def _get_page(session_name, create=False, options=None):
    """Get or create a ChromiumPage for the given session.

    DrissionPage manages browser instances via CDP. We track ports per session
    so that multiple named sessions can coexist.
    """
    from DrissionPage import ChromiumPage, ChromiumOptions

    sessions = _load_sessions()
    info = sessions.get(session_name)

    if info:
        # Try to reconnect to existing session
        co = ChromiumOptions()
        co.set_address(info["address"])
        try:
            page = ChromiumPage(addr_or_opts=co)
            if not create:
                return page
            # create=True but session is alive — close old one first
            try:
                page.quit()
            except Exception:
                pass
            _kill_session(sessions, session_name)
            sessions = _load_sessions()
        except Exception:
            # Browser is dead — clean up stale entry
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

    # Create new session
    co = ChromiumOptions()

    use_system_user_path = options and options.get("system_user_path")
    if use_system_user_path:
        # auto_port picks a free port; use_system_user_path then causes DrissionPage
        # to strip the --user-data-dir arg at launch, so Chrome uses the system profile.
        co.auto_port()
        co.use_system_user_path(True)
    else:
        co.auto_port()  # pick a free port to avoid conflicts with stale browsers

    if options:
        if options.get("headless") is not None:
            co.headless(options["headless"])
        if options.get("browser_path"):
            co.set_browser_path(options["browser_path"])
        if options.get("user_data_path"):
            co.set_user_data_path(options["user_data_path"])
        if options.get("proxy"):
            co.set_proxy(options["proxy"])
        if options.get("port"):
            co.set_local_port(options["port"])
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
    }
    _save_sessions(sessions)
    return page


def _format_snapshot(page, element=None):
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
        # Save snapshot to file
        timestamp = time.strftime("%Y-%m-%dT%H-%M-%S")
        snap_dir = CLI_DIR / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap_file = snap_dir / f"page-{timestamp}.html"
        try:
            snap_file.write_text(page.html)
            lines.append(f"[Snapshot]({snap_file})")
        except Exception:
            lines.append("[Snapshot could not be saved]")

    return "\n".join(lines)


def _find_element(page, ref):
    """Find an element by reference. Supports CSS, XPath, DrissionPage locator syntax."""
    if not ref:
        return None
    # DrissionPage native locator syntax
    return page.ele(ref)


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
        "headless": not getattr(args, "headed", False),
        "user_data_path": getattr(args, "profile", None),
        "port": getattr(args, "port", None),
        "system_user_path": getattr(args, "system_user_path", False),
    }
    page = _get_page(session, create=True, options=options)

    url = getattr(args, "url", None)
    if url:
        page.get(url)

    _inject_console_capture(page)
    print(_format_snapshot(page))


def cmd_goto(args):
    """Navigate to a URL."""
    session = _get_session_name(args)
    page = _get_page(session)
    page.get(args.url)
    _inject_console_capture(page)
    print(_format_snapshot(page))


def cmd_click(args):
    """Click an element."""
    session = _get_session_name(args)
    page = _get_page(session)
    ele = _find_element(page, args.ref)
    if not ele:
        print(f"Error: element not found: {args.ref}", file=sys.stderr)
        sys.exit(1)
    ele.click()
    print(_format_snapshot(page))


def cmd_dblclick(args):
    """Double-click an element."""
    session = _get_session_name(args)
    page = _get_page(session)
    ele = _find_element(page, args.ref)
    if not ele:
        print(f"Error: element not found: {args.ref}", file=sys.stderr)
        sys.exit(1)
    ele.click(times=2)
    print(_format_snapshot(page))


def cmd_right_click(args):
    """Right-click an element."""
    session = _get_session_name(args)
    page = _get_page(session)
    ele = _find_element(page, args.ref)
    if not ele:
        print(f"Error: element not found: {args.ref}", file=sys.stderr)
        sys.exit(1)
    ele.click(button="right")
    print(_format_snapshot(page))


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
        # Type into active element
        page.actions.type(args.text)
    print(_format_snapshot(page))


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
    print(_format_snapshot(page))


def cmd_hover(args):
    """Hover over an element."""
    session = _get_session_name(args)
    page = _get_page(session)
    ele = _find_element(page, args.ref)
    if not ele:
        print(f"Error: element not found: {args.ref}", file=sys.stderr)
        sys.exit(1)
    ele.hover()
    print(_format_snapshot(page))


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
    print(_format_snapshot(page))


def cmd_select(args):
    """Select an option in a dropdown."""
    session = _get_session_name(args)
    page = _get_page(session)
    ele = _find_element(page, args.ref)
    if not ele:
        print(f"Error: element not found: {args.ref}", file=sys.stderr)
        sys.exit(1)
    ele.select.by_text(args.value)
    print(_format_snapshot(page))


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
    print(_format_snapshot(page))


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
    print(_format_snapshot(page))


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
        print(f"Session '{session}' not found")
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
    """Kill all browser processes."""
    import subprocess

    sessions = _load_sessions()
    for name, info in sessions.items():
        pid = info.get("pid")
        if pid:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    _save_sessions({})
    # Also kill any orphaned chrome/chromium
    try:
        subprocess.run(
            ["pkill", "-f", "chrome.*--remote-debugging-port"],
            capture_output=True,
        )
    except Exception:
        pass
    print("All browser processes killed")


def cmd_delete_data(args):
    """Delete user data for a session."""
    session = _get_session_name(args)
    sessions = _load_sessions()
    info = sessions.get(session, {})

    # Try to close the browser first
    try:
        page = _get_page(session)
        user_data = page.user_data_path
        page.quit()
    except Exception:
        user_data = None

    if session in sessions:
        del sessions[session]
        _save_sessions(sessions)

    if user_data and Path(user_data).exists():
        import shutil

        shutil.rmtree(user_data, ignore_errors=True)
        print(f"Deleted user data for '{session}' at {user_data}")
    else:
        print(f"Deleted session '{session}' (no user data directory found)")


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
    p.add_argument("--headed", action="store_true", help="Run in headed mode")
    p.add_argument("--profile", help="User data directory path")
    p.add_argument("--system-user-path", action="store_true", dest="system_user_path",
                   help="Use system default Chrome profile (inherits login sessions)")
    p.add_argument("--port", type=int, help="CDP debugging port")
    p.set_defaults(func=cmd_open)

    # goto
    p = subparsers.add_parser("goto", help="Navigate to a URL")
    p.add_argument("url", help="URL to navigate to")
    p.set_defaults(func=cmd_goto)

    # click
    p = subparsers.add_parser("click", help="Click an element")
    p.add_argument("ref", help="Element locator")
    p.set_defaults(func=cmd_click)

    # dblclick
    p = subparsers.add_parser("dblclick", help="Double-click an element")
    p.add_argument("ref", help="Element locator")
    p.set_defaults(func=cmd_dblclick)

    # right-click
    p = subparsers.add_parser("right-click", help="Right-click an element")
    p.add_argument("ref", help="Element locator")
    p.set_defaults(func=cmd_right_click)

    # type
    p = subparsers.add_parser("type", help="Type text")
    p.add_argument("text", help="Text to type")
    p.add_argument("ref", nargs="?", help="Element locator (optional)")
    p.set_defaults(func=cmd_type)

    # fill
    p = subparsers.add_parser("fill", help="Clear and fill text into element")
    p.add_argument("ref", help="Element locator")
    p.add_argument("text", help="Text to fill")
    p.add_argument("--submit", action="store_true", help="Press Enter after filling")
    p.set_defaults(func=cmd_fill)

    # hover
    p = subparsers.add_parser("hover", help="Hover over element")
    p.add_argument("ref", help="Element locator")
    p.set_defaults(func=cmd_hover)

    # drag
    p = subparsers.add_parser("drag", help="Drag element to another")
    p.add_argument("start_ref", help="Source element locator")
    p.add_argument("end_ref", help="Target element locator")
    p.set_defaults(func=cmd_drag)

    # select
    p = subparsers.add_parser("select", help="Select dropdown option")
    p.add_argument("ref", help="Select element locator")
    p.add_argument("value", help="Option text to select")
    p.set_defaults(func=cmd_select)

    # check / uncheck
    p = subparsers.add_parser("check", help="Check a checkbox")
    p.add_argument("ref", help="Checkbox element locator")
    p.set_defaults(func=cmd_check)

    p = subparsers.add_parser("uncheck", help="Uncheck a checkbox")
    p.add_argument("ref", help="Checkbox element locator")
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
    subparsers.add_parser(
        "delete-data", help="Delete user data for session"
    ).set_defaults(func=cmd_delete_data)

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

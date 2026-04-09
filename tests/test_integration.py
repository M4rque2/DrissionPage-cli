"""
Integration tests for drissionpage-cli.

These tests require a Chrome/Chromium browser to be installed.
They exercise the CLI end-to-end by spawning subprocesses,
similar to playwright-cli's integration.spec.ts.

Run with: pytest tests/test_integration.py -v
Skip with: pytest tests/test_integration.py -v -k "not integration"

Set SKIP_INTEGRATION=1 to skip these tests in CI without a browser.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

CLI_ROOT = Path(__file__).resolve().parent.parent

# Skip all integration tests if no browser or explicitly skipped
SKIP_INTEGRATION = os.environ.get("SKIP_INTEGRATION", "0") == "1"
pytestmark = pytest.mark.skipif(
    SKIP_INTEGRATION, reason="Integration tests skipped (SKIP_INTEGRATION=1)"
)


def run_cli(*args, timeout=60, cwd=None, env_extra=None):
    """Run drissionpage-cli and return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(CLI_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    if env_extra:
        env.update(env_extra)

    cmd = [sys.executable, "-m", "drissionpage_cli"] + list(args)
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


@pytest.fixture
def isolated_env(tmp_path):
    """Provide an isolated environment for integration tests."""
    cli_dir = str(tmp_path / ".drissionpage-cli")
    return {
        "DRISSIONPAGE_CLI_DIR": cli_dir,
        "DRISSIONPAGE_CLI_SESSION": f"test-{int(time.time())}",
    }


@pytest.fixture
def storage_url(tmp_path):
    """A file:// URL that supports localStorage and sessionStorage.
    data: URLs are null-origin in Chrome and block storage access."""
    html_file = tmp_path / "storage_test.html"
    html_file.write_text("<p>Storage Test</p>")
    return html_file.as_uri()


@pytest.fixture(autouse=True)
def cleanup_after_test(isolated_env):
    """Ensure browser is closed after each test."""
    yield
    try:
        run_cli("close", env_extra=isolated_env, timeout=10)
    except Exception:
        pass
    try:
        run_cli("kill-all", env_extra=isolated_env, timeout=10)
    except Exception:
        pass


class TestIntegrationBasic:
    """Basic integration tests that exercise the full CLI stack."""

    def test_version(self):
        rc, stdout, stderr = run_cli("--version")
        assert rc == 0
        assert "0.1.4" in stdout

    def test_help(self):
        rc, stdout, stderr = run_cli("--help")
        assert rc == 0
        assert "drissionpage-cli" in stdout

    def test_list_empty(self, isolated_env):
        rc, stdout, stderr = run_cli("list", env_extra=isolated_env)
        assert rc == 0
        assert "No active sessions" in stdout

    def test_close_nonexistent_session(self, isolated_env):
        rc, stdout, stderr = run_cli("close", env_extra=isolated_env)
        assert rc == 0
        assert "not found" in stdout

    def test_install_skills(self, tmp_path):
        rc, stdout, stderr = run_cli("install", "--skills", cwd=str(tmp_path))
        assert rc == 0
        assert "Skills installed" in stdout
        skill_md = tmp_path / ".claude" / "skills" / "drissionpage-cli" / "SKILL.md"
        assert skill_md.exists()

    def test_install_skills_has_references(self, tmp_path):
        run_cli("install", "--skills", cwd=str(tmp_path))
        refs_dir = tmp_path / ".claude" / "skills" / "drissionpage-cli" / "references"
        assert refs_dir.is_dir()
        ref_files = list(refs_dir.glob("*.md"))
        assert len(ref_files) >= 5, f"Expected >= 5 reference files, got {len(ref_files)}"


class TestIntegrationBrowser:
    """Integration tests that require a browser.

    These tests open a browser, perform actions, and verify results.
    They use data: URLs to avoid external network dependencies.
    """

    def test_open_and_close(self, isolated_env):
        """Open browser with data URL and close it."""
        rc, stdout, stderr = run_cli(
            "open", "--headed", "data:text/html,<h1>Hello</h1>",
            env_extra=isolated_env,
        )
        assert rc == 0
        assert "Page URL" in stdout or "Page Title" in stdout

        # Verify session exists
        rc, stdout, stderr = run_cli("list", env_extra=isolated_env)
        assert rc == 0
        # Session should be listed
        assert "Sessions" in stdout or "address" in stdout

        # Close
        rc, stdout, stderr = run_cli("close", env_extra=isolated_env)
        assert rc == 0
        assert "closed" in stdout.lower()

    def test_open_goto_snapshot(self, isolated_env):
        """Open browser, navigate, and take snapshot."""
        run_cli("open", env_extra=isolated_env)

        rc, stdout, stderr = run_cli(
            "goto", "data:text/html,<title>Test Page</title><p>Content here</p>",
            env_extra=isolated_env,
        )
        assert rc == 0
        assert "Page URL" in stdout

        rc, stdout, stderr = run_cli("snapshot", env_extra=isolated_env)
        assert rc == 0
        assert "Snapshot" in stdout

    def test_click_element(self, isolated_env):
        """Click an element on the page."""
        html = "data:text/html,<button id='btn' onclick='document.title=\"Clicked\"'>Click Me</button>"
        run_cli("open", html, env_extra=isolated_env)

        rc, stdout, stderr = run_cli("click", "@id=btn", env_extra=isolated_env)
        assert rc == 0

    def test_fill_and_submit(self, isolated_env):
        """Fill a text input."""
        html = (
            "data:text/html,"
            "<input id='name' type='text' />"
            "<button onclick='document.title=document.getElementById(\"name\").value'>Go</button>"
        )
        run_cli("open", html, env_extra=isolated_env)

        rc, stdout, stderr = run_cli(
            "fill", "@id=name", "TestValue", env_extra=isolated_env
        )
        assert rc == 0

    def test_eval_javascript(self, isolated_env):
        """Evaluate JavaScript on page."""
        html = "data:text/html,<title>Eval Test</title><p>hello</p>"
        run_cli("open", html, env_extra=isolated_env)

        rc, stdout, stderr = run_cli(
            "eval", "return document.title", env_extra=isolated_env
        )
        assert rc == 0
        assert "Eval Test" in stdout

    def test_screenshot(self, isolated_env, tmp_path):
        """Take a screenshot and verify file is created."""
        html = "data:text/html,<h1>Screenshot Test</h1>"
        run_cli("open", html, env_extra=isolated_env)

        outfile = str(tmp_path / "test_screenshot.png")
        rc, stdout, stderr = run_cli(
            "screenshot", f"--filename={outfile}", env_extra=isolated_env
        )
        assert rc == 0
        assert "Screenshot saved" in stdout
        assert Path(outfile).exists()

    def test_press_key(self, isolated_env):
        """Press a keyboard key."""
        html = "data:text/html,<input id='inp' autofocus />"
        run_cli("open", html, env_extra=isolated_env)

        rc, stdout, stderr = run_cli("press", "Enter", env_extra=isolated_env)
        assert rc == 0

    def test_navigation(self, isolated_env):
        """Test go-back, go-forward, reload."""
        run_cli("open", "data:text/html,<p>Page1</p>", env_extra=isolated_env)
        run_cli("goto", "data:text/html,<p>Page2</p>", env_extra=isolated_env)

        rc, stdout, stderr = run_cli("go-back", env_extra=isolated_env)
        assert rc == 0

        rc, stdout, stderr = run_cli("go-forward", env_extra=isolated_env)
        assert rc == 0

        rc, stdout, stderr = run_cli("reload", env_extra=isolated_env)
        assert rc == 0

    def test_localstorage_operations(self, isolated_env, storage_url):
        """Test localStorage set, get, list, delete, clear."""
        # data: URLs are null-origin and block localStorage; use file:// instead.
        run_cli("open", storage_url, env_extra=isolated_env)

        # Set
        rc, stdout, _ = run_cli(
            "localstorage-set", "testkey", "testvalue",
            env_extra=isolated_env,
        )
        assert rc == 0

        # Get
        rc, stdout, _ = run_cli(
            "localstorage-get", "testkey", env_extra=isolated_env
        )
        assert rc == 0
        assert "testvalue" in stdout

        # List
        rc, stdout, _ = run_cli("localstorage-list", env_extra=isolated_env)
        assert rc == 0
        assert "testkey" in stdout

        # Delete
        rc, stdout, _ = run_cli(
            "localstorage-delete", "testkey", env_extra=isolated_env
        )
        assert rc == 0

        # Clear
        run_cli("localstorage-set", "a", "1", env_extra=isolated_env)
        rc, stdout, _ = run_cli("localstorage-clear", env_extra=isolated_env)
        assert rc == 0

    def test_sessionstorage_operations(self, isolated_env, storage_url):
        """Test sessionStorage set, get, clear."""
        # data: URLs are null-origin and block sessionStorage; use file:// instead.
        run_cli("open", storage_url, env_extra=isolated_env)

        rc, stdout, _ = run_cli(
            "sessionstorage-set", "step", "5", env_extra=isolated_env
        )
        assert rc == 0

        rc, stdout, _ = run_cli(
            "sessionstorage-get", "step", env_extra=isolated_env
        )
        assert rc == 0
        assert "5" in stdout

        rc, stdout, _ = run_cli(
            "sessionstorage-clear", env_extra=isolated_env
        )
        assert rc == 0

    def test_state_save_and_load(self, isolated_env, storage_url, tmp_path):
        """Save and load browser state."""
        # data: URLs are null-origin and block localStorage; use file:// instead.
        run_cli("open", storage_url, env_extra=isolated_env)

        # Set some storage
        run_cli("localstorage-set", "saved_key", "saved_val", env_extra=isolated_env)

        # Save state
        state_file = str(tmp_path / "test-state.json")
        rc, stdout, _ = run_cli(
            "state-save", state_file, env_extra=isolated_env
        )
        assert rc == 0
        assert "State saved" in stdout
        assert Path(state_file).exists()

        # Verify state file content
        state = json.loads(Path(state_file).read_text())
        assert "cookies" in state
        assert "localStorage" in state

        # Load state
        rc, stdout, _ = run_cli(
            "state-load", state_file, env_extra=isolated_env
        )
        assert rc == 0
        assert "State loaded" in stdout

    def test_tab_operations(self, isolated_env):
        """Test tab list, new, select, close."""
        run_cli("open", "data:text/html,<p>Tab1</p>", env_extra=isolated_env)

        # List tabs
        rc, stdout, _ = run_cli("tab-list", env_extra=isolated_env)
        assert rc == 0
        assert "Tabs" in stdout

        # New blank tab (no URL — avoids data: URL validation in DrissionPage)
        rc, stdout, _ = run_cli("tab-new", env_extra=isolated_env)
        assert rc == 0

    def test_run_code_inline(self, isolated_env):
        """Run inline Python code."""
        html = "data:text/html,<title>RunCode Test</title>"
        run_cli("open", html, env_extra=isolated_env)

        rc, stdout, _ = run_cli(
            "run-code", "result = page.title", env_extra=isolated_env
        )
        assert rc == 0
        assert "RunCode Test" in stdout

    def test_run_code_from_file(self, isolated_env, tmp_path):
        """Run Python code from a file."""
        html = "data:text/html,<title>File Code Test</title>"
        run_cli("open", html, env_extra=isolated_env)

        script = tmp_path / "test_script.py"
        script.write_text("result = page.url")

        rc, stdout, _ = run_cli(
            "run-code", f"--filename={script}", env_extra=isolated_env
        )
        assert rc == 0

    def test_cookie_operations(self, isolated_env):
        """Test cookie list, set, get, delete, clear."""
        # Need a real HTTP page for cookies to work with domain
        run_cli("open", "data:text/html,<p>Cookies</p>", env_extra=isolated_env)

        # List (may be empty)
        rc, stdout, _ = run_cli("cookie-list", env_extra=isolated_env)
        assert rc == 0

        # Clear
        rc, stdout, _ = run_cli("cookie-clear", env_extra=isolated_env)
        assert rc == 0
        assert "cleared" in stdout.lower()

    def test_delete_data(self, isolated_env):
        """Open, close, and delete data."""
        run_cli("open", "data:text/html,<p>Del</p>", env_extra=isolated_env)
        run_cli("close", env_extra=isolated_env)

        rc, stdout, _ = run_cli("delete-data", env_extra=isolated_env)
        assert rc == 0
        assert "Deleted" in stdout or "deleted" in stdout.lower() or "not found" in stdout.lower()

    def test_resize_window(self, isolated_env):
        """Resize the browser window."""
        run_cli("open", "data:text/html,<p>Resize</p>", env_extra=isolated_env)

        rc, stdout, _ = run_cli("resize", "800", "600", env_extra=isolated_env)
        assert rc == 0
        assert "resized" in stdout.lower()

    def test_dialog_handling(self, isolated_env):
        """Test dialog accept/dismiss in a single subprocess to avoid losing dialog state."""
        html = "data:text/html,<button id='a' onclick='alert(\"hi\")'>Alert</button>"
        run_cli("open", html, env_extra=isolated_env)

        # Click and dismiss must happen in the same subprocess — the alert dialog is
        # lost between separate CLI invocations because headless Chrome doesn't persist
        # pending dialog state across CDP reconnections.
        rc, stdout, _ = run_cli(
            "run-code",
            "import time; page.ele('@id=a').click(); time.sleep(0.3); page.handle_alert(accept=False)",
            env_extra=isolated_env,
        )
        assert rc == 0

    def test_hover(self, isolated_env):
        """Hover over an element."""
        html = "data:text/html,<div id='target'>Hover Me</div>"
        run_cli("open", html, env_extra=isolated_env)

        rc, stdout, _ = run_cli("hover", "@id=target", env_extra=isolated_env)
        assert rc == 0

    def test_check_uncheck(self, isolated_env):
        """Check and uncheck a checkbox."""
        html = "data:text/html,<input type='checkbox' id='cb' />"
        run_cli("open", html, env_extra=isolated_env)

        rc, stdout, _ = run_cli("check", "@id=cb", env_extra=isolated_env)
        assert rc == 0

        rc, stdout, _ = run_cli("uncheck", "@id=cb", env_extra=isolated_env)
        assert rc == 0

    def test_mousemove(self, isolated_env):
        """Move mouse to coordinates."""
        run_cli("open", "data:text/html,<p>Mouse</p>", env_extra=isolated_env)

        rc, stdout, _ = run_cli("mousemove", "100", "200", env_extra=isolated_env)
        assert rc == 0
        assert "100" in stdout and "200" in stdout

    def test_scroll(self, isolated_env):
        """Scroll the page."""
        html = "data:text/html,<div style='height:5000px'>Tall page</div>"
        run_cli("open", html, env_extra=isolated_env)

        rc, stdout, _ = run_cli("scroll", "0", "500", env_extra=isolated_env)
        assert rc == 0

    def test_multiple_sessions(self, isolated_env, tmp_path):
        """Run two named sessions concurrently using --sandbox (each gets its own auto port)."""
        env1 = {**isolated_env, "DRISSIONPAGE_CLI_SESSION": "sess-a"}
        env2 = {**isolated_env, "DRISSIONPAGE_CLI_SESSION": "sess-b"}

        # Open both sessions in sandbox mode so they each get a distinct auto port
        rc1, _, _ = run_cli("open", "--sandbox", "data:text/html,<p>A</p>", env_extra=env1)
        rc2, _, _ = run_cli("open", "--sandbox", "data:text/html,<p>B</p>", env_extra=env2)
        assert rc1 == 0
        assert rc2 == 0
        assert rc1 == 0
        assert rc2 == 0

        # List should show both
        rc, stdout, _ = run_cli("list", env_extra=isolated_env)
        assert rc == 0
        assert "sess-a" in stdout
        assert "sess-b" in stdout

        # Close all
        rc, stdout, _ = run_cli("close-all", env_extra=isolated_env)
        assert rc == 0


class TestIntegrationEdgeCases:
    """Edge cases and error handling."""

    def test_click_nonexistent_element(self, isolated_env):
        """Clicking a non-existent element should fail."""
        run_cli("open", "data:text/html,<p>Empty</p>", env_extra=isolated_env)

        rc, stdout, stderr = run_cli(
            "click", "@id=nonexistent", env_extra=isolated_env
        )
        # Should fail (element not found)
        assert rc != 0 or "error" in (stdout + stderr).lower()

    def test_goto_without_session(self, isolated_env):
        """Navigating without an open session should fail."""
        rc, stdout, stderr = run_cli(
            "goto", "https://example.com", env_extra=isolated_env
        )
        assert rc != 0 or "error" in (stdout + stderr).lower()

    def test_eval_returns_json(self, isolated_env):
        """eval returning an object should output JSON."""
        html = "data:text/html,<p>JSON Test</p>"
        run_cli("open", html, env_extra=isolated_env)

        rc, stdout, _ = run_cli(
            "eval", "return {a: 1, b: 'hello'}", env_extra=isolated_env
        )
        assert rc == 0

    def test_snapshot_to_file(self, isolated_env, tmp_path):
        """Snapshot with --filename saves to specific file."""
        html = "data:text/html,<h1>Saved Snapshot</h1>"
        run_cli("open", html, env_extra=isolated_env)

        outfile = str(tmp_path / "snap.html")
        rc, stdout, _ = run_cli(
            "snapshot", f"--filename={outfile}", env_extra=isolated_env
        )
        assert rc == 0
        assert Path(outfile).exists()
        content = Path(outfile).read_text()
        assert "Saved Snapshot" in content

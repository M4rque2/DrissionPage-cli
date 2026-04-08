"""
Unit tests for the CLI argument parser and utility functions.

These tests do NOT require a browser — they test the CLI scaffolding itself.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent dir to path so we can import the module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import drissionpage_cli as cli


# ---------------------------------------------------------------------------
# Version / help
# ---------------------------------------------------------------------------


class TestVersionAndHelp:
    def test_version_string(self):
        assert cli.__version__ == "0.1.2"

    def test_build_parser(self):
        parser = cli.build_parser()
        assert parser.prog == "drissionpage-cli"

    def test_parse_open_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["open", "https://example.com", "--headed"])
        assert args.command == "open"
        assert args.url == "https://example.com"
        assert args.headed is True

    def test_parse_goto_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["goto", "https://example.com"])
        assert args.command == "goto"
        assert args.url == "https://example.com"

    def test_parse_click_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["click", "#submit"])
        assert args.command == "click"
        assert args.ref == "#submit"

    def test_parse_fill_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["fill", "@name=email", "test@example.com", "--submit"])
        assert args.command == "fill"
        assert args.ref == "@name=email"
        assert args.text == "test@example.com"
        assert args.submit is True

    def test_parse_session_flag(self):
        parser = cli.build_parser()
        args = parser.parse_args(["-s", "mysession", "open"])
        assert args.session == "mysession"
        assert args.command == "open"

    def test_parse_session_equals_flag(self):
        parser = cli.build_parser()
        args = parser.parse_args(["-s=mysession", "open"])
        assert args.session == "mysession"

    def test_parse_eval_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["eval", "document.title"])
        assert args.command == "eval"
        assert args.expression == "document.title"

    def test_parse_eval_with_ref(self):
        parser = cli.build_parser()
        args = parser.parse_args(["eval", "return this.id", "#element"])
        assert args.command == "eval"
        assert args.expression == "return this.id"
        assert args.ref == "#element"

    def test_parse_screenshot_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["screenshot", "--filename=test.png"])
        assert args.command == "screenshot"
        assert args.filename == "test.png"

    def test_parse_screenshot_with_ref(self):
        parser = cli.build_parser()
        args = parser.parse_args(["screenshot", "#hero"])
        assert args.command == "screenshot"
        assert args.ref == "#hero"

    def test_parse_type_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["type", "hello world"])
        assert args.command == "type"
        assert args.text == "hello world"

    def test_parse_drag_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["drag", "@id=src", "@id=dst"])
        assert args.command == "drag"
        assert args.start_ref == "@id=src"
        assert args.end_ref == "@id=dst"

    def test_parse_select_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["select", "tag:select", "Option A"])
        assert args.command == "select"
        assert args.ref == "tag:select"
        assert args.value == "Option A"

    def test_parse_resize_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["resize", "1920", "1080"])
        assert args.command == "resize"
        assert args.width == 1920
        assert args.height == 1080

    def test_parse_press_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["press", "Enter"])
        assert args.command == "press"
        assert args.key == "Enter"

    def test_parse_mousemove_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["mousemove", "100", "200"])
        assert args.command == "mousemove"
        assert args.x == 100
        assert args.y == 200

    def test_parse_scroll_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["scroll", "0", "500"])
        assert args.command == "scroll"
        assert args.dx == 0
        assert args.dy == 500

    def test_parse_tab_commands(self):
        parser = cli.build_parser()

        args = parser.parse_args(["tab-list"])
        assert args.command == "tab-list"

        args = parser.parse_args(["tab-new", "https://example.com"])
        assert args.command == "tab-new"
        assert args.url == "https://example.com"

        args = parser.parse_args(["tab-close", "2"])
        assert args.command == "tab-close"
        assert args.index == 2

        args = parser.parse_args(["tab-select", "0"])
        assert args.command == "tab-select"
        assert args.index == 0

    def test_parse_cookie_commands(self):
        parser = cli.build_parser()

        args = parser.parse_args(["cookie-list", "--domain=example.com"])
        assert args.command == "cookie-list"
        assert args.domain == "example.com"

        args = parser.parse_args(["cookie-get", "session_id"])
        assert args.command == "cookie-get"
        assert args.name == "session_id"

        args = parser.parse_args([
            "cookie-set", "session", "abc123",
            "--domain=example.com", "--secure", "--httpOnly",
        ])
        assert args.command == "cookie-set"
        assert args.name == "session"
        assert args.value == "abc123"
        assert args.domain == "example.com"
        assert args.secure is True
        assert args.httpOnly is True

        args = parser.parse_args(["cookie-delete", "session_id"])
        assert args.command == "cookie-delete"

        args = parser.parse_args(["cookie-clear"])
        assert args.command == "cookie-clear"

    def test_parse_localstorage_commands(self):
        parser = cli.build_parser()

        args = parser.parse_args(["localstorage-list"])
        assert args.command == "localstorage-list"

        args = parser.parse_args(["localstorage-get", "theme"])
        assert args.command == "localstorage-get"
        assert args.key == "theme"

        args = parser.parse_args(["localstorage-set", "theme", "dark"])
        assert args.command == "localstorage-set"
        assert args.key == "theme"
        assert args.value == "dark"

        args = parser.parse_args(["localstorage-delete", "theme"])
        assert args.command == "localstorage-delete"

        args = parser.parse_args(["localstorage-clear"])
        assert args.command == "localstorage-clear"

    def test_parse_sessionstorage_commands(self):
        parser = cli.build_parser()

        args = parser.parse_args(["sessionstorage-list"])
        assert args.command == "sessionstorage-list"

        args = parser.parse_args(["sessionstorage-get", "step"])
        assert args.key == "step"

        args = parser.parse_args(["sessionstorage-set", "step", "3"])
        assert args.key == "step"
        assert args.value == "3"

    def test_parse_state_commands(self):
        parser = cli.build_parser()

        args = parser.parse_args(["state-save", "auth.json"])
        assert args.command == "state-save"
        assert args.filename == "auth.json"

        args = parser.parse_args(["state-load", "auth.json"])
        assert args.command == "state-load"
        assert args.filename == "auth.json"

    def test_parse_runcode_command(self):
        parser = cli.build_parser()

        args = parser.parse_args(["run-code", "result = page.title"])
        assert args.command == "run-code"
        assert args.code == "result = page.title"

        args = parser.parse_args(["run-code", "--filename=script.py"])
        assert args.command == "run-code"
        assert args.filename == "script.py"

    def test_parse_navigation_commands(self):
        parser = cli.build_parser()

        for cmd in ["go-back", "go-forward", "reload"]:
            args = parser.parse_args([cmd])
            assert args.command == cmd

    def test_parse_session_management_commands(self):
        parser = cli.build_parser()

        for cmd in ["list", "close", "close-all", "kill-all", "delete-data"]:
            args = parser.parse_args([cmd])
            assert args.command == cmd

    def test_parse_dialog_commands(self):
        parser = cli.build_parser()

        args = parser.parse_args(["dialog-accept", "ok"])
        assert args.command == "dialog-accept"
        assert args.text == "ok"

        args = parser.parse_args(["dialog-dismiss"])
        assert args.command == "dialog-dismiss"

    def test_parse_install_skills(self):
        parser = cli.build_parser()
        args = parser.parse_args(["install", "--skills"])
        assert args.command == "install"
        assert args.skills is True

    def test_parse_pdf_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["pdf", "--filename=report.pdf"])
        assert args.command == "pdf"
        assert args.filename == "report.pdf"

    def test_parse_open_with_port(self):
        parser = cli.build_parser()
        args = parser.parse_args(["open", "--port=9222"])
        assert args.command == "open"
        assert args.port == 9222

    def test_parse_open_with_profile(self):
        parser = cli.build_parser()
        args = parser.parse_args(["open", "--profile=/tmp/profile"])
        assert args.command == "open"
        assert args.profile == "/tmp/profile"

    def test_parse_open_with_system_user_path(self):
        parser = cli.build_parser()
        args = parser.parse_args(["open", "--system-user-path"])
        assert args.command == "open"
        assert args.system_user_path is True

    def test_parse_open_system_user_path_default_false(self):
        parser = cli.build_parser()
        args = parser.parse_args(["open"])
        assert args.system_user_path is False

    def test_parse_console_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["console", "warning"])
        assert args.command == "console"
        assert args.level == "warning"

    def test_parse_check_uncheck(self):
        parser = cli.build_parser()

        args = parser.parse_args(["check", "@type=checkbox"])
        assert args.command == "check"
        assert args.ref == "@type=checkbox"

        args = parser.parse_args(["uncheck", "@type=checkbox"])
        assert args.command == "uncheck"

    def test_parse_upload_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["upload", "css:input[type=file]", "./doc.pdf"])
        assert args.command == "upload"
        assert args.ref == "css:input[type=file]"
        assert args.file == "./doc.pdf"

    def test_parse_dblclick_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["dblclick", "@id=item"])
        assert args.command == "dblclick"
        assert args.ref == "@id=item"

    def test_parse_right_click_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["right-click", "tag:div"])
        assert args.command == "right-click"
        assert args.ref == "tag:div"

    def test_parse_hover_command(self):
        parser = cli.build_parser()
        args = parser.parse_args(["hover", "tag:button"])
        assert args.command == "hover"


# ---------------------------------------------------------------------------
# Session management (file-based, no browser)
# ---------------------------------------------------------------------------


class TestSessionManagement:
    def test_load_sessions_empty(self, tmp_path):
        """Loading sessions from non-existent file returns empty dict."""
        with patch.object(cli, "SESSIONS_FILE", tmp_path / "sessions.json"):
            sessions = cli._load_sessions()
            assert sessions == {}

    def test_save_and_load_sessions(self, tmp_path):
        """Sessions can be saved and reloaded."""
        sessions_file = tmp_path / "sessions.json"
        cli_dir = tmp_path / ".drissionpage-cli"
        cli_dir.mkdir()

        with patch.object(cli, "SESSIONS_FILE", sessions_file), \
             patch.object(cli, "CLI_DIR", cli_dir):
            test_sessions = {
                "default": {
                    "address": "127.0.0.1:9222",
                    "pid": 12345,
                    "started": 1700000000.0,
                },
                "auth": {
                    "address": "127.0.0.1:9223",
                    "pid": 12346,
                    "started": 1700000001.0,
                },
            }
            cli._save_sessions(test_sessions)
            loaded = cli._load_sessions()
            assert loaded == test_sessions

    def test_load_sessions_corrupt_json(self, tmp_path):
        """Corrupt JSON file returns empty dict."""
        sessions_file = tmp_path / "sessions.json"
        sessions_file.write_text("not valid json{{{")

        with patch.object(cli, "SESSIONS_FILE", sessions_file):
            sessions = cli._load_sessions()
            assert sessions == {}

    def test_get_session_name_default(self):
        """Default session name is 'default'."""
        args = MagicMock()
        args.session = None
        with patch.dict(os.environ, {}, clear=False):
            # Remove env var if it exists
            os.environ.pop("DRISSIONPAGE_CLI_SESSION", None)
            name = cli._get_session_name(args)
            assert name == "default"

    def test_get_session_name_from_args(self):
        """Session name from -s flag."""
        args = MagicMock()
        args.session = "mysession"
        name = cli._get_session_name(args)
        assert name == "mysession"

    def test_get_session_name_from_env(self):
        """Session name from DRISSIONPAGE_CLI_SESSION env var."""
        args = MagicMock()
        args.session = None
        with patch.dict(os.environ, {"DRISSIONPAGE_CLI_SESSION": "envtest"}):
            name = cli._get_session_name(args)
            assert name == "envtest"

    def test_args_flag_overrides_env(self):
        """Args -s flag takes priority over env var."""
        args = MagicMock()
        args.session = "fromargs"
        with patch.dict(os.environ, {"DRISSIONPAGE_CLI_SESSION": "fromenv"}):
            name = cli._get_session_name(args)
            assert name == "fromargs"


# ---------------------------------------------------------------------------
# Snapshot formatting
# ---------------------------------------------------------------------------


class TestSnapshotFormatting:
    def test_format_snapshot_page(self, tmp_path):
        """Snapshot includes page URL and title."""
        mock_page = MagicMock()
        mock_page.url = "https://example.com/"
        mock_page.title = "Example Domain"
        mock_page.html = "<html><body>Hello</body></html>"

        with patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            result = cli._format_snapshot(mock_page)
            assert "Page URL: https://example.com/" in result
            assert "Page Title: Example Domain" in result
            assert "Snapshot" in result

    def test_format_snapshot_element(self, tmp_path):
        """Element snapshot includes tag and text."""
        mock_page = MagicMock()
        mock_page.url = "https://example.com/"
        mock_page.title = "Example"

        mock_element = MagicMock()
        mock_element.tag = "button"
        mock_element.text = "Click Me"
        mock_element.attrs = {"id": "submit", "class": "btn"}

        with patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            result = cli._format_snapshot(mock_page, element=mock_element)
            assert "Element Snapshot" in result
            assert "button" in result
            assert "Click Me" in result
            assert "@id=submit" in result


# ---------------------------------------------------------------------------
# CLI invocation (subprocess)
# ---------------------------------------------------------------------------


class TestCliInvocation:
    def test_version_flag(self):
        """--version prints version and exits 0."""
        from tests.conftest import run_cli

        result = run_cli("--version")
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_no_command_shows_help(self):
        """No command shows help text."""
        from tests.conftest import run_cli

        result = run_cli()
        assert result.exit_code == 0
        assert "drissionpage-cli" in result.output or "usage" in result.output.lower()

    def test_list_no_sessions(self):
        """list with no sessions shows empty."""
        from tests.conftest import run_cli

        result = run_cli(
            "list",
            env_extra={"DRISSIONPAGE_CLI_DIR": tempfile.mkdtemp()},
        )
        assert result.exit_code == 0
        assert "No active sessions" in result.output


# ---------------------------------------------------------------------------
# Install skills
# ---------------------------------------------------------------------------


class TestInstallSkills:
    def test_install_skills_copies_files(self, tmp_path):
        """install --skills copies skill files to .claude/skills."""
        from tests.conftest import run_cli

        result = run_cli(
            "install", "--skills",
            cwd=str(tmp_path),
        )
        assert result.exit_code == 0
        skill_dir = tmp_path / ".claude" / "skills" / "drissionpage-cli"
        assert skill_dir.exists()
        assert (skill_dir / "SKILL.md").exists()
        assert (skill_dir / "references").is_dir()

    def test_install_without_skills_flag(self):
        """install without --skills shows hint."""
        from tests.conftest import run_cli

        result = run_cli("install")
        assert result.exit_code == 0
        assert "--skills" in result.output


# ---------------------------------------------------------------------------
# State save / load (mocked)
# ---------------------------------------------------------------------------


class TestStateSaveLoad:
    def test_state_save_creates_file(self, tmp_path):
        """state-save creates a JSON file with cookies and storage."""
        mock_page = MagicMock()
        mock_page.url = "https://example.com/"
        mock_page.cookies.return_value = [
            {"name": "test", "value": "123", "domain": "example.com"}
        ]
        mock_page.run_js.side_effect = lambda js: (
            json.dumps([["theme", "dark"]]) if "localStorage" in js
            else json.dumps([["step", "2"]]) if "sessionStorage" in js
            else None
        )

        state_file = tmp_path / "test-state.json"

        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.filename = str(state_file)
            cli.cmd_state_save(args)

        assert state_file.exists()
        state = json.loads(state_file.read_text())
        assert state["url"] == "https://example.com/"
        assert len(state["cookies"]) == 1
        assert state["cookies"][0]["name"] == "test"
        assert state["localStorage"] == [["theme", "dark"]]
        assert state["sessionStorage"] == [["step", "2"]]

    def test_state_load_restores_state(self, tmp_path):
        """state-load restores cookies and storage from JSON file."""
        state_file = tmp_path / "test-state.json"
        state_file.write_text(json.dumps({
            "url": "https://example.com/",
            "cookies": [{"name": "test", "value": "123", "domain": "example.com"}],
            "localStorage": [["theme", "dark"]],
            "sessionStorage": [["step", "2"]],
        }))

        mock_page = MagicMock()
        mock_page.url = "https://example.com/"
        mock_page.title = "Example"
        mock_page.html = "<html></html>"

        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.filename = str(state_file)
            cli.cmd_state_load(args)

        # Verify cookies were set
        mock_page.set.cookies.assert_called()
        # Verify localStorage was set
        assert any("localStorage.setItem" in str(call) for call in mock_page.run_js.call_args_list)
        # Verify sessionStorage was set
        assert any("sessionStorage.setItem" in str(call) for call in mock_page.run_js.call_args_list)


# ---------------------------------------------------------------------------
# _get_page options (mocked ChromiumOptions / ChromiumPage)
# ---------------------------------------------------------------------------


class TestGetPageOptions:
    """Test that _get_page passes options correctly to ChromiumOptions."""

    def _make_mock_co(self):
        return MagicMock()

    def _run_get_page(self, options, tmp_path, mock_co, mock_page):
        sessions_file = tmp_path / "sessions.json"
        cli_dir_path = tmp_path / ".drissionpage-cli"
        cli_dir_path.mkdir()

        with patch.object(cli, "SESSIONS_FILE", sessions_file), \
             patch.object(cli, "CLI_DIR", cli_dir_path), \
             patch("DrissionPage.ChromiumOptions", return_value=mock_co), \
             patch("DrissionPage.ChromiumPage", return_value=mock_page):
            mock_page.address = "127.0.0.1:9333"
            mock_page.process_id = 999
            cli._get_page("default", create=True, options=options)

    def test_system_user_path_calls_use_system_user_path(self, tmp_path):
        mock_co = self._make_mock_co()
        mock_page = MagicMock()
        self._run_get_page({"system_user_path": True}, tmp_path, mock_co, mock_page)
        mock_co.use_system_user_path.assert_called_once_with(True)

    def test_system_user_path_also_calls_auto_port(self, tmp_path):
        mock_co = self._make_mock_co()
        mock_page = MagicMock()
        self._run_get_page({"system_user_path": True}, tmp_path, mock_co, mock_page)
        mock_co.auto_port.assert_called_once()

    def test_no_system_user_path_calls_auto_port(self, tmp_path):
        mock_co = self._make_mock_co()
        mock_page = MagicMock()
        self._run_get_page({"system_user_path": False}, tmp_path, mock_co, mock_page)
        mock_co.auto_port.assert_called_once()
        mock_co.use_system_user_path.assert_not_called()

    def test_system_user_path_with_headed(self, tmp_path):
        mock_co = self._make_mock_co()
        mock_page = MagicMock()
        self._run_get_page({"system_user_path": True, "headless": False}, tmp_path, mock_co, mock_page)
        mock_co.use_system_user_path.assert_called_once_with(True)
        mock_co.headless.assert_called_once_with(False)


# ---------------------------------------------------------------------------
# Command handlers (mocked browser)
# ---------------------------------------------------------------------------


class TestCommandHandlersMocked:
    """Test command handlers with mocked DrissionPage to avoid requiring a browser."""

    def _make_mock_page(self):
        mock_page = MagicMock()
        mock_page.url = "https://example.com/"
        mock_page.title = "Example Domain"
        mock_page.html = "<html><body>Hello</body></html>"
        mock_page.address = "127.0.0.1:9222"
        mock_page.process_id = 12345
        mock_page.tab_id = "tab-1"
        mock_page.tab_ids = ["tab-1", "tab-2"]
        return mock_page

    def test_cmd_goto(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.url = "https://example.com"
            cli.cmd_goto(args)
        mock_page.get.assert_called_once_with("https://example.com")

    def test_cmd_click(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_ele = MagicMock()
        mock_page.ele.return_value = mock_ele

        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.ref = "#submit"
            cli.cmd_click(args)
        mock_page.ele.assert_called_once_with("#submit")
        mock_ele.click.assert_called_once()

    def test_cmd_dblclick(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_ele = MagicMock()
        mock_page.ele.return_value = mock_ele

        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.ref = "@id=item"
            cli.cmd_dblclick(args)
        mock_ele.click.assert_called_once_with(times=2)

    def test_cmd_right_click(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_ele = MagicMock()
        mock_page.ele.return_value = mock_ele

        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.ref = "tag:div"
            cli.cmd_right_click(args)
        mock_ele.click.assert_called_once_with(button="right")

    def test_cmd_fill(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_ele = MagicMock()
        mock_page.ele.return_value = mock_ele

        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.ref = "@name=email"
            args.text = "test@example.com"
            args.submit = False
            cli.cmd_fill(args)
        mock_ele.clear.assert_called_once()
        mock_ele.input.assert_called_once_with("test@example.com")

    def test_cmd_fill_with_submit(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_ele = MagicMock()
        mock_page.ele.return_value = mock_ele

        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.ref = "@name=email"
            args.text = "test@example.com"
            args.submit = True
            cli.cmd_fill(args)
        mock_ele.clear.assert_called_once()
        # input called twice: once for text, once for Enter
        assert mock_ele.input.call_count == 2

    def test_cmd_hover(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_ele = MagicMock()
        mock_page.ele.return_value = mock_ele

        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.ref = "tag:button"
            cli.cmd_hover(args)
        mock_ele.hover.assert_called_once()

    def test_cmd_drag(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_src = MagicMock()
        mock_dst = MagicMock()
        mock_page.ele.side_effect = [mock_src, mock_dst]

        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.start_ref = "@id=src"
            args.end_ref = "@id=dst"
            cli.cmd_drag(args)
        mock_src.drag_to.assert_called_once_with(mock_dst)

    def test_cmd_select(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_ele = MagicMock()
        mock_page.ele.return_value = mock_ele

        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.ref = "tag:select"
            args.value = "Option A"
            cli.cmd_select(args)
        mock_ele.select.by_text.assert_called_once_with("Option A")

    def test_cmd_check(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_ele = MagicMock()
        mock_ele.states.is_checked = False
        mock_page.ele.return_value = mock_ele

        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.ref = "@type=checkbox"
            cli.cmd_check(args)
        mock_ele.click.assert_called_once()

    def test_cmd_check_already_checked(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_ele = MagicMock()
        mock_ele.states.is_checked = True
        mock_page.ele.return_value = mock_ele

        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.ref = "@type=checkbox"
            cli.cmd_check(args)
        mock_ele.click.assert_not_called()

    def test_cmd_uncheck(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_ele = MagicMock()
        mock_ele.states.is_checked = True
        mock_page.ele.return_value = mock_ele

        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.ref = "@type=checkbox"
            cli.cmd_uncheck(args)
        mock_ele.click.assert_called_once()

    def test_cmd_eval_page(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_page.run_js.return_value = "Example Domain"

        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.expression = "document.title"
            args.ref = None
            cli.cmd_eval(args)
        mock_page.run_js.assert_called_once_with("document.title")

    def test_cmd_eval_element(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_ele = MagicMock()
        mock_ele.run_js.return_value = "submit-btn"
        mock_page.ele.return_value = mock_ele

        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.expression = "return this.id"
            args.ref = "#element"
            cli.cmd_eval(args)
        mock_ele.run_js.assert_called_once_with("return this.id")

    def test_cmd_go_back(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            cli.cmd_go_back(args)
        mock_page.back.assert_called_once()

    def test_cmd_go_forward(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            cli.cmd_go_forward(args)
        mock_page.forward.assert_called_once()

    def test_cmd_reload(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            cli.cmd_reload(args)
        mock_page.refresh.assert_called_once()

    def test_cmd_resize(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.width = 1920
            args.height = 1080
            cli.cmd_resize(args)
        mock_page.set.window.size.assert_called_once_with(1920, 1080)

    def test_cmd_dialog_accept(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.text = None
            cli.cmd_dialog_accept(args)
        mock_page.handle_alert.assert_called_once_with(accept=True, send=None)

    def test_cmd_dialog_dismiss(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            cli.cmd_dialog_dismiss(args)
        mock_page.handle_alert.assert_called_once_with(accept=False)

    def test_cmd_tab_list(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_tab = MagicMock()
        mock_tab.title = "Tab Title"
        mock_tab.url = "https://example.com"
        mock_page.get_tab.return_value = mock_tab

        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            cli.cmd_tab_list(args)

    def test_cmd_tab_new(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_tab = MagicMock()
        mock_tab.url = "https://example.com"
        mock_page.new_tab.return_value = mock_tab

        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.url = "https://example.com"
            cli.cmd_tab_new(args)
        mock_page.new_tab.assert_called_once_with(url="https://example.com")

    def test_cmd_cookie_list(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_page.cookies.return_value = [
            {"name": "test", "value": "123", "domain": "example.com"}
        ]

        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.domain = None
            cli.cmd_cookie_list(args)
        mock_page.cookies.assert_called_once_with(as_dict=False, all_info=True)

    def test_cmd_cookie_list_filtered(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_page.cookies.return_value = [
            {"name": "a", "value": "1", "domain": "example.com"},
            {"name": "b", "value": "2", "domain": "other.com"},
        ]

        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.domain = "example.com"
            cli.cmd_cookie_list(args)

    def test_cmd_cookie_set(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.name = "test"
            args.value = "123"
            args.domain = "example.com"
            args.path = "/"
            args.secure = True
            args.httpOnly = True
            cli.cmd_cookie_set(args)
        mock_page.set.cookies.assert_called_once()

    def test_cmd_cookie_clear(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            cli.cmd_cookie_clear(args)
        mock_page.set.cookies.clear.assert_called_once()

    def test_cmd_localstorage_set(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.key = "theme"
            args.value = "dark"
            cli.cmd_localstorage_set(args)
        mock_page.run_js.assert_called_once_with("localStorage.setItem('theme', 'dark')")

    def test_cmd_localstorage_get(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_page.run_js.return_value = "dark"
        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.key = "theme"
            cli.cmd_localstorage_get(args)
        mock_page.run_js.assert_called_once_with("return localStorage.getItem('theme')")

    def test_cmd_localstorage_delete(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.key = "theme"
            cli.cmd_localstorage_delete(args)
        mock_page.run_js.assert_called_once_with("localStorage.removeItem('theme')")

    def test_cmd_localstorage_clear(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            cli.cmd_localstorage_clear(args)
        mock_page.run_js.assert_called_once_with("localStorage.clear()")

    def test_cmd_sessionstorage_set(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.key = "step"
            args.value = "3"
            cli.cmd_sessionstorage_set(args)
        mock_page.run_js.assert_called_once_with("sessionStorage.setItem('step', '3')")

    def test_cmd_sessionstorage_clear(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            cli.cmd_sessionstorage_clear(args)
        mock_page.run_js.assert_called_once_with("sessionStorage.clear()")

    def test_cmd_screenshot(self, tmp_path):
        mock_page = self._make_mock_page()
        outfile = str(tmp_path / "test.png")
        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.filename = outfile
            args.ref = None
            cli.cmd_screenshot(args)
        mock_page.get_screenshot.assert_called_once_with(path=outfile)

    def test_cmd_screenshot_element(self, tmp_path):
        mock_page = self._make_mock_page()
        mock_ele = MagicMock()
        mock_page.ele.return_value = mock_ele
        outfile = str(tmp_path / "elem.png")

        with patch.object(cli, "_get_page", return_value=mock_page):
            args = MagicMock()
            args.session = None
            args.filename = outfile
            args.ref = "#hero"
            cli.cmd_screenshot(args)
        mock_ele.get_screenshot.assert_called_once_with(path=outfile)

    def test_cmd_run_code_inline(self, tmp_path):
        mock_page = self._make_mock_page()
        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.code = "result = page.title"
            args.filename = None
            cli.cmd_run_code(args)

    def test_cmd_run_code_from_file(self, tmp_path):
        mock_page = self._make_mock_page()
        script_file = tmp_path / "script.py"
        script_file.write_text("result = page.url")

        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "CLI_DIR", tmp_path / ".drissionpage-cli"):
            args = MagicMock()
            args.session = None
            args.code = None
            args.filename = str(script_file)
            cli.cmd_run_code(args)

    def test_cmd_close(self, tmp_path):
        sessions_file = tmp_path / "sessions.json"
        cli_dir_path = tmp_path / ".drissionpage-cli"
        cli_dir_path.mkdir()

        sessions = {"default": {"address": "127.0.0.1:9222", "pid": 1, "started": 0}}
        sessions_file.write_text(json.dumps(sessions))

        mock_page = MagicMock()
        with patch.object(cli, "_get_page", return_value=mock_page), \
             patch.object(cli, "SESSIONS_FILE", sessions_file), \
             patch.object(cli, "CLI_DIR", cli_dir_path):
            args = MagicMock()
            args.session = None
            cli.cmd_close(args)

        mock_page.quit.assert_called_once()
        loaded = json.loads(sessions_file.read_text())
        assert "default" not in loaded

    def test_cmd_list_with_sessions(self, tmp_path, capsys):
        sessions_file = tmp_path / "sessions.json"
        sessions = {
            "default": {"address": "127.0.0.1:9222", "pid": 1234, "started": 1700000000.0},
            "auth": {"address": "127.0.0.1:9223", "pid": 1235, "started": 1700000001.0},
        }
        sessions_file.write_text(json.dumps(sessions))

        with patch.object(cli, "SESSIONS_FILE", sessions_file):
            args = MagicMock()
            cli.cmd_list(args)

        captured = capsys.readouterr()
        assert "Sessions (2)" in captured.out
        assert "default" in captured.out
        assert "auth" in captured.out

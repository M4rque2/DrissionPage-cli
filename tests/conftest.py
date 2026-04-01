"""
Shared test fixtures for drissionpage-cli tests.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

CLI_PATH = Path(__file__).resolve().parent.parent / "drissionpage_cli.py"


class CliResult:
    """Wrapper for CLI invocation results."""

    def __init__(self, returncode: int, stdout: str, stderr: str):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.output = stdout.strip()
        self.error = stderr.strip()
        self.exit_code = returncode

    def __repr__(self):
        return (
            f"CliResult(exit_code={self.exit_code}, "
            f"output={self.output[:80]!r}, "
            f"error={self.error[:80]!r})"
        )


def run_cli(*args, env_extra=None, cwd=None, timeout=30):
    """Run drissionpage-cli with the given arguments and return a CliResult."""
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)

    cmd = [sys.executable, str(CLI_PATH)] + list(args)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=cwd,
        )
        return CliResult(proc.returncode, proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired:
        return CliResult(-1, "", "Command timed out")


@pytest.fixture
def cli_dir(tmp_path):
    """Provide a temporary CLI directory for test isolation."""
    d = tmp_path / ".drissionpage-cli"
    d.mkdir()
    return d


@pytest.fixture
def cli_env(tmp_path):
    """Provide environment with isolated CLI dir."""
    return {
        "DRISSIONPAGE_CLI_DIR": str(tmp_path / ".drissionpage-cli"),
    }


@pytest.fixture
def run(cli_env, tmp_path):
    """Fixture that returns a function to run CLI commands with test isolation."""

    def _run(*args, **kwargs):
        kwargs.setdefault("env_extra", {}).update(cli_env)
        kwargs.setdefault("cwd", str(tmp_path))
        return run_cli(*args, **kwargs)

    return _run

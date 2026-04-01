#!/usr/bin/env python3
"""Update script: reinstall skills from the CLI source."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT_DIR / "skills"


def run(cmd, **kwargs):
    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd, cwd=str(ROOT_DIR), **kwargs)


def main():
    print("\n=== Running drissionpage-cli install --skills ===\n")
    run([sys.executable, str(ROOT_DIR / "drissionpage_cli.py"), "install", "--skills"])

    print("\n=== Updating skills folder ===\n")
    generated = ROOT_DIR / ".claude" / "skills" / "drissionpage-cli"
    target = SKILLS_DIR / "drissionpage-cli"

    if generated.exists():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(generated, target)
        print(f"Copied skills from {generated} to {target}")

        shutil.rmtree(generated)
        print("Cleaned up generated skills directory")
    else:
        print(f"Warning: Generated skills directory not found at {generated}")

    print("\n=== Update complete! ===\n")


if __name__ == "__main__":
    main()

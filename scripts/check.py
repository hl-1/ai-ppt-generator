"""Run the repository's checks; add --java for the optional Java backend."""

import argparse
import subprocess
import sys

from dev import ROOT, executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java", action="store_true")
    args = parser.parse_args()
    commands = [
        ("backend", ["uv", "run", "ruff", "check", "."]),
        ("backend", ["uv", "run", "ruff", "check", "../scripts", "--config", "pyproject.toml"]),
        ("backend", ["uv", "run", "pytest"]),
        ("frontend", ["npm", "run", "lint"]),
        ("frontend", ["npm", "run", "build"]),
    ]
    if args.java:
        commands.append(("java-backend", ["mvn", "test"]))
    for directory, command in commands:
        print(f"[{directory}] {' '.join(command)}", flush=True)
        result = subprocess.run([executable(command[0]), *command[1:]], cwd=ROOT / directory)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())

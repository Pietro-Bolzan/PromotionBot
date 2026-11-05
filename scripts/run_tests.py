"""Run the test suite with the project's virtualenv, whoever calls this.

pre-commit runs hooks with an interpreter of its own, without the project's
dependencies, and a commit made from an editor button has no virtualenv
activated. This finds the project's virtualenv and runs pytest with it.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = [
    ROOT / "venv" / "Scripts" / "python.exe",
    ROOT / "venv" / "bin" / "python",
    ROOT / ".venv" / "Scripts" / "python.exe",
    ROOT / ".venv" / "bin" / "python",
]


def main() -> int:
    python = next((path for path in CANDIDATES if path.exists()), None)
    if python is None:
        print(
            "No virtualenv found in venv/ or .venv/. Create one and run: "
            "pip install -r requirements-dev.txt",
            file=sys.stderr,
        )
        return 1

    command = [str(python), "-m", "pytest", "-q", *sys.argv[1:]]
    return subprocess.call(command, cwd=ROOT)  # noqa: S603 - fixed command, no user input


if __name__ == "__main__":
    sys.exit(main())

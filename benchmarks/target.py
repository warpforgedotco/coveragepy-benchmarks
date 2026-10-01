# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/coveragepy/coveragepy/blob/main/NOTICE.txt

"""Identify the coverage.py being benchmarked.

The benchmarks measure whatever `coverage` is importable in the running
interpreter.  Usually that is an editable install of a coveragepy checkout, so
that the C tracer is built in place:

    pip install -e ../coveragepy

COVERAGE_UNDER_TEST can name a different pip requirement or path for the
environments this suite builds itself (the Jinja2 workload).

"""

from __future__ import annotations

import os
import pathlib
import subprocess
from typing import Any

import coverage

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_DIR = pathlib.Path(coverage.__file__).resolve().parent


def checkout_root() -> pathlib.Path | None:
    """The coveragepy source checkout that `coverage` was imported from, if any."""
    root = PACKAGE_DIR.parent
    if (root / "pyproject.toml").exists() and (root / "coverage" / "ctracer").is_dir():
        return root
    return None


def install_args() -> list[str]:
    """`pip install` arguments that reproduce the coverage.py under test."""
    if spec := os.getenv("COVERAGE_UNDER_TEST"):
        return ["-e", spec] if pathlib.Path(spec).is_dir() else [spec]
    if root := checkout_root():
        return ["-e", str(root)]
    return [f"coverage=={coverage.__version__}"]


def describe() -> dict[str, Any]:
    """Identity of the coverage.py under test, for benchmark metadata."""
    info: dict[str, Any] = {
        "coverage_version": coverage.__version__,
        "coverage_file": coverage.__file__,
    }
    if root := checkout_root():
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            info["coverage_commit"] = result.stdout.strip()
    return info

# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/coveragepy/coveragepy/blob/main/NOTICE.txt

"""Command-line options for the benchmark suite."""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add command-line options for controlling the benchmarks."""
    parser.addoption(
        "--bench-rounds",
        type=int,
        default=None,
        help="Measured rounds for setup-dependent benchmarks (10, or 5 for slow cases).",
    )
    parser.addoption(
        "--bench-smoke",
        action="store_true",
        help="Validate workloads once without recording performance results.",
    )
    parser.addoption(
        "--bench-real", action="store_true", help="Include the explicitly prepared Jinja2 workload."
    )

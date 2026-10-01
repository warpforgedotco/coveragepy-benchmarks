# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/coveragepy/coveragepy/blob/main/NOTICE.txt

"""Facts about the coverage.py under test and the interpreter running it.

This stands in for coverage.py's own tests/testenv.py, which isn't installed
with the package.

"""

from __future__ import annotations

import os

from coverage import env
from coverage.core import CTRACER_FILE

# What core would coverage.py pick here, either requested or defaulted?
CORE = os.getenv("COVERAGE_CORE", "sysmon" if env.SYSMON_DEFAULT else "ctrace")

# The name each core's collector reports for itself.
TRACER_CLASSES = {
    "ctrace": "CTracer",
    "pytrace": "PyTracer",
    "sysmon": "SysMonitor",
}

# Are dynamic contexts supported by the default core?
DYN_CONTEXTS = CORE in ("ctrace", "pytrace")

# Can sys.monitoring measure branches?
CAN_MEASURE_BRANCHES = env.PYBEHAVIOR.branch_right_left

# Which cores could we use here?  These are about availability, not about which
# core is the default, so they are what the benchmarks need when they sweep
# over all three cores in one process.
HAVE_PYTRACE = True
HAVE_CTRACE = CTRACER_FILE is not None
HAVE_SYSMON = env.PYBEHAVIOR.pep669

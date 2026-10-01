# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/coveragepy/coveragepy/blob/main/NOTICE.txt

"""Explicit preparation of coverage.py's own test suite, run under metacov.

The workload is coverage.py measuring itself the way its maintainers do with
`make metacov`: igor.py runs the whole test suite under the coverage.py being
tested, with subprocesses measured through a .pth file.

Preparation copies the checkout under test, so the test run's outputs and
igor.py's removal of the C extension never touch the real checkout.  It then
builds an isolated environment from coverage.py's own pinned requirements,
the same ones its tox environments use.

hyperfine does the timing (see `make bench-self`): `start`, `reset`, and
`validate` are its untimed setup, prepare, and conclude steps around `run`.

"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import venv
import xml.etree.ElementTree as ET
from importlib.machinery import EXTENSION_SUFFIXES
from typing import Any

from coverage import CoverageData

from benchmarks.helpers import run_subprocess, subprocess_env
from benchmarks.target import PROJECT_ROOT, checkout_root

PREPARED_ROOT = PROJECT_ROOT / ".benchmarks" / "self"
CORES = ["ctrace", "pytrace", "sysmon"]
# coverage.py's tox.ini installs these for Python 3.14.
REQUIREMENTS = ["pip.txt", "pytest.txt", "light-threads.txt"]
# coverage.py has about 1650 tests; fewer means collection went wrong.
MIN_TESTS = 1500


def prepared_python(root: pathlib.Path = PREPARED_ROOT) -> pathlib.Path:
    """The isolated interpreter created during preparation."""
    return root / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def source_checkout() -> pathlib.Path:
    """The coverage.py checkout under test: only a checkout has its test suite."""
    root = checkout_root()
    if root is None:
        raise RuntimeError(
            "coverage.py's own test suite needs a source checkout. Run make install first."
        )
    return root


def checkout_files(root: pathlib.Path) -> list[str]:
    """Files git would commit, including uncommitted edits, in a stable order."""
    output = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return sorted(name for name in output.split("\0") if name and (root / name).is_file())


def source_hashes(root: pathlib.Path, names: list[str]) -> dict[str, str]:
    """Identity of the checkout, so a stale copy can't be benchmarked."""
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


def verify_prepared(root: pathlib.Path = PREPARED_ROOT) -> dict[str, Any]:
    """Fail explicitly instead of preparing inside a benchmark fixture."""
    manifest_path = root / "prepared.json"
    if not manifest_path.exists() or not prepared_python(root).exists():
        raise RuntimeError(
            "coverage.py's test suite is not prepared. Run make bench-self-prepare with Python 3.14."
        )
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    checkout = source_checkout()
    if source_hashes(checkout, checkout_files(checkout)) != manifest["source_hashes"]:
        raise RuntimeError(
            "The coverage.py checkout changed since preparation. Run make bench-self-prepare again."
        )
    return manifest


def prepare(root: pathlib.Path = PREPARED_ROOT) -> None:
    """Copy the checkout and install its test requirements before any measurements."""
    if sys.version_info[:2] != (3, 14):
        raise RuntimeError("Prepare the self-test workload using Python 3.14.")
    checkout = source_checkout()
    names = checkout_files(checkout)
    copy = root / "coveragepy"
    shutil.rmtree(copy, ignore_errors=True)
    for name in names:
        (copy / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(checkout / name, copy / name)

    python = prepared_python(root)
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(root / "venv")
    env = subprocess_env()
    requirements = [arg for name in REQUIREMENTS for arg in ["-r", f"requirements/{name}"]]
    print(
        run_subprocess(
            [str(python), "-m", "pip", "install", "--require-hashes", *requirements],
            copy,
            env,
            timeout=900,
        )
    )
    # Editable, as tox does: metacov then measures the copy's own source, and the
    # C extension is built in place.
    print(run_subprocess([str(python), "-m", "pip", "install", "-e", "."], copy, env, timeout=900))
    run_subprocess([str(python), "igor.py", "zip_mods"], copy, env)
    manifest = {
        "coverage_checkout": str(checkout),
        "python": sys.version,
        "source_hashes": source_hashes(checkout, names),
    }
    (root / "prepared.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {copy}. Run make bench-self to time it.")


def suite_env() -> dict[str, str]:
    """What tox gives coverage.py's tests, with metacov turned on."""
    env = subprocess_env()
    # The suite needs its plugins: xdist, flaky, hypothesis.
    env.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD")
    # The tests run `coverage` and `python` by name, from the active environment.
    env["PATH"] = str(prepared_python().parent) + os.pathsep + env["PATH"]
    env["COVERAGE_COVERAGE"] = "yes"
    env["PYTHONWARNDEFAULTENCODING"] = "1"
    env["PYTHON_COLORS"] = "0"
    return env


def junit_path(core: str) -> pathlib.Path:
    """Where a run's test results go."""
    return PREPARED_ROOT / "coveragepy" / f"junit-{core}.xml"


def reference_path(core: str) -> pathlib.Path:
    """The tests and outcomes of a sweep's first run, for comparing later runs."""
    return PREPARED_ROOT / f"reference-{core}.json"


def log_path(core: str) -> pathlib.Path:
    """The suite's output from the latest run: hyperfine itself discards it."""
    return PREPARED_ROOT / f"run-{core}.log"


def start(core: str) -> None:
    """Before a core's runs: igor.py removes the C extension for the other cores."""
    verify_prepared()
    reference_path(core).unlink(missing_ok=True)
    root = PREPARED_ROOT / "coveragepy"
    python = str(prepared_python())
    env = subprocess_env()
    if core == "ctrace":
        # Not just any tracer.*: coverage/tracer.pyi is always there.
        if not any(
            (root / "coverage" / f"tracer{suffix}").exists() for suffix in EXTENSION_SUFFIXES
        ):
            run_subprocess(
                [python, "setup.py", "--quiet", "build_ext", "--inplace"], root, env, timeout=600
            )
    else:
        run_subprocess([python, "igor.py", "clean_for_core", core], root, env)


def reset(core: str) -> None:
    """Before every run: no output from an earlier run can count for this one."""
    junit_path(core).unlink(missing_ok=True)
    log_path(core).unlink(missing_ok=True)
    for data_file in (PREPARED_ROOT / "coveragepy").glob(".metacov*"):
        data_file.unlink()


def run(core: str) -> None:
    """The timed command: the whole test suite under metacov, as `make metacov` does."""
    python = str(prepared_python())
    command = [
        python,
        "igor.py",
        "test_with_core",
        core,
        # The suite's own addopts use --failed-first: keep the order fixed.
        "--cache-clear",
        "--hypothesis-seed=0",
        "--junitxml",
        str(junit_path(core)),
    ]
    with log_path(core).open("w", encoding="utf-8") as log:
        status = subprocess.run(
            command,
            cwd=PREPARED_ROOT / "coveragepy",
            env=suite_env(),
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        ).returncode
    if status:
        sys.exit(f"coverage.py's tests failed (exit {status}); see {log_path(core)}")


def suite_identities(junit: pathlib.Path) -> list[list[str]]:
    """Every test and its outcome; fail on any failure or error."""
    tree = ET.parse(junit)
    problems = [
        f"{case.get('classname')}::{case.get('name')}"
        for case in tree.iter("testcase")
        if case.find("failure") is not None or case.find("error") is not None
    ]
    if problems:
        raise RuntimeError(f"coverage.py's tests failed: {problems}")
    cases = sorted(
        [
            case.get("classname", ""),
            case.get("name", ""),
            "skipped" if case.find("skipped") is not None else "passed",
        ]
        for case in tree.iter("testcase")
    )
    if len(cases) < MIN_TESTS:
        raise RuntimeError(f"Only {len(cases)} tests ran; expected at least {MIN_TESTS}")
    return cases


def validate_metacov(root: pathlib.Path) -> None:
    """Ensure coverage.py measured itself, including in subprocesses."""
    data_files = list(root.glob(".metacov.*"))
    # One file for the test runner, and many from measured subprocesses.
    if len(data_files) <= 10:
        raise RuntimeError(f"Only {len(data_files)} metacov data files")
    measured: set[str] = set()
    lines = 0
    for data_file in data_files:
        data = CoverageData(basename=str(data_file))
        data.read()
        if not data.has_arcs():
            raise RuntimeError(f"{data_file.name} has no branch data")
        for name in data.measured_files():
            measured.add(name)
            lines += len(data.lines(name) or [])
        data.close()
    source = [f for f in measured if "/coverage/" in f.replace("\\", "/")]
    if len(source) < 40 or lines < 20_000:
        raise RuntimeError(f"Too little measured: {len(source)} source files, {lines} lines")


def validate(core: str) -> None:
    """After every run, untimed: the same tests ran, passed, and were measured."""
    identities = suite_identities(junit_path(core))
    reference = reference_path(core)
    if reference.exists():
        if identities != json.loads(reference.read_text(encoding="utf-8")):
            raise RuntimeError(f"A different set of tests ran, or skipped, than in {reference}")
    else:
        reference.write_text(json.dumps(identities), encoding="utf-8")
    validate_metacov(PREPARED_ROOT / "coveragepy")


def main() -> None:
    """Command-line entry point: preparation, and the steps hyperfine runs."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare", help="Copy the checkout and build the environment.")
    commands.add_parser("verify", help="Check the prepared copy is still current.")
    steps = {"start": start, "reset": reset, "run": run, "validate": validate}
    for name, step in steps.items():
        commands.add_parser(name, help=step.__doc__).add_argument("core", choices=CORES)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "verify":
        verify_prepared()
        print("Prepared copy and environment verified.")
    else:
        steps[args.command](args.core)


if __name__ == "__main__":
    main()

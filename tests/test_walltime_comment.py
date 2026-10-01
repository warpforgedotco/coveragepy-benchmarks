# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/coveragepy/coveragepy/blob/main/NOTICE.txt

"""The pull request comment built from hyperfine's results."""

from __future__ import annotations

import json
import pathlib

from benchmarks.walltime_comment import MARKER, Timing, change, comment, load_timings


def write_hyperfine(path: pathlib.Path, core: str, times: list[float]) -> None:
    """A hyperfine --export-json file, as one matrix job's artifact holds it."""
    mean = sum(times) / len(times)
    stddev = (sum((t - mean) ** 2 for t in times) / (len(times) - 1)) ** 0.5
    path.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "command": f"metacov-{core}",
        "mean": mean,
        "stddev": stddev,
        "times": times,
        "parameters": {"core": core},
    }
    path.write_text(json.dumps({"results": [result]}), encoding="utf-8")


def test_load_from_artifact_directories(tmp_path: pathlib.Path) -> None:
    write_hyperfine(tmp_path / "benchmark-self-ctrace" / "benchmark-self.json", "ctrace", [10, 12])
    write_hyperfine(tmp_path / "benchmark-self-sysmon" / "benchmark-self.json", "sysmon", [5, 5])
    timings = load_timings(tmp_path)
    assert timings.keys() == {"ctrace", "sysmon"}
    assert timings["ctrace"].mean == 11 and timings["ctrace"].runs == 2


def test_change_distinguishes_noise() -> None:
    assert change(Timing(101, 5, 5), Timing(100, 5, 5)) == "+1.0% (within noise)"
    assert change(Timing(90, 1, 5), Timing(100, 1, 5)) == "**-10.0%** (faster)"
    assert change(Timing(110, 1, 5), Timing(100, 1, 5)) == "**+10.0%** (slower)"


def test_comment_without_baseline_and_with_a_failed_core() -> None:
    body = comment({"ctrace": Timing(100, 2, 5)}, {}, "https://run", "")
    assert body.startswith(MARKER)
    assert "| ctrace | 100.0 s ± 2.0 |" in body
    assert "| pytrace | failed, see the job log |" in body
    assert "No successful run on main yet" in body


def test_comment_with_baseline() -> None:
    current = {core: Timing(90, 1, 5) for core in ["ctrace", "pytrace", "sysmon"]}
    baseline = {core: Timing(100, 1, 5) for core in ["ctrace", "pytrace", "sysmon"]}
    body = comment(current, baseline, "https://run", "https://main")
    assert "| ctrace | 90.0 s ± 1.0 | 100.0 s ± 1.0 | **-10.0%** (faster) |" in body
    assert "[main baseline](https://main)" in body

# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/coveragepy/coveragepy/blob/main/NOTICE.txt

"""The pull request comment built from hyperfine's results."""

from __future__ import annotations

import json
import pathlib

from benchmarks.walltime_comment import MARKER, Timing, change, comment, load_timings


def write_hyperfine(path: pathlib.Path, core: str, runs: dict[str, list[float]]) -> None:
    """A hyperfine --export-json file, as one matrix job's artifact holds it."""
    results = []
    for variant, times in runs.items():
        mean = sum(times) / len(times)
        stddev = (sum((t - mean) ** 2 for t in times) / (len(times) - 1)) ** 0.5
        results.append(
            {
                "command": f"metacov-{variant}-{core}",
                "mean": mean,
                "stddev": stddev,
                "times": times,
                "parameters": {"variant": variant, "core": core},
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"results": results}), encoding="utf-8")


def test_load_from_artifact_directories(tmp_path: pathlib.Path) -> None:
    write_hyperfine(
        tmp_path / "benchmark-self-ctrace" / "benchmark-self.json",
        "ctrace",
        {"base": [20, 22], "head": [10, 12]},
    )
    write_hyperfine(
        tmp_path / "benchmark-self-sysmon" / "benchmark-self.json", "sysmon", {"head": [5, 5]}
    )
    timings = load_timings(tmp_path)
    assert timings.keys() == {"ctrace", "sysmon"}
    assert timings["ctrace"]["head"].mean == 11 and timings["ctrace"]["head"].runs == 2
    assert timings["ctrace"]["base"].mean == 21
    assert timings["sysmon"].keys() == {"head"}


def test_failed_run_leaves_unreadable_results(tmp_path: pathlib.Path) -> None:
    write_hyperfine(
        tmp_path / "benchmark-self-sysmon" / "benchmark-self.json", "sysmon", {"head": [5, 5]}
    )
    (tmp_path / "benchmark-self-ctrace").mkdir()
    (tmp_path / "benchmark-self-ctrace" / "benchmark-self.json").write_text("", encoding="utf-8")
    assert load_timings(tmp_path).keys() == {"sysmon"}


def test_change_distinguishes_noise() -> None:
    assert change(Timing(101, 5, 5), Timing(100, 5, 5)) == "+1.0% (within noise)"
    assert change(Timing(90, 1, 5), Timing(100, 1, 5)) == "**-10.0%** (faster)"
    assert change(Timing(110, 1, 5), Timing(100, 1, 5)) == "**+10.0%** (slower)"


def test_comment_without_base_and_with_a_failed_core() -> None:
    body = comment({"ctrace": {"head": Timing(100, 2, 5)}}, "https://run", "")
    assert body.startswith(MARKER)
    assert "| ctrace | 100.0 s ± 2.0 |" in body
    assert "| pytrace | failed, see the job log |" in body
    assert "doesn't change coverage.py" in body


def test_comment_with_base() -> None:
    timings = {
        core: {"base": Timing(100, 1, 5), "head": Timing(90, 1, 5)}
        for core in ["ctrace", "pytrace", "sysmon"]
    }
    del timings["sysmon"]["base"]
    body = comment(timings, "https://run", "coverage.py at main")
    assert "| ctrace | 100.0 s ± 1.0 | 90.0 s ± 1.0 | **-10.0%** (faster) |" in body
    assert "| sysmon | failed, see the job log | 90.0 s ± 1.0 |  |" in body
    assert "Base is coverage.py at main, timed in the same job" in body

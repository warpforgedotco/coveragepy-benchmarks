# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/coveragepy/coveragepy/blob/main/NOTICE.txt

"""Write the pull request comment for walltime.yml's hyperfine results.

    python -m benchmarks.walltime_comment RESULTS_DIR [--baseline MAIN_DIR]

Each directory holds hyperfine --export-json files, one per core, possibly in
subdirectories (as downloaded artifacts are).  The baseline is the latest
successful run on main, when there is one.

"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
from dataclasses import dataclass

# walltime.yml's matrix.  Not imported from self_suite: the commenting job
# doesn't install coverage.py.
CORES = ["ctrace", "pytrace", "sysmon"]
# Find the comment again, to update it instead of adding another.
MARKER = "<!-- walltime-self-suite -->"


@dataclass
class Timing:
    """One core's hyperfine result, in seconds."""

    mean: float
    stddev: float
    runs: int

    def __str__(self) -> str:
        return f"{self.mean:.1f} s ± {self.stddev:.1f}"


def load_timings(directory: pathlib.Path) -> dict[str, Timing]:
    """hyperfine results by core, from every JSON export under `directory`."""
    timings: dict[str, Timing] = {}
    for path in sorted(directory.rglob("*.json")):
        try:
            results = json.loads(path.read_text(encoding="utf-8"))["results"]
        except (ValueError, KeyError):
            # hyperfine stopped early, as it does when a run fails.
            continue
        for result in results:
            times = result["times"]
            timings[result["parameters"]["core"]] = Timing(
                result["mean"], result["stddev"] or 0.0, len(times)
            )
    return timings


def change(current: Timing, baseline: Timing) -> str:
    """The relative change, and whether it stands out from run-to-run noise."""
    delta = current.mean - baseline.mean
    percent = 100 * delta / baseline.mean
    # Two standard errors of the difference between the means.
    noise = 2 * math.sqrt(current.stddev**2 / current.runs + baseline.stddev**2 / baseline.runs)
    if abs(delta) <= noise:
        return f"{percent:+.1f}% (within noise)"
    return f"**{percent:+.1f}%** ({'slower' if delta > 0 else 'faster'})"


def comment(
    current: dict[str, Timing], baseline: dict[str, Timing], run_url: str, baseline_url: str
) -> str:
    """The markdown comment body."""
    lines = [
        MARKER,
        "### Wall time: coverage.py's test suite under metacov",
        "",
    ]
    if baseline:
        lines += ["| Core | This PR | main | Change |", "| --- | --- | --- | --- |"]
    else:
        lines += ["| Core | This PR |", "| --- | --- |"]
    for core in CORES:
        now = str(current[core]) if core in current else "failed, see the job log"
        if not baseline:
            lines.append(f"| {core} | {now} |")
            continue
        then = str(baseline[core]) if core in baseline else "n/a"
        delta = (
            change(current[core], baseline[core]) if core in current and core in baseline else ""
        )
        lines.append(f"| {core} | {now} | {then} | {delta} |")
    runs = sorted({t.runs for t in current.values()})
    lines += [
        "",
        (
            f"Mean ± standard deviation of {'/'.join(map(str, runs)) or '?'} runs after a warmup, "
            "measured with hyperfine on a shared GitHub runner: expect a few percent of noise."
        ),
        "",
        f"[This run]({run_url})" + (f" · [main baseline]({baseline_url})" if baseline else ""),
    ]
    if not baseline:
        lines.append("No successful run on main yet to compare with.")
    return "\n".join(lines) + "\n"


def main() -> None:
    """Command-line entry point: print the comment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=pathlib.Path)
    parser.add_argument("--baseline", type=pathlib.Path)
    parser.add_argument("--run-url", default="")
    parser.add_argument("--baseline-url", default="")
    args = parser.parse_args()
    baseline = load_timings(args.baseline) if args.baseline and args.baseline.exists() else {}
    print(comment(load_timings(args.results), baseline, args.run_url, args.baseline_url), end="")


if __name__ == "__main__":
    main()

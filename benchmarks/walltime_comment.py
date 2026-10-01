# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/coveragepy/coveragepy/blob/main/NOTICE.txt

"""Write the pull request comment for walltime.yml's hyperfine results.

    python -m benchmarks.walltime_comment RESULTS_DIR [--base-label TEXT]

RESULTS_DIR holds hyperfine --export-json files, one per core, possibly in
subdirectories (as downloaded artifacts are).  Each file has a "head" result
and, when there was a different coverage.py to compare with, a "base" result
timed in the same job, on the same machine.

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
    """One variant's hyperfine result, in seconds."""

    mean: float
    stddev: float
    runs: int

    def __str__(self) -> str:
        return f"{self.mean:.1f} s ± {self.stddev:.1f}"


# Core, then variant ("base" or "head").
Timings = dict[str, dict[str, Timing]]


def load_timings(directory: pathlib.Path) -> Timings:
    """hyperfine results by core and variant, from every JSON export under `directory`."""
    timings: Timings = {}
    for path in sorted(directory.rglob("*.json")):
        try:
            results = json.loads(path.read_text(encoding="utf-8"))["results"]
        except (ValueError, KeyError):
            # hyperfine stopped early, as it does when a run fails.
            continue
        for result in results:
            parameters = result["parameters"]
            timings.setdefault(parameters["core"], {})[parameters["variant"]] = Timing(
                result["mean"], result["stddev"] or 0.0, len(result["times"])
            )
    return timings


def change(head: Timing, base: Timing) -> str:
    """The relative change, and whether it stands out from run-to-run noise."""
    delta = head.mean - base.mean
    percent = 100 * delta / base.mean
    # Two standard errors of the difference between the means.  Only fair
    # because both were timed in the same job, on the same machine.
    noise = 2 * math.sqrt(head.stddev**2 / head.runs + base.stddev**2 / base.runs)
    if abs(delta) <= noise:
        return f"{percent:+.1f}% (within noise)"
    return f"**{percent:+.1f}%** ({'slower' if delta > 0 else 'faster'})"


def comment(timings: Timings, run_url: str, base_label: str) -> str:
    """The markdown comment body."""
    compared = any("base" in variants for variants in timings.values())
    lines = [
        MARKER,
        "### Wall time: coverage.py's test suite under metacov",
        "",
    ]
    if compared:
        lines += ["| Core | Base | This PR | Change |", "| --- | --- | --- | --- |"]
    else:
        lines += ["| Core | This PR |", "| --- | --- |"]
    failed = "failed, see the job log"
    for core in CORES:
        variants = timings.get(core, {})
        head = str(variants["head"]) if "head" in variants else failed
        if not compared:
            lines.append(f"| {core} | {head} |")
            continue
        base = str(variants["base"]) if "base" in variants else failed
        delta = change(variants["head"], variants["base"]) if len(variants) == 2 else ""
        lines.append(f"| {core} | {base} | {head} | {delta} |")
    runs = sorted({t.runs for variants in timings.values() for t in variants.values()})
    lines += [
        "",
        (
            f"Mean ± standard deviation of {'/'.join(map(str, runs)) or '?'} "
            f"run{'' if runs == [1] else 's'} after a warmup, "
            "measured with hyperfine on a shared GitHub runner."
        ),
    ]
    if compared:
        lines.append(
            f"Base is {base_label}, timed in the same job, on the same machine. "
            "Compare a core only with itself: each core skips different tests."
        )
    else:
        lines.append("This PR doesn't change coverage.py, so there is nothing to compare with.")
    lines += ["", f"[This run]({run_url})"]
    return "\n".join(lines) + "\n"


def main() -> None:
    """Command-line entry point: print the comment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=pathlib.Path)
    parser.add_argument("--run-url", default="")
    parser.add_argument("--base-label", default="the coverage.py pinned by this PR's base commit")
    args = parser.parse_args()
    print(comment(load_timings(args.results), args.run_url, args.base_label), end="")


if __name__ == "__main__":
    main()

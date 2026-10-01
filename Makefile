# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/coveragepy/coveragepy/blob/main/NOTICE.txt

# Benchmarks measure whatever `coverage` is importable.  `make install` makes
# that the pinned coveragepy/ submodule; COVERAGE_DIR=../coveragepy uses your own
# checkout instead.

PYTHON ?= python3
COVERAGE_DIR ?= coveragepy
BENCH = $(PYTHON) -m pytest benchmarks

.PHONY: help install bench bench-smoke bench-prepare bench-real codspeed test lint upgrade

help:				#- Show this help.
	@grep '^[a-zA-Z_-]*:.*#-' Makefile | sed -e 's/:.*#-/\t/'

install:				#- Install the tools and the coverage.py under test.
	git submodule update --init coveragepy
	$(PYTHON) -m pip install --group bench --group codspeed --group lint
	$(PYTHON) -m pip install -e $(COVERAGE_DIR)

bench:				#- Time the component benchmarks.  ARGS='-k html' to select.
	$(BENCH) -m "benchmark and not slow" --benchmark-min-rounds=10 --benchmark-max-time=3 $(ARGS)

bench-smoke:			#- Run every component workload once and check its work.
	$(BENCH) --bench-smoke -m "benchmark and not real_project" $(ARGS)

bench-prepare:			#- Prepare the Jinja2 workload (Python 3.14, needs network).
	$(PYTHON) -m benchmarks.real_project prepare

bench-real:			#- Run the prepared Jinja2 workload.
	$(BENCH) --bench-real -m "benchmark and real_project" $(ARGS)

codspeed:			#- Run the CodSpeed-tracked benchmarks locally.
	$(BENCH) --codspeed -m "benchmark and not slow" $(ARGS)

test:				#- Check the workloads themselves, without timing.
	$(PYTHON) -m pytest tests $(ARGS)

lint:				#- Run ruff and mypy.
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	$(PYTHON) -m mypy

upgrade:			#- Re-pin the Jinja2 workload's dependencies.
	uv pip compile --quiet --generate-hashes --universal --python-version=3.14 -o requirements/real.txt requirements/real.in

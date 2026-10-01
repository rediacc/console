"""Ported campaign drills (`scripts/drills/`), dispatched by `./run.sh drill <name>`.

`lib` is the shared harness (the port of `scripts/drills/lib.sh`); each drill is its own module and builds on `lib.Drill`. A drill is a script with explicit setup, numbered assertions, teardown, and a non-zero exit on any failed assertion; it runs by hand or in the gated Drills CI job, never as a unit test.
"""

__all__: list[str] = []

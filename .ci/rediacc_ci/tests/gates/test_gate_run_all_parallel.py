"""Port of `.ci/scripts/test/gates/test-run-all-parallel.sh`.

Proof battery for the parallel scheduler inside `.ci/scripts/test/run-all.sh`.

WHY THIS EXISTS. run-all.sh is the runner for every OTHER gate test, so a defect in
it does not fail loudly: it fails by running FEWER tests, or by shredding their
output, or by reintroducing the real-tree collision the schedule exists to prevent.
All three of those look like a green run. What is pinned here is the four properties
that separate "fast" from "still a gate", and every timing assertion carries its own
control, because a stopwatch that can only ever read "fast enough" measures nothing.

  1. The pool really runs tests at the same time -- with the control that proves the
     measurement can FAIL (the same set at jobs=1 must be slow).
  2. jobs=1 and jobs=4 produce byte-identical transcripts, exit codes and failure
     sets over a mixed set (pass / red / vacuous-exit-0).
  3. No test's output interleaves with another's, under `--verbose`, where a naive
     worker-prints-directly design would shred both.
  4. The W/S hold-back actually holds: a scanner never runs while a real-tree writer
     is alive. Its control removes the schedule and shows the same fixtures go red,
     so a green here is the hold-back and not luck.

Everything runs against PLANTED FIXTURES in pytest's own `tmp_path` via
`RUN_ALL_GATES_DIR`, so this touches no real gate and no real tree.

THE STOPWATCH IS THE ONE PLACE THE PORT IS SIMPLER, and the twin's comment explains
why it had to be complicated. `date +%s%3N` is NOT portable: uutils coreutils (the
Rust reimplementation) IGNORES the precision digit and returns full NANOSECONDS
while GNU honours it, so on a GNU host the twin's first draft returned milliseconds
and passed, and on a uutils host it returned a number a million times larger and the
`>= 6000` assertion could never be satisfied. Measured 2026-08-27: four 2s tests
"took 2034286583ms", which is 2.03 SECONDS in the units actually returned. The twin
answers that with `EPOCHREALTIME`, a bash builtin that depends on no `date` at all.
`time.monotonic()` is the same answer in Python and is additionally immune to a wall
clock stepping mid-measurement, which `EPOCHREALTIME` is not.

NO `xdist_group`. Every case owns its fixture directory under `tmp_path`, and
`RUN_ALL_GATES_DIR` / `RUN_ALL_JOBS` / `RUN_ALL_WRITERS` / `RUN_ALL_SCANNERS` are
passed as an ENV OVERLAY per invocation rather than exported onto this process. Two
of these in one worker cannot see each other's fixtures or each other's schedule.

IT IS SLOW ON PURPOSE. The concurrency control needs the serial arm to take longer
than 8 seconds; a fixture set fast enough to be cheap would make the measurement
unable to fail, which is the whole point of having a control.
"""

import re
import stat
import time

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-run-all-parallel.sh"

RUNNER = paths.from_root(".ci", "scripts", "test", "run-all.sh")

BLOCK_LINE = re.compile(r"^(alpha|beta)-[0-9]", re.MULTILINE)


def mk_fixture(directory, name: str, *body: str) -> None:
    """One executable gate-test fixture, `set -euo pipefail` and all."""
    path = directory / name
    path.write_text(
        "#!/bin/bash\nset -euo pipefail\n" + "".join("%s\n" % line for line in body),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run_runner(gate, gates_dir, *args: str, env: dict[str, str] | None = None):
    """Drive the real runner over a fixture directory. Streams MERGED, as the twin does."""
    if not RUNNER.is_file():
        gate.log_fail(
            "%s is missing; this gate has nothing to prove" % paths.relative_to_root(RUNNER)
        )
    bash = harness.require_tool("bash", "install bash; the subject is a bash script")
    overlay = {"RUN_ALL_GATES_DIR": str(gates_dir)}
    overlay.update(env or {})
    return harness.run([bash, str(RUNNER), *args], env=overlay, timeout=600)


def test_pool_runs_tests_concurrently(gate, tmp_path):
    """The pool overlaps, AND the stopwatch that says so can fail."""
    gate.log_test("four 2s fixtures must overlap at jobs=4 and must NOT at jobs=1")
    gates = tmp_path / "gates"
    gates.mkdir()
    for i in (1, 2, 3, 4):
        mk_fixture(
            gates, "test-sleeper-%d.sh" % i, "sleep 2", 'echo "PASS: sleeper %d finished"' % i
        )

    start = time.monotonic()
    run_runner(gate, gates, env={"RUN_ALL_JOBS": "4"})
    parallel_ms = int((time.monotonic() - start) * 1000)
    if parallel_ms >= 6000:
        gate.log_fail("four 2s tests took %dms at jobs=4; they are not overlapping" % parallel_ms)
    gate.assertions += 1
    gate.log_pass("four 2s tests finish in %dms at jobs=4 (ceiling 6000ms)" % parallel_ms)

    # THE CONTROL. Without it, a runner that silently ignored RUN_ALL_JOBS and ran
    # everything at once anyway would pass the assertion above, and so would a
    # broken stopwatch. The same four fixtures at jobs=1 must be SLOW.
    start = time.monotonic()
    run_runner(gate, gates, env={"RUN_ALL_JOBS": "1"})
    serial_ms = int((time.monotonic() - start) * 1000)
    if serial_ms < 8000:
        gate.log_fail(
            "control failed: the same four took %dms at jobs=1, so the timing assertion "
            "above cannot fire" % serial_ms
        )
    gate.assertions += 1
    gate.log_pass(
        "control: the same four take %dms at jobs=1 (floor 8000ms), so the measurement "
        "can fail" % serial_ms
    )


def test_jobs_one_and_jobs_four_agree(gate, tmp_path):
    """Determinism across worker counts, over a set that is NOT all-green."""
    gate.log_test("a mixed pass / red / vacuous set must score identically at 1 and 4 workers")
    gates = tmp_path / "gates"
    gates.mkdir()
    mk_fixture(gates, "test-a-green.sh", 'echo "PASS: green fixture asserted something"')
    mk_fixture(gates, "test-b-red.sh", 'echo "diagnostic line from the red fixture"', "exit 1")
    # Exit 0 with no PASS: line at all. run-all.sh must score this as a FAILURE in
    # both modes; a mode that scored it differently would mean the vacuity guard
    # moved with the scheduler.
    mk_fixture(gates, "test-c-vacuous.sh", 'echo "this fixture asserts nothing"', "exit 0")
    mk_fixture(
        gates, "test-d-green.sh", "sleep 1", 'echo "PASS: slow green fixture asserted something"'
    )

    serial = run_runner(gate, gates, env={"RUN_ALL_JOBS": "1"})
    parallel = run_runner(gate, gates, env={"RUN_ALL_JOBS": "4"})

    gate.assert_eq(serial.rc, 1, "the mixed fixture set must exit 1 at jobs=1")
    gate.assert_eq(parallel.rc, serial.rc, "exit code must not depend on the worker count")
    gate.assert_eq(
        parallel.combined, serial.combined, "the transcript must not depend on the worker count"
    )
    gate.assert_contains(
        serial.combined, "2 passed, 2 failed", "the mixed set must score 2 pass / 2 fail"
    )
    gate.assert_contains(
        serial.combined,
        "test-c-vacuous.sh (exited 0 but made no assertions)",
        "the vacuity guard must still fire under the scheduler",
    )
    gate.log_pass("jobs=1 and jobs=4 agree byte-for-byte on transcript, exit code and failure set")


def test_output_blocks_never_interleave(gate, tmp_path):
    """No interleaving. This is what the main-printer design buys."""
    gate.log_test("--verbose replays each whole log, so a direct-printing worker would shred it")
    gates = tmp_path / "gates"
    gates.mkdir()
    for name in ("alpha", "beta"):
        mk_fixture(
            gates,
            "test-%s.sh" % name,
            'echo "%s-1"' % name,
            "sleep 0.4",
            'echo "%s-2"' % name,
            "sleep 0.4",
            'echo "%s-3"' % name,
            'echo "PASS: %s emitted three lines"' % name,
        )

    result = run_runner(gate, gates, "--verbose", env={"RUN_ALL_JOBS": "4"})
    # `grep -oE '^(alpha|beta)-[0-9]' | paste -sd' '` in the twin. The same scan in
    # Python: an anchored per-line match, joined with single spaces. Anchored, so a
    # line merely CONTAINING the token (a summary line naming the fixture) is not
    # counted on either side.
    seen = " ".join(
        line[: len(match.group(0))]
        for line in result.combined.splitlines()
        for match in [BLOCK_LINE.match(line)]
        if match
    )
    gate.assert_eq(
        seen,
        "alpha-1 alpha-2 alpha-3 beta-1 beta-2 beta-3",
        "each test's lines must stay contiguous and in glob order",
    )
    gate.log_pass("two concurrent tests emit contiguous, glob-ordered blocks under --verbose")


def test_scanners_never_overlap_writers(gate, tmp_path):
    """The W/S hold-back, and the control that proves it is doing the work."""
    gate.log_test("a scanner must never run while a real-tree writer holds the tree")
    gates = tmp_path / "gates"
    gates.mkdir()
    sentinel = tmp_path / "writer.sentinel"

    # The writer holds a sentinel for 2s, exactly as the two real writers hold a
    # fixture file inside .ci/scripts and scripts.
    mk_fixture(
        gates,
        "test-w-writer.sh",
        'touch "%s"' % sentinel,
        "sleep 2",
        'rm -f "%s"' % sentinel,
        'echo "PASS: writer held and released its fixture"',
    )
    # The scanner reds if it sees the sentinel, exactly as a recursive copy of a
    # directory reds when a file vanishes underneath it.
    mk_fixture(
        gates,
        "test-x-scanner.sh",
        "sleep 1",
        'if [[ -e "%s" ]]; then' % sentinel,
        '    echo "writer fixture was present while the scanner ran" >&2',
        "    exit 1",
        "fi",
        'echo "PASS: scanner saw a quiet tree"',
    )

    scheduled = run_runner(
        gate,
        gates,
        env={
            "RUN_ALL_JOBS": "4",
            "RUN_ALL_WRITERS": "test-w-writer.sh",
            "RUN_ALL_SCANNERS": "test-x-scanner.sh",
        },
    )
    gate.assert_eq(
        scheduled.rc, 0, "with the W/S schedule the scanner must never see the writer's fixture"
    )
    gate.assert_contains(
        scheduled.combined, "2 passed, 0 failed", "both fixtures must pass under the schedule"
    )
    gate.log_pass("the S set is held back until the W chain has released the tree")

    # THE CONTROL. Drop both fixtures into T -- which is what a flat pool is -- and
    # the same two must collide. Without this, a runner that ran everything serially,
    # or one whose scanner check never fired, would look identical.
    unscheduled = run_runner(
        gate, gates, env={"RUN_ALL_JOBS": "4", "RUN_ALL_WRITERS": "", "RUN_ALL_SCANNERS": ""}
    )
    gate.assert_eq(
        unscheduled.rc,
        1,
        "control failed: a flat pool must reproduce the collision this schedule prevents",
    )
    gate.assert_contains(
        unscheduled.combined,
        "writer fixture was present while the scanner ran",
        "control failed: the collision must be the reported reason",
    )
    gate.log_pass(
        "control: without the schedule the same two fixtures collide, so the green above is "
        "the hold-back"
    )

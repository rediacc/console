"""Port of `.ci/scripts/test/gates/test-ci-runner.sh`, retired in W7 P5.

Unit test for the parallel gate runner: `scripts/ci-runner/{run,pool,exec,report}.ts`.

WHAT THIS GUARDS, carried across from the twin's header. `npm run ci` used to be a 93-step `&&` string. Replacing it with a scheduler moves four properties out of the shell and into TypeScript, and every one of them is silent when it breaks:

  1. A failing gate must make the run exit non-zero AND print its complete
     captured output. A runner that swallowed either would report green over a
     red tree, which is worse than the chain it replaced.
  2. stdout and stderr are captured SEPARATELY. Merging them hides
     progress-text-on-stdout and swallowed-output defects, a class this repo has
     been bitten by; the house rule exists because of it.
  3. A gate whose dependency FAILED is reported skipped, never passed, and makes
     the run non-zero. "Skipped" silently becoming "ok" is exactly the shape of
     rediacc/console#549.
  4. mutex and jobs really constrain overlap. These cannot be verified by
     reading; the pool has to be observed, so every concurrency case records
     real start/end timestamps from the gate processes themselves.

CONTROL-PROVEN. Cases 4 and 6 each carry an inverted leg: the same probe over the same fixture with the constraint removed must observe the OPPOSITE concurrency. Without that, a probe hardcoded to report 1 (or a runner that accidentally serialises everything) would pass the mutex case while proving nothing at all.

--------------------------------------------------------------------------
NO CASE HERE CAN LAUNCH A REAL GATE SWEEP, AND THAT IS CHECKED
--------------------------------------------------------------------------
THIS IS THE TRAP THE PORT WAS WARNED ABOUT. The subject IS the CI runner, so a port that got the seam wrong would not fail -- it would run the entire 400-plus gate battery inside `check:ci-pytest`, nested, once per case.

Two things stop that, and neither is a promise:

  * Every case drives a SYNTHETIC manifest through `CI_RUNNER_MANIFEST`,
    exactly as the twin does. The real manifest is not the subject: what is
    under test is the scheduler, and a fixture is the only way to plant a
    failing gate without breaking the tree.
  * The one case that runs with no manifest seam at all, case 11, invokes
    `--selftest`, and `run.ts`'s selftest builds its own three synthetic specs
    (`selftest:pass`, `selftest:fail`, `selftest:dependent`) rather than reading
    the manifest. It runs `echo`, not a gate.

`test_the_manifest_seam_is_honoured` is the control on the first bullet, added by the port: it drives a one-gate fixture and requires the summary to name exactly ONE gate, against a real registered set two orders of magnitude bigger. A seam that stopped being honoured therefore reds by name, in under a second, instead of quietly turning one pytest case into a full nested battery.

NO CASE WAS NARROWED. Every one of the twin's twelve is driven against the same fixture the twin uses, with the same real `tsx` invocation of the same real `run.ts`.

--------------------------------------------------------------------------
THE TWO PLACES THIS PORT DOES NOT SHELL OUT WHERE THE TWIN DOES
--------------------------------------------------------------------------
Both are the same substitution and neither changes a claim.

  * Case 10 parses the `--json` document with `json.loads` instead of a nested
    `node -e` program. The assertions are the seven the node program made, one
    for one, and they now fail with a Python diagnostic naming the field rather
    than with "node exited 1".
  * Case 11 reads `package.json`'s `scripts.ci` with `json.loads` instead of
    `node -e 'require("./package.json")'`.

`tsx` and `node` are still REQUIRED, loudly, because the subject is TypeScript and cannot be driven without them. A missing one is a failure carrying the fix, never a skip: a case that could not run has not been checked.
"""

import json
import os
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

# THE OPT-IN IS OWED, AND THE FIRST DRAFT OF THIS FILE GOT IT WRONG. The reasoning was that every case drives a synthetic manifest in a tempdir, so nothing here touches the real tree and the attribute would be an over-claim. The LOCK says otherwise: `gate-test:ci-runner` declares `reads: ["tree:repo"]`, which puts the twin in the real-tree set that `xdist_groups.real_tree_twins`
# derives, and `real_tree_admission` refuses a member that does not opt in. The declaration is also right on the merits: the runner is driven FROM the repo root, case 11 reads
# package.json and runs `--selftest` with no seam at all, and the added seam control
# reads gates.lock.json. Reading the tree while another step rewrites it is the divergence that would be blamed on this port.
REAL_TREE_TWIN = True

TSX_REL = "node_modules/.bin/tsx"
RUNNER_REL = "scripts/ci-runner/run.ts"
TSX = paths.from_root(*TSX_REL.split("/"))
RUNNER = paths.from_root(*RUNNER_REL.split("/"))
LOCK_REL = "scripts/ci-runner/gates.lock.json"

# `3 gates: 3 ok, 0 failed, 0 skipped`, and `1 gate: ...` when there is one. THE PLURAL IS OPTIONAL ON PURPOSE: the added seam control drives a ONE-entry fixture, and a pattern demanding "gates" matched nothing against the runner's singular line. It was the control saying so that found this, in one run.
SUMMARY_RE = re.compile(r"^(\d+) gates?: ", re.MULTILINE)


class Run:
    """`RC`, `OUT` and `ERR` from the twin, as one object.

    The twin keeps the two streams in SEPARATE FILES and case 2 asserts on the split; nothing here merges them either, for the same reason.
    """

    def __init__(self, result: harness.RunResult) -> None:
        self.rc = result.rc
        self.out = result.out
        self.err = result.err


def require_runner(gate) -> str:
    """tsx and the runner, proved present before anything is claimed.

    A MISSING TOOL IS A LOUD FAILURE CARRYING THE FIX, not a stack trace that reads as flake and not a skip. The twin does the same two checks at file scope; here they are per-case so one missing binary names itself in every
    case rather than aborting collection.
    """
    if not os.access(TSX, os.X_OK):
        gate.log_fail(
            "tsx not installed at %s, so the subject could not be driven at all -- "
            "which is a FAILURE and not a pass. Fix: npm install && npm run "
            "install:natives" % TSX_REL
        )
    if not RUNNER.is_file():
        gate.log_fail("runner not found at %s" % RUNNER_REL)
    return os.fspath(TSX)


def manifest(gate, work, name: str, entries: list[dict]) -> str:
    """`manifest <name>` -- write a JSON fixture, substituting @WORK@.

    ANTI-VACUITY. An EMPTY entry list here would mean the case drove the runner over nothing, and `test_empty_manifest_refuses` is the only case entitled to do that -- it passes its own literal `[]` rather than coming through here. Everywhere else an empty fixture is a broken test, not a quiet one.
    """
    if not entries:
        gate.log_fail(
            "manifest(%s) was given ZERO entries, so the runner would have been driven "
            "over nothing and every assertion about its summary would be about an "
            "empty run." % name
        )
    text = json.dumps(entries).replace("@WORK@", os.fspath(work))
    path = work / (name + ".json")
    path.write_text(text, encoding="utf-8")
    return os.fspath(path)


def spec(gid: str, run: str, **extra) -> dict:
    """One synthetic manifest entry, in the twin's exact shape.

    `ci.kind: local-only` with a BLOCKER reason is what the twin writes on every fixture entry, and it is not decoration: the runner validates the `ci` block, so a fixture without it would be rejected before the scheduler was reached.
    """
    entry = {
        "id": gid,
        "run": run,
        "gate": True,
        "leaves": [],
        "ci": {"kind": "local-only", "blocker": "BLOCKER: synthetic fixture"},
    }
    entry.update(extra)
    return entry


def stamped(log: str) -> str:
    """The twin's timestamp probe body: `S <ns>`, sleep, `E <ns>`."""
    return "echo S $(date +%%s%%N) >> %s; sleep 0.4; echo E $(date +%%s%%N) >> %s" % (log, log)


def run_ci(gate, mf: str, *args: str, env: dict | None = None) -> Run:
    """`run_ci <manifest> [args...]` -- drive the REAL runner, streams apart.

    Never merged: case 2 asserts on the split, and a helper that merged them here would make that case unfalsifiable.
    """
    tsx = require_runner(gate)
    overlay = {"CI_RUNNER_MANIFEST": mf}
    overlay.update(env or {})
    return Run(
        harness.run(
            [tsx, os.fspath(RUNNER), *args], cwd=paths.repo_root(), env=overlay, timeout=300
        )
    )


def max_concurrency(gate, path) -> int:
    """`max_concurrency <logfile>` -- replay S/E events in timestamp order.

    The gates write these lines THEMSELVES, so this measures real process overlap rather than the scheduler's own bookkeeping. An empty log is a FAILURE: zero observed events is what a probe that never ran looks like, and reporting concurrency 0 would satisfy nothing and alarm no one.
    """
    if not path.is_file():
        gate.log_fail(
            "the concurrency probe wrote no log at %s, so the gates never ran and any "
            "concurrency reported from it would be a number about nothing." % path.name
        )
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in {"S", "E"}:
            events.append((int(parts[1]), parts[0]))
    if not events:
        gate.log_fail(
            "the concurrency log %s holds ZERO S/E events; the probe is broken, so the "
            "measurement below would mean nothing." % path.name
        )
    events.sort()
    current = peak = 0
    for _ts, kind in events:
        if kind == "S":
            current += 1
            peak = max(peak, current)
        else:
            current -= 1
    return peak


def first_ts(marker: str, path) -> int | None:
    """`first_ts <marker> <logfile>` -- the earliest timestamp for a marker.

    FILE ORDER, not sorted order, exactly as the twin's `grep | head -1` reads it. `None` rather than an empty string when nothing matched, so the explicit check in case 5 reports what went wrong instead of comparing against "".
    """
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == marker:
            return int(parts[1])
    return None


# ---------------------------------------------------------------- case 1


def test_all_pass_is_quiet(gate):
    with harness.temp_dir() as work:
        mf = manifest(
            gate,
            work,
            "case1",
            [
                spec("g1", "echo one-output"),
                spec("g2", "echo two-output"),
                spec("g3", "echo three-output"),
            ],
        )
        r = run_ci(gate, mf, "--jobs", "2")
        gate.assert_exit_code(0, r.rc, "an all-pass manifest must exit 0")
        for gid in ("g1", "g2", "g3"):
            gate.assert_contains(r.out, "  ok    " + gid, "every gate reports a line")
        gate.assert_not_contains(r.out, "one-output", "a passing gate's output stays quiet")
        gate.assert_contains(
            r.out, "3 gates: 3 ok, 0 failed, 0 skipped", "summary counts every gate"
        )
        gate.log_pass("case 1: all-pass run is quiet, exits 0, one line per gate")


# ---------------------------------------------------------------- case 2


def test_failure_prints_both_streams(gate):
    with harness.temp_dir() as work:
        probe = work / "case2.probe"
        mf = manifest(
            gate,
            work,
            "case2",
            [
                spec("ok-a", "echo ran-a >> @WORK@/case2.probe"),
                spec("boom", "echo BOOM-ON-STDOUT; echo BOOM-ON-STDERR >&2; exit 7"),
                spec("ok-b", "echo ran-b >> @WORK@/case2.probe"),
            ],
        )
        r = run_ci(gate, mf, "--jobs", "2")
        gate.assert_exit_code(1, r.rc, "one failing gate must make the run exit 1")
        gate.assert_contains(r.out, "FAIL  boom", "the failing gate is named")
        gate.assert_contains(r.out, "exit 7", "the real exit code is reported")
        gate.assert_contains(r.out, "--- stdout ---", "captured stdout has its own header")
        gate.assert_contains(r.out, "--- stderr ---", "captured stderr has its own header")
        # Asserting only that both markers appear SOMEWHERE would pass on a runner that merged the two streams, which is the defect the separation exists to prevent. So each marker is required in its own block and forbidden in the other. The stderr slice stops at the blank line that closes the failure block: the footer's "rerun all failures" line quotes the whole gate body, both
        # markers included, and would defeat a naive to-end-of-file slice.
        lines = r.out.splitlines()
        stdout_block, stderr_block, mode = [], [], None
        for line in lines:
            if "--- stdout ---" in line:
                mode = "out"
                stdout_block.append(line)
                continue
            if "--- stderr ---" in line:
                stdout_block.append(line)
                mode = "err"
                stderr_block.append(line)
                continue
            if mode == "out":
                stdout_block.append(line)
            elif mode == "err":
                if line.strip() == "":
                    mode = None
                    continue
                stderr_block.append(line)
        stdout_text, stderr_text = "\n".join(stdout_block), "\n".join(stderr_block)
        gate.assert_contains(
            stdout_text, "BOOM-ON-STDOUT", "captured stdout is printed under the stdout header"
        )
        gate.assert_not_contains(
            stdout_text, "BOOM-ON-STDERR", "stderr must not leak into the stdout block"
        )
        gate.assert_contains(
            stderr_text, "BOOM-ON-STDERR", "captured stderr is printed under the stderr header"
        )
        gate.assert_not_contains(
            stderr_text, "BOOM-ON-STDOUT", "stdout must not leak into the stderr block"
        )
        gate.assert_contains(r.out, "rerun: echo BOOM-ON-STDOUT", "the rerun command is printed")
        # keep-going is the default for the same reason CI puts !cancelled() on every quality step: one run has to surface every failure.
        if not probe.is_file():
            gate.log_fail("neither gate around the failure wrote the probe file")
        text = probe.read_text(encoding="utf-8")
        gate.assert_contains(text, "ran-a", "gates before the failure still ran")
        gate.assert_contains(text, "ran-b", "gates after the failure still ran")
        gate.log_pass("case 2: a failure prints both streams separately and the rest still runs")


# ---------------------------------------------------------------- case 3


def test_fail_fast_stops_the_run(gate):
    with harness.temp_dir() as work:
        mf = manifest(
            gate,
            work,
            "case3",
            [
                spec("boom", "exit 1"),
                spec("after-1", "echo ran >> @WORK@/case3.probe"),
                spec("after-2", "echo ran >> @WORK@/case3.probe"),
            ],
        )
        r = run_ci(gate, mf, "--jobs", "1", "--fail-fast")
        gate.assert_exit_code(1, r.rc, "--fail-fast still exits 1")
        gate.assert_contains(
            r.out, "not run (--fail-fast)", "the remaining gates say why they did not run"
        )
        gate.assertions += 1
        if (work / "case3.probe").is_file():
            gate.log_fail("--fail-fast let a later gate execute")
        gate.log_pass("case 3: --fail-fast stops the run and the remaining gates never execute")


# ---------------------------------------------------------------- case 4


def test_mutex_serialises(gate):
    with harness.temp_dir() as work:
        log = work / "case4.log"
        mf = manifest(
            gate,
            work,
            "case4",
            [
                spec("m1", stamped("@WORK@/case4.log"), mutex=["shared"]),
                spec("m2", stamped("@WORK@/case4.log"), mutex=["shared"]),
            ],
        )
        r = run_ci(gate, mf, "--jobs", "4")
        gate.assert_exit_code(0, r.rc, "the mutex fixture passes")
        gate.assert_eq(
            max_concurrency(gate, log),
            1,
            "two gates sharing a mutex group must never overlap",
        )

        # CONTROL: the same probe, the same two gates, no mutex. If this does not observe an overlap the assertion above proves nothing.
        log_b = work / "case4b.log"
        mf = manifest(
            gate,
            work,
            "case4b",
            [
                spec("f1", stamped("@WORK@/case4b.log")),
                spec("f2", stamped("@WORK@/case4b.log")),
            ],
        )
        run_ci(gate, mf, "--jobs", "4")
        gate.assert_eq(
            max_concurrency(gate, log_b),
            2,
            "CONTROL: without a mutex the same two gates do overlap",
        )
        gate.log_pass("case 4: mutex serialises, and the control proves the probe sees overlap")


# ---------------------------------------------------------------- case 4b


def test_reads_shares_and_excludes(gate):
    """The OTHER claim strength. `reads` is the shared half of the isolation contract defined in pool.ts: any number of readers of a resource may overlap, none may overlap a writer of it. Case 4 above proves the exclusive half and would stay green if `reads` were ignored entirely, or if it were treated as a second exclusive group -- and those two mistakes fail in opposite
    directions, one losing the isolation and one serialising twenty-one read-only tests for nothing. Both have to be observed, so both are asserted here.

    WHY IT MATTERS BEYOND THE SCHEDULER. Until 2026-09-06 the two schedulers over the gate-test battery decided isolation separately: the shell runner then at .ci/scripts/test/run-all.sh carried hand-maintained W/S name lists while the manifest declared nothing, so `npm run ci` ran the three real-tree writers concurrently with the scanners that enumerate the same directories. The
    battery derives its sets
    from the same `mutex`/`reads` declarations this case exercises.
    """
    with harness.temp_dir() as work:
        # Two SHARED holders of one resource must overlap. If this reads 1, `reads` has been collapsed into `mutex` and the battery's scanners serialise.
        mf = manifest(
            gate,
            work,
            "case4c",
            [
                spec("r1", stamped("@WORK@/case4c.log"), reads=["tree:x"]),
                spec("r2", stamped("@WORK@/case4c.log"), reads=["tree:x"]),
            ],
        )
        r = run_ci(gate, mf, "--jobs", "4")
        gate.assert_exit_code(0, r.rc, "the reads fixture passes")
        gate.assert_eq(
            max_concurrency(gate, work / "case4c.log"),
            2,
            "two gates SHARING a resource must overlap; reads is not a second mutex",
        )

        # A writer and a reader of the SAME resource must not. If this reads 2, `reads` is being ignored and the writer runs while the tree is enumerated.
        mf = manifest(
            gate,
            work,
            "case4d",
            [
                spec("w1", stamped("@WORK@/case4d.log"), mutex=["tree:x"]),
                spec("r1", stamped("@WORK@/case4d.log"), reads=["tree:x"]),
            ],
        )
        r = run_ci(gate, mf, "--jobs", "4")
        gate.assert_exit_code(0, r.rc, "the writer/reader fixture passes")
        gate.assert_eq(
            max_concurrency(gate, work / "case4d.log"),
            1,
            "an exclusive holder must never overlap a shared holder of the same resource",
        )

        # CONTROL: the same two gates naming DIFFERENT resources must overlap. The lock is keyed, not global, and without this the assertion above is satisfied by a scheduler that simply serialises everything.
        mf = manifest(
            gate,
            work,
            "case4e",
            [
                spec("w1", stamped("@WORK@/case4e.log"), mutex=["tree:x"]),
                spec("r1", stamped("@WORK@/case4e.log"), reads=["tree:y"]),
            ],
        )
        run_ci(gate, mf, "--jobs", "4")
        gate.assert_eq(
            max_concurrency(gate, work / "case4e.log"),
            2,
            "CONTROL: a writer and a reader of DIFFERENT resources do overlap",
        )
        gate.log_pass(
            "case 4b: reads shares among readers, excludes against a writer, and is "
            "keyed per resource"
        )


# ---------------------------------------------------------------- case 5


def test_needs_orders_and_skips(gate):
    with harness.temp_dir() as work:
        log = work / "case5.log"
        mf = manifest(
            gate,
            work,
            "case5",
            [
                {
                    **spec(
                        "prep",
                        "echo S $(date +%s%N) >> @WORK@/case5.log; sleep 0.3; "
                        "echo E $(date +%s%N) >> @WORK@/case5.log",
                    ),
                    "gate": False,
                },
                spec("user", "echo U $(date +%s%N) >> @WORK@/case5.log", needs=["prep"]),
                {**spec("badprep", "echo prep-failed >&2; exit 2"), "gate": False},
                spec("victim", "echo victim-ran >> @WORK@/case5.probe", needs=["badprep"]),
            ],
        )
        r = run_ci(gate, mf, "--jobs", "4")
        gate.assert_exit_code(1, r.rc, "a skipped gate makes the run non-zero")
        prep_end = first_ts("E", log)
        user_start = first_ts("U", log)
        gate.assertions += 1
        if prep_end is None or user_start is None:
            gate.log_fail("case 5 probe did not record both timestamps")
        gate.assertions += 1
        if user_start <= prep_end:
            gate.log_fail("a dependent started before its dependency finished")
        gate.assert_contains(
            r.out, "SKIP  victim", "a dependent of a failed gate is reported skipped"
        )
        gate.assert_contains(r.out, "needs badprep", "the skip names the dependency that failed")
        gate.assert_not_contains(
            r.out, "ok    victim", "a skipped gate is never reported as passed"
        )
        gate.assertions += 1
        if (work / "case5.probe").is_file():
            gate.log_fail("a dependent of a failed gate executed anyway")
        gate.log_pass(
            "case 5: needs orders execution, and a failed dependency skips rather than passes"
        )


# ---------------------------------------------------------------- case 6


def test_jobs_bounds_concurrency(gate):
    with harness.temp_dir() as work:
        log = work / "case6.log"
        body = (
            "echo S $(date +%s%N) >> @WORK@/case6.log; sleep 0.3; "
            "echo E $(date +%s%N) >> @WORK@/case6.log"
        )
        mf = manifest(gate, work, "case6", [spec("j%d" % n, body) for n in range(1, 7)])
        r = run_ci(gate, mf, "--jobs", "2")
        gate.assert_exit_code(0, r.rc, "the concurrency fixture passes")
        gate.assert_eq(max_concurrency(gate, log), 2, "--jobs 2 admits exactly two gates at a time")

        # CONTROL: the same six gates at --jobs 5 must exceed 2, or the assertion above would also pass on a runner that serialises everything.
        log.unlink()
        run_ci(gate, mf, "--jobs", "5")
        conc = max_concurrency(gate, log)
        gate.assertions += 1
        if conc <= 2:
            gate.log_fail("CONTROL: --jobs 5 observed only %d concurrent gates" % conc)
        gate.log_pass("case 6: --jobs bounds concurrency exactly, proven against a wider budget")


# ---------------------------------------------------------------- case 7


def test_empty_manifest_refuses(gate):
    with harness.temp_dir() as work:
        path = work / "case7.json"
        path.write_text("[]\n", encoding="utf-8")
        r = run_ci(gate, os.fspath(path))
        gate.assertions += 1
        if r.rc == 0:
            gate.log_fail("an empty manifest must not exit 0")
        gate.assert_contains(
            r.err, "Refusing to run", "the diagnostic uses the house refusal wording"
        )
        gate.log_pass("case 7: an empty manifest refuses to run and exits non-zero")


# ---------------------------------------------------------------- case 8


def test_missing_duration_cache(gate):
    with harness.temp_dir() as work:
        cache = work / "no" / "such" / "dir" / "gate-durations.json"
        mf = manifest(
            gate,
            work,
            "case8",
            [spec("c1", "true"), {**spec("c2", "true"), "weight": 2}],
        )
        r = run_ci(gate, mf, "--jobs", "2", env={"CI_RUNNER_CACHE": os.fspath(cache)})
        gate.assert_exit_code(0, r.rc, "a missing duration cache must not fail the run")
        gate.assertions += 1
        if not cache.is_file():
            gate.log_fail("the run did not write the duration cache it was pointed at")
        gate.assertions += 1
        if '"c1"' not in cache.read_text(encoding="utf-8"):
            gate.log_fail("the duration cache recorded no timing for c1")
        gate.log_pass("case 8: a missing duration cache is created, not fatal")


# ---------------------------------------------------------------- case 9


def test_summary_is_deterministic(gate):
    def summary(text: str) -> str:
        out, taking = [], False
        for line in text.splitlines():
            if line.startswith("FAILED:"):
                taking = True
            if taking:
                out.append(line)
            if taking and line.startswith("===="):
                break
        return "\n".join(out)

    with harness.temp_dir() as work:
        mf = manifest(
            gate,
            work,
            "case9",
            [
                spec("d1", "true"),
                spec("d2", "exit 1"),
                spec("d3", "sleep 0.2"),
                spec("d4", "true"),
                spec("d5", "exit 1"),
                spec("d6", "true"),
            ],
        )
        first = run_ci(gate, mf, "--jobs", "4")
        first_summary = summary(first.out)
        second = run_ci(gate, mf, "--jobs", "4")
        second_summary = summary(second.out)
        gate.assert_exit_code(first.rc, second.rc, "the exit code is stable across runs")
        gate.assert_eq(
            second_summary,
            first_summary,
            "the failure summary ordering is stable across runs",
        )
        gate.assert_contains(first_summary, "d2", "the summary names the failing gates")
        gate.log_pass("case 9: exit code and summary ordering are stable across runs")


# ---------------------------------------------------------------- case 10


def test_json_matches_what_was_printed(gate):
    with harness.temp_dir() as work:
        rerun = "echo JSON-STDOUT-MARKER; echo JSON-STDERR-MARKER >&2; exit 4"
        mf = manifest(gate, work, "case10", [spec("jok", "echo fine"), spec("jbad", rerun)])
        # Under --json the machine document owns stdout and the human stream moves to stderr, so an agent can consume one and tail the other.
        r = run_ci(gate, mf, "--jobs", "2", "--json")
        gate.assert_exit_code(1, r.rc, "--json does not change the exit code")
        try:
            doc = json.loads(r.out)
        except json.JSONDecodeError as exc:
            gate.log_fail(
                "--json did not put a parseable document on stdout (%s). stdout was: %s"
                % (exc, r.out)
            )
        bad = next((g for g in doc.get("gates", []) if g.get("id") == "jbad"), None)
        gate.assert_eq(doc.get("exitCode"), 1, "json exitCode")
        gate.assert_eq(doc.get("partial"), False, "a full run must not report partial:true")
        gate.assertions += 1
        if bad is None:
            gate.log_fail("the failing gate is missing from the json")
        gate.assert_contains(
            bad.get("stdout", ""),
            "JSON-STDOUT-MARKER",
            "json stdout does not carry the captured stdout",
        )
        gate.assert_contains(
            bad.get("stderr", ""),
            "JSON-STDERR-MARKER",
            "json stderr does not carry the captured stderr",
        )
        gate.assert_eq(bad.get("status"), "fail", "json status")
        gate.assert_eq(bad.get("rerun"), rerun, "json rerun is wrong")
        # The same bytes must appear in the human stream, or the two views disagree.
        gate.assert_contains(
            r.err, "JSON-STDOUT-MARKER", "the human stream carries the captured stdout"
        )
        gate.assert_contains(
            r.err, "JSON-STDERR-MARKER", "the human stream carries the captured stderr"
        )
        gate.log_pass("case 10: --json parses and agrees with the printed output")


# ---------------------------------------------------------------- case 11


def test_selftest_is_wired_into_the_npm_key(gate):
    """The control has to run on every real invocation. A --selftest that sits behind a flag nothing passes is the exact failure check-gate-reachability recorded for check-i18n-cross-locale, which shipped broken for months."""
    tsx = require_runner(gate)
    pkg = paths.from_root("package.json")
    if not pkg.is_file():
        gate.log_fail("package.json is missing, so the wiring claim cannot be checked")
    ci_key = json.loads(pkg.read_text(encoding="utf-8")).get("scripts", {}).get("ci", "")
    gate.assert_contains(ci_key, "--selftest", "the ci npm key must invoke the runner's control")
    result = harness.run([tsx, os.fspath(RUNNER), "--selftest"], cwd=paths.repo_root(), timeout=300)
    gate.assert_exit_code(0, result.rc, "--selftest passes on a healthy runner")
    gate.assert_contains(result.out, "selftest ok", "--selftest reports its assertion count")
    gate.log_pass("case 11: the anti-vacuity control is wired into the ci npm key and fires")


# ---------------------------------------------------------------- case 12


def test_missing_tool_fails_loudly(gate):
    """A gate whose tool does not resolve must FAIL, never pass quietly. This is not hypothetical: during this work an `npx biome` in a directory with no node_modules link exited 0 on a deliberately misformatted file, and the green came from a tool that never really ran. A runner that swallowed a 127 would turn that class of accident into a green CI report."""
    with harness.temp_dir() as work:
        mf = manifest(
            gate,
            work,
            "case12",
            [
                spec("missing-tool", "definitely-not-a-real-command --check"),
                spec("real", "true"),
            ],
        )
        r = run_ci(gate, mf, "--jobs", "2")
        gate.assert_exit_code(1, r.rc, "a gate whose command does not exist must fail the run")
        gate.assert_contains(r.out, "FAIL  missing-tool", "the unresolvable gate is named")
        gate.assert_contains(r.out, "exit 127", "the shell's command-not-found status is reported")
        gate.assert_contains(
            r.out, "command not found", "the shell's diagnostic reaches the operator"
        )
        gate.assert_contains(
            r.out, "  ok    real", "CONTROL: a resolvable gate in the same run still passes"
        )
        gate.log_pass("case 12: a gate whose tool does not resolve fails loudly, never silently")


# --------------------------------------------------------------------------- ADDED BY THE PORT. ---------------------------------------------------------------------------


def test_the_manifest_seam_is_honoured(gate):
    """ADDED BY THE PORT: the guard against this file becoming a nested battery.

    The subject is the CI runner. If `CI_RUNNER_MANIFEST` ever stopped being read, none of the twelve cases above would report "the seam broke" -- they would each launch the REAL gate set, inside `check:ci-pytest`, and the first symptom would be a pytest run that never ends.

    So this drives a ONE-gate fixture and requires the summary to name exactly one gate, against a registered set two orders of magnitude larger. It costs under a second and it fails in one, by name, saying which number it saw.
    """
    lock = paths.from_root(*LOCK_REL.split("/"))
    if not lock.is_file():
        gate.log_fail(
            "%s is missing, so this control cannot say how big the real set is and its "
            "green would mean nothing." % LOCK_REL
        )
    registered = len(json.loads(lock.read_text(encoding="utf-8")))
    if registered < 50:
        gate.log_fail(
            "the real gate lock holds only %d entr(ies); this control needs the real set "
            "to be visibly larger than the fixture, or it proves nothing." % registered
        )
    with harness.temp_dir() as work:
        mf = manifest(gate, work, "seam", [spec("only-one", "true")])
        r = run_ci(gate, mf, "--jobs", "1")
        gate.assert_exit_code(0, r.rc, "the one-gate fixture passes")
        match = SUMMARY_RE.search(r.out)
        if not match:
            gate.log_fail(
                "the run printed no `<n> gates: ` summary, so this control could not read "
                'how many gates ran. stdout was: "%s"' % r.out
            )
        counted = int(match.group(1))
        gate.assert_eq(
            counted,
            1,
            "CI_RUNNER_MANIFEST is not being honoured: the runner scheduled %d gate(s) "
            "for a one-entry fixture, against %d registered in %s. Every case in this "
            "file would be running the real battery, nested." % (counted, registered, LOCK_REL),
        )
        gate.log_pass(
            "the manifest seam is honoured: a 1-entry fixture scheduled 1 gate, not the "
            "%d registered in %s, so no case here can launch a real sweep" % (registered, LOCK_REL)
        )

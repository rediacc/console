#!/usr/bin/env python3
"""The quality-gate battery: run every `.ci/scripts/test/gates/test-*.sh` and judge it.

THE TWIN IT COEXISTS WITH IS `.ci/scripts/test/run-all.sh`, AND IT IS NOT DELETED. Invariant 5: a twin is never removed in the change that ports it. Both runners schedule the same 148 files and both must reach the same verdict; deleting the shell one here would remove the only thing that can contradict this one on a real tree.

WHAT IT KEEPS FROM run-all.sh, deliberately byte-for-byte, because a reader will put the two transcripts side by side:

  * the per-test block: `TEST: <file>` then the test's own PASS lines,
  * the verdict banner `Quality-gate tests: N passed, M failed (A assertions)`,
  * the `Failed tests:` list, one `  - <name>` per line,
  * and the three refusals that make those numbers mean something.

THE THREE REFUSALS, and every one of them was paid for on the shell side first:

  1. NO RESULT RECORDED is a FAILURE, never a skip. A test the scheduler lost has
     to present as red, because a scheduling bug that presents as a shorter green
     run is a battery that stopped gating and got faster doing it.
  2. EXIT 0 WITH NO `PASS:` LINE is a FAILURE. A gate test that asserts nothing
     exits 0, and from the outside that is indistinguishable from one that asserted
     forty things. This is the single most important line in the file.
  3. ZERO TESTS MATCHED is a FAILURE. A glob that stops matching otherwise reports
     success having run nothing.

Plus a fourth this runner inherits: the battery may not leave a TRACKED file modified. On 2026-09-03 a gate test drove `--upgrade` against the real .devcontainer/Dockerfile and restored it from a trap, and an unrelated gate reported "setup --check changed the working tree", sending the reader into run.sh.

WHERE ISOLATION COMES FROM, AND WHAT HAPPENS WHEN IT IS NOT THERE. The W/S/T schedule is DERIVED from `scripts/ci-runner/gates.lock.json`: a gate test declaring a `tree:` resource under `mutex` is a real-tree WRITER, one declaring it under `reads` is a SCANNER, and everything else is fixture-isolated. That is the same contract `scripts/ci-runner/pool.ts` schedules by, which is the
whole point -- two schedulers that decide isolation separately WILL disagree, and on 2026-09-06 they did: run-all.sh honoured three writers while the manifest registered none, so `npm run ci` ran exactly the combination that manufactures a flake.

MEASURED 2026-09-07, EARLIER THE SAME DAY: zero of the 148 gate-test entries in gates.lock.json carried `mutex`, `reads`, `heavy` or `weight` -- the lock declared no isolation at all, and this paragraph said so. The cause was a MISSING TYPE rather than missing effort: `gate-spec.ts` declared `mutex?: string[]` and had no `reads` field, so the 21 scanner gate tests were undeclarable
while `classify_from_lock` was already asking for exactly that claim.

CORRECTED LATER THE SAME DAY: `reads?: string[]` was added to the spec and the lock now carries `mutex: ['tree:repo']` on the 4 real-tree writers and `reads: ['tree:repo']` on the 21 scanners, derived FROM run-all.sh's fallback arrays rather than invented. So this runner reads a real contract and no longer degrades to serial on the live lock.

The degrade-to-serial path STAYS, because the reason for it is unchanged: this runner still does NOT carry a hand-written W/S list -- copying the fallback arrays here would make three copies of a definition whose duplication is the defect being removed -- and serial is the only safe choice under an unknown contract. Classifying everything as fixture-isolated would be a guess, and
the guess is wrong for at least four files.

    RUN_ALL_WRITERS / RUN_ALL_SCANNERS override membership, the same names and the
    same meaning run-all.sh gives them, so a driver that already sets them gets the
    same schedule from either runner rather than learning a second vocabulary.

EXIT CODES

    0   every test ran, asserted something, and passed
    1   a real verdict: a test failed, asserted nothing, was lost, or the battery
        left a tracked file modified
    77  bash is not available, so no verdict was reached at all -- BLOCKED, never
        a judgement on the code

    .ci/rediacc_ci/battery.py               run the battery
    .ci/rediacc_ci/battery.py --list        print the schedule without running it
    .ci/rediacc_ci/battery.py --selftest    prove this runner can fail

NO `---- gate ----` HEADER HERE, AND THE REASON THIS FILE USED TO GIVE WAS FALSE. It said `scripts/gate-bind.ts` "only scans `.ci/scripts/` and `scripts/`", so a header at this path would be inert. Measured 2026-09-09 by CALLING the real
function rather than reading it: `inScope('.ci/rediacc_ci/battery.py')` is TRUE.
`.ci/rediacc_ci` was added to that regex on 2026-09-06 and the comment above it says why -- a header outside the scan is INVISIBLE rather than unregistered, which is worse. The live scope is `scripts/gate-bind.ts:207-208`: `/^(\\.ci\\/scripts|\\.ci\\/rediacc_ci|scripts)\\//`. A stale premise here would have decided the registration, so it is corrected rather than left as prose.

THE DECISION IS UNCHANGED, but it now rests on the real reason: this file is a RUNNER, not a gate. `check:ci-quality-gates` is registered by hand in `scripts/ci-runner/manifest.ts` with `gate: false` against the existing "Quality-gate unit tests" step, exactly as its predecessor was, and the runner it points at carries no header either. Registration is the root driver's, via
package.json, the manifest and the workflow.
"""

import concurrent.futures
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from rediacc_ci import paths
from rediacc_ci import proc as ci_proc
from rediacc_ci.controls import Controls

GATES_SUBDIR = (".ci", "scripts", "test", "gates")
LOCK_SUBDIR = ("scripts", "ci-runner", "gates.lock.json")
DEFAULT_PATTERN = "test-*.sh"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_CANNOT_RUN = 77

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# run-all.sh spells this `^(\033\[0;32m)?PASS:` -- it admits the ONE colour log_pass emits and the bare form `ok` emits. Stripping every escape first is the same predicate on content and is not fooled by a helper that changes colour, which is worth having: the shell version's previous spelling used a literal "x1b" and matched NOTHING, so every colour-emitting test contributed zero
# visible evidence
# while the counter stayed right.
PASS_RE = re.compile(r"^PASS:", re.MULTILINE)


def _colours():
    if os.environ.get("CI") == "true" or not sys.stdout.isatty():
        return "", "", "", ""
    return "\033[0;31m", "\033[0;32m", "\033[1;33m", "\033[0m"


RED, GREEN, YELLOW, NC = _colours()


# --------------------------------------------------------------------------- Isolation, read from the lock ---------------------------------------------------------------------------


def classify_from_lock(lock_path: pathlib.Path, claim: str) -> set[str]:
    """Basenames of gate tests whose lock entry declares a `tree:` resource under `claim` (`mutex` for exclusive, `reads` for shared).

    Returns an EMPTY SET when the lock is unreadable or declares nothing, and the caller decides what that means -- "no declarations yet" and "the lock is broken" must not silently become the same thing as "nothing needs isolating".
    """
    try:
        with lock_path.open(encoding="utf-8") as handle:
            entries = json.load(handle)
    except (OSError, ValueError):
        return set()
    if not isinstance(entries, list):
        return set()
    found = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        run = entry.get("run")
        if not isinstance(run, str) or "/".join(GATES_SUBDIR) + "/" not in run:
            continue
        claimed = entry.get(claim)
        if not isinstance(claimed, list):
            continue
        if not any(isinstance(r, str) and r.startswith("tree:") for r in claimed):
            continue
        # A `run` is a command line in the general case, so take the word that actually names the script rather than assuming it is the whole string.
        for word in run.split():
            if word.startswith("/".join(GATES_SUBDIR) + "/"):
                found.add(os.path.basename(word))
                break
    return found


def _env_set(name: str, env: dict[str, str]) -> set[str] | None:
    value = env.get(name)
    if value is None:
        return None
    return {token for token in value.split() if token}


class Schedule:
    """W / S / T membership, plus WHERE it came from and what that costs.

    `source` is part of the value, not a log line. A caller that cannot tell a schedule derived from the registry apart from one that fell back has no way to decide whether running in parallel is safe, which is exactly the decision that went wrong when two runners disagreed about isolation.
    """

    def __init__(self, writers: set[str], scanners: set[str], source: str) -> None:
        self.writers = writers
        self.scanners = scanners
        self.source = source

    @property
    def declared(self) -> bool:
        return self.source != "undeclared"

    def bucket(self, name: str) -> str:
        if name in self.writers:
            return "W"
        if name in self.scanners:
            return "S"
        return "T"


def build_schedule(lock_path: pathlib.Path, env: dict[str, str] | None = None) -> Schedule:
    """`env` is an EXPLICIT INPUT, defaulting to the process environment.

    IT IS A PARAMETER BECAUSE THE SELFTEST NEEDS TO CONTROL IT, and that was not a guess: this function read os.environ directly until 2026-09-07, when the runner was driven on a shell that had exported RUN_ALL_WRITERS for the twin. Four controls that assert on the SOURCE of a schedule ("lock", "undeclared") got "env" instead and the runner refused to report -- correctly, loudly,
    and for a defect in its own controls rather than in the battery. A control whose verdict depends on an ambient variable is a control that passes or fails for reasons the reader cannot see.
    """
    env = os.environ if env is None else env
    env_writers = _env_set("RUN_ALL_WRITERS", env)
    env_scanners = _env_set("RUN_ALL_SCANNERS", env)
    if env_writers is not None or env_scanners is not None:
        return Schedule(env_writers or set(), env_scanners or set(), "env")
    writers = classify_from_lock(lock_path, "mutex")
    scanners = classify_from_lock(lock_path, "reads")
    if writers or scanners:
        return Schedule(writers, scanners, "lock")
    return Schedule(set(), set(), "undeclared")


def undeclared_notice(lock_path: pathlib.Path, root: pathlib.Path) -> list[str]:
    """The loud refusal. Named as a function so the selftest can assert its content rather than its existence."""
    return [
        "battery: no 'tree:' isolation is declared in %s for any gate test."
        % paths.relative_to_root(lock_path, root),
        "  Running SERIAL, because the alternative is to guess. Classifying every test",
        "  as fixture-isolated would be a guess, and it is wrong for at least the four",
        "  files that write into the real tree; that combination is what manufactures a",
        "  flake nobody can reproduce at --jobs 1.",
        "  THE FIX IS A REGISTRY EDIT, not an edit here: give each real-tree writer a",
        "  `mutex: ['tree:<path>']` and each real-tree scanner a `reads: ['tree:<path>']`",
        "  in scripts/ci-runner/manifest.ts, regenerate gates.lock.json, and both this",
        "  runner and scripts/ci-runner/pool.ts pick it up with no code change.",
        "  RUN_ALL_WRITERS / RUN_ALL_SCANNERS override membership for one run.",
    ]


# --------------------------------------------------------------------------- Running one test ---------------------------------------------------------------------------


class Outcome:
    """One test's result. `recorded=False` is the "the scheduler lost it" case."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.recorded = False
        self.rc: int | None = None
        self.log = ""
        self.assertions = 0

    @property
    def verdict(self) -> str:
        """"pass" | "fail" | "vacuous" | "lost". Four outcomes and not two, because `vacuous` and `lost` are the ones a boolean would fold into `pass`."""
        if not self.recorded:
            return "lost"
        if self.rc != 0:
            return "fail"
        if self.assertions == 0:
            return "vacuous"
        return "pass"


def run_one(gates_dir: pathlib.Path, name: str, timeout: int = 1800) -> Outcome:
    outcome = Outcome(name)
    # THROUGH THE SHARED RUNNER. Every one of these is a bash gate test that spawns children of its own -- `npm run`, `npx tsx`, a planted fixture's
    # own subshell. `subprocess.run(capture_output=True, timeout=...)` kills the
    # test script and then blocks in communicate() on pipes a grandchild still holds, so the battery's per-test timeout could not actually bound a test. `proc.run` gives each test its own session and signals the whole group.
    #
    # THE LAUNCH CHECK MOVED AHEAD OF THE RUN, because it can no longer be read off the result. `proc.run` reports a failed spawn as rc 127 with the OSError on stderr, and a gate test whose own body hits `command not found` exits 127 too -- indistinguishable after the fact. Asking the filesystem first keeps "could not be launched" (no verdict) apart from "ran and exited 127" (a
    # verdict, and a failing one).
    if not os.access(gates_dir / name, os.X_OK):
        # NOT recorded. A test that could not be launched has no verdict, and
        # reporting rc=1 here would say "your gate test failed", which is false.
        outcome.log = "battery: could not run %s: not an executable file\n" % name
        return outcome
    result = ci_proc.run(["./" + name], cwd=gates_dir, timeout=timeout)
    outcome.recorded = True
    outcome.rc = result.returncode
    outcome.log = result.stdout + result.stderr
    outcome.assertions = len(PASS_RE.findall(ANSI_RE.sub("", outcome.log)))
    return outcome


# --------------------------------------------------------------------------- The tracked-tree guard ---------------------------------------------------------------------------


def tree_state(root: pathlib.Path) -> str:
    """Tracked modifications only, sorted. Untracked noise is excluded because several tests legitimately plant fixtures inside the tree; a TRACKED file changing is the defect.

    An unavailable git yields an EMPTY snapshot on both sides, so the before/after comparison stays honest rather than firing spuriously.
    """
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return "\n".join(sorted(ln for ln in proc.stdout.splitlines() if not ln.startswith("??")))


# --------------------------------------------------------------------------- The battery ---------------------------------------------------------------------------


class Report:
    def __init__(self) -> None:
        self.outcomes: list[Outcome] = []
        self.failed: list[str] = []
        self.passed = 0
        self.assertions = 0
        self.notices: list[str] = []
        self.jobs = 1
        self.schedule_source = "undeclared"

    @property
    def ok(self) -> bool:
        return not self.failed


def score(outcome: Outcome, report: Report) -> None:
    """The whole verdict for one test, as a pure function of its Outcome.

    PURE AND SEPARATE FROM PRINTING, so the selftest can drive every branch -- including `lost`, which is hard to produce for real -- without a scheduler.
    """
    verdict = outcome.verdict
    if verdict == "pass":
        report.passed += 1
        report.assertions += outcome.assertions
        return
    if verdict == "lost":
        report.failed.append("%s (no result recorded)" % outcome.name)
        return
    if verdict == "vacuous":
        report.failed.append("%s (exited 0 but made no assertions)" % outcome.name)
        return
    report.failed.append(outcome.name)


def print_block(outcome: Outcome, *, verbose: bool) -> None:
    print("%sTEST:%s %s" % (YELLOW, NC, outcome.name))
    verdict = outcome.verdict
    if verdict == "pass":
        if verbose:
            print(outcome.log, end="")
        else:
            for line in ANSI_RE.sub("", outcome.log).splitlines():
                if line.startswith("PASS:"):
                    print("%sPASS:%s%s" % (GREEN, NC, line[len("PASS:") :]))
    else:
        print(outcome.log, end="")
        if verdict == "lost":
            print(
                "%sFAIL:%s %s produced no result: the scheduler never completed it"
                % (RED, NC, outcome.name),
                file=sys.stderr,
            )
        elif verdict == "vacuous":
            print(
                "%sFAIL:%s %s exited 0 without a single PASS: line" % (RED, NC, outcome.name),
                file=sys.stderr,
            )
    print()


def discover(gates_dir: pathlib.Path, pattern: str) -> list[str]:
    return sorted(p.name for p in gates_dir.glob(pattern) if p.is_file())


def run_battery(
    *,
    gates_dir: pathlib.Path,
    root: pathlib.Path,
    lock_path: pathlib.Path,
    pattern: str = DEFAULT_PATTERN,
    jobs: int | None = None,
    verbose: bool = False,
    check_tree: bool = True,
    env: dict[str, str] | None = None,
    quiet: bool = False,
) -> Report:
    report = Report()
    names = discover(gates_dir, pattern)
    if not names:
        report.failed.append(
            "the battery itself: pattern %r matched NO test in %s"
            % (pattern, paths.relative_to_root(gates_dir, root))
        )
        return report

    schedule = build_schedule(lock_path, env)
    report.schedule_source = schedule.source
    if not schedule.declared:
        report.notices.extend(undeclared_notice(lock_path, root))

    requested = jobs if jobs and jobs > 0 else _default_jobs()
    # SERIAL WHEN THE CONTRACT IS UNKNOWN. Not a warning-and-carry-on: the whole cost of getting this wrong is a flake that reproduces nowhere.
    report.jobs = 1 if not schedule.declared else requested

    writers = [n for n in names if schedule.bucket(n) == "W"]
    scanners = [n for n in names if schedule.bucket(n) == "S"]
    temps = [n for n in names if schedule.bucket(n) == "T"]

    before = tree_state(root) if check_tree else ""
    results: dict[str, Outcome] = {}

    def chain(members: list[str]) -> None:
        for member in members:
            results[member] = run_one(gates_dir, member)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, report.jobs)) as pool:
        # The W chain starts at t=0 as ONE unit and T fills the remaining slots
        # while it runs; S is released only once the chain has finished, because a
        # scanner reading a file mid-rewrite is a hard error that passes on the very next serial re-run.
        writer_future = pool.submit(chain, writers) if writers else None
        temp_futures = {pool.submit(run_one, gates_dir, n): n for n in temps}
        for future in concurrent.futures.as_completed(temp_futures):
            results[temp_futures[future]] = future.result()
        if writer_future is not None:
            writer_future.result()
        scanner_futures = {pool.submit(run_one, gates_dir, n): n for n in scanners}
        for future in concurrent.futures.as_completed(scanner_futures):
            results[scanner_futures[future]] = future.result()

    for name in names:
        outcome = results.get(name) or Outcome(name)
        report.outcomes.append(outcome)
        score(outcome, report)
        if not quiet:
            print_block(outcome, verbose=verbose)

    # The self-guard on the guard: every discovered file must have been scored.
    if len(report.outcomes) != len(names):
        report.failed.append(
            "the battery itself: scored %d of %d tests; results were lost"
            % (len(report.outcomes), len(names))
        )

    if check_tree:
        after = tree_state(root)
        if before != after:
            if not quiet:
                print()
                print("✗ the battery CHANGED TRACKED FILES in the working tree:")
                for line in sorted(set(after.splitlines()) - set(before.splitlines())):
                    print("    + %s" % line)
                for line in sorted(set(before.splitlines()) - set(after.splitlines())):
                    print("    - %s" % line)
                print("  A gate test must work on a COPY. The validator it drives should take a")
                print("  path seam so the test can hand it a fixture instead of the tracked file.")
                print("  IN A SHARED CHECKOUT, CHECK THE OBVIOUS FIRST: this snapshot spans the")
                print("  whole run, so a CONCURRENT session editing a tracked file is reported")
                print("  here too, identically. Compare the named files against what the tests")
                print("  above actually touch before hunting for a culprit inside the battery.")
            report.failed.append("the battery itself: it left a tracked file modified")

    return report


def _default_jobs() -> int:
    # 4 on ubuntu-latest. Capped at 8 locally so a bare run on a 20-core box does not fork-bomb node: several of these tests shell out to npx/tsx, and 20 concurrent node startups cost more in contention than they buy.
    return min(8, os.cpu_count() or 4)


def print_report(report: Report) -> None:
    for line in report.notices:
        print(line, file=sys.stderr)
    print("==============================================")
    print(
        "Quality-gate tests: %d passed, %d failed (%d assertions)"
        % (report.passed, len(report.failed), report.assertions)
    )
    print(
        "  schedule: %s, jobs: %d, %d test(s)"
        % (report.schedule_source, report.jobs, len(report.outcomes))
    )
    print("==============================================")
    if report.failed:
        print("Failed tests:")
        for name in report.failed:
            print("  - %s" % name)


# --------------------------------------------------------------------------- THE SELFTEST. A runner that cannot fail is worse than no runner. ---------------------------------------------------------------------------


def _fixture(directory: pathlib.Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def selftest(*, verbose: bool = False) -> bool:
    import tempfile  # noqa: PLC0415 -- only the selftest needs it

    controls = Controls("battery", floor=24, verbose=verbose)

    # -- score(), the whole matrix, without a scheduler
    for verdict, recorded, rc, assertions in (
        ("pass", True, 0, 3),
        ("fail", True, 1, 3),
        ("vacuous", True, 0, 0),
        ("lost", False, None, 0),
    ):
        outcome = Outcome("test-x.sh")
        outcome.recorded = recorded
        outcome.rc = rc
        outcome.assertions = assertions
        controls.check(
            "verdict %s is classified as %s" % (verdict, verdict), outcome.verdict, verdict
        )

    report = Report()
    green = Outcome("g.sh")
    green.recorded, green.rc, green.assertions = True, 0, 5
    score(green, report)
    controls.check("a green test adds its assertions to the total", report.assertions, 5)
    vacuous = Outcome("v.sh")
    vacuous.recorded, vacuous.rc, vacuous.assertions = True, 0, 0
    score(vacuous, report)
    controls.truthy(
        "THE FAILURE THIS RUNNER EXISTS FOR: exit 0 with no PASS line is scored as a FAILURE",
        any("made no assertions" in f for f in report.failed),
    )
    lost = Outcome("l.sh")
    score(lost, report)
    controls.truthy(
        "a test the scheduler lost is a FAILURE and never a skip",
        any("no result recorded" in f for f in report.failed),
    )
    controls.check("and the pass count did not move", report.passed, 1)

    # -- the PASS predicate, both directions and both colour forms
    controls.check("an uncoloured PASS line counts", len(PASS_RE.findall("PASS: a\n")), 1)
    controls.check(
        "a coloured PASS line counts once the escapes are stripped",
        len(PASS_RE.findall(ANSI_RE.sub("", "\033[0;32mPASS:\033[0m a\n"))),
        1,
    )
    controls.check(
        "CONTROL: a line merely CONTAINING the word does not count",
        len(PASS_RE.findall("we should PASS: eventually\n")),
        0,
    )
    controls.check("CONTROL: a FAIL line does not count", len(PASS_RE.findall("FAIL: a\n")), 0)

    # -- classification from a lock, both directions
    with tempfile.TemporaryDirectory() as temp:
        base = pathlib.Path(temp)
        lock = base / "gates.lock.json"
        lock.write_text(
            json.dumps(
                [
                    {
                        "id": "a",
                        "run": ".ci/scripts/test/gates/test-w.sh",
                        "mutex": ["tree:scripts"],
                    },
                    {
                        "id": "b",
                        "run": ".ci/scripts/test/gates/test-s.sh",
                        "reads": ["tree:scripts"],
                    },
                    {"id": "c", "run": ".ci/scripts/test/gates/test-t.sh"},
                    {"id": "d", "run": "npm run check:other", "mutex": ["tree:scripts"]},
                    {"id": "e", "run": ".ci/scripts/test/gates/test-n.sh", "mutex": ["renet-bin"]},
                ]
            ),
            encoding="utf-8",
        )
        controls.check(
            "a `tree:` mutex on a gate test makes it a WRITER",
            classify_from_lock(lock, "mutex"),
            {"test-w.sh"},
        )
        controls.check(
            "a `tree:` reads on a gate test makes it a SCANNER",
            classify_from_lock(lock, "reads"),
            {"test-s.sh"},
        )
        controls.check(
            "CONTROL: an unreadable lock classifies NOTHING rather than guessing",
            classify_from_lock(base / "absent.json", "mutex"),
            set(),
        )
        schedule = build_schedule(lock, env={})
        controls.check("a declared lock is the schedule's source", schedule.source, "lock")
        controls.check("an undeclared test lands in T", schedule.bucket("test-t.sh"), "T")
        controls.check(
            "CONTROL: a non-`tree:` mutex does NOT make a writer", schedule.bucket("test-n.sh"), "T"
        )
        empty_lock = base / "empty.json"
        empty_lock.write_text("[]", encoding="utf-8")
        undeclared = build_schedule(empty_lock, env={})
        controls.check("an empty lock is 'undeclared'", undeclared.source, "undeclared")
        controls.truthy(
            "and the notice names the file that has to change",
            any("manifest.ts" in line for line in undeclared_notice(empty_lock, base)),
        )
        # THE SEAM ITSELF, BOTH WAYS. The controls above pass `env={}` so an
        # operator shell that happens to export RUN_ALL_WRITERS cannot change what they measure -- which is exactly what happened on 2026-09-07. These two
        # prove the seam is still LIVE, so passing `env={}` is a deliberate
        # isolation rather than a variable nothing reads any more.
        controls.check(
            "RUN_ALL_WRITERS in the passed env overrides the lock",
            build_schedule(lock, env={"RUN_ALL_WRITERS": "test-x.sh"}).bucket("test-x.sh"),
            "W",
        )
        controls.check(
            "CONTROL: ...and the same lock with an empty env is decided by the lock",
            build_schedule(lock, env={}).bucket("test-x.sh"),
            "T",
        )

    # -- END TO END against a fixture battery
    with tempfile.TemporaryDirectory() as temp:
        base = pathlib.Path(temp)
        gates = base / "gates"
        gates.mkdir()
        lock = base / "lock.json"
        lock.write_text("[]", encoding="utf-8")
        _fixture(gates, "test-green.sh", "#!/bin/bash\necho 'PASS: it held'\necho 'PASS: twice'\n")
        result = run_battery(
            gates_dir=gates, root=base, lock_path=lock, check_tree=False, env={}, quiet=True
        )
        controls.truthy("SANITY: a healthy fixture battery is green", result.ok)
        controls.check("...and counts its assertions", result.assertions, 2)
        controls.check("...and runs SERIAL while isolation is undeclared", result.jobs, 1)

        _fixture(gates, "test-vacuous.sh", "#!/bin/bash\necho 'did nothing'\nexit 0\n")
        result = run_battery(
            gates_dir=gates, root=base, lock_path=lock, check_tree=False, env={}, quiet=True
        )
        controls.falsy("PLANTED: a test that exits 0 asserting nothing reds the battery", result.ok)
        controls.truthy(
            "PLANTED: ...and the failure names the reason",
            any("made no assertions" in f for f in result.failed),
        )
        (gates / "test-vacuous.sh").unlink()

        _fixture(gates, "test-red.sh", "#!/bin/bash\necho 'PASS: one'\nexit 1\n")
        result = run_battery(
            gates_dir=gates, root=base, lock_path=lock, check_tree=False, env={}, quiet=True
        )
        controls.falsy("PLANTED: a test that exits non-zero reds the battery", result.ok)
        (gates / "test-red.sh").unlink()

        result = run_battery(
            gates_dir=gates, root=base, lock_path=lock, check_tree=False, env={}, quiet=True
        )
        controls.truthy("CONTROL: removing the plants returns the battery to green", result.ok)

        result = run_battery(
            gates_dir=gates,
            root=base,
            lock_path=lock,
            pattern="test-nothing-*.sh",
            check_tree=False,
        )
        controls.falsy("PLANTED: a pattern matching ZERO tests is a FAILURE, not a pass", result.ok)
        controls.truthy(
            "PLANTED: ...and says the glob matched nothing",
            any("matched NO test" in f for f in result.failed),
        )

        # A DECLARED lock lets the runner go parallel, which is the other direction of the serial degradation above.
        lock.write_text(
            json.dumps(
                [{"id": "g", "run": ".ci/scripts/test/gates/test-green.sh", "reads": ["tree:x"]}]
            ),
            encoding="utf-8",
        )
        result = run_battery(
            gates_dir=gates,
            root=base,
            lock_path=lock,
            jobs=4,
            check_tree=False,
            env={},
            quiet=True,
        )
        controls.check("a declared lock restores the requested worker count", result.jobs, 4)
        controls.check(
            "...and the declaration is recorded as its source", result.schedule_source, "lock"
        )

    return controls.report()


def main(argv: list[str]) -> int:
    root = paths.repo_root()
    gates_dir = pathlib.Path(os.environ.get("RUN_ALL_GATES_DIR") or paths.from_root(*GATES_SUBDIR))
    lock_path = paths.from_root(*LOCK_SUBDIR, root=root)
    pattern = DEFAULT_PATTERN
    jobs = int(os.environ.get("RUN_ALL_JOBS") or 0) or None
    verbose = False

    rest = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("--verbose", "-v"):
            verbose = True
        elif arg == "--jobs":
            index += 1
            jobs = int(argv[index])
        elif arg in ("--selftest", "--list"):
            rest.append(arg)
        else:
            pattern = arg
        index += 1

    if "--selftest" in rest:
        return EXIT_OK if selftest(verbose=True) else EXIT_FAIL

    if shutil.which("bash") is None:
        print(
            "%serror%s: bash is not on PATH, so no gate test can be run." % (RED, NC),
            file=sys.stderr,
        )
        print("  install bash, or run the battery inside the devbox:", file=sys.stderr)
        print("    ./run.sh devbox shell", file=sys.stderr)
        print(
            "  NOT skipping: exit 77 means NO VERDICT was reached, which the ci-runner\n"
            "  classifies as BLOCKED. Reporting 0 here would say the battery passed.",
            file=sys.stderr,
        )
        return EXIT_CANNOT_RUN

    if not gates_dir.is_dir():
        print(
            "%s✗%s the gates directory %s does not exist, so this runner has nothing to\n"
            "  run and its green would mean nothing."
            % (RED, NC, paths.relative_to_root(gates_dir, root)),
            file=sys.stderr,
        )
        return EXIT_FAIL

    if "--list" in rest:
        schedule = build_schedule(lock_path)
        names = discover(gates_dir, pattern)
        if not names:
            print("%s✗%s pattern %r matched no test" % (RED, NC, pattern), file=sys.stderr)
            return EXIT_FAIL
        for line in [] if schedule.declared else undeclared_notice(lock_path, root):
            print(line, file=sys.stderr)
        for name in names:
            print("%s  %s" % (schedule.bucket(name), name))
        print(
            "%d test(s): %d W, %d S, %d T (schedule from %s)"
            % (
                len(names),
                sum(1 for n in names if schedule.bucket(n) == "W"),
                sum(1 for n in names if schedule.bucket(n) == "S"),
                sum(1 for n in names if schedule.bucket(n) == "T"),
                schedule.source,
            )
        )
        return EXIT_OK

    # The controls run BEFORE the battery is judged, and a control failure refuses to judge it at all: a verdict from an instrument that cannot fail is worse than no verdict.
    #
    # THE LABEL IS NOT DECORATION. `Controls.report()` prints a bare "N control(s) passed", and this call happens before anything else, so the FIRST line of every CI transcript was a count of nothing named. run-all.sh spelled its equivalent "tree-guard selftest: N control(s) passed" on one line; the text lives in rediacc_ci.controls and is shared, so the label goes above it here
    # rather than into every other caller's output.
    print("runner controls, before the battery is judged:")
    if not selftest():
        print(
            "%s✗ CONTROL FAILED%s: this runner's own controls did not pass, so it refuses\n"
            "  to report on the battery." % (RED, NC),
            file=sys.stderr,
        )
        return EXIT_FAIL

    report = run_battery(
        gates_dir=gates_dir,
        root=root,
        lock_path=lock_path,
        pattern=pattern,
        jobs=jobs,
        verbose=verbose,
    )
    print_report(report)
    return EXIT_OK if report.ok else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Port of `.ci/scripts/test/gates/test-rebase-resolve.sh`.

Drive `wl_git.py rebase-resolve` against REAL halted rebases, one per kind.

WHY A REAL HALT AND NOT A STAGE TABLE. wl_git.py's own selftest already checks the classifier and the union as pure functions over hand-written inputs, and that proves their ARITHMETIC. It says nothing about whether the verb reads what git actually writes into `.git/rebase-merge` and the index, and it did not: the first wiring passed `conflicted_paths`' `(sha, mode)` tuples to an
oracle that wanted bare shas, and unpacked a `(target, why)` return as if it were a string. Both are invisible to a pure-function test and both died instantly here.

The five kinds are the taxonomy measured across two real rebases of branch 0826-3 on 2026-08-26/27: ten conflicts, one gitlink, six registry unions, two genuine judgement calls.

THE FIXTURE LIBRARY IS DRIVEN, NOT REIMPLEMENTED. `git_fixture_rebase <kind>` and `git_fixture_cleanup <dir>` live in `.ci/scripts/test/lib/git-fixture.sh` and
build a real repository with a real halted rebase in it; this module calls them
through `bash -c 'source ...; git_fixture_rebase <kind>'` and reads the directory
off stdout. Reimplementing a hundred lines of git plumbing in Python would be a second fixture, and two fixtures that are supposed to be one is how the two sides stop testing the same thing.

WHY ONE PYTEST FUNCTION PER KIND rather than the twin's accumulate-and-summarise loop. The twin uses `soft_fail` and a counter because `log_fail` EXITS, and eight independent kinds stopping at the first would hide seven behind one fixture problem. pytest gives that property natively: each case is its own function, so a failure in one leaves the other seven still driven and still
reported. The twin's `ran < 8` anti-vacuity counter is therefore replaced by something stronger, not dropped: `test_every_kind_ran` asserts the case table itself still holds the eight it is supposed to, so a case deleted from the table is a finding rather than a smaller green.

THE TWIN IS FLAT (it declares no `test_*` functions), so `test_twin_parity.py` compares this module's control count against the twin's runtime `PASS:` count. Nine controls here against the twin's nine PASS lines.

NO `xdist_group`, and the question was asked rather than assumed because this is the port in the batch that comes closest to needing one. `git_fixture_rebase` builds a COMPLETE repository under its own `mktemp -d` and every git command runs
with `-C` or `cwd` pointed at it, so the two cases that drive
`rebase-continue --execute` write only inside their own throwaway repo and there is no index, no lock and no ref shared between two cases. The subject (`wl_git.py`) and the fixture library are read, never written. Nothing here is observable from a second worker, so grouping would only serialise the slowest cases in the module for no property gained.
"""

import hashlib
import pathlib
import shlex
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-rebase-resolve.sh"

WL = paths.from_root(".claude", "hooks", "stop", "wl_git.py")
FIXTURE_LIB = paths.from_root(".ci", "scripts", "test", "lib", "git-fixture.sh")

# The twin's `ran < 8` floor, stated as the table it is a count of.
PLAN_KINDS = ("registry", "judgement", "gitlink", "gitlink-rebased", "mixed")
EXEC_CASES = 2
DRY_RUN_CASES = 1
EXPECTED_CASES = len(PLAN_KINDS) + EXEC_CASES + DRY_RUN_CASES


def require_subjects(gate) -> None:
    for path in (WL, FIXTURE_LIB):
        if not path.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(path))
    harness.require_tool("git", "install git")


def fixture_rebase(gate, kind: str) -> pathlib.Path:
    """`git_fixture_rebase <kind>`, or a loud refusal. Returns the repo path."""
    require_subjects(gate)
    result = harness.run(
        [
            "bash",
            "-c",
            "source %s; git_fixture_rebase %s" % (shlex.quote(str(FIXTURE_LIB)), shlex.quote(kind)),
        ]
    )
    directory = result.out.strip()
    if result.rc != 0 or not directory or not pathlib.Path(directory).is_dir():
        gate.log_fail(
            "%s: the fixture did not halt, so it proves nothing (rc=%d, stderr: %s)"
            % (kind, result.rc, result.err.strip())
        )
    return pathlib.Path(directory)


def fixture_cleanup(directory: pathlib.Path) -> None:
    harness.run(
        [
            "bash",
            "-c",
            "source %s; git_fixture_cleanup %s"
            % (shlex.quote(str(FIXTURE_LIB)), shlex.quote(str(directory))),
        ]
    )


def wl_git(directory: pathlib.Path, *args: str) -> harness.RunResult:
    """`python3 wl_git.py <args>` inside the fixture repo, streams MERGED.

    Merged because the twin captures `2>&1` and every needle below is asserted
    against that one text; splitting them here would change which stream a needle
    is looked for on.
    """
    return harness.run([sys.executable, str(WL), *args], cwd=directory)


def drive(gate, kind: str, *needles: str) -> None:
    """`drive <kind> <must-contain>...`."""
    directory = fixture_rebase(gate, kind)
    try:
        result = wl_git(directory, "rebase-resolve")
        missing = [needle for needle in needles if needle not in result.combined]
        if missing:
            gate.log_fail(
                "%s (exit %d) never said: %s\n%s"
                % (
                    kind,
                    result.rc,
                    " ".join("[%s]" % n for n in missing),
                    "\n".join("        " + line for line in result.combined.splitlines()[:16]),
                )
            )
        gate.log_pass("%s (exit %d)" % (kind, result.rc))
    finally:
        fixture_cleanup(directory)


def test_registry_union_is_decided_and_says_the_identity_set_was_verified(gate):
    # A registry union it CAN decide, and it must SAY the identity set was verified rather than merely exiting 0 -- a union that parses proves nothing.
    drive(gate, "registry", "registry union", "identity set verified")


def test_a_judgement_collision_is_left_untouched(gate):
    # A genuine design collision stays untouched, and says so in the words that stop the next reader reaching for --skip.
    drive(gate, "judgement", "judgement", "NOTHING was written")


def test_divergent_gitlinks_are_refused_rather_than_guessed(gate):
    # Divergent submodule pointers: the oracle REFUSES rather than guessing, and the refusal is one path's verdict, not an exception that abandons the report.
    drive(gate, "gitlink", "neither contains the other", "NOTHING was written")


def test_a_rebased_submodule_gitlink_is_resolvable(gate):
    # The insight the whole oracle rests on: the submodule was rebased FIRST, so its HEAD contains both sides and is in NEITHER conflict stage. Without this
    # case the only gitlink control proves the refusal and never the resolution.
    drive(gate, "gitlink-rebased", "gitlink")


def test_a_mixed_halt_is_all_or_nothing(gate):
    # ALL OR NOTHING. A gitlink AND a judgement file in one halt must write nothing, even though the gitlink half is perfectly decidable: resolving only that half leaves an index that reads as nearly done, and the next --continue then fails for a reason that no longer names the submodule.
    drive(gate, "mixed", "NOTHING was written")


def exec_case(gate, label: str, kind: str, want_done: bool, needle: str) -> None:
    """`exec_case <label> <kind> <expect-finished> <needle>`, against a real repo.

    Everything above drives the PLAN. This drives the EXECUTOR, because "it decided correctly" and "it left the tree in the state it claimed" are different questions, and only the second one can leave a rebase half-applied.
    """
    directory = fixture_rebase(gate, kind)
    try:
        git = harness.require_tool("git", "install git")

        def commit_count() -> int:
            counted = harness.run([git, "rev-list", "--count", "HEAD"], cwd=directory)
            if counted.rc != 0:
                gate.log_fail(
                    "%s: could not count commits, so the no-commit-vanishes claim could "
                    "not be made: %s" % (label, counted.err.strip())
                )
            return int(counted.out.strip())

        before = commit_count()
        result = wl_git(directory, "rebase-continue", "--execute")
        in_progress = (directory / ".git" / "rebase-merge").is_dir()
        after = commit_count()

        problems = []
        if in_progress == want_done:
            problems.append(
                "[mid-rebase=%s, wanted finished=%s]"
                % ("yes" if in_progress else "no", "yes" if want_done else "no")
            )
        if needle not in result.combined:
            problems.append("[never said: %s]" % needle)
        # NO COMMIT MAY VANISH. `git rebase --skip` is the one thing this verb must never do, and a dropped commit is exactly how it would show up.
        if after < before:
            problems.append("[commits went %d -> %d]" % (before, after))
        if problems:
            gate.log_fail(
                "%s:%s\n%s"
                % (
                    label,
                    " " + " ".join(problems),
                    "\n".join("        " + line for line in result.combined.splitlines()[:12]),
                )
            )
        gate.log_pass(label)
    finally:
        fixture_cleanup(directory)


def test_execute_completes_a_decidable_halt(gate):
    exec_case(
        gate, "execute: a decidable halt COMPLETES the rebase", "registry", True, "rebase finished"
    )


def test_execute_stops_on_a_judgement_halt(gate):
    exec_case(
        gate,
        "execute: a judgement halt STOPS, mid-rebase, untouched",
        "judgement",
        False,
        "STOPPED, nothing written",
    )


def test_a_dry_run_writes_nothing(gate):
    # THE DRY RUN MUST NOT WRITE. Without this, every green above is compatible
    # with a verb that ignores --execute and always writes.
    directory = fixture_rebase(gate, "registry")
    try:
        registry = directory / "reg.json"
        before = hashlib.md5(registry.read_bytes()).hexdigest()
        result = wl_git(directory, "rebase-continue")
        after = hashlib.md5(registry.read_bytes()).hexdigest()
        still_mid_rebase = (directory / ".git" / "rebase-merge").is_dir()
        if not (before == after and still_mid_rebase and "DRY RUN" in result.combined):
            gate.log_fail(
                "a dry run wrote, advanced the rebase, or did not say so "
                "(md5 %s -> %s, mid-rebase=%s)" % (before, after, still_mid_rebase)
            )
        gate.log_pass("no --execute: nothing written, rebase untouched")
    finally:
        fixture_cleanup(directory)


def test_every_kind_ran(gate):
    # ANTI-VACUITY, and the twin's `ran < 8` floor stated as the table it counts. Every assertion above lives inside a helper, so a harness that silently produced nothing would print no failures at all.
    own = pathlib.Path(__file__).read_text(encoding="utf-8")
    declared = len([line for line in own.splitlines() if line.startswith("def test_")])
    # This case itself is not one of the eight.
    driven = declared - 1
    if driven != EXPECTED_CASES:
        gate.log_fail(
            "this module drives %d case(s), but the taxonomy is %d (%d plan kind(s) + %d "
            "execute + %d dry run); a green over missing cases is not a green"
            % (driven, EXPECTED_CASES, len(PLAN_KINDS), EXEC_CASES, DRY_RUN_CASES)
        )
    gate.log_pass(
        "%d conflict kind(s) decided, and the loop executed, against real halts "
        "(%d case(s) total)" % (len(PLAN_KINDS), driven)
    )
    gate.log_info(
        "Blind spot, stated so the green is not read as more than it is: the fixtures are "
        "single-halt, so a MULTI-halt rebase (the loop actually looping) is not covered here."
    )

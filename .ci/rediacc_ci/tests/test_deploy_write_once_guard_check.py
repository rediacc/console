"""`rediacc_ci.deploy.write_once_guard_check` against the bytes it printed when its subject was the bash guard.

THE BASH GUARD IS GONE (operator ruling D5, 2026-10-08). `.ci/scripts/test/test-write-once-guard.sh` was the registered gate until `write_once_guard_check` took the registration, and `write_once_guard` itself was a bash function in `.ci/scripts/deploy/upload-to-r2.sh` until it moved to `rediacc_ci.deploy.write_once_guard`. The goldens under `goldens/write-once-guard/` are the bytes the harness printed against the BASH guard, planted mutations
included, and the Python guard reproduces every one. `test_deploy_write_once_guard.py` holds the guard itself to the bash function's own frozen answers.

WHICH CASES ARE RECORDED AND WHICH ARE NOT. Every case driving a FIXTURE has a golden. The case that runs against the LIVE checkout does not: it reads the repository's own guard, which is the subject, and a recording of it would go stale with every edit.

THE HAPPY PATH IS THE WEAKEST CASE HERE, so most of this file is about the FAILURE paths. Every case below therefore runs a harness against a guard with ONE planted defect, and the four `log_fail` branches are reached and compared byte for byte against the recording, ANSI escapes included.

HOW THE SUBJECT IS POINTED AT A FIXTURE. The harness resolves the guard through `paths.repo_root()`, whose single override is `$REDIACC_CI_ROOT`, so a fixture holding a mutated copy of `write_once_guard.py` is enough. A MISSING `write_once_guard` FUNCTION is exit 127, as a missing bash function was.

NOTHING ON DISK IS MUTATED. Every fixture is built under pytest's `tmp_path` from a copy of the real file.

NO NETWORK, NO AWS. The harness mocks `aws` with a bash script on `PATH`.

K=5 LEDGER: `.ci/shadow/w7p6-write-once-guard.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import typing

from rediacc_ci import paths
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "write_once_guard_check.py"
GUARD = ROOT / ".ci" / "rediacc_ci" / "deploy" / "write_once_guard.py"
SLUG = "write-once-guard"
GUARD_REL = ".ci/rediacc_ci/deploy/write_once_guard.py"

# Every case with a golden. The live-checkout case is deliberately absent; the docstring says why.
RECORDED_CASES = {
    "unmutated",
    "a-guard-that-scrubs",
    "a-guard-that-returns-zero-when-sealed",
    "sealed-but-empty-that-does-not-fail-loud",
    "a-guard-that-scrubs-an-orphan",
    "a-dry-run-that-still-calls-aws",
    "a-missing-guard-function",
}

# The scrubbing mutation, named once because the plant control reuses it.
RM_CALL = (
    '__import__("subprocess").run(["aws", "s3", "rm", "s3://x/y", "--recursive"], check=False)'
)
SCRUB_ANCHOR = "            log.info(IDEMPOTENT[0]"
SCRUB_MUTANT = "            %s\n            log.info(IDEMPOTENT[0]" % RM_CALL

# NOT named `PASS_...`: ruff S105 reads any constant whose NAME contains
# "PASS" as a hardcoded password, and a per-line noqa to get past a gate is
# the thing this repo refuses. The VALUE is the twin's literal PASS line.
OK_LINE = "\033[0;32mPASS:\033[0m "
BAD_LINE = "\033[0;31mFAIL:\033[0m "


def build_fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    """A one-file `.ci` skeleton the harness resolves the guard inside."""
    fixture = tmp_path / "fixture"
    target = fixture / ".ci" / "rediacc_ci" / "deploy"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(GUARD, target / GUARD.name)
    return fixture


def mutate(fixture: pathlib.Path, relative: str, old: str, new: str) -> None:
    """Edit ONE fixture file, refusing silently-vacuous mutations."""
    target = fixture / relative
    text = target.read_text(encoding="utf-8")
    assert old in text, "mutation anchor %r is not in %s" % (old, relative)
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def _run(subject: pathlib.Path, fixture: pathlib.Path) -> subprocess.CompletedProcess[str]:
    """The licensed invocation, verbatim: the ledger's `new` command."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "REDIACC_CI_ROOT": str(fixture),
    }
    runner = ["python3", str(subject)]
    return subprocess.run(runner, env=env, capture_output=True, text=True, check=False, timeout=120)


def recorded(case: str) -> tuple[int, str, str]:
    """One golden, split back into exit code, stdout and stderr."""
    body = frozen.read(SLUG, case)
    head, rest = body.split("\n--- stdout ---\n", 1)
    out, err = rest.split("--- stderr ---\n", 1)
    return int(head[len("exit: ") :]), out, err


def assert_same(old: tuple[int, str, str], new: subprocess.CompletedProcess[str]) -> None:
    assert new.returncode == old[0], "exit: recorded %s, port %s" % (old[0], new.returncode)
    assert new.stdout == old[1]
    assert new.stderr == old[2]


def drive(case: str, tmp_path: pathlib.Path, mutation: tuple[str, str, str] | None = None):
    """Build the case's fixture, apply its mutation, run the port, return both sides."""
    fixture = build_fixture(tmp_path)
    if mutation is not None:
        mutate(fixture, *mutation)
    return recorded(case), _run(PORT, fixture)


# --------------------------------------------------------------------------- The live checkout, deliberately NOT recorded ---------------------------------------------------------------------------


def test_the_live_tree_still_runs_every_case_green() -> None:
    """NOT RECORDED: it reads the repository's own bash, which is the subject.

    The assertion is on the SHAPE the gate has to keep -- five passes and the idempotent-skip line -- which is what a caller of `test:write-once-guard` depends on and what no recording could hold without going stale.
    """
    new = _run(PORT, ROOT)
    assert new.returncode == 0, new.stderr
    assert new.stdout.count(OK_LINE) == 5
    assert "sealed + binaries \u2192 idempotent SKIP (rc=10)" in new.stdout


# --------------------------------------------------------------------------- The fixture cases, each against the twin's recording ---------------------------------------------------------------------------


def test_unmutated_fixture_is_the_recorded_run(tmp_path: pathlib.Path) -> None:
    old, new = drive("unmutated", tmp_path)
    assert new.returncode == 0
    assert_same(old, new)
    # The fixture must be a faithful stand-in, or every mutation below is measuring the fixture rather than the mutation.
    assert old[1].count(OK_LINE) == 5, "the recorded green run lost its passes"


# --------------------------------------------------------------------------- The four log_fail branches, each reached by a real mutation ---------------------------------------------------------------------------


def test_a_guard_that_scrubs_is_caught_in_case_one(tmp_path: pathlib.Path) -> None:
    old, new = drive("a-guard-that-scrubs", tmp_path, (GUARD_REL, SCRUB_ANCHOR, SCRUB_MUTANT))
    assert old[0] == 1
    assert old[2] == BAD_LINE + "guard must NEVER scrub\n"
    assert old[1] == "", "the FIRST case fails, so no PASS line is printed"
    assert_same(old, new)


def test_a_guard_that_returns_zero_when_sealed_is_caught(tmp_path: pathlib.Path) -> None:
    old, new = drive(
        "a-guard-that-returns-zero-when-sealed",
        tmp_path,
        (GUARD_REL, "            return SKIP", "            return PROCEED"),
    )
    assert old[0] == 1
    assert "should SKIP (rc=10, idempotent rerun); got rc=0" in old[2]
    assert old[2].startswith(BAD_LINE)
    assert_same(old, new)


def test_sealed_but_empty_that_does_not_fail_loud_is_caught(tmp_path: pathlib.Path) -> None:
    old, new = drive(
        "sealed-but-empty-that-does-not-fail-loud",
        tmp_path,
        (
            GUARD_REL,
            "        log.error(CORRUPT[0]",
            "        return PROCEED\n        log.error(CORRUPT[0]",
        ),
    )
    assert old[0] == 1
    # Case one passed, so its PASS line is on stdout and the FAIL is case two's.
    assert old[1].count(OK_LINE) == 1
    assert "sealed-but-empty) should FAIL loud (rc=1); got rc=0" in old[2]
    assert_same(old, new)


def test_a_guard_that_scrubs_an_orphan_is_caught_in_case_three(
    tmp_path: pathlib.Path,
) -> None:
    """The em-dash message, which is the one this port writes as an escape."""
    old, new = drive(
        "a-guard-that-scrubs-an-orphan",
        tmp_path,
        (
            GUARD_REL,
            "    # No sentinel: a clean prefix or a byte-only orphan from a cancelled run.",
            (
                "    if rsv.prefix_nonempty(prefix, endpoint) is rsv.Probe.YES:\n"
                "        %s\n"
                "    # No sentinel: a clean prefix or a byte-only orphan from a cancelled run."
                % RM_CALL
            ),
        ),
    )
    assert old[0] == 1
    assert "-- that is the nightly housekeeping job's responsibility" in old[2]
    assert_same(old, new)


def test_a_dry_run_that_still_calls_aws_is_caught_in_case_four(
    tmp_path: pathlib.Path,
) -> None:
    old, new = drive(
        "a-dry-run-that-still-calls-aws",
        tmp_path,
        (
            GUARD_REL,
            "    if dry_run:\n",
            (
                "    if dry_run:\n"
                '        __import__("subprocess").run(\n'
                '            ["aws", "s3api", "head-object", "--bucket", "x", "--key", "y"], check=False\n'
                "        )\n"
            ),
        ),
    )
    assert old[0] == 1
    assert old[1].count(OK_LINE) == 3, "the first three cases still pass"
    assert old[2] == BAD_LINE + "DRY_RUN must not call aws at all\n"
    assert_same(old, new)


def test_the_corpus_and_the_goldens_are_the_same_set() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, RECORDED_CASES)


def test_the_recording_holds_both_verdicts() -> None:
    """A corpus of refusals only would agree with a port that never passes anything."""
    codes = {recorded(case)[0] for case in RECORDED_CASES}
    assert codes == {0, 1}, "the recording must hold a green and a red"


# --------------------------------------------------------------------------- The control: a planted defect must turn this suite red ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_this_comparison(tmp_path: pathlib.Path) -> None:
    """Delete the never-scrub assertion from a COPY of the port.

    That check is the whole reason this gate exists (the guard must not delete a retried release's binaries), and it is invisible on every green run. A port that dropped it would agree with the recording on the real tree and disagree only against a scrubbing guard, which is exactly the fixture built here.
    """
    source = PORT.read_text(encoding="utf-8")
    anchor = """    if h.logged("s3 rm"):
        log_fail("guard must NEVER scrub")
"""
    assert source.count(anchor) == 2, "the plant's anchor must still be where it was"
    broken = tmp_path / "write_once_guard_check_broken.py"
    broken.write_text(source.replace(anchor, "", 1), encoding="utf-8")

    fixture = build_fixture(tmp_path)
    mutate(fixture, GUARD_REL, SCRUB_ANCHOR, SCRUB_MUTANT)
    old = recorded("a-guard-that-scrubs")
    assert old[0] == 1, "the recording must hold the twin catching the scrubbing guard"
    broken_run = _run(broken, fixture)
    assert broken_run.returncode != old[0] or broken_run.stdout != old[1], (
        "PLANT DID NOT FIRE: the comparison is vacuous"
    )
    # And the unmutated port still agrees against the same fixture.
    assert_same(old, _run(PORT, fixture))

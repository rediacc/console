"""`rediacc_ci.deploy.write_once_guard_check` against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. `.ci/scripts/test/test-write-once-guard.sh` was the registered gate until this module took the registration; the K=5 ledger `.ci/shadow/w7p6-write-once-guard.observations.jsonl` holds five rows of equivalence over five distinct trees, and `goldens/write-once-guard/` holds the twin's OWN recorded bytes, captured on its last day in the tree. Each
golden's provenance header carries two blob shas, the twin's and the `upload-to-r2.sh` it ran against, so `git cat-file -p <sha>` still yields both programs.

WHICH CASES ARE RECORDED AND WHICH ARE NOT. Every case driving a FIXTURE has a golden. The case that runs against the LIVE checkout does not: freezing it would freeze a tracked file's content into a golden, and that tracked file is the guard under test, so the recording would go stale the first time somebody edited it and would red the port for a change it did not make.

THE HAPPY PATH IS THE WEAKEST CASE HERE, so most of this file is about the FAILURE paths. Both subjects pass on the real tree today, which proves only that two programs agree about a guard neither of them is currently catching out. Every case below therefore runs both against a FIXTURE TREE holding a MUTATED copy of `upload-to-r2.sh` or `release-state-validator.sh`, so the twin's
four `log_fail` branches are actually reached and compared byte for byte against the recording -- including the ANSI escapes, which are the part a reader of a CI log sees and the part a "tidier" port would drop.

HOW THE TWO SIDES WERE POINTED AT A FIXTURE, and it was different for each. The
twin resolved `ROOT_DIR` from `${BASH_SOURCE[0]}`, so it was COPIED into the
fixture and run from there. The port resolves it through `paths.repo_root()`, whose documented single override is `$REDIACC_CI_ROOT`, so it runs from the real tree with that variable set. Both read the same mutated bash, and the fixture no longer holds a copy of the twin because nothing runs it any more.

NOTHING ON DISK IS MUTATED. Every fixture is built under pytest's `tmp_path`
from `shutil.copy2` of the real files; the repository's own
`upload-to-r2.sh` and `release-state-validator.sh` are only ever read.

NO NETWORK, NO AWS. The subject under test mocks `aws` with a bash script on `PATH`, which is the twin's own design and is reproduced rather than replaced.

K=5 LEDGER: `.ci/shadow/w7p6-write-once-guard.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import typing

from rediacc_ci import paths
from rediacc_ci.deploy import write_once_guard_check
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "write_once_guard_check.py"
UPLOAD = ROOT / ".ci" / "scripts" / "deploy" / "upload-to-r2.sh"
VALIDATOR = ROOT / ".ci" / "scripts" / "lib" / "release-state-validator.sh"
SLUG = "write-once-guard"
UPLOAD_REL = ".ci/scripts/deploy/upload-to-r2.sh"

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
SCRUB_ANCHOR = '            log_info "Idempotent:'
SCRUB_MUTANT = (
    '            aws s3 rm "s3://${RELEASES_BUCKET}/${prefix}" --recursive\n'
    '            log_info "Idempotent:'
)

# NOT named `PASS_...`: ruff S105 reads any constant whose NAME contains
# "PASS" as a hardcoded password, and a per-line noqa to get past a gate is
# the thing this repo refuses. The VALUE is the twin's literal PASS line.
OK_LINE = "\033[0;32mPASS:\033[0m "
BAD_LINE = "\033[0;31mFAIL:\033[0m "


def build_fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    """A three-file `.ci` skeleton the twin and the port both resolve inside."""
    fixture = tmp_path / "fixture"
    for target in (
        fixture / ".ci" / "scripts" / "test",
        fixture / ".ci" / "scripts" / "deploy",
        fixture / ".ci" / "scripts" / "lib",
    ):
        target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(UPLOAD, fixture / ".ci" / "scripts" / "deploy" / UPLOAD.name)
    shutil.copy2(VALIDATOR, fixture / ".ci" / "scripts" / "lib" / VALIDATOR.name)
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
    old, new = drive("a-guard-that-scrubs", tmp_path, (UPLOAD_REL, SCRUB_ANCHOR, SCRUB_MUTANT))
    assert old[0] == 1
    assert old[2] == BAD_LINE + "guard must NEVER scrub\n"
    assert old[1] == "", "the FIRST case fails, so no PASS line is printed"
    assert_same(old, new)


def test_a_guard_that_returns_zero_when_sealed_is_caught(tmp_path: pathlib.Path) -> None:
    old, new = drive(
        "a-guard-that-returns-zero-when-sealed",
        tmp_path,
        (UPLOAD_REL, "            return 10", "            return 0"),
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
            UPLOAD_REL,
            '        log_error "Corrupt release state:',
            '        return 0\n        log_error "Corrupt release state:',
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
            UPLOAD_REL,
            "    # No sentinel: clean prefix or a byte-only orphan from a cancelled run.",
            (
                '    if [[ "$(rsv_prefix_nonempty "$prefix"; echo $?)" == "0" ]]; then\n'
                '        aws s3 rm "s3://${RELEASES_BUCKET}/${prefix}" --recursive\n'
                "    fi\n"
                "    # No sentinel: clean prefix or a byte-only orphan from a cancelled run."
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
            UPLOAD_REL,
            '        log_info "[DRY-RUN] sentinel-aware guard would check',
            (
                "        aws s3api head-object --bucket x --key y >/dev/null 2>&1 || true\n"
                '        log_info "[DRY-RUN] sentinel-aware guard would check'
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


# --------------------------------------------------------------------------- The sed extraction, which is the port's other moving part ---------------------------------------------------------------------------


def test_a_missing_guard_function_is_rc_127_on_both_sides(tmp_path: pathlib.Path) -> None:
    """`sed -n '/^write_once_guard()/,/^}/p'` finding nothing.

    The bundle then has no such function, `bash -c` exits 127, and the twin
    reported `got rc=127` rather than crashing. A port whose extractor silently
    produced the WHOLE file instead of nothing would disagree with that recording.
    """
    old, new = drive(
        "a-missing-guard-function",
        tmp_path,
        (UPLOAD_REL, "write_once_guard() {", "renamed_write_once_guard() {"),
    )
    assert old[0] == 1
    assert "got rc=127" in old[2]
    assert_same(old, new)


def test_extract_guard_takes_only_the_function() -> None:
    text = "before\nwrite_once_guard() {\n  body\n}\nafter\n"
    assert write_once_guard_check.extract_guard(text) == "write_once_guard() {\n  body\n}\n"


def test_extract_guard_stops_at_the_first_column_zero_brace() -> None:
    # A nested `}` that is INDENTED does not end the sed range; only `^}` does.
    text = "write_once_guard() {\n  if x; then\n    :\n  fi\n}\ntrailing\n"
    got = write_once_guard_check.extract_guard(text)
    assert got.endswith("}\n")
    assert "trailing" not in got


def test_extract_guard_finds_nothing_when_the_name_changed() -> None:
    assert write_once_guard_check.extract_guard("renamed() {\n  :\n}\n") == ""


def test_extract_guard_matches_the_real_sed() -> None:
    """Not asserted from reading sed's manual: sed is RUN and compared."""
    expected = subprocess.run(
        ["sed", "-n", "/^write_once_guard()/,/^}/p", str(UPLOAD)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert write_once_guard_check.extract_guard(UPLOAD.read_text(encoding="utf-8")) == expected
    assert expected != "", "the anchor moved; this comparison would be vacuous"


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
    mutate(fixture, UPLOAD_REL, SCRUB_ANCHOR, SCRUB_MUTANT)
    old = recorded("a-guard-that-scrubs")
    assert old[0] == 1, "the recording must hold the twin catching the scrubbing guard"
    broken_run = _run(broken, fixture)
    assert broken_run.returncode != old[0] or broken_run.stdout != old[1], (
        "PLANT DID NOT FIRE: the comparison is vacuous"
    )
    # And the unmutated port still agrees against the same fixture.
    assert_same(old, _run(PORT, fixture))

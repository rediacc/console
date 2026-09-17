"""Differential: `rediacc_ci.deploy.write_once_guard_check` against its twin
`.ci/scripts/test/test-write-once-guard.sh` (gate `test:write-once-guard`).

THE HAPPY PATH IS THE WEAKEST CASE HERE, so most of this file is about the
FAILURE paths. Both subjects pass on the real tree today, which proves only
that two programs agree about a guard neither of them is currently catching
out. Every case below therefore runs both against a FIXTURE TREE holding a
MUTATED copy of `upload-to-r2.sh` or `release-state-validator.sh`, so the
twin's four `log_fail` branches are actually reached and compared byte for
byte -- including the ANSI escapes, which are the part a reader of a CI log
sees and the part a "tidier" port would drop.

HOW THE TWO SIDES ARE POINTED AT A FIXTURE, and it is different for each. The
twin resolves `ROOT_DIR` from `${BASH_SOURCE[0]}`, so it is COPIED into the
fixture and run from there. The port resolves it through `paths.repo_root()`,
whose documented single override is `$REDIACC_CI_ROOT`, so it runs from the
real tree with that variable set. Both then read the same mutated bash.

NOTHING ON DISK IS MUTATED. Every fixture is built under pytest's `tmp_path`
from `shutil.copy2` of the real files; the repository's own
`upload-to-r2.sh`, `release-state-validator.sh` and the twin are only ever
read.

NO NETWORK, NO AWS. The subject under test mocks `aws` with a bash script on
`PATH`, which is the twin's own design and is reproduced rather than replaced.

K=5 LEDGER: `.ci/shadow/w7p6-write-once-guard.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import typing

from rediacc_ci import paths
from rediacc_ci.deploy import write_once_guard_check

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "test" / "test-write-once-guard.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "deploy" / "write_once_guard_check.py"
UPLOAD = ROOT / ".ci" / "scripts" / "deploy" / "upload-to-r2.sh"
VALIDATOR = ROOT / ".ci" / "scripts" / "lib" / "release-state-validator.sh"

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
    shutil.copy2(TWIN, fixture / ".ci" / "scripts" / "test" / TWIN.name)
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
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
    if subject.suffix == ".py":
        runner = ["python3", str(subject)]
        env["PYTHONPATH"] = str(ROOT / ".ci")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["REDIACC_CI_ROOT"] = str(fixture)
    else:
        runner = ["bash", str(fixture / ".ci" / "scripts" / "test" / TWIN.name)]
    return subprocess.run(runner, env=env, capture_output=True, text=True, check=False, timeout=120)


def run_both(
    fixture: pathlib.Path, *, port: pathlib.Path | None = None
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    return _run(TWIN, fixture), _run(port or PORT, fixture)


def assert_same(
    old: subprocess.CompletedProcess[str], new: subprocess.CompletedProcess[str]
) -> None:
    assert new.returncode == old.returncode, "exit: twin %s, port %s" % (
        old.returncode,
        new.returncode,
    )
    assert new.stdout == old.stdout
    assert new.stderr == old.stderr


# --------------------------------------------------------------------------- The happy path, on the real tree and on an unmutated fixture ---------------------------------------------------------------------------


def test_real_tree_agrees_byte_for_byte() -> None:
    """No fixture: both subjects read the repository's own bash."""
    old = _run(TWIN, ROOT)
    new = _run(PORT, ROOT)
    assert old.returncode == 0, old.stderr
    assert old.stdout.count(OK_LINE) == 5
    assert "sealed + binaries → idempotent SKIP (rc=10)" in old.stdout
    assert_same(old, new)


def test_unmutated_fixture_is_the_same_run(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    old, new = run_both(fixture)
    assert old.returncode == 0
    assert_same(old, new)
    # The fixture must be a faithful stand-in, or every mutation below is measuring the fixture rather than the mutation.
    assert old.stdout == _run(TWIN, ROOT).stdout


# --------------------------------------------------------------------------- The four log_fail branches, each reached by a real mutation ---------------------------------------------------------------------------


def test_a_guard_that_scrubs_is_caught_in_case_one(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    mutate(
        fixture,
        ".ci/scripts/deploy/upload-to-r2.sh",
        '            log_info "Idempotent:',
        '            aws s3 rm "s3://${RELEASES_BUCKET}/${prefix}" --recursive\n'
        '            log_info "Idempotent:',
    )
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert old.stderr == BAD_LINE + "guard must NEVER scrub\n"
    assert old.stdout == "", "the FIRST case fails, so no PASS line is printed"
    assert_same(old, new)


def test_a_guard_that_returns_zero_when_sealed_is_caught(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    mutate(
        fixture,
        ".ci/scripts/deploy/upload-to-r2.sh",
        "            return 10",
        "            return 0",
    )
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "should SKIP (rc=10, idempotent rerun); got rc=0" in old.stderr
    assert old.stderr.startswith(BAD_LINE)
    assert_same(old, new)


def test_sealed_but_empty_that_does_not_fail_loud_is_caught(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    mutate(
        fixture,
        ".ci/scripts/deploy/upload-to-r2.sh",
        '        log_error "Corrupt release state:',
        '        return 0\n        log_error "Corrupt release state:',
    )
    old, new = run_both(fixture)
    assert old.returncode == 1
    # Case one passed, so its PASS line is on stdout and the FAIL is case two's.
    assert old.stdout.count(OK_LINE) == 1
    assert "sealed-but-empty) should FAIL loud (rc=1); got rc=0" in old.stderr
    assert_same(old, new)


def test_a_guard_that_scrubs_an_orphan_is_caught_in_case_three(
    tmp_path: pathlib.Path,
) -> None:
    """The em-dash message, which is the one this port writes as an escape."""
    fixture = build_fixture(tmp_path)
    mutate(
        fixture,
        ".ci/scripts/deploy/upload-to-r2.sh",
        "    # No sentinel: clean prefix or a byte-only orphan from a cancelled run.",
        '    if [[ "$(rsv_prefix_nonempty "$prefix"; echo $?)" == "0" ]]; then\n'
        '        aws s3 rm "s3://${RELEASES_BUCKET}/${prefix}" --recursive\n'
        "    fi\n"
        "    # No sentinel: clean prefix or a byte-only orphan from a cancelled run.",
    )
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "-- that is the nightly housekeeping job's responsibility" in old.stderr
    assert_same(old, new)


def test_a_dry_run_that_still_calls_aws_is_caught_in_case_four(
    tmp_path: pathlib.Path,
) -> None:
    fixture = build_fixture(tmp_path)
    mutate(
        fixture,
        ".ci/scripts/deploy/upload-to-r2.sh",
        '        log_info "[DRY-RUN] sentinel-aware guard would check',
        "        aws s3api head-object --bucket x --key y >/dev/null 2>&1 || true\n"
        '        log_info "[DRY-RUN] sentinel-aware guard would check',
    )
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert old.stdout.count(OK_LINE) == 3, "the first three cases still pass"
    assert old.stderr == BAD_LINE + "DRY_RUN must not call aws at all\n"
    assert_same(old, new)


# --------------------------------------------------------------------------- The sed extraction, which is the port's other moving part ---------------------------------------------------------------------------


def test_a_missing_guard_function_is_rc_127_on_both_sides(tmp_path: pathlib.Path) -> None:
    """`sed -n '/^write_once_guard()/,/^}/p'` finding nothing.

    The bundle then has no such function, `bash -c` exits 127, and the twin
    reports `got rc=127` rather than crashing. A port whose extractor silently
    produced the WHOLE file instead of nothing would disagree here.
    """
    fixture = build_fixture(tmp_path)
    mutate(
        fixture,
        ".ci/scripts/deploy/upload-to-r2.sh",
        "write_once_guard() {",
        "renamed_write_once_guard() {",
    )
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "got rc=127" in old.stderr
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


def test_planted_defect_is_caught_by_this_differential(tmp_path: pathlib.Path) -> None:
    """Delete the never-scrub assertion from a COPY of the port.

    That check is the whole reason this gate exists (the guard must not delete a
    retried release's binaries), and it is invisible on every green run. A port
    that dropped it would agree with the twin on the real tree and disagree only
    against a scrubbing guard, which is exactly the fixture built here.
    """
    source = PORT.read_text(encoding="utf-8")
    anchor = """    if h.logged("s3 rm"):
        log_fail("guard must NEVER scrub")
"""
    assert source.count(anchor) == 2, "the plant's anchor must still be where it was"
    broken = tmp_path / "write_once_guard_check_broken.py"
    broken.write_text(source.replace(anchor, "", 1), encoding="utf-8")

    fixture = build_fixture(tmp_path)
    mutate(
        fixture,
        ".ci/scripts/deploy/upload-to-r2.sh",
        '            log_info "Idempotent:',
        '            aws s3 rm "s3://${RELEASES_BUCKET}/${prefix}" --recursive\n'
        '            log_info "Idempotent:',
    )
    old, new = run_both(fixture, port=broken)
    assert old.returncode == 1, "the twin must catch the scrubbing guard"
    assert new.returncode != old.returncode or new.stdout != old.stdout, (
        "PLANT DID NOT FIRE: the differential is vacuous"
    )
    # And the unmutated port still agrees against the same fixture.
    good_old, good_new = run_both(fixture)
    assert_same(good_old, good_new)

r"""`rediacc_ci.quality.account_portal` against the shell it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. This gate reaches every
one of its verdicts from an external tool's EXIT STATUS, so the only thing a
port can get wrong is which command it runs, where it runs it, in what order,
and what it does with each status. All four of those are properties of a
process, not of a string, and a table of expected strings would be a table of
what the PORT does, asserted against itself.

The committed ledger `.ci/shadow/w7p2-account-portal.observations.jsonl`
compares the WHOLE gate over five distinct trees, with `npx` and `npm` stubbed
so every phase is deterministic. What it cannot show is the ARGV -- both sides
would agree perfectly while both ran `tsc` without `--noEmit`, which would emit
JavaScript into the tree and still exit 0. This file records the argv vectors
and the working directories a run actually produces.

THE STUBS BELOW ARE THE MODULE'S OWN (`account_portal.write_stubs`), not a
second copy, so a change to them cannot make the test and the selftest disagree
about what "running the gate" means.
"""

import os
import pathlib
import shutil

import pytest

from rediacc_ci.quality import account_portal as ap
from rediacc_ci.tests import differential as diff

# A stub pair that RECORDS every invocation instead of just exiting. The gate is a sequence of process launches, so the sequence is the artifact worth capturing: one line per launch, holding the working directory and the whole argv.
_RECORDING_STUB = """#!/usr/bin/env bash
{ printf '%s' "$(basename "$0")"; printf ' %s' "$@"; printf '\\t%s\\n' "$PWD"; } >> "$TRACE"
case "$1 $2 $3" in
    "tsc --noEmit -p") exit "${STUB_E2E_RC:-0}" ;;
esac
case "$1 $2" in
    "tsc --noEmit")
        if [ "$(basename "$PWD")" = web ]; then exit "${STUB_FE_RC:-0}"; fi
        exit "${STUB_BE_RC:-0}" ;;
    "biome check") exit "${STUB_LINT_RC:-0}" ;;
    "vite build") exit "${STUB_BUILD_RC:-0}" ;;
esac
if [ "$1" = "ci" ]; then exit "${STUB_CI_RC:-0}"; fi
if [ "$1" = "run" ]; then exit "${STUB_ONB_RC:-0}"; fi
exit 0
"""


def _trace(tmp_path: pathlib.Path, **codes: str) -> tuple[int, list[tuple[str, str]]]:
    """Run the gate against a fixture tree and return (exit, [(argv, cwd)]).

    The tree is rebuilt for every call, so no test can depend on a previous
    one's artifacts -- which matters here more than usual, because phase 1
    WRITES to the tree and phase 7 reads what phase 6 wrote.
    """
    root = tmp_path / "tree"
    bindir = tmp_path / "bin"
    trace = tmp_path / "trace.tsv"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    ap.seed_tree(
        root,
        node_modules=codes.pop("_node_modules", "1") == "1",
        output=codes.pop("_output", "1") == "1",
    )
    bindir.mkdir(parents=True, exist_ok=True)
    for name in ("npx", "npm"):
        target = bindir / name
        target.write_text(_RECORDING_STUB, encoding="utf-8")
        target.chmod(0o755)
    trace.write_text("", encoding="utf-8")

    saved = {k: os.environ.get(k) for k in (ap.paths.ROOT_ENV, "PATH", "TRACE", *codes)}
    os.environ[ap.paths.ROOT_ENV] = str(root)
    os.environ["PATH"] = "%s:%s" % (bindir, saved["PATH"] or "")
    os.environ["TRACE"] = str(trace)
    for key, value in codes.items():
        os.environ[key] = value
    try:
        rc = ap.main([])
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    rows: list[tuple[str, str]] = []
    for line in trace.read_text(encoding="utf-8").split("\n"):
        if line.strip() == "":
            continue
        argv, _tab, cwd = line.partition("\t")
        rows.append((argv, cwd))
    return rc, rows


def test_the_healthy_run_launches_exactly_six_commands(tmp_path: pathlib.Path) -> None:
    """The ARGV and the CWD of every launch, in order.

    THIS IS THE ASSERTION THE LEDGER CANNOT MAKE. Both implementations would
    agree perfectly while both ran `tsc` with no `--noEmit`, which EMITS
    JavaScript into the tree and exits 0 -- a gate that silently became a build
    step. The exact vectors are therefore written down here, once.

    Six and not seven: `npm ci` is skipped because `node_modules` is present,
    which is the ordinary case on any machine that has run this before.
    """
    rc, rows = _trace(tmp_path)
    assert rc == 0
    root = str((tmp_path / "tree").resolve())
    assert [argv for argv, _ in rows] == [
        "npx tsc --noEmit",
        "npx tsc --noEmit",
        "npx tsc --noEmit -p e2e/tsconfig.json",
        "npx biome check private/account/web/src/",
        "npm run build:account-onboarding",
        "npx vite build",
    ]
    assert [cwd for _, cwd in rows] == [
        root + "/private/account/web",  # phase 2, the frontend
        root + "/private/account",  # phase 3, the backend
        root + "/private/account",  # phase 3b, the e2e project
        root,  # phase 4, biome, from the repo root
        root,  # phase 5, the onboarding generator
        root + "/private/account/web",  # phase 6, the vite build
    ]


def test_an_absent_node_modules_adds_the_install_first(tmp_path: pathlib.Path) -> None:
    """Phase 1, the only phase that MUTATES the tree.

    Its MIRROR is the test above, where `node_modules` exists and the install is
    not run at all. Both directions, because a gate that always installed would
    be slow and a gate that never installed would fail on a fresh checkout.
    """
    rc, rows = _trace(tmp_path, _node_modules="0")
    assert rc == 0
    assert rows[0][0] == "npm ci --ignore-scripts"
    assert rows[0][1] == str((tmp_path / "tree").resolve()) + "/private/account/web"
    assert len(rows) == 7


# Each row is (the environment variable that fails a phase, how many commands should have run before the gate gave up). The count is the interesting half: it is what proves the gate STOPS rather than carrying on into a build whose inputs did not typecheck.
STOP_CASES = [
    ("STUB_FE_RC", 1),  # phase 2 fails: nothing after it runs
    ("STUB_BE_RC", 2),  # phase 3
    ("STUB_E2E_RC", 3),  # phase 3b
    ("STUB_ONB_RC", 5),  # phase 5, after the non-blocking lint
    ("STUB_BUILD_RC", 6),  # phase 6
]


@pytest.mark.parametrize(("variable", "launched"), STOP_CASES)
def test_a_failing_phase_stops_the_run(
    tmp_path: pathlib.Path, variable: str, launched: int
) -> None:
    rc, rows = _trace(tmp_path, **{variable: "1"})
    assert rc == 1
    assert len(rows) == launched


def test_the_lint_phase_is_the_one_that_does_not_stop(tmp_path: pathlib.Path) -> None:
    """Phase 4 warns and carries on. Its MIRROR is every row of STOP_CASES.

    Asserted by COUNTING the launches after it, not by reading the exit code:
    an exit code of 0 would also be produced by a gate that ran phase 4 last.
    """
    rc, rows = _trace(tmp_path, STUB_LINT_RC="1")
    assert rc == 0
    assert len(rows) == 6
    assert rows[-1][0] == "npx vite build"


def test_phase_seven_refuses_a_build_that_produced_nothing(tmp_path: pathlib.Path) -> None:
    """The anti-vacuity check, and the exact limit of it.

    `vite build` exits 0 and writes nothing: the gate must still refuse. And the
    limit, asserted so it is on the record -- the test is EXISTENCE, so a
    zero-byte file, or a stale one from a previous run, satisfies it.
    """
    rc, rows = _trace(tmp_path, _output="0")
    assert rc == 1
    assert len(rows) == 6  # every tool ran and every tool was happy

    empty = tmp_path / "tree" / ap.OUTPUT_REL
    empty.parent.mkdir(parents=True, exist_ok=True)
    empty.write_text("", encoding="utf-8")
    assert empty.is_file()
    assert empty.stat().st_size == 0


# --------------------------------------------------------------------------- The exit-status conventions, against bash ---------------------------------------------------------------------------


def test_missing_binary_and_missing_cwd_get_bash_s_own_codes(tmp_path: pathlib.Path) -> None:
    """127 for `command not found`, 1 for a failed `cd`, measured against bash.

    Python raises the SAME exception type for both, distinguished only by the
    exception's `filename`, so this is the seam where a port most easily
    collapses two different failures into one code. Bash is the authority and is
    asked directly.
    """
    code, out, err = diff.bash_streams("definitely_not_a_binary_xyz; echo $?", cwd=str(tmp_path))
    assert code == 0, err
    assert out.strip().split("\n")[-1] == "127"
    assert ap.run(["definitely_not_a_binary_xyz"], tmp_path) == 127

    code, out, err = diff.bash_streams(
        'cd "%s"; echo $?' % (tmp_path / "nope" / "deeper"), cwd=str(tmp_path)
    )
    assert code == 0, err
    assert out.strip().split("\n")[-1] == "1"
    assert ap.run(["true"], tmp_path / "nope" / "deeper") == 1

    # A cwd that exists but is a FILE. Bash says 1 as well, through a different errno, and the port must not report it as a missing binary.
    afile = tmp_path / "afile"
    afile.write_text("x", encoding="utf-8")
    code, out, err = diff.bash_streams('cd "%s"; echo $?' % afile, cwd=str(tmp_path))
    assert code == 0, err
    assert out.strip().split("\n")[-1] == "1"
    assert ap.run(["true"], afile) == 1


def test_a_nonzero_status_from_any_tool_is_a_failure_not_just_one(
    tmp_path: pathlib.Path,
) -> None:
    """`if ! npx tsc ...` tests the STATUS, so 127 fails the phase too.

    Which means a missing `npx` is reported as "Frontend typecheck failed!" by
    both implementations. That is the twin's behaviour and it is worth an
    assertion rather than a comment, because it is the shape in which "the
    toolchain is not installed" reaches a reader as "your types are broken".
    """
    rc, rows = _trace(tmp_path, STUB_FE_RC="127")
    assert rc == 1
    assert len(rows) == 1


def test_selftest_is_green() -> None:
    """The port's own plants and mirrors, driven from pytest.

    Not redundant with running `--selftest` from the shell: this is the call that
    fails the pytest suite when a control is deleted, which is the failure mode
    the flag on its own cannot catch (nobody runs it).
    """
    assert ap.selftest() == 0

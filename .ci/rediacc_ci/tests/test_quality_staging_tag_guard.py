"""`rediacc_ci.quality.staging_tag_guard` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-staging-tag-guard.sh` over a fixture -- pointed there with the twin's own `STAGING_GUARD_ROOT` seam, which is why the twin does not have to be copied -- with stdout and stderr captured SEPARATELY, and its bytes are compared against the port's.

STDOUT IS COMPARED BYTE FOR BYTE HERE, and that is not the usual bar. This gate's output IS its tally: ` ok <label>` lines and a `✓ <subject>: N control(s) passed` verdict, all of it interpolated from the same subject string that appears in the FAILING verdict, where it carries a ✗ and is therefore a compared finding. The first draft of this port enriched that subject with a
scanned-file count and
the shadow differential refused all three trees with MISMATCH_FINDINGS; the rows
are in `.ci/shadow/w7p2-stagingtag.observations.jsonl` and those tree ids stay disqualified. Comparing the bytes here is what stops that returning.

The committed ledger records the same comparison over K distinct trees, three of which embed BOTH implementations so that the tree id really is the content the disqualification rule assumes it is.
"""

import pathlib

import pytest

from rediacc_ci.quality import staging_tag_guard as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-staging-tag-guard.sh"
SUBJECT_REL = ".ci/scripts/docker/cleanup-staging.sh"
CALLER_REL = ".ci/scripts/release/cleanup-channel-docker-tags.sh"

GUARDED = (
    "#!/bin/bash\n"
    'if [[ "$CHANNEL" =~ ^staging- ]]; then\n'
    '  "$SCRIPT_DIR/../docker/cleanup-staging.sh" --tag "$CHANNEL"\n'
    "fi\n"
)
UNGUARDED = '#!/bin/bash\n"$SCRIPT_DIR/../docker/cleanup-staging.sh" --tag "$CHANNEL"\n'
LITERAL = '#!/bin/bash\n"$SCRIPT_DIR/../docker/cleanup-staging.sh" --tag staging-abc123\n'

# The `.py`-caller shape the scanner was widened for (agent/PLAN-w7p4w-docker-cutover.md §3): same unguarded-call shape as UNGUARDED, naming the Python entry point instead of the bash twin.
UNGUARDED_PY = '"$SCRIPT_DIR/../docker/cleanup_staging.py" --tag "$CHANNEL"\n'


def build(tmp_path: pathlib.Path, files: dict[str, str], rail: bool = True) -> pathlib.Path:
    """A fixture tree holding the SUBJECT and its callers. The twin is not copied:
    it reads `$STAGING_GUARD_ROOT`, so the real one judges this tree."""
    root = tmp_path / "fixture"
    subject = root / SUBJECT_REL
    subject.parent.mkdir(parents=True)
    body = "#!/bin/bash\n# usage: cleanup-staging.sh --tag staging-abc123\n"
    if rail:
        body += '[[ "$TAG" =~ ^staging- ]] || exit 1\n'
    subject.write_text(body, encoding="utf-8")
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    repo = pathlib.Path(diff.repo())
    env = diff.env_for(
        STAGING_GUARD_ROOT=str(root),
        PYTHONPATH=str(repo / ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s/%s" % (repo, TWIN), env=env, cwd=str(root))
    new = diff.bash_streams(
        "python3 -m rediacc_ci.quality.staging_tag_guard", env=env, cwd=str(root)
    )
    return old, new


@pytest.mark.parametrize(
    ("files", "rail", "want_exit"),
    [
        pytest.param({CALLER_REL: GUARDED}, True, 0, id="caller-pre-checks"),
        pytest.param({".ci/scripts/release/x.sh": LITERAL}, True, 0, id="caller-passes-literal"),
        pytest.param({CALLER_REL: UNGUARDED}, True, 1, id="the-2026-09-06-defect"),
        pytest.param({".github/workflows/r.yml": UNGUARDED}, True, 1, id="unguarded-in-a-workflow"),
        pytest.param({CALLER_REL: GUARDED}, False, 1, id="rail-removed"),
        pytest.param({}, True, 1, id="no-call-site-is-vacuous"),
        pytest.param(
            {".ci/scripts/release/d.sh": '# cleanup-staging.sh --tag "$X" would fail\n'},
            True,
            1,
            id="a-comment-is-not-a-call-site",
        ),
        pytest.param(
            {".ci/scripts/release/x.py": UNGUARDED_PY},
            True,
            1,
            id="unguarded-py-caller-is-found-and-fails",
        ),
        pytest.param(
            {".ci/rediacc_ci/quality/noise.py": UNGUARDED_PY},
            True,
            1,
            id="a-py-mention-outside-ci-scripts-is-not-a-call-site--still-vacuous",
        ),
    ],
)
def test_port_and_twin_agree_byte_for_byte(
    tmp_path: pathlib.Path, files: dict[str, str], rail: bool, want_exit: int
) -> None:
    root = build(tmp_path, files, rail=rail)
    (old_exit, old_out, old_err), (new_exit, new_out, new_err) = run_both(root)
    assert old_exit == want_exit
    assert new_exit == old_exit
    assert new_out == old_out, "the tally on stdout is the gate's output contract"
    # stderr carries the port's one extra `→` line, which shadow-gate.ts reads as chatter. Everything else must match, including the FAIL lines and the two closing advice lines that the comparator reads as continuation findings.
    assert [x for x in new_err.split("\n") if not x.startswith("→")] == old_err.split("\n")


def test_the_green_case_is_not_vacuously_equal(tmp_path: pathlib.Path) -> None:
    """Two implementations that both print nothing agree about nothing."""
    green = run_both(build(tmp_path / "a", {CALLER_REL: GUARDED}))[0][1]
    red = run_both(build(tmp_path / "b", {CALLER_REL: UNGUARDED}))[0][1]
    assert green != red
    assert "ok    " in green


def test_a_duplicated_rail_fails_on_both_sides(tmp_path: pathlib.Path) -> None:
    """`grep -c` counts LINES and the twin wants exactly "1". Carried, not fixed."""
    root = build(tmp_path, {CALLER_REL: GUARDED})
    subject = root / SUBJECT_REL
    subject.write_text(
        subject.read_text() + '[[ "$OTHER" =~ ^staging- ]] || exit 1\n', encoding="utf-8"
    )
    (old_exit, old_out, old_err), (new_exit, new_out, new_err) = run_both(root)
    assert old_exit == 1
    assert new_exit == 1
    assert new_out == old_out
    assert "(got '2' want '1')" in old_err
    assert "(got '2' want '1')" in new_err


def test_a_missing_subject_refuses_on_both_sides(tmp_path: pathlib.Path) -> None:
    root = build(tmp_path, {CALLER_REL: GUARDED})
    (root / SUBJECT_REL).unlink()
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(root)
    assert (old_exit, new_exit) == (1, 1)
    assert "nothing was verified" in old_err
    assert "nothing was verified" in new_err


def test_a_colon_in_a_caller_path_yields_a_verdict_on_both_sides(
    tmp_path: pathlib.Path,
) -> None:
    """A truncated path must fail its control, not raise out of main().

    `${hit%%:*}` splits the grep hit at its FIRST colon, so a caller named
    `a:b.sh` collapses to `.../release/a` on both sides. The twin hands that to `grep -qE`, which prints `No such file or directory`, exits non-zero, leaves `guarded` at 0 and still reaches a verdict. This port called `read_text` on it and died with an uncaught FileNotFoundError -- the same exit status by accident, no verdict, and a stack trace where the twin prints a control.
    Measured 2026-09-06; the `try/except OSError` in `main` is what this pins.
    """
    root = build(tmp_path, {".ci/scripts/release/a:b.sh": UNGUARDED})
    (old_exit, old_out, old_err), (new_exit, new_out, new_err) = run_both(root)
    assert (old_exit, new_exit) == (1, 1)
    assert new_out == old_out
    assert "Traceback (most recent call last)" not in new_err
    fail_line = ".ci/scripts/release/a guards its call against a non-staging tag (got '0' want '1')"
    assert fail_line in old_err
    assert fail_line in new_err
    # The twin's own `grep:` error is the evidence that it did not read the file either. It is the only stderr line the two sides do not share, besides the port's `→` progress line.
    noise = ("\u2192", "grep:")
    assert [x for x in new_err.split("\n") if not x.startswith(noise)] == [
        x for x in old_err.split("\n") if not x.startswith(noise)
    ]


def test_executing_calls_filters_prose_and_the_subject_itself() -> None:
    """The two filter greps, pinned in both directions."""
    target = pathlib.Path("/repo/.ci/scripts/docker/cleanup-staging.sh")
    files, n_calls = gate.executing_calls(
        [
            '/repo/a.sh:66:  "$D/cleanup-staging.sh" --tag "$CHANNEL"',
            '/repo/a.sh:15:# cleanup-staging.sh --tag "$CHANNEL" is refused',
            "/repo/a.sh:20:echo see cleanup-staging.sh for why",
            "%s:6:#   cleanup-staging.sh --tag staging-abc123" % target,
            '/repo/b.yml:9:      - run: cleanup-staging.sh --tag "$T"',
        ],
        target,
    )
    assert files == ["/repo/a.sh", "/repo/b.yml"]
    assert n_calls == 2


def test_grep_hits_only_reads_sh_and_yml(tmp_path: pathlib.Path) -> None:
    """`--include='*.sh' --include='*.yml'`, and the file count that proves it ran."""
    root = build(
        tmp_path,
        {
            ".ci/scripts/release/x.sh": LITERAL,
            ".ci/notes.md": LITERAL,
            ".github/workflows/r.yml": "name: r\n",
        },
    )
    hits, files_read = gate.grep_hits(root)
    assert files_read == 3, "the .md is not read"
    assert all(".md" not in h.split(":", 1)[0] for h in hits)


def test_grep_hits_scopes_py_to_ci_scripts(tmp_path: pathlib.Path) -> None:
    """`.py` is read under `.ci/scripts`, and NOWHERE else in `.ci`.

    Scanning ALL of `.ci` for `.py` (a literal reading of
    agent/PLAN-w7p4w-docker-cutover.md §3's "add `--include='*.py'`") turned 1
    real call site into 18 at widening time: `.ci/rediacc_ci` is this package's own implementation/tests/regex-constants tree and is full of self-referential mentions of this exact needle. This pins the fix: a `.py` file under `.ci/scripts` is read, the SAME needle under `.ci/rediacc_ci` is not.
    """
    root = build(
        tmp_path,
        {
            ".ci/scripts/release/x.py": UNGUARDED_PY,
            ".ci/rediacc_ci/quality/noise.py": UNGUARDED_PY,
        },
    )
    hits, _ = gate.grep_hits(root)
    hit_files = {h.split(":", 1)[0] for h in hits}
    assert str(root / ".ci/scripts/release/x.py") in hit_files
    assert str(root / ".ci/rediacc_ci/quality/noise.py") not in hit_files


def test_selftest_passes() -> None:
    assert gate.selftest() == 0

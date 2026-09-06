"""`rediacc_ci.quality.staging_tag_guard` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-staging-tag-guard.sh` over
a fixture -- pointed there with the twin's own `STAGING_GUARD_ROOT` seam, which
is why the twin does not have to be copied -- with stdout and stderr captured
SEPARATELY, and its bytes are compared against the port's.

STDOUT IS COMPARED BYTE FOR BYTE HERE, and that is not the usual bar. This gate's
output IS its tally: `  ok    <label>` lines and a `✓ <subject>: N control(s)
passed` verdict, all of it interpolated from the same subject string that appears
in the FAILING verdict, where it carries a ✗ and is therefore a compared finding.
The first draft of this port enriched that subject with a scanned-file count and
the shadow differential refused all three trees with MISMATCH_FINDINGS; the rows
are in `.ci/shadow/w7p2-stagingtag.observations.jsonl` and those tree ids stay
disqualified. Comparing the bytes here is what stops that returning.

The committed ledger records the same comparison over K distinct trees, three of
which embed BOTH implementations so that the tree id really is the content the
disqualification rule assumes it is.
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
    # stderr carries the port's one extra `→` line, which shadow-gate.ts reads as
    # chatter. Everything else must match, including the FAIL lines and the two
    # closing advice lines that the comparator reads as continuation findings.
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


def test_selftest_passes() -> None:
    assert gate.selftest() == 0

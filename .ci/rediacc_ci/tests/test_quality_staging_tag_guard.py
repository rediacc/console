"""`rediacc_ci.quality.staging_tag_guard`, driven directly against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-staging-tag-guard.sh` over each fixture below -- pointed there with the twin's own `STAGING_GUARD_ROOT` seam, which is why the twin never had to be copied -- with stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. The ledger
`.ci/shadow/w7p2-stagingtag.observations.jsonl` recorded the same comparison over twelve distinct trees, three of which embed BOTH implementations so that the tree id really is the content the disqualification rule assumes it is. The twin has now been deleted, and every case that executed it compares against `goldens/staging-tag-guard/`, which holds the twin's OWN recorded output,
captured from the tracked script on its last day in the tree. The provenance header of each golden carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed those bytes.

STDOUT IS COMPARED BYTE FOR BYTE, and that is not the usual bar. This gate's output IS its tally: ` ok <label>` lines and a `✓ <subject>: N control(s) passed` verdict, all of it interpolated from the same subject string that appears in the FAILING verdict, where it carries a ✗ and is therefore a compared finding. The first draft of this port enriched that subject with a
scanned-file count and the shadow differential refused all three trees with MISMATCH_FINDINGS; those tree ids stay disqualified. Comparing the recorded bytes here is what stops that returning.

ONE THING IS FILTERED OUT OF THE PORT'S STDERR, and it is the same one the differential filtered: the `→` progress line the port emits and `shadow-gate.ts` reads as chatter. Everything else is compared verbatim, including the FAIL lines and the two closing advice lines the comparator reads as continuation findings. The colon case filters `grep:` as well, for the reason its own
docstring gives.
"""

from __future__ import annotations

import pathlib

import pytest

from rediacc_ci.quality import staging_tag_guard as gate
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

SLUG = "staging-tag-guard"
PORT = pathlib.Path(diff.repo()) / ".ci" / "rediacc_ci" / "quality" / "staging_tag_guard.py"

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


def build(
    tmp_path: pathlib.Path,
    files: dict[str, str],
    rail: bool = True,
    extra_rail: bool = False,
    drop_subject: bool = False,
) -> pathlib.Path:
    """A fixture tree holding the SUBJECT and its callers."""
    root = tmp_path / "fixture"
    subject = root / SUBJECT_REL
    subject.parent.mkdir(parents=True)
    body = "#!/bin/bash\n# usage: cleanup-staging.sh --tag staging-abc123\n"
    if rail:
        body += '[[ "$TAG" =~ ^staging- ]] || exit 1\n'
    if extra_rail:
        body += '[[ "$OTHER" =~ ^staging- ]] || exit 1\n'
    subject.write_text(body, encoding="utf-8")
    if drop_subject:
        subject.unlink()
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def run_port(root: pathlib.Path, port: pathlib.Path | None = None) -> tuple[int, str, str]:
    repo = pathlib.Path(diff.repo())
    env = diff.env_for(
        STAGING_GUARD_ROOT=str(root),
        PYTHONPATH=str(repo / ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    command = (
        "python3 -m rediacc_ci.quality.staging_tag_guard" if port is None else "python3 %s" % port
    )
    return diff.bash_streams(command, env=env, cwd=str(root))


NOISE = ("→",)


def split_golden(text: str) -> tuple[int, str, str]:
    """A recorded twin render, back into its three parts."""
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def compare(
    root: pathlib.Path,
    name: str,
    noise: tuple[str, ...] = NOISE,
    port: pathlib.Path | None = None,
) -> tuple[int, str, str]:
    want_exit, want_out, want_err = split_golden(frozen.read(SLUG, name))
    returncode, stdout, stderr = run_port(root, port=port)
    stdout = frozen.mask_root(stdout, root)
    stderr = frozen.mask_root(stderr, root)
    assert returncode == want_exit, "%s: the twin exited %d, the port %d" % (
        name,
        want_exit,
        returncode,
    )
    assert stdout == want_out, "%s: the tally on stdout is the gate's output contract" % name
    assert [x for x in stderr.split("\n") if not x.startswith(noise)] == [
        x for x in want_err.split("\n") if not x.startswith(noise)
    ], "%s: stderr diverged from the twin's recorded bytes" % name
    return returncode, stdout, stderr


CASES: list[tuple[str, dict[str, object]]] = [
    ("caller-pre-checks", {"files": {CALLER_REL: GUARDED}}),
    ("caller-passes-literal", {"files": {".ci/scripts/release/x.sh": LITERAL}}),
    ("the-2026-09-06-defect", {"files": {CALLER_REL: UNGUARDED}}),
    ("unguarded-in-a-workflow", {"files": {".github/workflows/r.yml": UNGUARDED}}),
    ("rail-removed", {"files": {CALLER_REL: GUARDED}, "rail": False}),
    ("no-call-site-is-vacuous", {"files": {}}),
    (
        "a-comment-is-not-a-call-site",
        {"files": {".ci/scripts/release/d.sh": '# cleanup-staging.sh --tag "$X" would fail\n'}},
    ),
    (
        "unguarded-py-caller-is-found-and-fails",
        {"files": {".ci/scripts/release/x.py": UNGUARDED_PY}},
    ),
    (
        "a-py-mention-outside-ci-scripts-is-not-a-call-site--still-vacuous",
        {"files": {".ci/rediacc_ci/quality/noise.py": UNGUARDED_PY}},
    ),
    # `grep -c` counts LINES and the twin wants exactly "1". Carried, not fixed.
    ("a-duplicated-rail", {"files": {CALLER_REL: GUARDED}, "extra_rail": True}),
    ("a-missing-subject", {"files": {CALLER_REL: GUARDED}, "drop_subject": True}),
    # A caller named `a:b.sh` collapses to `.../release/a` under `${hit%%:*}` on both sides.
    ("a-colon-in-a-caller-path", {"files": {".ci/scripts/release/a:b.sh": UNGUARDED}}),
]

EXPECTED_EXIT = {
    "caller-pre-checks": 0,
    "caller-passes-literal": 0,
    "the-2026-09-06-defect": 1,
    "unguarded-in-a-workflow": 1,
    "rail-removed": 1,
    "no-call-site-is-vacuous": 1,
    "a-comment-is-not-a-call-site": 1,
    "unguarded-py-caller-is-found-and-fails": 1,
    "a-py-mention-outside-ci-scripts-is-not-a-call-site--still-vacuous": 1,
    "a-duplicated-rail": 1,
    "a-missing-subject": 1,
    "a-colon-in-a-caller-path": 1,
}

# The one case whose stderr carries a line the port never emits. The twin handed the truncated path to `grep -qE`, which printed `No such file or directory` and exited non-zero; that error IS the evidence the twin did not read the file either, and the port reaches the same verdict through `try/except OSError`.
COLON_NOISE = ("→", "grep:")


@pytest.mark.parametrize(("name", "kwargs"), CASES, ids=[c[0] for c in CASES])
def test_port_matches_the_twins_recorded_output(
    tmp_path: pathlib.Path, name: str, kwargs: dict[str, object]
) -> None:
    root = build(tmp_path, **kwargs)  # type: ignore[arg-type]
    noise = COLON_NOISE if name == "a-colon-in-a-caller-path" else NOISE
    returncode, _, _ = compare(root, name, noise=noise)
    assert returncode == EXPECTED_EXIT[name], "the recorded verdict moved"


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, {name for name, _ in CASES})


def test_the_green_case_is_not_vacuously_equal() -> None:
    """Two implementations that both print nothing agree about nothing."""
    green = split_golden(frozen.read(SLUG, "caller-pre-checks"))[1]
    red = split_golden(frozen.read(SLUG, "the-2026-09-06-defect"))[1]
    assert green != red
    assert "ok    " in green


def test_the_duplicated_rail_reason_is_carried_not_fixed(tmp_path: pathlib.Path) -> None:
    """`grep -c` counts LINES, so two rails is not "at least one"."""
    recorded = frozen.read(SLUG, "a-duplicated-rail")
    assert "(got '2' want '1')" in recorded
    root = build(tmp_path, {CALLER_REL: GUARDED}, extra_rail=True)
    assert "(got '2' want '1')" in run_port(root)[2]


def test_a_missing_subject_refuses_rather_than_ruling(tmp_path: pathlib.Path) -> None:
    recorded = frozen.read(SLUG, "a-missing-subject")
    assert "nothing was verified" in recorded
    root = build(tmp_path, {CALLER_REL: GUARDED}, drop_subject=True)
    assert "nothing was verified" in run_port(root)[2]


def test_a_colon_in_a_caller_path_yields_a_verdict_rather_than_a_traceback(
    tmp_path: pathlib.Path,
) -> None:
    """A truncated path must fail its control, not raise out of main().

    `${hit%%:*}` splits the grep hit at its FIRST colon, so a caller named `a:b.sh` collapses to `.../release/a` on both sides. The twin handed that to `grep -qE`, which printed `No such file or directory`, exited non-zero, left `guarded` at 0 and still reached a verdict.

    This port called `read_text` on it and died with an uncaught FileNotFoundError: the same exit status by accident, no verdict, and a stack trace where the twin printed a control. Measured 2026-09-06; the `try/except OSError` in `main` is what this pins.
    """
    root = build(tmp_path, {".ci/scripts/release/a:b.sh": UNGUARDED})
    _, _, stderr = compare(root, "a-colon-in-a-caller-path", noise=COLON_NOISE)
    assert "Traceback (most recent call last)" not in stderr
    fail_line = ".ci/scripts/release/a guards its call against a non-staging tag (got '0' want '1')"
    assert fail_line in stderr
    assert fail_line in frozen.read(SLUG, "a-colon-in-a-caller-path")


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

    Scanning ALL of `.ci` for `.py` (a literal reading of agent/PLAN-w7p4w-docker-cutover.md §3's "add `--include='*.py'`") turned 1 real call site into 18 at widening time: `.ci/rediacc_ci` is this package's own implementation and tests tree, full of self-referential mentions of this exact needle.

    This pins the fix: a `.py` file under `.ci/scripts` is read, the SAME needle under `.ci/rediacc_ci` is not.
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


def test_planted_defect_is_caught_by_the_goldens(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Let the comment arm through as a call site.

    Dropping the prose filter is exactly the simplification a reader would make on sight, and it turns the vacuous `a-comment-is-not-a-call-site` tree into one that looks like it holds a guarded caller. The mutation is written to a throwaway file; the tracked port is never touched.
    """
    source = PORT.read_text(encoding="utf-8")
    anchor = 'COMMENT_HIT_RE = re.compile(r":[0-9]+:[ \\t\\n\\r\\f\\v]*#")\n'
    assert source.count(anchor) == 1, "the plant's anchor moved"
    broken_src = source.replace(anchor, 'COMMENT_HIT_RE = re.compile(r"(?!x)x")\n')
    assert broken_src != source

    root = build(
        tmp_path, {".ci/scripts/release/d.sh": '# cleanup-staging.sh --tag "$X" would fail\n'}
    )
    broken = tmp_path / "staging_tag_guard_broken.py"
    broken.write_text(broken_src, encoding="utf-8")
    with pytest.raises(AssertionError):
        compare(root, "a-comment-is-not-a-call-site", port=broken)
    # And the real, unmutated file still agrees against the same fixture.
    compare(root, "a-comment-is-not-a-call-site")
    assert PORT.read_text(encoding="utf-8") == source


def test_selftest_passes() -> None:
    assert gate.selftest() == 0

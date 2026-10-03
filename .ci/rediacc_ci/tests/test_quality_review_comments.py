"""`rediacc_ci.quality.review_comments`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-review-comments.sh` over a specimen with a stubbed `gh` on PATH, stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. Same recipe as the committed ledger, `.ci/shadow/w7p2-review-comments.observations.jsonl`. The twin has now been deleted and every case that
executed it compares against `goldens/review-comments/`, which holds the twin's OWN recorded output, captured from the tracked script on its last day in the tree. The provenance header of each golden carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed those bytes.

THE STUB DISPATCHES ON `$2`, THE ENDPOINT, and that is a scar. `gh_json` calls `gh api <endpoint> --paginate`, so the endpoint is `$2`; the first version of this fixture keyed on `$3`, which is `--paginate`, and therefore failed EVERY call. Both implementations then failed identically, byte for byte, over six specimens, and the differential scored EQUIVALENT each time. What refused
it was the comparator's distinct-fingerprint rule: six trees, one finding set, "that is one observation re-shaded". A stub that answers nothing is rule 2's both-empty trap in disguise, and a RECORDING of nothing is the same trap with the stub no longer around to blame, so the control that proves the clean case reached the SUCCESS path now reads the golden.

TWO PORT BUGS WERE FOUND BY THIS DIFFERENTIAL ONCE THE STUB WORKED, and both are one character wide:

  * `gh_json` returns `$(gh ...)`, and COMMAND SUBSTITUTION STRIPS TRAILING
    NEWLINES. The twin then compares the result against the literal `"[]"`. A port
    returning `"[]\\n"` takes the other branch and prints "All 0 inline review
    comments have been addressed" where the twin prints "No inline review comments
    found".
  * `jq -r '.body' | tr '\\n' ' '` turns jq's OWN terminating newline into a space,
    so the summary excerpt ends with a space before the `...`. A port that
    translated only the body's internal newlines was one character short on every
    summary.

Neither is visible by reading, both are in the recorded bytes, and the second is what the planted control below re-breaks.
"""

import json
import pathlib
import shutil

import pytest

from rediacc_ci.quality import review_comments as gate
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen
from rediacc_ci.well_known import GH_REPO

SLUG = "review-comments"
MODULE = "review_comments"

ENV_PREFIX = "PR_NUMBER=42 GH_TOKEN=t GITHUB_REPOSITORY=" + GH_REPO + ' PATH="$PWD/fxbin:$PATH"'

GH_STUB = """#!/bin/bash
D="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/fxdata"
case "$2" in
  */pulls/*)  cat "$D/inline.json"  2>/dev/null || exit 1; exit 0 ;;
  */issues/*) cat "$D/issues.json"  2>/dev/null || exit 1; exit 0 ;;
esac
exit 1
"""

BOT = {"login": "github-actions[bot]"}
HUMAN = {"login": "muhammed"}
LONG = "y" * 250
FENCE = "x ```json:review-findings\n[]"
SUMMARY = {"id": 5189236393, "user": BOT, "created_at": "2026-08-05T10:00:00Z", "body": FENCE}


def build(tmp_path: pathlib.Path, inline: list[dict], issues: list[dict]) -> pathlib.Path:
    """The fixture tree the twin was recorded over, minus the twin itself."""
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    for rel in (".ci/rediacc_ci/quality", "fxbin", "fxdata"):
        (root / rel).mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "log.py", "paths.py", "well_known.py", "controls.py"):
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    (root / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        src / ".ci" / "config" / "well-known.env", root / ".ci" / "config" / "well-known.env"
    )
    shutil.copy2(
        src / ".ci" / "config" / "well-known.generated.sh",
        root / ".ci" / "config" / "well-known.generated.sh",
    )
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    (root / "fxbin" / "gh").write_text(GH_STUB, encoding="utf-8")
    (root / "fxbin" / "gh").chmod(0o755)
    (root / "fxdata" / "inline.json").write_text(json.dumps(inline), encoding="utf-8")
    (root / "fxdata" / "issues.json").write_text(json.dumps(issues), encoding="utf-8")
    return root


def run_port(root: pathlib.Path) -> tuple[int, str, str]:
    return diff.bash_streams(
        "%s PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s"
        % (ENV_PREFIX, MODULE),
        cwd=str(root),
    )


def split_golden(text: str) -> tuple[int, str, str]:
    """A recorded twin render, back into its three parts."""
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def compare(root: pathlib.Path, name: str) -> tuple[int, str, str]:
    """Byte equality on BOTH streams against the twin's recorded bytes."""
    want_exit, want_out, want_err = split_golden(frozen.read(SLUG, name))
    returncode, stdout, stderr = run_port(root)
    stdout = frozen.mask_root(stdout, root)
    stderr = frozen.mask_root(stderr, root)
    assert returncode == want_exit, "%s: the twin exited %d, the port %d" % (
        name,
        want_exit,
        returncode,
    )
    assert stdout == want_out, "%s: stdout diverged from the twin's recorded bytes" % name
    assert stderr == want_err, "%s: stderr diverged from the twin's recorded bytes" % name
    return returncode, stdout, stderr


def inline_thread(ident: int, body: str) -> dict:
    return {
        "id": ident,
        "in_reply_to_id": None,
        "path": "src/a.ts",
        "line": 12,
        "user": HUMAN,
        "body": body,
    }


CASES = [
    # THE NEGATIVE HALF, first: nothing to answer on either surface.
    ("an-empty-pr-is-silent-on-both-surfaces", [], [], 0),
    ("an-unreplied-inline-comment-blocks", [inline_thread(1, "please rename this")], [], 1),
    (
        "a-substantive-inline-reply-clears-it",
        [
            inline_thread(1, "please rename this"),
            {
                "id": 2,
                "in_reply_to_id": 1,
                "user": HUMAN,
                "body": "Renamed to validateInput and added the null check",
            },
        ],
        [],
        0,
    ),
    (
        # THE LOW-EFFORT CATEGORY IS SEPARATE, with its own count and its own third line. Collapsing it into "unreplied" would change both printed counts.
        "a-low-effort-inline-reply-is-its-own-category",
        [
            inline_thread(1, "please rename this"),
            {"id": 2, "in_reply_to_id": 1, "user": HUMAN, "body": "Done"},
        ],
        [],
        1,
    ),
    ("an-unanswered-top-level-summary-blocks", [], [SUMMARY], 1),
    (
        # CLAUSE (a) ON SURFACE 2. The pipeline's own marker landed 14 seconds after the summary on PR #551 and is long enough to clear every substance test.
        "the-reviewers-own-later-comment-does-not-answer-its-own-summary",
        [],
        [
            SUMMARY,
            {"id": 5189238817, "user": BOT, "created_at": "2026-08-05T10:00:14Z", "body": LONG},
        ],
        1,
    ),
    (
        "a-long-form-answer-from-another-author-clears-the-summary",
        [],
        [SUMMARY, {"id": 9, "user": HUMAN, "created_at": "2026-08-05T11:00:00Z", "body": LONG}],
        0,
    ),
    (
        # BOOKKEEPING IS STATE, NOT A VERDICT. Blocking on it would block every PR the pipeline has ever touched.
        "a-bookkeeping-marker-comment-is-not-a-summary",
        [],
        [
            {
                "id": 7,
                "user": BOT,
                "created_at": "2026-08-05T10:00:00Z",
                "body": "<!-- claude-reviewed: abc -->",
            }
        ],
        0,
    ),
    (
        "a-verdict-heading-with-no-fence-is-still-a-summary",
        [],
        [dict(SUMMARY, body="## Review verdict: approve with one correctness finding to fix")],
        1,
    ),
    (
        "both-surfaces-can-fail-at-once",
        [inline_thread(1, "please rename this")],
        [SUMMARY],
        1,
    ),
    (
        # THE EXCERPT CASE, promoted to a recorded case of its own: the trailing space it pins is a property of the twin's bytes, so it has to be one of them.
        "a-summary-excerpt-keeps-the-trailing-space",
        [],
        [dict(SUMMARY, body="## Review verdict: approve")],
        1,
    ),
]


@pytest.mark.parametrize(
    ("name", "inline", "issues", "want_exit"),
    CASES,
    ids=[c[0] for c in CASES],
)
def test_port_matches_the_twins_recorded_output(tmp_path, name, inline, issues, want_exit):
    """Byte equality on BOTH streams, plus the exit code the case expects."""
    root = build(tmp_path, inline, issues)
    returncode, _stdout, _stderr = compare(root, name)
    assert returncode == want_exit, "the recorded verdict moved"


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, {name for name, _i, _s, _e in CASES})


def test_the_stub_actually_answered(tmp_path):
    """The control on the control. See the module docstring for what it cost.

    Six specimens once agreed perfectly because the stub failed every call. The twin's RECORDED clean case is asserted to have reached the SUCCESS path, and the port is asserted to reach it today, so a stub that stops answering reds this test instead of quietly turning every case above into a comparison of two identical error messages.
    """
    _rc, recorded_out, recorded_err = split_golden(
        frozen.read(SLUG, "an-empty-pr-is-silent-on-both-surfaces")
    )
    assert "gh failed after 3 attempts" not in recorded_err
    assert "No inline review comments found - OK" in recorded_out
    assert "No top-level review summary found - OK" in recorded_out
    root = build(tmp_path, [], [])
    code, out, _err = run_port(root)
    assert code == 0
    assert "No inline review comments found - OK" in out


def test_an_empty_list_is_compared_as_the_raw_string(tmp_path):
    """`"$COMMENTS" == "[]"`, on gh's stdout with its trailing newline stripped.

    The port returned `"[]\\n"` and therefore printed "All 0 inline review comments have been addressed with substantive replies - OK" where the twin printed "No inline review comments found - OK". Same verdict, different bytes, and nothing but a byte comparison would have noticed.
    """
    recorded = split_golden(frozen.read(SLUG, "an-empty-pr-is-silent-on-both-surfaces"))[1]
    assert "No inline review comments found - OK" in recorded
    assert "All 0 inline review comments" not in recorded
    compare(build(tmp_path, [], []), "an-empty-pr-is-silent-on-both-surfaces")


def test_the_summary_excerpt_keeps_the_trailing_space(tmp_path):
    """`jq -r | tr '\\n' ' '` turns jq's OWN terminating newline into a space.

    So the excerpt ends `... "` rather than `..."`, and a port translating only the body's internal newlines is one character short on every summary.
    """
    recorded = split_golden(frozen.read(SLUG, "a-summary-excerpt-keeps-the-trailing-space"))[1]
    assert '"## Review verdict: approve ..."' in recorded
    root = build(tmp_path, [], [dict(SUMMARY, body="## Review verdict: approve")])
    compare(root, "a-summary-excerpt-keeps-the-trailing-space")


def test_planted_defect_is_caught_by_the_goldens(tmp_path):
    """THE CONTROL ON THE GOLDENS. Drop the synthetic newline before the `tr`.

    Translating only the body's INTERNAL newlines is the reading a careful person arrives at, and it costs the excerpt its one trailing space, which is the whole of the second bug the module docstring records. The mutation is applied to the module COPY inside the throwaway fixture; the tracked port is never touched.
    """
    tracked = pathlib.Path(diff.repo()) / ".ci" / "rediacc_ci" / "quality" / ("%s.py" % MODULE)
    before = tracked.read_text(encoding="utf-8")
    anchor = 'clip(((summary.get("body") or "") + "\\n").replace("\\n", " "), 120)'
    assert before.count(anchor) == 1, "the plant's anchor moved"

    body = [], [dict(SUMMARY, body="## Review verdict: approve")]
    root = build(tmp_path, *body)
    copy = root / ".ci" / "rediacc_ci" / "quality" / ("%s.py" % MODULE)
    copy.write_text(
        copy.read_text(encoding="utf-8").replace(
            anchor, 'clip((summary.get("body") or "").replace("\\n", " "), 120)'
        ),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError):
        compare(root, "a-summary-excerpt-keeps-the-trailing-space")

    # And the real, unmutated module still agrees against the same fixture.
    clean = build(tmp_path / "clean", *body)
    compare(clean, "a-summary-excerpt-keeps-the-trailing-space")
    assert tracked.read_text(encoding="utf-8") == before


def test_the_two_floors_are_different_and_both_are_load_bearing():
    """10 inline, 30 for the summary. Unifying them changes one gate silently."""
    assert gate.INLINE_MIN_CHARS == 10
    assert gate.SUMMARY_MIN_CHARS == 30
    assert gate.is_low_effort_reply("x" * 10) is False
    assert gate.is_low_effort_reply("x" * 10, gate.SUMMARY_MIN_CHARS) is True


def test_the_summary_constants_keep_their_values():
    """The sibling report-replies gate these once had to agree with was retired on 2026-10-02; the values stay pinned."""
    assert gate.SUMMARY_MIN_CHARS == 30
    assert gate.SUMMARY_LONGFORM_CHARS == 200


def test_clip_cuts_bytes_like_head_c():
    """`head -c 100` and `${var:0:120}` are byte operations under LC_ALL=C."""
    assert gate.clip("a" * 150, 100) == "a" * 100
    assert gate.clip("short", 100) == "short"


def test_selftest_exits_zero_and_prints_a_count():
    """Exit 0 with zero PASS lines is a failure, so the count is asserted too."""
    code, out, err = diff.bash_streams(
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.ci python3 -m rediacc_ci.quality.%s --selftest"
        % MODULE
    )
    assert code == 0, err
    assert "control(s) passed" in out
    assert int(out.split(" control(s)")[0].strip()) >= 24


# THE EMPTY-FINDINGS RULE (operator ruling 2026-10-03, PLAN-github-pr-review-restore GR6). A summary whose line-anchored `json:review-findings` fence parses to `[]` has nothing to answer, so it needs no reply. Every other shape keeps the reply rule: one finding, an unparseable fence and an absent fence all still block. These cases run against the fixture rather than a golden, because the twin
# never had the rule and so never recorded these bytes.
EMPTY_FENCE = "## Review verdict: approve\n\nNo findings.\n\n```json:review-findings\n[]\n```\n"
ONE_FENCE = (
    "## Review verdict: fix one\n\n```json:review-findings\n"
    '[{"path": "a.py", "line": 3, "severity": "major", "body": "off by one"}]\n```\n'
)
BROKEN_FENCE = "## Review verdict: approve\n\n```json:review-findings\n[\n```\n"
PER_COMMIT = (
    "<!-- per-commit-reviews: 1003-1 -->\n## Review verdict: per-commit records\n\n"
    '```json:review-findings\n[{"path": "a.py", "line": 1, "body": "x"}]\n```\n'
)


@pytest.mark.parametrize(
    ("label", "body", "want_exit", "want_line"),
    [
        (
            "an-empty-findings-array-needs-no-reply",
            EMPTY_FENCE,
            0,
            "carries an empty findings array, nothing to answer - OK",
        ),
        ("a-one-entry-findings-array-still-blocks", ONE_FENCE, 1, "UNANSWERED REVIEW SUMMARY (1):"),
        (
            "an-unparseable-fence-fails-closed",
            BROKEN_FENCE,
            1,
            "UNANSWERED REVIEW SUMMARY (1):",
        ),
    ],
)
def test_the_empty_findings_rule_end_to_end(tmp_path, label, body, want_exit, want_line):
    """The real module over the stubbed gh, with no reply posted in any case."""
    root = build(tmp_path, [], [dict(SUMMARY, body=body)])
    code, out, err = run_port(root)
    assert code == want_exit, "%s: exit %d\n%s\n%s" % (label, code, out, err)
    assert want_line in out, label


def test_a_per_commit_reviews_comment_is_never_a_summary(tmp_path):
    """The per-commit review mirror opens `<!-- per-commit-reviews:` and may carry both summary keys, yet it is bookkeeping, never a verdict awaiting an answer."""
    comment = dict(SUMMARY, body=PER_COMMIT)
    assert gate.newest_summary([comment]) is None
    code, out, _err = run_port(build(tmp_path, [], [comment]))
    assert code == 0
    assert "No top-level review summary found - OK" in out


def test_findings_fence_reader():
    """`[]` is empty; one entry, an object, broken JSON, an unanchored or unclosed fence and no fence at all are not."""
    assert gate.findings_fence_is_empty(EMPTY_FENCE) is True
    assert gate.findings_fence_is_empty("```json:review-findings\n  [ ]\n```") is True
    assert gate.findings_fence_is_empty(ONE_FENCE) is False
    assert gate.findings_fence_is_empty(BROKEN_FENCE) is False
    assert gate.findings_fence_is_empty("```json:review-findings\n{}\n```") is False
    assert gate.findings_fence_is_empty("## Review verdict: approve") is False
    # The legacy fixture body: opener not at line start, no closer. Fail closed, which is why the recorded goldens keep their verdicts.
    assert gate.findings_fence_is_empty(FENCE) is False
    assert gate.findings_fence_is_empty("```json:review-findings\n[]\n") is False
    # A pr-labels fence after the findings fence does not leak into the findings array.
    assert gate.findings_fence_is_empty(EMPTY_FENCE + '\n```json:pr-labels\n{"bump": "patch"}\n```\n')
    # LAST opener wins, matching the producer's scanner.
    assert gate.findings_fence_is_empty(ONE_FENCE + EMPTY_FENCE) is True
    assert gate.findings_fence_is_empty(EMPTY_FENCE + ONE_FENCE) is False

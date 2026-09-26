"""`rediacc_ci.quality.announce_gate_skips`, driven directly against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/announce-gate-skips.sh` over each case below and its bytes were compared against the port's, byte-identical on every path but one.

THE K=5 LEDGER IS `.ci/shadow/w7p6-announce-gate-skips.observations.jsonl`, recorded over five distinct trees against a disposable scratch git repo built OUTSIDE this checkout: this repo's working tree is not clean and `shadow-gate.ts --record` refuses a dirty tree.

The twin has now been deleted, and every case compares against `goldens/announce-gate-skips/`, which holds the twin's OWN recorded output. The provenance header of each golden carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed those bytes.

THE ONE EXCEPTION IS NAMED IN THE PORT'S DOCSTRING: the `$# -lt 2` usage line interpolates `$0`, which is the program path the shell was handed, and a module invoked as `python3 -m ...` cannot have the same one. `mask_program` replaces that single token on both sides so the rest of the line is still compared byte for byte rather than being dropped from the comparison altogether.

THE STEP SUMMARY IS RECORDED AS A FOURTH SECTION, not inferred from stdout. It is the only output a human reads on a GitHub run summary page, it is APPENDED rather than written, and nothing on stdout would reveal a port that wrote the header and forgot the bullet list. `(absent)` in that section is a recorded observation in its own right: hard mode must create no file at all.

BOTH DIRECTIONS ARE COVERED, which for this script means the two REFUSALS as much as the two working modes: an unrecognised `GATE_SKIP_MODE` must exit 2 (it is the only place a typo'd mode string is ever reported, since the step `if:` treats it as "run" silently), and fewer than two arguments must exit 2 because an announcer with nothing to announce is a miswired announcer.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

SLUG = "announce-gate-skips"
MODULE = "rediacc_ci.quality.announce_gate_skips"
PORT = pathlib.Path(diff.repo()) / ".ci" / "rediacc_ci" / "quality" / "announce_gate_skips.py"

PROGRAM_RE = re.compile(r"GATE_SKIP_MODE=hard\|skip \S+ <label>")

ABSENT = "(absent)\n"
EARLIER = "### An earlier step wrote this\n"


def mask_program(text: str) -> str:
    return PROGRAM_RE.sub("GATE_SKIP_MODE=hard|skip <prog> <label>", text)


def render(returncode: int, stdout: str, stderr: str, summary: str) -> str:
    return "%s--- summary ---\n%s" % (
        frozen.render(returncode, mask_program(stdout), mask_program(stderr)),
        summary,
    )


def run_port(
    tmp_path: pathlib.Path,
    args: list[str],
    mode: str | None = None,
    summary: str | None = None,
    port: str | None = None,
) -> str:
    """Drive the port over one case and return the recorded shape."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    extra: dict[str, str] = {}
    if mode is not None:
        extra["GATE_SKIP_MODE"] = mode
    summary_path = tmp_path / "summary.md"
    if summary is not None:
        extra["GITHUB_STEP_SUMMARY"] = str(summary_path)
        if summary:
            summary_path.write_text(summary, encoding="utf-8")
    env = diff.env_for(**extra, PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    command = "python3 -m %s" % MODULE if port is None else "python3 %s" % port
    arg_str = " ".join("'%s'" % a for a in args)
    returncode, stdout, stderr = diff.bash_streams(
        "%s %s" % (command, arg_str), env=env, timeout=30
    )
    written = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ABSENT
    return render(returncode, stdout, stderr, written)


CASES: list[tuple[str, dict[str, object]]] = [
    (
        "hard-mode-names-the-enforced-count",
        {
            "args": ["no-media-quality", "check:ci-tutorial-casts", "check:ci-tutorial-parity"],
            "mode": "hard",
        },
    ),
    # `mode=None` means the variable is genuinely absent from the environment, which `diff.env_for` supports and `env["X"] = ""` cannot express. A wiring break must never read as "gates removed".
    ("unset-mode-is-hard-never-skip", {"args": ["no-media-quality", "check:ci-i18n-media"]}),
    # `${GATE_SKIP_MODE:-hard}` falls back on EMPTY, not merely on unset, so a workflow that computes the mode into an empty string still enforces.
    (
        "empty-mode-string-is-also-hard",
        {"args": ["no-media-quality", "check:ci-i18n-media"], "mode": ""},
    ),
    (
        "skip-mode-warns-and-names-every-gate",
        {
            "args": ["no-media-quality", "check:ci-tutorial-casts", "check:ci-tutorial-parity"],
            "mode": "skip",
        },
    ),
    (
        "skip-mode-writes-the-step-summary",
        {
            "args": ["no-media-quality", "check:ci-tutorial-casts", "check:ci-i18n-media"],
            "mode": "skip",
            "summary": "",
        },
    ),
    # GITHUB_STEP_SUMMARY accumulates across steps. A port opening the file with `w` would silently delete every earlier step's contribution, and nothing on stdout would show it.
    (
        "the-step-summary-is-appended-not-truncated",
        {"args": ["no-media-quality", "check:ci-i18n-media"], "mode": "skip", "summary": EARLIER},
    ),
    (
        "hard-mode-writes-no-step-summary",
        {"args": ["no-media-quality", "check:ci-i18n-media"], "mode": "hard", "summary": ""},
    ),
    # `[ -n "${GITHUB_STEP_SUMMARY:-}" ]` guards the block, so running outside Actions must not fail.
    (
        "skip-mode-without-a-summary-file-still-exits-zero",
        {"args": ["no-media-quality", "check:ci-i18n-media"], "mode": "skip"},
    ),
    # The ONLY place a typo'd mode string is ever reported. The step `if:` treats any unrecognised value as "run", which is fail-closed and silent.
    (
        "unknown-mode-refuses-with-exit-two",
        {"args": ["no-media-quality", "check:ci-i18n-media"], "mode": "Hard"},
    ),
    # One argument is a label with nothing behind it, and an announcer with nothing to announce is miswired.
    ("zero-gate-names-is-a-refusal", {"args": ["no-media-quality"], "mode": "skip"}),
    ("no-arguments-at-all-is-the-same-refusal", {"args": [], "mode": "hard"}),
    # Order matters and is easy to get wrong: the twin checks `$#` BEFORE it validates the mode, so a one-argument call under a bogus mode reports the usage error, not the mode error.
    (
        "the-usage-refusal-outranks-an-unknown-mode",
        {"args": ["no-media-quality"], "mode": "nonsense"},
    ),
    # `$*` joins with the first character of IFS, a plain space, and the twin never re-quotes the elements. A gate name that itself contains a space is therefore indistinguishable from two gates in the printed line, reproduced rather than corrected.
    (
        "gate-names-with-spaces-join-the-way-dollar-star-does",
        {"args": ["lbl", "a b", "c"], "mode": "skip"},
    ),
]


@pytest.mark.parametrize(("name", "kwargs"), CASES, ids=[c[0] for c in CASES])
def test_port_matches_the_twins_recorded_output(
    tmp_path: pathlib.Path, name: str, kwargs: dict[str, object]
) -> None:
    actual = run_port(tmp_path, **kwargs)  # type: ignore[arg-type]
    expected = frozen.read(SLUG, name)
    assert actual == expected, "%s diverged from the twin's recorded bytes:\n%s\n%s" % (
        name,
        expected,
        actual,
    )


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, {name for name, _ in CASES})


def test_the_recorded_bytes_are_the_announcement_and_not_a_banner() -> None:
    """ANTI-VACUITY on the recording: an announcer that printed nothing would compare equal to a port that printed nothing, and the two would agree about nothing."""
    hard = frozen.read(SLUG, "hard-mode-names-the-enforced-count")
    skip = frozen.read(SLUG, "skip-mode-warns-and-names-every-gate")
    assert hard != skip
    assert "gate-skips: none. 2 gate(s) enforced in this job " in hard
    assert "::warning::" not in hard, "a green run must not carry a skip warning"
    assert "::warning::label 'no-media-quality' removed 2 gate(s) from this job: " in skip
    assert "check:ci-tutorial-casts check:ci-tutorial-parity" in skip

    summary = frozen.read(SLUG, "skip-mode-writes-the-step-summary")
    assert "### Gates skipped by `no-media-quality` (2 in this job)" in summary
    assert "- `check:ci-tutorial-casts` -- did NOT run" in summary
    assert ABSENT in frozen.read(SLUG, "hard-mode-writes-no-step-summary")
    assert frozen.read(SLUG, "the-step-summary-is-appended-not-truncated").count(EARLIER) == 1

    usage = frozen.read(SLUG, "zero-gate-names-is-a-refusal")
    assert "exit: 2\n" in usage
    assert "usage: GATE_SKIP_MODE=hard|skip <prog> <label> <gate...>\n" in usage
    assert "unknown GATE_SKIP_MODE" not in frozen.read(
        SLUG, "the-usage-refusal-outranks-an-unknown-mode"
    )
    assert "unknown GATE_SKIP_MODE 'Hard' (expected hard|skip)" in frozen.read(
        SLUG, "unknown-mode-refuses-with-exit-two"
    )


def test_planted_defect_is_caught_by_the_goldens(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Open the step summary for writing instead of appending.

    GITHUB_STEP_SUMMARY accumulates across steps, and `w` is the mode a reader reaches for without thinking about it. It leaves stdout untouched, so only the recorded fourth section can see it. The mutation is written to a throwaway file; the tracked port is never touched.
    """
    source = PORT.read_text(encoding="utf-8")
    anchor = '"a", encoding="utf-8"'
    assert source.count(anchor) == 1, "the plant's anchor moved"
    broken_src = source.replace(anchor, '"w", encoding="utf-8"')
    assert broken_src != source

    broken = tmp_path / "announce_gate_skips_broken.py"
    broken.write_text(broken_src, encoding="utf-8")
    name = "the-step-summary-is-appended-not-truncated"
    kwargs = dict(next(k for n, k in CASES if n == name))
    expected = frozen.read(SLUG, name)
    assert run_port(tmp_path / "broken", port=str(broken), **kwargs) != expected, (
        "PLANT DID NOT FIRE: the goldens cannot see an earlier step's summary being deleted"
    )
    # And the real, unmutated file still agrees against the same case.
    assert run_port(tmp_path / "real", **kwargs) == expected
    assert PORT.read_text(encoding="utf-8") == source

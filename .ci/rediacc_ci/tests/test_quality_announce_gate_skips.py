"""`rediacc_ci.quality.announce_gate_skips` against its bash twin.

BYTE-IDENTICAL ON EVERY PATH BUT ONE, and the exception is named in the port's docstring: the `$# -lt 2` usage line interpolates `$0`, which is the program path the shell was handed, and a module invoked as `python3 -m ...` cannot have the same one. `_mask_program` replaces that single token on both sides so the rest of the line is still compared byte for byte rather than being
dropped from the comparison altogether.

THE STEP SUMMARY IS COMPARED AS A FILE, not inferred from stdout. It is the only output a human reads on a GitHub run summary page, it is APPENDED rather than written, and nothing on stdout would reveal a port that wrote the header and forgot the bullet list. Each side gets its own file for the same reason `test_signal_create_complete.py` gives each side its own output directory.

BOTH DIRECTIONS ARE COVERED, which for this script means the two REFUSALS as much as the two working modes: an unrecognised `GATE_SKIP_MODE` must exit 2 (it is the only place a typo'd mode string is ever reported, since the step `if:` treats it as "run" silently), and fewer than two arguments must exit 2 because an announcer with nothing to announce is a miswired announcer.

K=5 LEDGER: `.ci/shadow/w7p6-announce-gate-skips.observations.jsonl`, recorded
against a disposable scratch git repo built OUTSIDE this checkout (this repo's working tree is not clean and `shadow-gate.ts --record` refuses a dirty tree).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:
    import pathlib

TWIN = ".ci/scripts/quality/announce-gate-skips.sh"
MODULE = "rediacc_ci.quality.announce_gate_skips"

_PROGRAM = re.compile(r"GATE_SKIP_MODE=hard\|skip \S+ <label>")


def _mask_program(text: str) -> str:
    return _PROGRAM.sub("GATE_SKIP_MODE=hard|skip <prog> <label>", text)


def run_both(
    args: list[str],
    *,
    mode: str | None = None,
    summary_old: pathlib.Path | None = None,
    summary_new: pathlib.Path | None = None,
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    extra: dict[str, str] = {}
    if mode is not None:
        extra["GATE_SKIP_MODE"] = mode
    arg_str = " ".join("'%s'" % a for a in args)
    old_env = diff.env_for(
        **extra, **({"GITHUB_STEP_SUMMARY": str(summary_old)} if summary_old else {})
    )
    new_env = diff.env_for(
        **extra,
        **({"GITHUB_STEP_SUMMARY": str(summary_new)} if summary_new else {}),
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    old = diff.bash_streams("bash %s %s" % (TWIN, arg_str), env=old_env, timeout=30)
    new = diff.bash_streams("python3 -m %s %s" % (MODULE, arg_str), env=new_env, timeout=30)
    return (
        (old[0], _mask_program(old[1]), _mask_program(old[2])),
        (new[0], _mask_program(new[1]), _mask_program(new[2])),
    )


def test_hard_mode_names_the_enforced_count() -> None:
    old, new = run_both(
        ["no-media-quality", "check:ci-tutorial-casts", "check:ci-tutorial-parity"], mode="hard"
    )
    assert old == (
        0,
        (
            "gate-skips: none. 2 gate(s) enforced in this job "
            "(label 'no-media-quality' not applied): "
            "check:ci-tutorial-casts check:ci-tutorial-parity\n"
        ),
        "",
    )
    assert new == old


def test_unset_mode_is_hard_never_skip() -> None:
    """A wiring break must never read as "gates removed". `mode=None` here
    means the variable is genuinely absent from the environment, which
    `diff.env_for` supports and `env["X"] = ""` cannot express."""
    old, new = run_both(["no-media-quality", "check:ci-i18n-media"], mode=None)
    assert old[0] == 0
    assert old[1].startswith("gate-skips: none. 1 gate(s) enforced")
    assert "::warning::" not in old[1]
    assert new == old


def test_empty_mode_string_is_also_hard() -> None:
    """`${GATE_SKIP_MODE:-hard}` falls back on EMPTY, not merely on unset, so
    a workflow that computes the mode into an empty string still enforces."""
    old, new = run_both(["no-media-quality", "check:ci-i18n-media"], mode="")
    assert old[0] == 0
    assert old[1].startswith("gate-skips: none. 1 gate(s) enforced")
    assert new == old


def test_skip_mode_warns_and_names_every_gate() -> None:
    old, new = run_both(
        ["no-media-quality", "check:ci-tutorial-casts", "check:ci-tutorial-parity"], mode="skip"
    )
    assert old == (
        0,
        (
            "::warning::label 'no-media-quality' removed 2 gate(s) from this job: "
            "check:ci-tutorial-casts check:ci-tutorial-parity\n"
            "gate-skips: 2 gate(s) NOT run in this job because the PR carries "
            "'no-media-quality': check:ci-tutorial-casts check:ci-tutorial-parity\n"
            "gate-skips: this is a temporary hold. Remove the label to restore them.\n"
        ),
        "",
    )
    assert new == old


def test_skip_mode_step_summary_is_byte_identical(tmp_path: pathlib.Path) -> None:
    summary_old = tmp_path / "summary-old.md"
    summary_new = tmp_path / "summary-new.md"
    old, new = run_both(
        ["no-media-quality", "check:ci-tutorial-casts", "check:ci-i18n-media"],
        mode="skip",
        summary_old=summary_old,
        summary_new=summary_new,
    )
    assert old[0] == 0
    assert new == old
    written = summary_old.read_text(encoding="utf-8")
    assert written == (
        "### Gates skipped by `no-media-quality` (2 in this job)\n"
        "\n"
        "- `check:ci-tutorial-casts` -- did NOT run\n"
        "- `check:ci-i18n-media` -- did NOT run\n"
        "\n"
        "These gates are held, not exempt. Remove the `no-media-quality` label as\n"
        "soon as the work it is waiting on lands, and let the run go red\n"
        "if the underlying defect is still there.\n"
        "See docs/agent-reference/ci-gates.md.\n"
    )
    assert summary_new.read_text(encoding="utf-8") == written


def test_step_summary_is_appended_not_truncated(tmp_path: pathlib.Path) -> None:
    """GITHUB_STEP_SUMMARY accumulates across steps. A port opening the file
    with `w` would silently delete every earlier step's contribution, and
    nothing on stdout would show it."""
    summary_old = tmp_path / "summary-old.md"
    summary_new = tmp_path / "summary-new.md"
    for path in (summary_old, summary_new):
        path.write_text("### An earlier step wrote this\n", encoding="utf-8")
    old, new = run_both(
        ["no-media-quality", "check:ci-i18n-media"],
        mode="skip",
        summary_old=summary_old,
        summary_new=summary_new,
    )
    assert old[0] == 0
    assert new == old
    written = summary_old.read_text(encoding="utf-8")
    assert written.startswith("### An earlier step wrote this\n### Gates skipped by")
    assert summary_new.read_text(encoding="utf-8") == written


def test_hard_mode_writes_no_step_summary(tmp_path: pathlib.Path) -> None:
    summary_old = tmp_path / "summary-old.md"
    summary_new = tmp_path / "summary-new.md"
    old, new = run_both(
        ["no-media-quality", "check:ci-i18n-media"],
        mode="hard",
        summary_old=summary_old,
        summary_new=summary_new,
    )
    assert old[0] == 0
    assert new == old
    assert not summary_old.exists()
    assert not summary_new.exists()


def test_skip_mode_without_a_summary_file_still_exits_zero() -> None:
    """`[ -n "${GITHUB_STEP_SUMMARY:-}" ]` guards the block, so running outside
    Actions must not fail."""
    old, new = run_both(["no-media-quality", "check:ci-i18n-media"], mode="skip")
    assert old[0] == 0
    assert old[2] == ""
    assert new == old


def test_unknown_mode_refuses_with_exit_two() -> None:
    """The ONLY place a typo'd mode string is ever reported. The step `if:` treats any unrecognised value as "run", which is fail-closed and silent."""
    old, new = run_both(["no-media-quality", "check:ci-i18n-media"], mode="Hard")
    assert old == (
        2,
        "",
        "announce-gate-skips: unknown GATE_SKIP_MODE 'Hard' (expected hard|skip)\n",
    )
    assert new == old


def test_zero_gate_names_is_a_refusal_not_a_clean_run() -> None:
    """The script's own anti-vacuity rule: one argument is a label with nothing behind it, and an announcer with nothing to announce is miswired."""
    old, new = run_both(["no-media-quality"], mode="skip")
    assert old[0] == 2
    assert old[1] == ""
    assert old[2] == "usage: GATE_SKIP_MODE=hard|skip <prog> <label> <gate...>\n"
    assert new == old


def test_no_arguments_at_all_is_the_same_refusal() -> None:
    old, new = run_both([], mode="hard")
    assert old[0] == 2
    assert old[2] == "usage: GATE_SKIP_MODE=hard|skip <prog> <label> <gate...>\n"
    assert new == old


def test_the_usage_refusal_outranks_an_unknown_mode() -> None:
    """Order matters and is easy to get wrong: the twin checks `$#` BEFORE it validates the mode, so a one-argument call under a bogus mode reports the usage error, not the mode error."""
    old, new = run_both(["no-media-quality"], mode="nonsense")
    assert old[0] == 2
    assert old[2].startswith("usage: GATE_SKIP_MODE=hard|skip")
    assert "unknown GATE_SKIP_MODE" not in old[2]
    assert new == old


def test_gate_names_with_spaces_join_the_way_dollar_star_does() -> None:
    """`$*` joins with the first character of IFS, a plain space, and the twin never re-quotes the elements. A gate name that itself contains a space is therefore indistinguishable from two gates in the printed line, on BOTH sides -- reproduced rather than corrected, because the announcement text is what the bash gate test greps."""
    old, new = run_both(["lbl", "a b", "c"], mode="skip")
    assert old[0] == 0
    assert "removed 2 gate(s) from this job: a b c\n" in old[1]
    assert new == old

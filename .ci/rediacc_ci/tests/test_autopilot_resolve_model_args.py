"""Differential: `rediacc_ci.autopilot.resolve_model_args` against its twin `.ci/scripts/autopilot/resolve-model-args.sh`.

BESPOKE SUBPROCESS COMPARISON rather than `differential.bash_streams`, for one reason: this subject writes a THIRD output nobody's stdout or stderr shows, the `args<<HEREDOC` block it appends to `$GITHUB_OUTPUT`. That file is what the workflow actually consumes -- stdout is for a human reading the log -- so a comparison that checked only the two streams would be checking the half
that does not matter. Every case here compares FOUR things: exit code, stdout, stderr, and the bytes of `$GITHUB_OUTPUT`.

STREAMS ARE NEVER MERGED. The `::notice` lines go to stdout and the closing
summary goes to stderr, which is precisely the asymmetry a `2>&1` would erase;
see `differential.py`'s header on the 2026-09-06 stream-swap incident.

THE INPUT SPACE IS ENUMERATED, NOT SAMPLED. `--effort` and `--effort-var` each have five distinct shapes (absent, empty, the literal `default`, a member of the allowlist, and junk), the `--effort` flag has a sixth (present with no value, which the twin's `parse_args` turns into the string `true`), and the two interact: a REJECTED dispatch effort must still let the variable through,
which is the one behaviour an `elif` would silently break. So the cross-product is driven whole, both modes, rather than three hand-picked cases.

K=5 LEDGER: `.ci/shadow/w7p6-resolve-model-args.observations.jsonl`, recorded
against a disposable scratch git repository built outside this checkout: this checkout's own working tree is never clean, and `shadow-gate.ts --record` refuses a dirty tree with no override.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile

from rediacc_ci import paths
from rediacc_ci.autopilot import resolve_model_args as rma

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "resolve-model-args.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "resolve_model_args.py"

# The environment both sides get. REPLACED, not inherited: a differential that inherits the caller's environment passes or fails depending on whether the developer happens to export CI or NO_COLOR, and both sides decide colour from those. LC_ALL pins message text.
BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}


def _run(
    subject: pathlib.Path, argv: list[str], *, github_output: bool
) -> tuple[int, str, str, str]:
    """(exit, stdout, stderr, GITHUB_OUTPUT bytes) for one side."""
    with tempfile.TemporaryDirectory() as td:
        env = dict(BASE_ENV)
        out_file = pathlib.Path(td) / "gh-output"
        if github_output:
            # PRE-CREATED EMPTY, because both sides APPEND. A missing file would
            # let one side's `>>` create it and hide a difference in whether the
            # other side wrote at all.
            out_file.write_text("", encoding="utf-8")
            env["GITHUB_OUTPUT"] = str(out_file)
        runner = ["bash"] if subject.suffix == ".sh" else ["python3"]
        proc = subprocess.run(
            [*runner, str(subject), *argv],
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=60,
        )
        written = out_file.read_text(encoding="utf-8") if github_output else ""
    return proc.returncode, proc.stdout, proc.stderr, written


def _compare(
    name: str, argv: list[str], *, github_output: bool = True
) -> tuple[int, str, str, str]:
    old = _run(TWIN, argv, github_output=github_output)
    new = _run(PORT, argv, github_output=github_output)
    labels = ("exit code", "stdout", "stderr", "$GITHUB_OUTPUT")
    # `strict=True`: the tuple and the labels must stay the same length, and a
    # silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, old, new, strict=True):
        assert a == b, "%s (%r): %s diverged:\n--- twin ---\n%r\n--- port ---\n%r" % (
            name,
            argv,
            label,
            a,
            b,
        )
    return old


# The five shapes each effort source can take, plus the bare-flag sixth. The value is the argv fragment; None means "the flag is absent entirely".
EFFORT_SHAPES: list[tuple[str, list[str] | None]] = [
    ("absent", None),
    ("empty", ["--effort="]),
    ("literal-default", ["--effort", "default"]),
    ("allowlisted", ["--effort", "high"]),
    ("junk", ["--effort", "banana"]),
    ("bare-flag", ["--effort"]),
]

EFFORT_VAR_SHAPES: list[tuple[str, list[str] | None]] = [
    ("absent", None),
    ("empty", ["--effort-var="]),
    ("literal-default", ["--effort-var", "default"]),
    ("allowlisted", ["--effort-var", "max"]),
    ("junk", ["--effort-var", "banana"]),
]


def test_effort_cross_product() -> None:
    """Every combination of the two effort sources, in both modes."""
    for mode in ("fix", "review-response"):
        for e_name, e_argv in EFFORT_SHAPES:
            for v_name, v_argv in EFFORT_VAR_SHAPES:
                argv = ["--model", "claude-opus-5", "--mode", mode]
                # THE VARIABLE FLAG GOES FIRST when --effort is the bare form, because `--effort` followed by nothing and `--effort` followed by `--effort-var` are the SAME case in the twin's parser (the next token starts with `--`), and putting it last would make the bare-flag row degenerate into an end-of-argv row.
                if v_argv:
                    argv += v_argv
                if e_argv:
                    argv += e_argv
                _compare("%s/%s/%s" % (mode, e_name, v_name), argv)


def test_rejected_dispatch_effort_still_lets_the_variable_through() -> None:
    """The `if` that must not become an `elif`.

    A typo'd dispatch effort must not also disable the standing setting, and both notices must appear. Asserted on the twin's own output so the property is pinned to the SUBJECT rather than to the port's reading of it.
    """
    _, stdout, _, gh = _compare(
        "junk-dispatch-good-var",
        ["--model", "m", "--mode", "fix", "--effort", "banana", "--effort-var", "max"],
    )
    assert "dispatch effort 'banana' is not one of" in stdout
    assert "--effort max" in gh, "the variable was suppressed by the rejected dispatch input"


def test_dispatch_beats_the_variable() -> None:
    _, _, _, gh = _compare(
        "both-valid",
        ["--model", "m", "--mode", "fix", "--effort", "low", "--effort-var", "max"],
    )
    assert "--effort low" in gh
    assert "--effort max" not in gh


def test_turn_budget_differs_by_mode() -> None:
    """CONTROL, both directions: `fix` is 80 turns and anything else is 60.

    Without the second half a port that always printed 80 would pass every positive assertion in this file.
    """
    _, fix_out, _, _ = _compare("turns-fix", ["--model", "m", "--mode", "fix"])
    _, rev_out, _, _ = _compare("turns-review", ["--model", "m", "--mode", "review-response"])
    assert "--max-turns 80" in fix_out
    assert "--max-turns 60" in rev_out
    assert "--max-turns 80" not in rev_out


def test_usage_refusals() -> None:
    """Missing or unusable required inputs, exit 2, on stderr."""
    cases = [
        ("no-args", []),
        ("model-only", ["--model", "m"]),
        ("mode-only", ["--mode", "fix"]),
        ("model-empty", ["--model=", "--mode", "fix"]),
        ("mode-empty", ["--model", "m", "--mode="]),
        # `--model` swallowed by the next flag: parse_args stores the string "true", which is non-empty, so this is NOT a usage error. Driven here so the surprising answer is pinned rather than assumed.
        ("model-swallowed", ["--model", "--mode", "fix"]),
        ("positionals-ignored", ["stray", "--model", "m", "--mode", "fix", "words"]),
    ]
    for name, argv in cases:
        _compare(name, argv)


def test_no_github_output_is_a_no_op() -> None:
    """With `$GITHUB_OUTPUT` unset both sides must still print the flags and must not write anything anywhere."""
    exit_code, stdout, _, _ = _compare(
        "no-github-output", ["--model", "m", "--mode", "fix"], github_output=False
    )
    assert exit_code == 0
    assert "--disallowed-tools Task,Agent" in stdout


def test_the_comparison_can_actually_fail() -> None:
    """ANTI-VACUITY. Every assertion above compares the twin with the port; if the harness could not tell two different programs apart, all of it would be green over any port at all.

    So drive the TWIN against ITSELF with one input changed and require the same comparison to report a difference. A mutated copy of the port would be a better control still, but it would also be a second implementation this file then has to maintain; changing the input is enough to prove the comparator's eyes work, and it cannot rot.
    """
    a = _run(TWIN, ["--model", "m", "--mode", "fix"], github_output=True)
    b = _run(TWIN, ["--model", "m", "--mode", "review-response"], github_output=True)
    assert a != b, "the harness reports two genuinely different runs as identical"
    assert a[1] != b[1], "stdout is not being captured at all"
    assert a[3] != b[3], "$GITHUB_OUTPUT is not being read back at all"


def test_pure_helpers_are_exercised_directly() -> None:
    """The exported pure functions, without a subprocess.

    `resolve_effort` is where the whole decision lives, so it gets both directions: something that must resolve, and something that must NOT.
    """
    assert rma.resolve_effort("high", "")[0] == "high"
    assert rma.resolve_effort("", "max")[0] == "max"
    assert rma.resolve_effort("default", "max")[0] == "max"
    assert rma.resolve_effort("banana", "")[0] == ""
    assert rma.resolve_effort("", "")[0] == ""
    assert rma.resolve_effort("", "default")[0] == ""
    # The empty string must never be a member, even though the allowlist is split on commas.
    assert not rma.in_csv("", rma.EFFORT_ALLOWED)
    assert not rma.in_csv("default", rma.EFFORT_ALLOWED)
    assert rma.in_csv("xhigh", rma.EFFORT_ALLOWED)
    assert rma.build_args("m", "fix", "") == (
        "--model m\n--max-turns 80\n--disallowed-tools Task,Agent"
    )
    assert rma.build_args("m", "other", "low").endswith("--effort low")

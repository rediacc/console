"""`rediacc_ci.autopilot.resolve_model_args`, driven against the bytes its bash twin produced.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/autopilot/resolve-model-args.sh` and the port over the same argv and compared FOUR things per case: exit code, stdout, stderr, and the bytes of `$GITHUB_OUTPUT`. The K=5 ledger `.ci/shadow/w7p6-resolve-model-args.observations.jsonl` recorded that comparison over five distinct trees.

THE TWIN HAS NOW BEEN DELETED, and every case compares against `goldens/resolve-model-args/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree. Each provenance header carries the twin's blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

THE THIRD OUTPUT IS STILL COMPARED, which is why the recorded shape carries `--- github output ---`. This subject writes an `args<<HEREDOC` block nobody's stdout or stderr shows, and that file is what the workflow actually consumes: stdout is for a human reading the log. A recording that froze only the two streams would have frozen the half that does not matter.

STREAMS ARE NEVER MERGED. The `::notice` lines go to stdout and the closing summary goes to stderr, which is precisely the asymmetry a `2>&1` would erase; see `differential.py`'s header on the 2026-09-06 stream-swap incident.

THE INPUT SPACE IS ENUMERATED, NOT SAMPLED. `--effort` and `--effort-var` each have five distinct shapes (absent, empty, the literal `default`, a member of the allowlist, and junk), and the `--effort` flag has a sixth: present with no value, which the twin's `parse_args` turned into the string `true`.

The two sources interact, and a REJECTED dispatch effort must still let the variable through, which is the one behaviour an `elif` would silently break. So the cross-product is recorded whole, both modes, rather than three hand-picked cases, and the corpus is sixty rows before the named cases are counted.

WHAT IS NORMALISED, and it is one path. `$GITHUB_OUTPUT` is a file in the case's own temporary directory, and a recording is compared against a directory built under a different tempdir name months later, so it becomes `<out>`. Nothing else is touched.

TWO CALL SITES READ THIS SUBJECT AND BOTH NOW READ THE PORT. `test_gate_autopilot_harness.py` drives `rediacc_ci.autopilot.resolve_model_args` as a module, the way `.github/workflows/autopilot.yml:537` does, and `test_gate_autopilot_guide_comment.py` reads `TURNS_DEFAULT` and `TURNS_FIX` out of the port's own source, holding the documented turn caps to the implementation.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.autopilot import resolve_model_args as rma
from rediacc_ci.tests import frozen

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "resolve_model_args.py"
SLUG = "resolve-model-args"

GH_MARKER = "--- github output ---\n"
NO_GH = "<unset>"

# The environment every case gets. REPLACED, not inherited: a run that inherits the caller's environment passes or fails depending on whether the developer happens to export CI or NO_COLOR, and this subject decides colour from those. LC_ALL pins message text.
BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}

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


def cross_product() -> dict[str, dict[str, typing.Any]]:
    """Every combination of the two effort sources, in both modes."""
    out: dict[str, dict[str, typing.Any]] = {}
    for mode in ("fix", "review-response"):
        for effort_name, effort_argv in EFFORT_SHAPES:
            for var_name, var_argv in EFFORT_VAR_SHAPES:
                argv = ["--model", "claude-opus-5", "--mode", mode]
                # THE VARIABLE FLAG GOES FIRST when --effort is the bare form, because `--effort` followed by nothing and `--effort` followed by `--effort-var` are the SAME case in the twin's parser (the next token starts with `--`), and putting it last would make the bare-flag row degenerate into an end-of-argv row.
                if var_argv:
                    argv += var_argv
                if effort_argv:
                    argv += effort_argv
                out["%s-effort-%s-var-%s" % (mode, effort_name, var_name)] = {"argv": argv}
    return out


NAMED: dict[str, dict[str, typing.Any]] = {
    "a-junk-dispatch-with-a-good-variable": {
        "argv": ["--model", "m", "--mode", "fix", "--effort", "banana", "--effort-var", "max"]
    },
    "both-sources-valid": {
        "argv": ["--model", "m", "--mode", "fix", "--effort", "low", "--effort-var", "max"]
    },
    "turns-for-a-fix-round": {"argv": ["--model", "m", "--mode", "fix"]},
    "turns-for-a-review-round": {"argv": ["--model", "m", "--mode", "review-response"]},
    "no-args": {"argv": []},
    "model-only": {"argv": ["--model", "m"]},
    "mode-only": {"argv": ["--mode", "fix"]},
    "model-empty": {"argv": ["--model=", "--mode", "fix"]},
    "mode-empty": {"argv": ["--model", "m", "--mode="]},
    # `--model` swallowed by the next flag: parse_args stores the string "true", which is non-empty, so this is NOT a usage error. Recorded so the surprising answer is pinned rather than assumed.
    "model-swallowed-by-the-next-flag": {"argv": ["--model", "--mode", "fix"]},
    "positionals-are-ignored": {"argv": ["stray", "--model", "m", "--mode", "fix", "words"]},
    "no-github-output": {"argv": ["--model", "m", "--mode", "fix"], "github_output": False},
}

CASE_KW = {**cross_product(), **NAMED}
CASES = tuple(CASE_KW)


def run(subject: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    """One subject, once. Returns exit code, stdout, stderr and the `$GITHUB_OUTPUT` bytes."""
    kw = CASE_KW[name]
    wants_output = kw.get("github_output", True)
    with tempfile.TemporaryDirectory() as raw:
        where = pathlib.Path(raw)
        env = dict(BASE_ENV)
        target = where / "gh-output"
        if wants_output:
            # PRE-CREATED EMPTY, because the subject APPENDS. A missing file would let `>>` create it and hide a difference in whether anything was written at all.
            target.write_text("", encoding="utf-8")
            env["GITHUB_OUTPUT"] = str(target)
        runner = "bash" if subject.suffix == ".sh" else "python3"
        proc = subprocess.run(
            [runner, str(subject), *kw["argv"]],
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=60,
        )
        written = target.read_text(encoding="utf-8") if wants_output else NO_GH
        mask = str(where)
    return (
        proc.returncode,
        proc.stdout.replace(mask, "<out>"),
        proc.stderr.replace(mask, "<out>"),
        written.replace(mask, "<out>"),
    )


def render(code: int, stdout: str, stderr: str, github_output: str) -> str:
    return "%s%s%s\n" % (frozen.render(code, stdout, stderr), GH_MARKER, github_output)


def recorded(name: str) -> tuple[int, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, github_output = rest.split(GH_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, github_output.removesuffix("\n")


def port(name: str) -> tuple[int, str, str, str]:
    return run(PORT, name)


def compare(name: str) -> tuple[int, str, str, str]:
    want = recorded(name)
    got = port(name)
    labels = ("exit code", "stdout", "stderr", "$GITHUB_OUTPUT")
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%r\n--- port ---\n%r" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(name: str) -> None:
    compare(name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_the_cross_product_is_whole() -> None:
    """The enumeration is the claim, so its size is asserted rather than trusted. Six effort shapes times five variable shapes times two modes is sixty, and a shape quietly dropped from either list would otherwise shrink the corpus in silence."""
    assert len(EFFORT_SHAPES) == 6
    assert len(EFFORT_VAR_SHAPES) == 5
    assert len(cross_product()) == 60
    assert len(CASES) == 72


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_a_rejected_dispatch_effort_still_lets_the_variable_through() -> None:
    """The `if` that must not become an `elif`.

    A typo'd dispatch effort must not also disable the standing setting, and both notices must appear.
    """
    _, stdout, _, github_output = recorded("a-junk-dispatch-with-a-good-variable")
    assert "dispatch effort 'banana' is not one of" in stdout
    assert "--effort max" in github_output, (
        "the variable was suppressed by the rejected dispatch input"
    )


def test_the_dispatch_input_beats_the_variable() -> None:
    _, _, _, github_output = recorded("both-sources-valid")
    assert "--effort low" in github_output
    assert "--effort max" not in github_output


def test_the_turn_budget_differs_by_mode() -> None:
    """CONTROL, both directions: `fix` is 80 turns and anything else is 60.

    Without the second half a port that always printed 80 would pass every positive assertion in this file.
    """
    fix_out = recorded("turns-for-a-fix-round")[1]
    review_out = recorded("turns-for-a-review-round")[1]
    assert "--max-turns 80" in fix_out
    assert "--max-turns 60" in review_out
    assert "--max-turns 80" not in review_out


def test_usage_refusals_exit_2_on_stderr() -> None:
    """Missing or unusable required inputs, exit 2, on stderr, writing nothing."""
    for name in ("no-args", "model-only", "mode-only", "model-empty", "mode-empty"):
        code, stdout, stderr, github_output = recorded(name)
        assert code == 2, "%s exited %d" % (name, code)
        assert stdout == "", name
        assert "usage: resolve-model-args.sh" in stderr, name
        assert github_output == "", name


def test_the_two_surprising_parses_are_pinned() -> None:
    """A swallowed `--model` is the string `true`, which is non-empty and therefore not a usage error, and positional words never reach the parser at all."""
    assert recorded("model-swallowed-by-the-next-flag")[0] == 0
    assert "--model true" in recorded("model-swallowed-by-the-next-flag")[3]
    assert recorded("positionals-are-ignored")[0] == 0
    assert "--model m" in recorded("positionals-are-ignored")[3]


def test_an_unset_github_output_is_a_no_op() -> None:
    """With `$GITHUB_OUTPUT` unset the flags are still printed and nothing is written anywhere."""
    code, stdout, _, github_output = recorded("no-github-output")
    assert code == 0
    assert "--disallowed-tools Task,Agent" in stdout
    assert github_output == NO_GH


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


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_elif_between_the_two_effort_sources_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Make a rejected dispatch effort suppress the variable.

    This is the exact regression the cross-product exists to catch, and nothing announces it: the mutant prints the same `ignoring it` notice as the recording, says nothing about the standing setting it has just dropped, and exits 0.

    What moves is the resolved flag, gone from stdout and from `$GITHUB_OUTPUT` alike, which is what the recordings hold. The mutant is a throwaway copy, and the tracked file is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = "    if not resolved and effort_var and effort_var != EFFORT_DEFAULT:\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(
        anchor, "    if resolved and effort_var and effort_var != EFFORT_DEFAULT:\n"
    )

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(mutated, encoding="utf-8")

    name = "a-junk-dispatch-with-a-good-variable"
    planted = run(mutant, name)
    want = recorded(name)
    assert "--effort max" in want[3], "the recorded corpus moved"
    assert "--effort max" not in planted[3], "the plant did not suppress the variable"
    assert "--effort max" not in planted[1], "the flag survived on stdout"
    notice = "dispatch effort 'banana' is not one of"
    assert notice in want[1], "the recorded notice moved"
    assert notice in planted[1], "the mutant stopped announcing the typo"
    assert planted[0] == want[0] == 0, "the mutant was supposed to succeed, not refuse"

    compare(name)
    assert PORT.read_text(encoding="utf-8") == original

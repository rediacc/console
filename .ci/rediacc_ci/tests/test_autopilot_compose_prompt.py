"""Differential: `rediacc_ci.autopilot.compose_prompt` against its twin
`.ci/scripts/autopilot/compose-prompt.sh`.

BESPOKE SUBPROCESS COMPARISON, because this subject's real output is neither stdout nor stderr: it is the FILE named by `--out` plus the `prompt<<HEREDOC` block appended to `$GITHUB_OUTPUT`. Every case here compares five things -- exit code, stdout, stderr, the `--out` bytes, and the `$GITHUB_OUTPUT` bytes -- and it compares the two files as BYTES rather than text, because a prompt
carries review-thread content written by whoever replied to the thread and a decoder in the test would refuse input the subject passes through untouched.

THE RANDOM DELIMITER IS NORMALISED, NOT ASSERTED. `compose-prompt.sh` draws a fresh 32-hex-character marker per run on purpose (a fixed marker inside attacker-influenceable text could close the step output early), so two runs cannot produce identical `$GITHUB_OUTPUT` bytes and a byte comparison would be a test that can never pass. The comparison masks the hex and asserts the SHAPE
separately: the prefix, exactly 32 lowercase hex characters, the same marker on both fence lines, and two runs of the SAME implementation differing. Asserting the value would be asserting that a CSPRNG repeats itself.

TWO REFUSALS DIVERGE IN TEXT AND ARE COMPARED STRUCTURALLY, and both are named in the port's docstring rather than discovered here: a bash `>"$OUT"` redirection failure and (in the parse path) `printf -v`'s identifier error both carry the twin's own path and LINE NUMBER. Exit code, stream and ordering are
compared exactly; only the text is compared by shape.

K=5 LEDGER: `.ci/shadow/w7p6-compose-prompt.observations.jsonl`, recorded
against a disposable scratch git repository built outside this checkout, since `shadow-gate.ts --record` refuses a dirty tree and this checkout is never clean.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import tempfile

from rediacc_ci import paths
from rediacc_ci.autopilot import compose_prompt as cp

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "compose-prompt.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "compose_prompt.py"

BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}

DELIM_RE = re.compile(rb"AUTOPILOT_PROMPT_EOF_[0-9a-f]{32}")

# A template with NO trailing newline, so the `printf '\n<autopilot_state>\n'` that follows is the only thing separating it from the state block. A template that ended in a newline would make the two implementations agree even if one of them dropped that leading `\n`.
TEMPLATE_BODY = b"You are the autopilot.\nRound template body."

# Deliberately not valid UTF-8. The subject concatenates bytes; a port that
# decoded would raise here and a port that decoded with errors="replace" would
# silently corrupt a review payload.
DECISION_BODY = b'{"decision":"fix","note":"caf\xe9"}\n'


def _fixture(base: pathlib.Path, **files: bytes | None) -> tuple[pathlib.Path, pathlib.Path]:
    """A prompts dir and an fx dir. A value of None omits the file entirely."""
    prompts = base / "prompts"
    fx = base / "fx"
    prompts.mkdir(parents=True, exist_ok=True)
    fx.mkdir(parents=True, exist_ok=True)
    default: dict[str, bytes | None] = {
        "prompts/round.md": TEMPLATE_BODY,
        "fx/decision.json": DECISION_BODY,
        "fx/state.txt": None,
        "fx/failed-jobs.txt": None,
        "fx/review-payload.json": None,
    }
    # KEYWORD KEYS ARE ENCODED PATHS: `__` is `/`, `_dash_` is `-`, `_dot_` is `.`. Spelled out because the first version of this helper forgot `_dash_`,
    # so `fx__review_dash_payload_dot_json=` silently created a file called
    # `fx/review_dash_payload.json` that the subject never reads -- every review
    # case was running with NO payload and agreeing for the wrong reason. The
    # assert below is what makes that class of typo loud instead of silent.
    for key, value in files.items():
        rel = key.replace("__", "/").replace("_dash_", "-").replace("_dot_", ".")
        assert rel in default, "unknown fixture key %r -> %r" % (key, rel)
        default[rel] = value
    for rel, body in default.items():
        path = base / rel
        if body is None:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    return prompts, fx


def _run(
    subject: pathlib.Path,
    base: pathlib.Path,
    argv: list[str],
    *,
    github_output: bool,
) -> tuple[int, str, str, bytes | None, bytes]:
    """(exit, stdout, stderr, --out bytes or None, $GITHUB_OUTPUT bytes)."""
    env = dict(BASE_ENV)
    gh = base / "gh-output"
    if github_output:
        gh.write_bytes(b"")
        env["GITHUB_OUTPUT"] = str(gh)
    runner = ["bash"] if subject.suffix == ".sh" else ["python3"]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=60,
    )
    out_path = None
    for i, flag in enumerate(argv):
        if flag == "--out" and i + 1 < len(argv):
            out_path = base / argv[i + 1]
    written = out_path.read_bytes() if out_path is not None and out_path.exists() else None
    return (
        proc.returncode,
        proc.stdout,
        proc.stderr,
        written,
        (gh.read_bytes() if github_output else b""),
    )


def _sides(
    name: str,
    argv_for: object,
    *,
    github_output: bool = True,
    exact_stderr: bool = True,
    **fixture: bytes | None,
) -> tuple[int, str, str, bytes | None, bytes]:
    """Build a fresh fixture per side, run both, and compare.

    A FRESH TREE PER SIDE, never one shared directory: the subject WRITES into the fixture, so a shared directory would let the first side's output become the second side's input, and the two would agree because one of them read what the other left.
    """
    with tempfile.TemporaryDirectory() as td:
        results = []
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            _fixture(base, **fixture)
            argv = argv_for(base) if callable(argv_for) else list(argv_for)
            results.append(_run(subject, base, argv, github_output=github_output))
        old, new = results

    assert new[0] == old[0], (
        "%s: exit code diverged: %r vs %r\n twin stderr: %s\n port stderr: %s"
        % (
            name,
            old[0],
            new[0],
            old[2],
            new[2],
        )
    )
    assert new[1] == old[1], "%s: stdout diverged:\n%r\n%r" % (name, old[1], new[1])
    if exact_stderr:
        assert new[2] == old[2], "%s: stderr diverged:\n--- twin ---\n%s\n--- port ---\n%s" % (
            name,
            old[2],
            new[2],
        )
    assert new[3] == old[3], "%s: the --out bytes diverged:\n%r\n%r" % (name, old[3], new[3])
    assert DELIM_RE.sub(b"<DELIM>", new[4]) == DELIM_RE.sub(b"<DELIM>", old[4]), (
        "%s: $GITHUB_OUTPUT diverged (delimiter masked):\n%r\n%r" % (name, old[4], new[4])
    )
    return old


def _argv(mode: str, template: str = "round.md", out: str = "prompt.txt") -> list[str]:
    return [
        "--prompts",
        "prompts",
        "--fx",
        "fx",
        "--template",
        template,
        "--mode",
        mode,
        "--out",
        out,
    ]


def test_happy_rounds() -> None:
    """The fixture shapes a real round produces, both modes."""
    _sides("fix-minimal", _argv("fix"))
    _sides(
        "fix-with-state",
        _argv("fix"),
        fx__state_dot_txt=b"state comment body\n",
    )
    _sides(
        "fix-with-failed-jobs",
        _argv("fix"),
        fx__failed_dash_jobs_dot_txt=b"quality-code\nquality-i18n\n",
    )
    _sides(
        "fix-everything",
        _argv("fix"),
        fx__state_dot_txt=b"state\n",
        fx__failed_dash_jobs_dot_txt=b"quality-code\n",
    )
    _sides(
        "review-with-payload",
        _argv("review-response"),
        fx__review_dash_payload_dot_json=b'[{"thread":"1","body":"fix the thing"}]',
    )
    # An unknown mode is NOT an error: only `review-response` is special-cased.
    _sides("unknown-mode", _argv("banana"))


def test_review_round_refuses_without_a_payload() -> None:
    """Exit 1, the gate's own message, and -- the part a port gets wrong -- the
    partial `--out` file is still on disk, because the refusal happens after the
    main block has been written."""
    for name, payload in (("missing", None), ("empty", b"")):
        exit_code, _, stderr, out_bytes, _ = _sides(
            "review-payload-%s" % name,
            _argv("review-response"),
            fx__review_dash_payload_dot_json=payload,
        )
        assert exit_code == 1
        assert "refusing to run a review round blind" in stderr
        assert out_bytes is not None, "no --out file was written at all"
        assert b"<autopilot_state>" in out_bytes, (
            "the partial prompt was not left on disk; the refusal is supposed to "
            "happen AFTER the main block is written"
        )


def test_missing_inputs() -> None:
    """The three checked inputs and the one that is NOT checked."""
    _sides("missing-template", _argv("fix", template="nope.md"))
    # A DIRECTORY where a template file is expected: `-f` is false for both.
    _sides("template-is-a-directory", _argv("fix", template="."))
    # THE HAZARD: decision.json has no require_file in front of it, so this is coreutils' message and a half-written --out, not a named refusal.
    exit_code, _, stderr, out_bytes, _ = _sides(
        "missing-decision", _argv("fix"), fx__decision_dot_json=None
    )
    assert exit_code == 1
    assert "cat: fx/decision.json: No such file or directory" in stderr
    assert out_bytes == TEMPLATE_BODY + b"\n<autopilot_state>\n", (
        "the partial file should hold the template and the opening tag and nothing more"
    )


def test_missing_directories() -> None:
    """`require_dir` on --prompts and --fx, exit 1, each naming itself."""
    for name, argv in (
        (
            "prompts-dir-absent",
            [
                "--prompts",
                "nope",
                "--fx",
                "fx",
                "--template",
                "round.md",
                "--mode",
                "fix",
                "--out",
                "p.txt",
            ],
        ),
        (
            "fx-dir-absent",
            [
                "--prompts",
                "prompts",
                "--fx",
                "nope",
                "--template",
                "round.md",
                "--mode",
                "fix",
                "--out",
                "p.txt",
            ],
        ),
        # A FILE where a directory is expected: `-d` is false for both, so both must refuse identically.
        (
            "prompts-is-a-file",
            [
                "--prompts",
                "prompts/round.md",
                "--fx",
                "fx",
                "--template",
                "round.md",
                "--mode",
                "fix",
                "--out",
                "p.txt",
            ],
        ),
    ):
        exit_code, _, stderr, _, _ = _sides(name, argv)
        assert exit_code == 1
        assert "does not exist" in stderr


def test_usage_refusals() -> None:
    """Each of the five required flags, absent and empty, exit 2."""
    full = {
        "--prompts": "prompts",
        "--fx": "fx",
        "--template": "round.md",
        "--mode": "fix",
        "--out": "p.txt",
    }
    for drop in list(full):
        argv: list[str] = []
        for flag, value in full.items():
            if flag == drop:
                continue
            argv += [flag, value]
        exit_code, _, stderr, _, _ = _sides("missing%s" % drop, argv)
        assert exit_code == 2, "%s: expected the usage refusal" % drop
        assert "usage: compose-prompt.sh" in stderr
        # And the same flag present but EMPTY (`--mode=`), which parse_args
        # stores as the empty string rather than leaving unset. The twin's test is `-n`, so both shapes must refuse.
        empty: list[str] = []
        for flag, value in full.items():
            empty += [flag + "="] if flag == drop else [flag, value]
        assert _sides("empty%s" % drop, empty)[0] == 2


def test_out_in_a_nonexistent_directory() -> None:
    """A redirection failure. Exit 1 on both, text compared by SHAPE: the twin
    emits a bash diagnostic carrying its own path and line number."""
    argv = [
        "--prompts",
        "prompts",
        "--fx",
        "fx",
        "--template",
        "round.md",
        "--mode",
        "fix",
        "--out",
        "nodir/p.txt",
    ]
    exit_code, _, stderr, _, _ = _sides("out-unwritable", argv, exact_stderr=False)
    assert exit_code == 1
    assert "nodir/p.txt" in stderr
    assert "No such file or directory" in stderr


def test_github_output_shape() -> None:
    """The heredoc fence, and the delimiter's shape.

    Compared by shape rather than value on purpose (see the module docstring), so this is where the shape itself is pinned: prefix, 32 lowercase hex, the SAME marker on the opening and closing fence, and the prompt bytes verbatim between them.
    """
    with tempfile.TemporaryDirectory() as td:
        seen = []
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            _fixture(base)
            _, _, _, out_bytes, gh = _run(subject, base, _argv("fix"), github_output=True)
            markers = DELIM_RE.findall(gh)
            assert len(markers) == 2, "%s: expected two fence lines, got %r" % (
                subject.name,
                markers,
            )
            assert markers[0] == markers[1], "%s: the fences disagree" % subject.name
            assert gh == b"prompt<<" + markers[0] + b"\n" + (out_bytes or b"") + markers[0] + b"\n"
            seen.append(markers[0])
        assert seen[0] != seen[1], (
            "the twin and the port produced the SAME delimiter; either one of them "
            "is not random or this test is reading a cached file"
        )


def test_the_delimiter_is_fresh_per_run() -> None:
    """CONTROL for the case above: a constant that happened to look like hex
    would satisfy every shape assertion. Two runs of the PORT must differ."""
    values = {cp.delimiter() for _ in range(8)}
    assert len(values) == 8, "the delimiter repeated inside eight calls: %r" % values


def test_pure_helpers_are_exercised_directly() -> None:
    """`compose` without a subprocess, both directions on the optional files."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        prompts, fx = _fixture(base)
        body = cp.compose(str(prompts), str(fx), "round.md")
        assert body.startswith(TEMPLATE_BODY)
        assert b"<autopilot_state>" in body
        assert b"</failed_jobs>" in body
        # The optional files are ABSENT here, so their content must not appear.
        assert b"state comment" not in body
        (fx / "state.txt").write_bytes(b"state comment\n")
        assert b"state comment" in cp.compose(str(prompts), str(fx), "round.md")

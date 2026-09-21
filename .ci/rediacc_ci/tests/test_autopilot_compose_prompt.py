"""`rediacc_ci.autopilot.compose_prompt`, driven against the bytes its bash twin wrote.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/autopilot/compose-prompt.sh` and the port over the same fixture and compared five things: exit code, stdout, stderr, the `--out` bytes and the `$GITHUB_OUTPUT` bytes. The K=5 ledger `.ci/shadow/w7p6-compose-prompt.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been deleted and
every case that executed it compares against `goldens/compose-prompt/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that wrote them.

THE ARTIFACT IS A FILE, NOT A STREAM. This subject's real output is the file named by `--out` plus the `prompt<<HEREDOC` block appended to `$GITHUB_OUTPUT`, and both are recorded beside the two streams. They are recorded as BYTES, because a prompt carries review-thread content written by whoever replied to the thread and a decoder would refuse input the subject passes
through untouched. Each is stored as a JSON string of its `latin-1` decoding, which is a byte-for-byte reversible mapping: `\\u00e9` in a golden is one byte, 0xE9, and `.encode("latin-1")` gives it back.

THE RANDOM DELIMITER IS MASKED, NOT RECORDED. The twin drew a fresh 32-hex-character marker per run on purpose (a fixed marker inside attacker-influenceable text could close the step output early), so no two runs produce identical `$GITHUB_OUTPUT` bytes and a recording of one would be a comparison nothing could satisfy. The recording masks the hex and the SHAPE is
asserted separately, live: the prefix, exactly 32 lowercase hex characters, the same marker on both fence lines, and two calls of the port differing. Recording the value would be recording that a CSPRNG repeats itself.

TWO REFUSALS DIVERGE IN TEXT AND ARE COMPARED STRUCTURALLY, and both were named in the port's docstring rather than discovered here: a bash `>"$OUT"` redirection failure carried the twin's own path and LINE NUMBER. Exit code, stream and the written artifact are compared exactly; only that text is compared by shape.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.autopilot import compose_prompt as cp
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "compose_prompt.py"

SLUG = "compose-prompt"

OUT_MARKER = "--- out file ---\n"
GH_MARKER = "--- github output ---\n"
NO_OUT = "<no file written>"

BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    "HOME": os.environ.get("HOME", "/tmp"),
    "LC_ALL": "C",
    "LANG": "C",
    "PYTHONPATH": str(ROOT / ".ci"),
    "PYTHONDONTWRITEBYTECODE": "1",
}

DELIM_RE = re.compile(rb"AUTOPILOT_PROMPT_EOF_[0-9a-f]{32}")

# A template with NO trailing newline, so the `printf '\n<autopilot_state>\n'` that follows is the only thing separating it from the state block. A template that ended in a newline would make a dropped leading `\n` invisible.
TEMPLATE_BODY = b"You are the autopilot.\nRound template body."

# Deliberately not valid UTF-8. The subject concatenates bytes; a port that decoded would raise here and a port that decoded with errors="replace" would silently corrupt a review payload.
DECISION_BODY = b'{"decision":"fix","note":"caf\xe9"}\n'

FULL_FLAGS = {
    "--prompts": "prompts",
    "--fx": "fx",
    "--template": "round.md",
    "--mode": "fix",
    "--out": "p.txt",
}


def argv_for(mode: str, template: str = "round.md", out: str = "prompt.txt") -> list[str]:
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


def _without(drop: str) -> list[str]:
    argv: list[str] = []
    for flag, value in FULL_FLAGS.items():
        if flag != drop:
            argv += [flag, value]
    return argv


def _emptied(drop: str) -> list[str]:
    argv: list[str] = []
    for flag, value in FULL_FLAGS.items():
        argv += [flag + "="] if flag == drop else [flag, value]
    return argv


def _dir_argv(prompts: str, fx: str) -> list[str]:
    return [
        "--prompts",
        prompts,
        "--fx",
        fx,
        "--template",
        "round.md",
        "--mode",
        "fix",
        "--out",
        "p.txt",
    ]


# name -> (argv, fixture overrides). A fixture value of None omits the file.
CASE_KW: dict[str, tuple[list[str], dict[str, bytes | None]]] = {
    "a-minimal-fix-round": (argv_for("fix"), {}),
    "a-fix-round-with-state": (argv_for("fix"), {"fx/state.txt": b"state comment body\n"}),
    "a-fix-round-with-failed-jobs": (
        argv_for("fix"),
        {"fx/failed-jobs.txt": b"quality-code\nquality-i18n\n"},
    ),
    "a-fix-round-with-everything": (
        argv_for("fix"),
        {"fx/state.txt": b"state\n", "fx/failed-jobs.txt": b"quality-code\n"},
    ),
    "a-review-round-with-a-payload": (
        argv_for("review-response"),
        {"fx/review-payload.json": b'[{"thread":"1","body":"fix the thing"}]'},
    ),
    "an-unknown-mode": (argv_for("banana"), {}),
    "a-review-round-with-no-payload": (argv_for("review-response"), {}),
    "a-review-round-with-an-empty-payload": (
        argv_for("review-response"),
        {"fx/review-payload.json": b""},
    ),
    "a-missing-template": (argv_for("fix", template="nope.md"), {}),
    "a-template-that-is-a-directory": (argv_for("fix", template="."), {}),
    "a-missing-decision": (argv_for("fix"), {"fx/decision.json": None}),
    "a-missing-prompts-directory": (_dir_argv("nope", "fx"), {}),
    "a-missing-fx-directory": (_dir_argv("prompts", "nope"), {}),
    "a-prompts-path-that-is-a-file": (_dir_argv("prompts/round.md", "fx"), {}),
    "no-prompts-flag": (_without("--prompts"), {}),
    "no-fx-flag": (_without("--fx"), {}),
    "no-template-flag": (_without("--template"), {}),
    "no-mode-flag": (_without("--mode"), {}),
    "no-out-flag": (_without("--out"), {}),
    "an-empty-prompts-flag": (_emptied("--prompts"), {}),
    "an-empty-fx-flag": (_emptied("--fx"), {}),
    "an-empty-template-flag": (_emptied("--template"), {}),
    "an-empty-mode-flag": (_emptied("--mode"), {}),
    "an-empty-out-flag": (_emptied("--out"), {}),
    "an-out-path-in-a-missing-directory": (
        [
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
        ],
        {},
    ),
}

CASES = tuple(CASE_KW)

# The one case the port does not reproduce byte for byte: the twin died at its redirection with a bash diagnostic carrying its own path and line number. Compared by shape, in its own test.
DIVERGENT = "an-out-path-in-a-missing-directory"

# Every flag whose absence and whose emptiness must both refuse.
REQUIRED_FLAGS = tuple(FULL_FLAGS)


def build_fixture(base: pathlib.Path, overrides: dict[str, bytes | None]) -> None:
    """A prompts dir and an fx dir. A value of None omits the file entirely."""
    (base / "prompts").mkdir(parents=True, exist_ok=True)
    (base / "fx").mkdir(parents=True, exist_ok=True)
    files: dict[str, bytes | None] = {
        "prompts/round.md": TEMPLATE_BODY,
        "fx/decision.json": DECISION_BODY,
        "fx/state.txt": None,
        "fx/failed-jobs.txt": None,
        "fx/review-payload.json": None,
    }
    for rel, body in overrides.items():
        assert rel in files, "unknown fixture path %r" % rel
        files[rel] = body
    for rel, body in files.items():
        if body is None:
            continue
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)


def run(
    where: pathlib.Path, subject: pathlib.Path, name: str
) -> tuple[int, str, str, bytes | None, bytes]:
    """One side, once, over a FRESH fixture.

    A fresh tree per run, never one shared directory: the subject WRITES into the fixture, so a shared directory would let one run's output become the next run's input, and the two would agree because one of them read what the other left.
    """
    argv, overrides = CASE_KW[name]
    where.mkdir(parents=True, exist_ok=True)
    build_fixture(where, overrides)
    gh = where / "gh-output"
    gh.write_bytes(b"")
    env = dict(BASE_ENV)
    env["GITHUB_OUTPUT"] = str(gh)
    runner = "bash" if subject.suffix == ".sh" else "python3"
    proc = subprocess.run(
        [runner, str(subject), *argv],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=str(where),
        timeout=60,
    )
    out_path = None
    for index, flag in enumerate(argv):
        if flag == "--out" and index + 1 < len(argv):
            out_path = where / argv[index + 1]
    written = out_path.read_bytes() if out_path is not None and out_path.exists() else None
    return proc.returncode, proc.stdout, proc.stderr, written, gh.read_bytes()


def _encode(body: bytes | None) -> str:
    """One artifact, as a reversible JSON string. See the module docstring."""
    if body is None:
        return json.dumps(None)
    return json.dumps(body.decode("latin-1"))


def _decode(text: str) -> bytes | None:
    value = json.loads(text)
    return None if value is None else value.encode("latin-1")


def render(
    returncode: int, stdout: str, stderr: str, written: bytes | None, github_output: bytes
) -> str:
    body = frozen.render(returncode, stdout, stderr)
    masked = DELIM_RE.sub(b"<DELIM>", github_output)
    return body + OUT_MARKER + _encode(written) + "\n" + GH_MARKER + _encode(masked) + "\n"


def recorded(name: str) -> tuple[int, str, str, bytes | None, bytes]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    streams, tail = rest.split(OUT_MARKER, 1)
    stdout, stderr = streams.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    written, github_output = tail.split(GH_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        _decode(written),
        _decode(github_output) or b"",
    )


def drive(tmp_path: pathlib.Path, name: str, *, subject: pathlib.Path = PORT):
    returncode, stdout, stderr, written, github_output = run(tmp_path / "run", subject, name)
    return returncode, stdout, stderr, written, DELIM_RE.sub(b"<DELIM>", github_output)


def compare(tmp_path: pathlib.Path, name: str, *, exact_stderr: bool = True):
    want = recorded(name)
    got = drive(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d\nport stderr: %s" % (
        name,
        want[0],
        got[0],
        got[2],
    )
    assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (name, want[1], got[1])
    if exact_stderr:
        assert got[2] == want[2], "%s: stderr diverged:\n%s\n%s" % (name, want[2], got[2])
    assert got[3] == want[3], "%s: the --out bytes diverged: %r vs %r" % (name, want[3], got[3])
    assert got[4] == want[4], "%s: $GITHUB_OUTPUT diverged: %r vs %r" % (name, want[4], got[4])
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c != DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_a_review_round_refuses_without_a_payload() -> None:
    """Exit 1, the gate's own message, and -- the part a port gets wrong -- the partial `--out` file is still on disk, because the refusal happens after the main block has been written."""
    for name in ("a-review-round-with-no-payload", "a-review-round-with-an-empty-payload"):
        returncode, _, stderr, written, _ = recorded(name)
        assert returncode == 1, name
        assert "refusing to run a review round blind" in stderr
        assert written is not None, "no --out file was written at all"
        assert b"<autopilot_state>" in written, (
            "the partial prompt was not left on disk; the refusal is supposed to "
            "happen AFTER the main block is written"
        )


def test_the_decision_file_has_no_guard_in_front_of_it() -> None:
    """THE HAZARD. `decision.json` has no `require_file`, so this is coreutils' message and a half-written `--out`, not a named refusal."""
    returncode, _, stderr, written, _ = recorded("a-missing-decision")
    assert returncode == 1
    assert "cat: fx/decision.json: No such file or directory" in stderr
    assert written == TEMPLATE_BODY + b"\n<autopilot_state>\n", (
        "the partial file should hold the template and the opening tag and nothing more"
    )


def test_missing_inputs_are_named_refusals() -> None:
    """`require_file` on the template, and `-f` is false for a directory too."""
    for name in ("a-missing-template", "a-template-that-is-a-directory"):
        returncode, _, stderr, _, _ = recorded(name)
        assert returncode == 1, name
        assert "does not exist" in stderr, name


def test_missing_directories_are_named_refusals() -> None:
    """`require_dir` on --prompts and --fx, exit 1, each naming itself. `-d` is false for a file, so a file where a directory belongs refuses identically."""
    for name in (
        "a-missing-prompts-directory",
        "a-missing-fx-directory",
        "a-prompts-path-that-is-a-file",
    ):
        returncode, _, stderr, _, _ = recorded(name)
        assert returncode == 1, name
        assert "does not exist" in stderr, name


def test_usage_refusals() -> None:
    """Each of the five required flags, absent and empty, exit 2.

    The EMPTY shape matters on its own: `--mode=` is stored by `parse_args` as the empty string rather than left unset, and the twin's test was `-n`, so both shapes had to refuse.
    """
    for flag in REQUIRED_FLAGS:
        stem = flag.removeprefix("--")
        absent = recorded("no-%s-flag" % stem)
        assert absent[0] == 2, "%s: expected the usage refusal" % flag
        assert "usage: compose-prompt.sh" in absent[2]
        assert recorded("an-empty-%s-flag" % stem)[0] == 2, flag


def test_an_unknown_mode_is_not_an_error() -> None:
    """Only `review-response` is special-cased; everything else composes normally."""
    returncode, _, _, written, _ = recorded("an-unknown-mode")
    assert returncode == 0
    assert written is not None
    assert written.startswith(TEMPLATE_BODY)


def test_the_optional_blocks_appear_only_when_their_files_do() -> None:
    """The negative half is what makes the positive half mean anything."""
    minimal = recorded("a-minimal-fix-round")[3] or b""
    assert b"state comment body" not in minimal
    assert b"quality-i18n" not in minimal
    assert b"state comment body" in (recorded("a-fix-round-with-state")[3] or b"")
    assert b"quality-i18n" in (recorded("a-fix-round-with-failed-jobs")[3] or b"")


def test_the_undecodable_decision_bytes_survive_verbatim() -> None:
    """The 0xE9 the fixture plants is in the recorded prompt, unreplaced."""
    written = recorded("a-minimal-fix-round")[3] or b""
    assert b"caf\xe9" in written, "the prompt was decoded and mangled somewhere"


def test_an_unwritable_out_path_refuses_in_both(tmp_path: pathlib.Path) -> None:
    """A redirection failure. Exit 1 in both, text compared by SHAPE: the twin emitted a bash diagnostic carrying its own path and line number."""
    want_exit, _, want_err, _, _ = recorded(DIVERGENT)
    returncode, _, stderr, _, _ = drive(tmp_path, DIVERGENT)
    assert want_exit == returncode == 1
    for text in (want_err, stderr):
        assert "nodir/p.txt" in text
        assert "No such file or directory" in text
    compare(tmp_path / "artifacts", DIVERGENT, exact_stderr=False)


# --------------------------------------------------------------------------- The delimiter, which no recording can hold ---------------------------------------------------------------------------


def test_github_output_shape(tmp_path: pathlib.Path) -> None:
    """The heredoc fence, and the delimiter's shape.

    Masked rather than recorded (see the module docstring), so this is where the shape itself is pinned, live: prefix, 32 lowercase hex, the SAME marker on the opening and closing fence, and the prompt bytes verbatim between them.
    """
    _, _, _, written, github_output = run(tmp_path / "shape", PORT, "a-minimal-fix-round")
    markers = DELIM_RE.findall(github_output)
    assert len(markers) == 2, "expected two fence lines, got %r" % markers
    assert markers[0] == markers[1], "the fences disagree"
    assert github_output == (
        b"prompt<<" + markers[0] + b"\n" + (written or b"") + markers[0] + b"\n"
    )
    # And the recording says the twin wrote the same fence around the same bytes.
    recorded_gh = recorded("a-minimal-fix-round")[4]
    assert recorded_gh == b"prompt<<<DELIM>\n" + (recorded("a-minimal-fix-round")[3] or b"") + (
        b"<DELIM>\n"
    )


def test_the_delimiter_is_fresh_per_run() -> None:
    """CONTROL for the case above: a constant that happened to look like hex would satisfy every shape assertion. Eight calls must differ."""
    values = {cp.delimiter() for _ in range(8)}
    assert len(values) == 8, "the delimiter repeated inside eight calls: %r" % values


def test_pure_helpers_are_exercised_directly(tmp_path: pathlib.Path) -> None:
    """`compose` without a subprocess, both directions on the optional files."""
    base = tmp_path / "helpers"
    build_fixture(base, {})
    prompts, fx = base / "prompts", base / "fx"
    body = cp.compose(str(prompts), str(fx), "round.md")
    assert body.startswith(TEMPLATE_BODY)
    assert b"<autopilot_state>" in body
    assert b"</failed_jobs>" in body
    # The optional files are ABSENT here, so their content must not appear.
    assert b"state comment" not in body
    (fx / "state.txt").write_bytes(b"state comment\n")
    assert b"state comment" in cp.compose(str(prompts), str(fx), "round.md")


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_acceptance_of_a_blind_review_round_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Accept an EMPTY review payload instead of refusing it.

    `[[ ! -s ... ]]` tests SIZE, not existence, and an empty payload file is exactly the shape a failed fetch leaves behind. A guard relaxed to `>= 0` therefore composes a review round with no findings in it, which reads to the model as "there is nothing to answer" and resolves threads it never saw. The recorded verdict for `a-review-round-with-an-empty-payload` is 1
    with the refusal on stderr; the mutant exits 0 and writes a complete prompt. The mutation runs from a throwaway copy of the package's module file; the tracked port is never touched.
    """
    with open(PORT, encoding="utf-8") as fh:
        original = fh.read()
    guard = "os.path.isfile(payload) and os.path.getsize(payload) > 0"
    assert original.count(guard) == 1, "the plant's anchor moved"
    assert "refusing to run a review round blind" in original, "the refusal's wording moved"
    mutated = original.replace(
        guard, "os.path.isfile(payload) and os.path.getsize(payload) >= 0", 1
    )

    mutant_dir = tmp_path / "mutant"
    mutant_dir.mkdir(parents=True, exist_ok=True)
    mutant = mutant_dir / "compose_prompt.py"
    mutant.write_text(mutated, encoding="utf-8")

    name = "a-review-round-with-an-empty-payload"
    returncode, _, stderr, written, _ = run(tmp_path / "planted", mutant, name)
    want_exit, _, want_err, _, _ = recorded(name)
    assert (want_exit, "refusing to run a review round blind" in want_err) == (1, True), (
        "the recorded verdict moved"
    )
    assert returncode == 0, "the plant did not change the verdict"
    assert "refusing" not in stderr, "the plant is still refusing"
    assert written is not None, "the plant wrote no prompt at all"
    assert b"review_payload" in written.lower().replace(b"-", b"_"), (
        "the plant composed no review block: %r" % written
    )

    compare(tmp_path / "good", name)
    with open(PORT, encoding="utf-8") as fh:
        assert fh.read() == original

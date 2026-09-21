"""`rediacc_ci.autopilot.update_state`, driven against the bytes its bash twin produced.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/autopilot/update-state.sh` and the port over one stubbed `gh` and compared FIVE things per case: exit code, stdout, stderr, the recorded `gh` argv, and the bytes of the file behind `-F body=@...`. The K=5 ledger `.ci/shadow/w7p6-update-state.observations.jsonl` recorded that comparison over five distinct trees.

THE TWIN HAS NOW BEEN DELETED, and every case compares against `goldens/update-state/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree. Each provenance header carries the twin's blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

THE FAKE `gh` IS NOT A CONVENIENCE. This subject's success path is an `api --method POST|PATCH` against a real repository, and a case that reached the real binary would write a comment onto whatever PR the argument named. Three independent things stop that, because one would be a claim rather than a control.

The stub directory is FIRST on PATH and `shutil.which` is asserted to resolve to the fake in `test_the_fake_gh_is_the_gh`; every case names a repository that does not exist (`acme/widget`); and `GH_TOKEN` is a fixture string with `GH_CONFIG_DIR` pointing into the temp tree, so a leaked real `gh` would fail auth instead of writing.

THE CALL LOG AND THE BODY ARE PRIMARY ARTIFACTS, not sanity checks, which is why the recorded shape carries `--- gh calls ---` and `--- gh body ---`. Almost everything this script does is invisible in stdout: which endpoint, which method, and what body bytes went up. A stdout-only recording would be satisfied by a port that logged the right sentence and PATCHed the wrong comment.

WHAT THE BODY BYTES PROVE. The rendered comment is the state renderer's output, which the subject spawns, so comparing it is not testing the renderer: it is testing that the same argv went into it.

The `--campaign`-shaped optional flags are the interesting half, since an omitted flag means "carry the previous value forward" and an empty one means "reset to none", so a port that passed every flag unconditionally would silently close a live campaign. `the-previous-body-is-carried-forward` is the recording that catches that.

TWO PRESERVED DEFECTS ARE PINNED BY NAME rather than described in prose: `a-mistyped-verdict-path` and `a-non-string-ruled-out-entry`. If either twin behaviour is ever repaired, the recording goes red and the repair gets noticed here first.

WHAT IS NORMALISED, and it is two things. The stub already rewrote the one volatile argument, the mktemp path behind `-F body=@`, to `<work>/body.md`, so that substitution predates the freezing and is unchanged.

The recording adds one more: every captured stream and the body are decoded with `backslashreplace`, because a golden is a UTF-8 text file and `body-bytes-are-not-decoded` deliberately carries a byte that is not valid UTF-8.

Both the recording and every later comparison pass through that same decode, so it is as strong as comparing raw bytes for every fixture here, none of which carries a literal backslash-x sequence of its own.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.autopilot import update_state as us
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "update_state.py"
SLUG = "update-state"

CALLS_MARKER = "--- gh calls ---\n"
BODY_MARKER = "--- gh body ---\n"
NO_BODY = "<no body>"

# The recording fake. It rewrites the one volatile argument (the mktemp path behind `-F body=@`) and copies the body it was handed, so a case can compare the bytes that would have gone to GitHub.
FAKE_GH = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
logged = []
for arg in argv:
    if arg.startswith("body=@"):
        path = arg[len("body=@"):]
        with open(path, "rb") as fh:
            body = fh.read()
        with open(os.environ["FAKE_GH_BODY"], "wb") as fh:
            fh.write(body)
        logged.append("body=@<work>/body.md")
    else:
        logged.append(arg)
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write("\\t".join(logged) + "\\n")

sys.stdout.write(os.environ.get("FAKE_GH_STDOUT", "{}") + "\\n")
sys.stderr.write(os.environ.get("FAKE_GH_STDERR", ""))
sys.exit(int(os.environ.get("FAKE_GH_RC", "0")))
"""

PR = "42"
REPO = "acme/widget"

BASE_ARGV = [
    "--pr",
    PR,
    "--repo",
    REPO,
    "--state",
    "fixing",
    "--round",
    "2",
    "--rounds-max",
    "8",
    "--head",
    "abc1234",
    "--last-run",
    "555/1 handled",
]

PREVIOUS_BODY = (
    b"### Autopilot state (machine-maintained, do not edit)\n"
    b"state: fixing | round: 1/8 | head: aaa | last_run: 1/1 handled | "
    b"campaign: open | model: opus | rounds_max: 8 | last_sig: none | sig_count: 0\n"
    b"\n#### Round ledger\n"
    b"r1 | run 111 | commit deadbee | did the first thing\n"
    b"\n#### Ruled out\n- the cache theory\n"
    b"\n#### DECISIONS (post-hoc review)\n- kept the retry\n"
)

RAW_BYTE_BODY = (
    b"### Autopilot state (machine-maintained, do not edit)\n"
    b"state: fixing | round: 1/8 | head: aaa | last_run: 1/1 handled | "
    b"campaign: none | model: none | rounds_max: 8 | last_sig: none | sig_count: 0\n"
    b"\n#### Round ledger\n\n#### Ruled out\n- caf\xe9 theory\n"
    b"\n#### DECISIONS (post-hoc review)\n"
)


def verdict(**fields: typing.Any) -> bytes:
    return json.dumps(fields).encode()


def without(flag: str) -> list[str]:
    """`BASE_ARGV` with one flag and its value removed."""
    argv: list[str] = []
    skip = False
    for token in BASE_ARGV:
        if skip:
            skip = False
            continue
        if token == flag:
            skip = True
            continue
        argv.append(token)
    return argv


# name -> argv, the fixture files it needs, and the environment it runs under
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "a-post-when-there-is-no-comment-yet": {},
    "a-patch-when-the-comment-exists": {"argv": [*BASE_ARGV, "--comment-id", "9001"]},
    "the-previous-body-is-carried-forward": {
        "argv": [
            *BASE_ARGV,
            "--body",
            "previous.md",
            "--ledger",
            "r2 | run 555 | commit cafe | did more",
        ],
        "files": {"previous.md": PREVIOUS_BODY},
    },
    "a-verdict-becomes-one-bullet-per-entry": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json"],
        "files": {
            "verdict.json": verdict(
                ruled_out=["not the cache", "not the clock\nsecond line", "third"],
                decisions=["kept the retry", "dropped the flag"],
            )
        },
    },
    "a-mistyped-verdict-path": {"argv": [*BASE_ARGV, "--verdict", "nope.json"]},
    "an-empty-verdict-file": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json"],
        "files": {"verdict.json": b""},
    },
    "a-non-string-ruled-out-entry": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json"],
        "files": {"verdict.json": verdict(ruled_out=["fine", 7])},
    },
    "a-malformed-verdict-file": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json"],
        "files": {"verdict.json": b"{truncated"},
    },
    "a-dry-run": {"argv": [*BASE_ARGV, "--dry-run"]},
    "a-dry-run-with-a-comment-id": {"argv": [*BASE_ARGV, "--dry-run", "--comment-id", "9001"]},
    "body-bytes-are-not-decoded": {
        "argv": [*BASE_ARGV, "--dry-run", "--body", "previous.md"],
        "files": {"previous.md": RAW_BYTE_BODY},
    },
    "the-stage-flag-unset": {"env": {"AUTOPILOT_ALLOW_STATE": ""}},
    "the-stage-flag-false": {"env": {"AUTOPILOT_ALLOW_STATE": "false"}},
    "the-stage-flag-uppercase": {"env": {"AUTOPILOT_ALLOW_STATE": "TRUE"}},
    "the-stage-flag-truthy": {"env": {"AUTOPILOT_ALLOW_STATE": "1"}},
    "no-rounds-max": {"argv": without("--rounds-max")},
    "a-failing-gh": {"env": {"FAKE_GH_RC": "4", "FAKE_GH_STDERR": "gh: fake auth failure\n"}},
    "renderer-chatter-reaches-fd-2": {
        "argv": [*BASE_ARGV, "--dry-run", "--body", "olddir"],
        "files": {"olddir/keep": b"x"},
    },
}

REQUIRED_FLAGS = ("--pr", "--repo", "--state", "--round", "--head", "--last-run")
for _flag in REQUIRED_FLAGS:
    CASE_KW["missing%s" % _flag] = {"argv": without(_flag)}

CASES = tuple(CASE_KW)


def stub_bin(base: pathlib.Path) -> str:
    """A directory holding the fake `gh`, prepended to the real PATH.

    PREPENDED rather than curated down to a symlink farm, because the subject reaches for a long tail of coreutils through its renderer (dirname, uname, tr, mktemp, awk, jq, wc, grep, sed). The safety property is therefore RESOLUTION ORDER, and it is asserted rather than assumed: see `test_the_fake_gh_is_the_gh`.
    """
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    fake = stub / "gh"
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def decode(raw: bytes) -> str:
    """Bytes as a golden can hold them. See the module docstring on what this costs."""
    return raw.decode("utf-8", errors="backslashreplace")


def run(subject: pathlib.Path, base: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    """One subject, once, over this case's own tree."""
    kw = CASE_KW[name]
    base.mkdir(parents=True, exist_ok=True)
    for rel, body in (kw.get("files") or {}).items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    call_log = base / "gh-calls.log"
    call_log.write_text("", encoding="utf-8")
    body_seen = base / "gh-body.md"
    env = {
        "PATH": stub_bin(base),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GH_LOG": str(call_log),
        "FAKE_GH_BODY": str(body_seen),
        # A leaked real `gh` would fail auth rather than write anything.
        "GH_TOKEN": "not-a-real-token",
        "GH_CONFIG_DIR": str(base / "gh-config"),
        "AUTOPILOT_ALLOW_STATE": "true",
    }
    env.update(kw.get("env") or {})
    runner = shutil.which("bash") or "/bin/bash" if subject.suffix == ".sh" else sys.executable
    proc = subprocess.run(
        [runner, str(subject), *kw.get("argv", BASE_ARGV)],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )
    return (
        proc.returncode,
        decode(proc.stdout),
        decode(proc.stderr),
        decode(call_log.read_bytes()),
        decode(body_seen.read_bytes()) if body_seen.exists() else NO_BODY,
    )


def render(code: int, stdout: str, stderr: str, calls: str, body: str) -> str:
    return "%s%s%s%s%s\n" % (
        frozen.render(code, stdout, stderr),
        CALLS_MARKER,
        calls,
        BODY_MARKER,
        body,
    )


def recorded(name: str) -> tuple[int, str, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, rest = rest.split(CALLS_MARKER, 1)
    calls, body = rest.split(BODY_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, calls, body.removesuffix("\n")


def lines(calls: str) -> list[str]:
    return [line for line in calls.splitlines() if line]


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    want = recorded(name)
    got = run(PORT, tmp_path / "port", name)
    labels = ("exit", "stdout", "stderr", "gh calls", "gh body")
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%r\n--- port ---\n%r" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_post_when_there_is_no_comment_yet() -> None:
    """The create arm: POST to the issue's comment collection."""
    code, stdout, stderr, calls, body = recorded("a-post-when-there-is-no-comment-yet")
    assert code == 0
    assert stdout == ""
    assert lines(calls) == [
        "api\t--method\tPOST\trepos/acme/widget/issues/42/comments\t-F\tbody=@<work>/body.md"
    ], calls
    assert body.startswith("### Autopilot state (machine-maintained, do not edit)\n")
    assert "round: 2/8" in body
    assert "state comment POST to repos/acme/widget/issues/42/comments" in stderr


def test_patch_when_the_comment_exists() -> None:
    """The update arm, which is what makes this idempotent: the same comment is rewritten in place rather than a second one appearing per round."""
    code, _, stderr, calls, body = recorded("a-patch-when-the-comment-exists")
    assert code == 0
    assert lines(calls) == [
        "api\t--method\tPATCH\trepos/acme/widget/issues/comments/9001\t-F\tbody=@<work>/body.md"
    ], calls
    assert body != NO_BODY
    assert "state comment PATCH to repos/acme/widget/issues/comments/9001" in stderr


def test_the_previous_body_is_carried_forward() -> None:
    """Round 2 renders round 1's ledger and ruled-out lines again, and does NOT close the campaign that round 1 opened, because `--campaign` is absent."""
    code, _, _, _, body = recorded("the-previous-body-is-carried-forward")
    assert code == 0
    assert "r1 | run 111" in body
    assert "r2 | run 555" in body
    assert "- the cache theory" in body
    assert "- kept the retry" in body
    assert "campaign: open" in body, (
        "the campaign was closed by a round that said nothing about it; the "
        "optional flags are being passed unconditionally"
    )


def test_the_verdict_becomes_one_bullet_per_entry() -> None:
    """The anti-thrash memory only works if it records more than the first entry, and a multi-line entry must collapse to ONE line."""
    code, _, _, _, body = recorded("a-verdict-becomes-one-bullet-per-entry")
    assert code == 0
    assert "- not the cache" in body
    assert "- not the clock second line" in body, "the newline did not collapse to a space"
    assert "- third" in body
    assert "- kept the retry" in body
    assert "- dropped the flag" in body


def test_a_mistyped_verdict_path_is_silent() -> None:
    """PRESERVED DEFECT. `--verdict` is `[[ -n && -s ]]`-checked, never `require_file`-checked, so a path that does not exist renders empty sections and exits 0. If this ever starts refusing, this recording goes red first."""
    code, _, stderr, _, body = recorded("a-mistyped-verdict-path")
    assert code == 0, "the mistyped path was refused; the hazard is fixed, update the port"
    assert "nope.json" not in stderr
    assert "#### Ruled out\n\n" in body


def test_an_empty_verdict_file_is_also_silent() -> None:
    """`-s` is a SIZE test, which is the right one: an empty file is the shape a failed validator leaves behind."""
    assert recorded("an-empty-verdict-file")[0] == 0


def test_a_non_string_ruled_out_entry_kills_the_write() -> None:
    """PRESERVED DEFECT. `gsub` refuses a number, jq exits 5, `set -e` takes the state write with it, so the round runs UNRECORDED, which is the one outcome this script exists to prevent."""
    code, _, stderr, calls, _ = recorded("a-non-string-ruled-out-entry")
    assert code == 5, "jq's runtime status is 5"
    assert "cannot be matched, as it is not a string" in stderr
    assert lines(calls) == [], "a comment was written despite the failure"


def test_a_malformed_verdict_file_fails_with_jqs_own_words() -> None:
    code, _, stderr, calls, _ = recorded("a-malformed-verdict-file")
    assert code == 5
    assert stderr.startswith("jq: parse error:")
    assert lines(calls) == []


def test_dry_run_writes_nothing_and_prints_the_body() -> None:
    """The comment the operator actually reads, exercisable offline."""
    code, stdout, stderr, calls, body = recorded("a-dry-run")
    assert code == 0
    assert lines(calls) == [], "a dry run called gh"
    assert body == NO_BODY
    assert stdout.startswith("### Autopilot state")
    assert "dry-run: would write the state comment for PR #42 (comment id 'none')" in stderr
    assert "(comment id '9001')" in recorded("a-dry-run-with-a-comment-id")[2]


def test_body_bytes_are_not_decoded() -> None:
    """A carried-over line that is not valid UTF-8 must survive the round trip. The comment carries model-authored text, and a port that decoded would fail the round on a stray byte the twin passed through."""
    code, stdout, _, _, _ = recorded("body-bytes-are-not-decoded")
    assert code == 0
    assert "caf\\xe9 theory" in stdout, "the stray byte did not survive"


def test_the_stage_flag_fails_closed() -> None:
    """Absent is off; only the exact string `true` arms it."""
    for name in (
        "the-stage-flag-unset",
        "the-stage-flag-false",
        "the-stage-flag-uppercase",
        "the-stage-flag-truthy",
    ):
        code, _, stderr, calls, _ = recorded(name)
        assert code == 1, name
        assert "stage-flag-disabled" in stderr, name
        assert lines(calls) == [], "the write happened with the stage flag off"


def test_usage_refusals() -> None:
    """The six required flags, each dropped in turn. `--body`, `--rounds-max`, `--comment-id` and `--verdict` are NOT required, and that is pinned too."""
    for flag in REQUIRED_FLAGS:
        code, _, stderr, calls, _ = recorded("missing%s" % flag)
        assert code == 2, "%s: expected the usage refusal" % flag
        assert "usage: update-state.sh" in stderr
        assert lines(calls) == []
    code, _, _, _, body = recorded("no-rounds-max")
    assert code == 0
    assert "round: 2/0" in body


def test_a_failing_gh_is_never_a_success() -> None:
    """Three attempts, the warnings between them, the indented child stderr, and exit 1: the swallowed-failure shape `_gh_probe` exists to end.

    SLOW ON PURPOSE (9 seconds): the retry sleeps are 3s then 6s, and a port that dropped them would stop being a retry past a rate limit.
    """
    code, _, stderr, calls, _ = recorded("a-failing-gh")
    assert code == 1
    assert (
        lines(calls)
        == ["api\t--method\tPOST\trepos/acme/widget/issues/42/comments\t-F\tbody=@<work>/body.md"]
        * 3
    ), "not three attempts"
    assert stderr.count("retrying...") == 2
    assert "gh failed after 3 attempts (last exit 4)." in stderr
    assert "    gh: fake auth failure" in stderr
    assert "state comment POST to" not in stderr, "the success line was printed after a failure"


def test_renderer_stderr_reaches_fd_2() -> None:
    """The renderer is spawned, not re-implemented, so its diagnostics have to arrive on this process's stderr. A DIRECTORY as `--body` makes awk warn without failing, which is a cheap way to prove the passthrough."""
    code, _, stderr, _, _ = recorded("renderer-chatter-reaches-fd-2")
    assert code == 0
    assert stderr.count("is a directory: skipped") == 5


def test_the_fake_gh_is_the_gh(tmp_path: pathlib.Path) -> None:
    """CONTROL for the whole file. If the stub ever stops winning the PATH lookup, every case above would be talking to the real GitHub CLI."""
    path = stub_bin(tmp_path)
    resolved = shutil.which("gh", path=path)
    assert resolved == str(tmp_path / "bin" / "gh"), (
        "the fake gh does not win the PATH lookup: %r" % resolved
    )


def test_pure_helpers_are_exercised_directly() -> None:
    """`endpoint_for` and `render_args` without a subprocess."""
    assert us.endpoint_for("o/r", "5", "") == ("repos/o/r/issues/5/comments", "POST")
    assert us.endpoint_for("o/r", "5", "77") == ("repos/o/r/issues/comments/77", "PATCH")
    argv = us.render_args({"ARG_STATE": "fixing", "ARG_ROUND": "2"}, "/w")
    assert argv[0] == "render"
    assert "--body" in argv
    assert argv[argv.index("--body") + 1] == "/dev/null"
    assert argv[argv.index("--round") + 1] == "2/0"
    assert "--campaign" not in argv, "an absent optional flag must stay absent"
    argv = us.render_args({"ARG_ROUND": "2", "ARG_ROUNDS_MAX": "8", "ARG_CAMPAIGN": "open"}, "/w")
    assert argv[argv.index("--round") + 1] == "2/8"
    assert argv[argv.index("--campaign") + 1] == "open"
    assert argv[argv.index("--rounds-max") + 1] == "8"


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def plant_tree(root: pathlib.Path) -> pathlib.Path:
    """A `.ci` shaped from symlinks, with one writable slot for a mutant.

    The port resolves its renderer from its OWN file location and hands the child a `PYTHONPATH` derived the same way, so a mutant dropped in an empty directory finds neither. Every entry of the real package is symlinked in and only `mutant.py` is a real file, which keeps the fixture a few hundred bytes and keeps the tracked tree read-only.
    """
    package = root / ".ci" / "rediacc_ci"
    here = package / "autopilot"
    here.mkdir(parents=True)
    for entry in sorted((ROOT / ".ci" / "rediacc_ci").iterdir()):
        if entry.name != "autopilot":
            (package / entry.name).symlink_to(entry)
    for entry in sorted((ROOT / ".ci" / "rediacc_ci" / "autopilot").iterdir()):
        (here / entry.name).symlink_to(entry)
    return here / "mutant.py"


def test_a_planted_unconditional_campaign_flag_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Pass `--campaign none` to the renderer on a round that said nothing about the campaign.

    An omitted optional flag means "carry the previous value forward", so a mutant that supplies one closes a live campaign.

    Nothing on either stream says so, the endpoint and the method are unchanged, and only the `--- gh body ---` section moves.

    The mutant is a throwaway copy and the tracked port is never touched, but it cannot live just anywhere: it resolves its renderer and its own `PYTHONPATH` from its file location, so `plant_tree` builds the two directories it needs out of symlinks to the real ones.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = '        value = args.get(key, "")\n        if value:\n'
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(
        anchor,
        '        value = args.get(key, "") or ("none" if flag == "--campaign" else "")\n'
        "        if value:\n",
    )

    mutant = plant_tree(tmp_path / "plant")
    mutant.write_text(mutated, encoding="utf-8")

    name = "the-previous-body-is-carried-forward"
    planted = run(mutant, tmp_path / "planted", name)
    want = recorded(name)
    assert planted[0] == want[0] == 0, "the mutant refused instead of closing the campaign"
    assert "campaign: open" in want[4], "the recorded corpus moved"
    assert "campaign: open" not in planted[4], "the plant did not close the campaign"
    assert planted[3] == want[3], "the plant was supposed to leave the gh call alone"

    compare(tmp_path, name)
    assert PORT.read_text(encoding="utf-8") == original

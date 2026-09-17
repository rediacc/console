"""Differential: `rediacc_ci.autopilot.post_escalation` against its twin
`.ci/scripts/autopilot/post-escalation.sh`.

A RECORDING FAKE `gh` ON A PREPENDED PATH, and the fake is the only thing between this file and a real comment on a real pull request. This script's success path is `api --method POST repos/<repo>/issues/<pr>/comments`, and a
case that reached the real binary would post an escalation onto whatever PR the
argument named and then LABEL it, latching a loop nobody armed. Three independent things stop that, because one would be a claim rather than a control:

  1. the stub directory is FIRST on PATH and `shutil.which("gh", path=...)` is
     asserted to resolve to the fake, in `test_the_fake_gh_is_the_gh` -- a
     control that fires if the ordering ever stops working;
  2. every case names a repository that does not exist (`acme/widget`);
  3. `GH_TOKEN` is a fixture string and `GH_CONFIG_DIR` points into the temp
     tree, so a leaked real `gh` would fail auth instead of writing.

THE CALL LOG AND THE BODY BYTES ARE PRIMARY ARTIFACTS. Which endpoint, in which ORDER, and what bytes went up are all invisible in stdout, and the order is the latch: the comment must be posted before the label, so a failed comment leaves the loop unlatched and the next round retries. A stdout-only comparison would be satisfied by a port that logged the right sentence and labelled
without commenting. So every case compares the recorded `gh` argv AND the bytes of the
file behind `-F body=@...`, and the fake rewrites that path to `<work>/body.md`
because the two sides' mktemp directories legitimately differ.

BOTH PRESERVED DEFECTS ARE PINNED BY NAME rather than described in prose: `test_a_mistyped_verdict_path_is_silent` and `test_a_bare_failure_token_names_itself`. If either twin behaviour is ever repaired, the test goes red and the repair gets noticed here first.

K=5 LEDGER: `.ci/shadow/w7p6-post-escalation.observations.jsonl`, recorded in a
disposable scratch git repository outside this checkout.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from rediacc_ci import paths
from rediacc_ci.autopilot import post_escalation as pe

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "post-escalation.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "post_escalation.py"
BASH = shutil.which("bash") or "/bin/bash"

# The recording fake. It rewrites the one volatile argument (the mktemp path
# behind `-F body=@`) and copies the body it was handed, so a case can compare
# the bytes that would have gone to GitHub.
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


def _stub_bin(base: pathlib.Path) -> str:
    """A directory holding the fake `gh`, prepended to the real PATH.

    PREPENDED rather than curated down to a symlink farm, because both subjects reach for a long tail of coreutils through `common.sh` (dirname, uname, tr, mktemp) plus jq, grep and awk. The safety property is therefore RESOLUTION ORDER, and it is asserted rather than assumed -- see `test_the_fake_gh_is_the_gh`.
    """
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    fake = stub / "gh"
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def _run(subject: pathlib.Path, base: pathlib.Path, argv: list[str], env_extra: dict[str, str]):
    call_log = base / "gh-calls.log"
    call_log.write_text("", encoding="utf-8")
    body_seen = base / "gh-body.md"
    env = {
        "PATH": _stub_bin(base),
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
    }
    env.update(env_extra)
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    body = body_seen.read_bytes() if body_seen.exists() else None
    return proc.returncode, proc.stdout, proc.stderr, calls, body


BASE_ARGV = ["--pr", PR, "--repo", REPO, "--title", "the round could not proceed"]


def _sides(
    name: str,
    argv: list[str] | None = None,
    *,
    files: dict[str, bytes] | None = None,
    env: dict[str, str] | None = None,
):
    """Both subjects, one fixture shape, two private trees."""
    argv = list(argv) if argv is not None else list(BASE_ARGV)
    env_extra = {"AUTOPILOT_ALLOW_STATE": "true"}
    env_extra.update(env or {})
    results = []
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            for rel, body in (files or {}).items():
                path = base / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
            results.append(_run(subject, base, argv, env_extra))
    old, new = results
    labels = ("exit", "stdout", "stderr", "gh calls", "gh body")
    for i, label in enumerate(labels):
        assert new[i] == old[i], "%s: %s diverged:\n twin: %r\n port: %r" % (
            name,
            label,
            old[i],
            new[i],
        )
    return old


def verdict(**fields: Any) -> bytes:
    return json.dumps(fields).encode()


COMMENT_CALL = "api\t--method\tPOST\trepos/acme/widget/issues/42/comments\t-F\tbody=@<work>/body.md"
LABEL_CALL = (
    "api\t--method\tPOST\trepos/acme/widget/issues/42/labels\t-f\tlabels[]=autopilot-blocked"
)


def test_the_comment_then_the_label_in_that_order() -> None:
    """The happy path, and THE ORDER IS THE LATCH: an escalation is never
    latched without the words that say why."""
    exit_code, stdout, stderr, calls, body = _sides(
        "post", [*BASE_ARGV, "--reason", "the validator refused three rounds running"]
    )
    assert exit_code == 0
    assert stdout == b"", "the body leaked onto stdout on a real post"
    assert calls == [COMMENT_CALL, LABEL_CALL], calls
    assert body is not None
    assert body.startswith(b"### Autopilot escalation: the round could not proceed\n\n")
    assert b"the validator refused three rounds running\n" in body
    assert b"escalation comment posted on PR #42" in stderr
    assert b"autopilot-blocked applied to PR #42" in stderr


def test_no_label_posts_the_comment_and_leaves_the_labels_alone() -> None:
    exit_code, _, stderr, calls, _ = _sides("no-label", [*BASE_ARGV, "--reason", "r", "--no-label"])
    assert exit_code == 0
    assert calls == [COMMENT_CALL], "the label was applied despite --no-label"
    assert b"autopilot-blocked applied" not in stderr


def test_a_failed_comment_never_latches_the_loop() -> None:
    """THE MOST IMPORTANT REFUSAL IN THE FILE. `gh_retry` fails, `set -e` ends
    the run, and the label write is never reached -- so the next round retries instead of the campaign stopping silently behind a wordless label.

    SLOW ON PURPOSE (9 seconds per side): the retry sleeps are 3s then 6s, and a port that dropped them would stop being a retry past a rate limit.
    """
    exit_code, _, stderr, calls, _ = _sides(
        "comment-fails",
        [*BASE_ARGV, "--reason", "r"],
        env={"FAKE_GH_RC": "4", "FAKE_GH_STDERR": "gh: fake auth failure\n"},
    )
    assert exit_code == 1
    assert calls == [COMMENT_CALL] * 3, "not three attempts, or the label was tried anyway"
    assert LABEL_CALL not in calls, "the loop was latched with no comment explaining it"
    assert stderr.count(b"retrying...") == 2
    assert b"escalation comment: gh failed after 3 attempts (last exit 4)." in stderr
    assert b"    gh: fake auth failure" in stderr
    assert b"escalation comment posted" not in stderr


def test_the_verdict_reason_becomes_the_body() -> None:
    exit_code, _, _, _, body = _sides(
        "verdict-reason",
        [*BASE_ARGV, "--verdict", "verdict.json", "--round", "3"],
        files={"verdict.json": verdict(escalation={"reason": "the fix does not survive CI"})},
    )
    assert exit_code == 0
    assert body is not None
    assert b"Round 3. The loop is latched" in body
    assert b"the fix does not survive CI\n" in body


def test_a_verdict_with_no_reason_says_so_rather_than_posting_nothing() -> None:
    """`//` treats null AND false as absent; that is jq's rule, not Python's."""
    for shape in ({}, {"escalation": None}, {"escalation": {"reason": None}}):
        _, _, _, _, body = _sides(
            "verdict-no-reason",
            [*BASE_ARGV, "--verdict", "verdict.json"],
            files={"verdict.json": verdict(**shape)},
        )
        assert body is not None
        assert b"The round escalated without recording a reason.\n" in body, shape


def test_the_verdict_wins_over_the_reason_flag() -> None:
    """Both supplied: the twin's `if/elif` takes the verdict arm, so a caller
    that passes both gets the model's words, not the harness's."""
    _, _, _, _, body = _sides(
        "verdict-beats-reason",
        [*BASE_ARGV, "--verdict", "verdict.json", "--reason", "harness words"],
        files={"verdict.json": verdict(escalation={"reason": "model words"})},
    )
    assert body is not None
    assert b"model words" in body
    assert b"harness words" not in body


def test_a_mistyped_verdict_path_is_silent() -> None:
    """PRESERVED DEFECT. `--verdict` is `[[ -n && -s ]]`-checked, never
    `require_file`-checked, so a path that does not exist falls through to `--reason` and the model's own words go quietly missing. If this ever starts
    refusing, this test goes red first."""
    exit_code, _, stderr, _, body = _sides(
        "mistyped-verdict",
        [*BASE_ARGV, "--verdict", "nope.json", "--reason", "fallback words"],
    )
    assert exit_code == 0, "the mistyped path was refused; the hazard is fixed, update the port"
    assert b"nope.json" not in stderr
    assert body is not None
    assert b"fallback words\n" in body


def test_an_empty_verdict_file_is_also_silent() -> None:
    """`-s` is a SIZE test, which is the right one: an empty file is the shape a
    failed validator leaves behind."""
    _, _, _, _, body = _sides(
        "empty-verdict",
        [*BASE_ARGV, "--verdict", "verdict.json", "--reason", "fallback words"],
        files={"verdict.json": b""},
    )
    assert body is not None
    assert b"fallback words\n" in body


def test_a_malformed_verdict_dies_with_jqs_own_words_and_writes_nothing() -> None:
    exit_code, _, stderr, calls, _ = _sides(
        "malformed-verdict",
        [*BASE_ARGV, "--verdict", "verdict.json"],
        files={"verdict.json": b"{truncated"},
    )
    assert exit_code == 5, "jq's runtime status is 5"
    assert stderr.startswith(b"jq: parse error:")
    assert calls == [], "an escalation was posted despite the verdict being unreadable"


def test_the_step_class_names_the_failed_stage() -> None:
    for key, phrase in (
        ("restore", b"the trusted-config assert (wall 4)"),
        ("model", b"the model step itself (turn cap, timeout, or a hard error)"),
        ("boundary", b"the harness boundary"),
        ("escalation", b"posting the escalation comment"),
        ("reply", b"answering and resolving the review threads"),
        ("state", b"the state-comment write"),
        ("submodules", b"the submodule push path"),
    ):
        _, _, _, _, body = _sides(
            "steps-%s" % key,
            [*BASE_ARGV, "--steps", "restore=success,%s=failure" % key]
            if key != "restore"
            else [*BASE_ARGV, "--steps", "restore=failure"],
        )
        assert body is not None
        assert b"The round failed in " + phrase in body, key


def test_an_unknown_step_key_is_reported_by_its_raw_name() -> None:
    """The `*)` arm is deliberate: a new stage is never silently unnameable."""
    _, _, _, _, body = _sides("steps-unknown", [*BASE_ARGV, "--steps", "brandnew=failure"])
    assert body is not None
    assert b"The round failed in brandnew.\n" in body


def test_the_first_failure_wins_and_successes_are_skipped() -> None:
    _, _, _, _, body = _sides(
        "steps-first",
        [*BASE_ARGV, "--steps", "restore=success, model=failure ,state=failure"],
    )
    assert body is not None
    assert b"the model step itself" in body
    assert b"the state-comment write" not in body


def test_no_failure_conclusion_is_named_as_such() -> None:
    for steps in ("restore=success,model=success", ",,,", "model=cancelled"):
        _, _, _, _, body = _sides("steps-none", [*BASE_ARGV, "--steps", steps])
        assert body is not None
        assert (
            b"The round failed in an unclassified step "
            b"(no step reported a failure conclusion).\n" in body
        ), steps


def test_a_bare_failure_token_names_itself() -> None:
    """PRESERVED DEFECT. `${pair#*=}` returns the whole token when it holds no
    `=`, so the bare word `failure` matches the test and is then handed to the
    class map as a key, which echoes it back. The comment reads "The round
    failed in failure." """
    _, _, _, _, body = _sides("steps-bare", [*BASE_ARGV, "--steps", "failure"])
    assert body is not None
    assert b"The round failed in failure.\n" in body


def test_the_step_class_rides_alongside_a_reason() -> None:
    """With a reason present the class is an EXTRA line, not the whole message."""
    _, _, _, _, body = _sides(
        "steps-with-reason", [*BASE_ARGV, "--reason", "why", "--steps", "model=failure"]
    )
    assert body is not None
    text = body.decode()
    assert "why\n" in text
    assert "\nFailed step class: the model step itself" in text
    assert text.count("the model step itself") == 1, "the class was printed twice"


def test_a_patch_is_attached_as_data_in_a_fitted_fence() -> None:
    """THE FENCE IS A SECURITY PROPERTY. A patch containing its own ``` run
    would close a three-backtick fence early and promote the remainder --
    untrusted, model-authored text -- from a code block into live markdown."""
    patch = "--- a/README.md\n+++ b/README.md\n+```\n+code\n+```\n"
    _, _, _, _, body = _sides(
        "patch-fence",
        [*BASE_ARGV, "--verdict", "verdict.json"],
        files={"verdict.json": verdict(escalation={"reason": "needs a human", "patch": patch})},
    )
    assert body is not None
    text = body.decode()
    assert "<details><summary>Proposed patch (data, not applied)</summary>\n\n````diff\n" in text
    assert "\n````\n\n</details>\n" in text
    assert "+```\n" in text, "the patch body was not attached verbatim"


def test_a_patch_with_no_backticks_uses_the_three_fence() -> None:
    """`{ grep -oE '`+' || true; }`: no match is the COMMON case and exits 1;
    a pipefail-shaped port would turn it into a failed escalation."""
    exit_code, _, _, _, body = _sides(
        "patch-plain",
        [*BASE_ARGV, "--verdict", "verdict.json"],
        files={
            "verdict.json": verdict(
                escalation={"reason": "r", "patch": "--- a/x\n+++ b/x\n+one line\n"}
            )
        },
    )
    assert exit_code == 0
    assert body is not None
    assert b"\n```diff\n" in body


def test_an_empty_patch_attaches_no_details_block() -> None:
    for shape in ({"reason": "r"}, {"reason": "r", "patch": ""}):
        _, _, _, _, body = _sides(
            "patch-absent",
            [*BASE_ARGV, "--verdict", "verdict.json"],
            files={"verdict.json": verdict(escalation=shape)},
        )
        assert body is not None
        assert b"<details>" not in body, shape


def test_the_run_url_is_the_last_line() -> None:
    _, _, _, _, body = _sides(
        "run-url", [*BASE_ARGV, "--reason", "r", "--run-url", "https://example.invalid/run/9"]
    )
    assert body is not None
    assert body.endswith(b"\nRun log: https://example.invalid/run/9\n")


def test_dry_run_writes_nothing_and_prints_the_body() -> None:
    """The words an operator reads at the moment a campaign stops, exercisable
    offline. A body only ever driven against the live API is a body nobody has
    read."""
    exit_code, stdout, stderr, calls, body = _sides(
        "dry-run", [*BASE_ARGV, "--reason", "r", "--dry-run"]
    )
    assert exit_code == 0
    assert calls == [], "a dry run called gh"
    assert body is None
    assert stdout.startswith(b"### Autopilot escalation: the round could not proceed\n")
    assert b"dry-run: would comment on PR #42 and apply autopilot-blocked" in stderr
    _, _, stderr2, _, _ = _sides(
        "dry-run-no-label", [*BASE_ARGV, "--reason", "r", "--dry-run", "--no-label"]
    )
    assert b"dry-run: would comment on PR #42 and leave the labels alone" in stderr2


def test_body_bytes_are_not_decoded() -> None:
    """The reason is model-authored and need not be valid UTF-8; a port that
    decoded would fail the escalation on a stray byte the twin passed through."""
    exit_code, stdout, _, _, _ = _sides(
        "raw-bytes",
        [*BASE_ARGV, "--verdict", "verdict.json", "--dry-run"],
        files={"verdict.json": b'{"escalation":{"reason":"caf\xc3\xa9 \xe2\x9c\x93 theory"}}'},
    )
    assert exit_code == 0
    assert "café ✓ theory".encode() in stdout


def test_the_stage_flag_fails_closed() -> None:
    """Absent is off; only the exact string `true` arms it. And it is checked
    BEFORE any network call, so a misconfigured stage cannot even read."""
    for name, value in (
        ("unset", None),
        ("false", "false"),
        ("uppercase", "TRUE"),
        ("empty", ""),
        ("truthy", "1"),
    ):
        env = {"AUTOPILOT_ALLOW_STATE": value if value is not None else ""}
        code, _, err, calls, _ = _sides("flag-%s" % name, [*BASE_ARGV, "--reason", "r"], env=env)
        assert code == 1, name
        assert b"stage-flag-disabled" in err
        assert calls == [], "a comment was posted with the stage flag off"


def test_the_stage_flag_is_checked_even_on_a_dry_run() -> None:
    """Unlike `autopilot-push.sh`, this script does NOT exempt a dry run: the
    flag guards the whole script, not only the write. Pinned so a port cannot
    'improve' it into an offline-always tool."""
    code, _, err, _, _ = _sides(
        "flag-dry-run",
        [*BASE_ARGV, "--reason", "r", "--dry-run"],
        env={"AUTOPILOT_ALLOW_STATE": ""},
    )
    assert code == 1
    assert b"stage-flag-disabled" in err


def test_usage_refusals_come_before_the_stage_flag() -> None:
    """The three required flags, each dropped in turn, with the flag OFF: the
    usage message must still win, so a broken invocation is diagnosable."""
    for drop in ("--pr", "--repo", "--title"):
        argv = []
        skip = False
        for token in BASE_ARGV:
            if skip:
                skip = False
                continue
            if token == drop:
                skip = True
                continue
            argv.append(token)
        code, _, err, calls, _ = _sides("missing%s" % drop, argv, env={"AUTOPILOT_ALLOW_STATE": ""})
        assert code == 2, "%s: expected the usage refusal" % drop
        assert b"usage: post-escalation.sh" in err
        assert b"stage-flag-disabled" not in err, "the flag was checked before the usage"
        assert calls == []


def test_the_fake_gh_is_the_gh() -> None:
    """CONTROL for the whole file. If the stub ever stops winning the PATH
    lookup, every case above would be talking to the real GitHub CLI and
    labelling real pull requests."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        path = _stub_bin(base)
        resolved = shutil.which("gh", path=path)
        assert resolved == str(base / "bin" / "gh"), (
            "the fake gh does not win the PATH lookup: %r" % resolved
        )


def test_pure_helpers_are_exercised_directly() -> None:
    """`failed_class`, `step_class`, `longest_backtick_run` and `fence_for`
    without a subprocess. BOTH DIRECTIONS: a case that must classify and a case
    that must not."""
    assert pe.step_class("model").startswith("the model step itself")
    assert pe.step_class("brandnew") == "brandnew"
    assert pe.failed_class("") == pe.NO_FAILURE
    assert pe.failed_class("a=success,b=success") == pe.NO_FAILURE
    assert pe.failed_class("state=failure") == "the state-comment write"
    assert pe.failed_class(" model = failure ") == pe.step_class("model")
    assert pe.failed_class("model=success,state=failure,reply=failure") == "the state-comment write"
    # The bare-token defect, at the unit level too.
    assert pe.failed_class("failure") == "failure"

    assert pe.longest_backtick_run(b"no ticks here") == 0
    assert pe.longest_backtick_run(b"a `b` c ```` d") == 4
    assert pe.fence_for(0) == b"```"
    assert pe.fence_for(2) == b"```"
    # `>=`, not `>`: exactly ``` must widen the fence or it would be closed.
    assert pe.fence_for(3) == b"````"
    assert pe.fence_for(7) == b"`" * 8

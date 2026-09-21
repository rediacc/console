"""`rediacc_ci.autopilot.post_escalation`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/autopilot/post-escalation.sh` and the port over one fixture shape and compared five things per case: exit code, stdout, stderr, the `gh` CALL LOG and the BODY BYTES behind `-F body=@...`.

The K=5 ledger `.ci/shadow/w7p6-post-escalation.observations.jsonl` recorded that comparison over five distinct trees, in a disposable scratch git repository outside this checkout.

Every case now compares against `goldens/post-escalation/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree, and each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

THE BODY IS THE PRODUCT, so the recorded shape carries it as its own `--- body ---` section. Almost nothing this script does is visible in its exit code: the words an operator reads at the moment a campaign stops are the output, and a recording that froze only the streams would have frozen the half nobody reads. A case that never reached `gh` records `<absent>` there, which is how
a dry run and a refusal stay distinguishable from a post with an empty body.

THE CALL LOG IS THE OTHER PRIMARY ARTIFACT, under `--- gh calls ---`. Which endpoint, in which ORDER, is invisible in stdout, and the order is the latch: the comment must be posted before the label, so a failed comment leaves the loop unlatched and the next round retries. A stream-only comparison would be satisfied by a port that logged the right sentence and labelled without
commenting, and by one that applied a label the loop does not watch. The control at the foot of this file plants the second of those.

A RECORDING FAKE `gh` ON A PREPENDED PATH is the only thing between this file and a real comment on a real pull request. The success path is `api --method POST repos/<repo>/issues/<pr>/comments`, and a case that reached the real binary would post an escalation onto whatever PR the argument named and then LABEL it, latching a loop nobody armed. Three independent things stop that,
because one would be a claim rather than a control:

  1. the stub directory is FIRST on PATH and `shutil.which("gh", path=...)` is
     asserted to resolve to the fake, in `test_the_fake_gh_is_the_gh`, a control
     that fires if the ordering ever stops working;
  2. every case names a repository that does not exist (`acme/widget`);
  3. `GH_TOKEN` is a fixture string and `GH_CONFIG_DIR` points into the temp
     tree, so a leaked real `gh` would fail auth instead of writing.

BOTH PRESERVED DEFECTS ARE PINNED BY NAME rather than described in prose: `test_a_mistyped_verdict_path_is_silent` and `test_a_bare_failure_token_names_itself`. If either twin behaviour is ever repaired, the test goes red and the repair gets noticed here first.

NOTHING HERE DIVERGES. Every case is compared byte for byte on all five channels, including the usage refusal and jq's parse error, so this file has no shape-compared arm and no exemption to keep honest.

WHAT IS MASKED, and it is two paths, neither of them the body file. The case's own directory is its `HOME` and its working directory and is rebuilt under a different tempdir name every run, so it becomes `<case>`; the checkout root becomes `<repo>`, so a bash diagnostic naming this worktree stays readable from any other. The `<work>/body.md` that appears in the call log is NOT a
mask: it is the stub's own rewrite of the one volatile argument, the twin's `mktemp -d` directory, which it performs before logging so that the recorded argv is stable while the bytes behind it are still compared in full.

THE BODY IS RECORDED AS UTF-8 TEXT, and one case drives a reason that is not ASCII on purpose. The bytes the twin wrote are UTF-8, so text and bytes are the same comparison here; a case that ever produced a byte outside it would have failed the recording rather than been silently mangled.
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
from rediacc_ci.autopilot import post_escalation as pe
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "post_escalation.py"
SLUG = "post-escalation"

BASH = shutil.which("bash") or "/bin/bash"
PYTHON = sys.executable

CALLS_MARKER = "--- gh calls ---\n"
BODY_MARKER = "--- body ---\n"
ABSENT = "<absent>"

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
BASE_ARGV = ["--pr", PR, "--repo", REPO, "--title", "the round could not proceed"]

COMMENT_CALL = "api\t--method\tPOST\trepos/acme/widget/issues/42/comments\t-F\tbody=@<work>/body.md"
LABEL_CALL = (
    "api\t--method\tPOST\trepos/acme/widget/issues/42/labels\t-f\tlabels[]=autopilot-blocked"
)

PATCH_WITH_FENCE = "--- a/README.md\n+++ b/README.md\n+```\n+code\n+```\n"


def verdict(**fields: typing.Any) -> dict[str, bytes]:
    return {"verdict.json": json.dumps(fields).encode()}


def steps(value: str) -> list[str]:
    return [*BASE_ARGV, "--steps", value]


def _without(flag: str) -> list[str]:
    """BASE_ARGV with one flag and its value dropped."""
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


OFF = {"AUTOPILOT_ALLOW_STATE": ""}

# name -> argv, the files written into the case's own directory, and the environment
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "a-comment-then-a-label": {
        "argv": [*BASE_ARGV, "--reason", "the validator refused three rounds running"]
    },
    "no-label": {"argv": [*BASE_ARGV, "--reason", "r", "--no-label"]},
    "a-failing-comment": {
        "argv": [*BASE_ARGV, "--reason", "r"],
        "env": {"FAKE_GH_RC": "4", "FAKE_GH_STDERR": "gh: fake auth failure\n"},
    },
    "a-verdict-reason": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json", "--round", "3"],
        "files": verdict(escalation={"reason": "the fix does not survive CI"}),
    },
    "a-verdict-with-no-escalation": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json"],
        "files": verdict(),
    },
    "a-verdict-with-a-null-escalation": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json"],
        "files": verdict(escalation=None),
    },
    "a-verdict-with-a-null-reason": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json"],
        "files": verdict(escalation={"reason": None}),
    },
    "a-verdict-and-a-reason-flag": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json", "--reason", "harness words"],
        "files": verdict(escalation={"reason": "model words"}),
    },
    "a-mistyped-verdict-path": {
        "argv": [*BASE_ARGV, "--verdict", "nope.json", "--reason", "fallback words"]
    },
    "an-empty-verdict-file": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json", "--reason", "fallback words"],
        "files": {"verdict.json": b""},
    },
    "a-malformed-verdict": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json"],
        "files": {"verdict.json": b"{truncated"},
    },
    "a-failed-restore-step": {"argv": steps("restore=failure")},
    "a-failed-model-step": {"argv": steps("restore=success,model=failure")},
    "a-failed-boundary-step": {"argv": steps("restore=success,boundary=failure")},
    "a-failed-escalation-step": {"argv": steps("restore=success,escalation=failure")},
    "a-failed-reply-step": {"argv": steps("restore=success,reply=failure")},
    "a-failed-state-step": {"argv": steps("restore=success,state=failure")},
    "a-failed-submodules-step": {"argv": steps("restore=success,submodules=failure")},
    "an-unknown-step-key": {"argv": steps("brandnew=failure")},
    "the-first-failure-wins": {"argv": steps("restore=success, model=failure ,state=failure")},
    "all-steps-successful": {"argv": steps("restore=success,model=success")},
    "only-empty-step-pairs": {"argv": steps(",,,")},
    "a-cancelled-step": {"argv": steps("model=cancelled")},
    "a-bare-failure-token": {"argv": steps("failure")},
    "a-step-class-alongside-a-reason": {
        "argv": [*BASE_ARGV, "--reason", "why", "--steps", "model=failure"]
    },
    "a-patch-with-its-own-fence": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json"],
        "files": verdict(escalation={"reason": "needs a human", "patch": PATCH_WITH_FENCE}),
    },
    "a-patch-with-no-backticks": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json"],
        "files": verdict(escalation={"reason": "r", "patch": "--- a/x\n+++ b/x\n+one line\n"}),
    },
    "a-verdict-with-no-patch": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json"],
        "files": verdict(escalation={"reason": "r"}),
    },
    "a-verdict-with-an-empty-patch": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json"],
        "files": verdict(escalation={"reason": "r", "patch": ""}),
    },
    "a-run-url": {
        "argv": [*BASE_ARGV, "--reason", "r", "--run-url", "https://example.invalid/run/9"]
    },
    "a-dry-run": {"argv": [*BASE_ARGV, "--reason", "r", "--dry-run"]},
    "a-dry-run-with-no-label": {"argv": [*BASE_ARGV, "--reason", "r", "--dry-run", "--no-label"]},
    "a-reason-that-is-not-ascii": {
        "argv": [*BASE_ARGV, "--verdict", "verdict.json", "--dry-run"],
        "files": {"verdict.json": b'{"escalation":{"reason":"caf\xc3\xa9 \xe2\x9c\x93 theory"}}'},
    },
    "the-stage-flag-empty": {"argv": [*BASE_ARGV, "--reason", "r"], "env": OFF},
    "the-stage-flag-false": {
        "argv": [*BASE_ARGV, "--reason", "r"],
        "env": {"AUTOPILOT_ALLOW_STATE": "false"},
    },
    "the-stage-flag-uppercase-true": {
        "argv": [*BASE_ARGV, "--reason", "r"],
        "env": {"AUTOPILOT_ALLOW_STATE": "TRUE"},
    },
    "the-stage-flag-one": {
        "argv": [*BASE_ARGV, "--reason", "r"],
        "env": {"AUTOPILOT_ALLOW_STATE": "1"},
    },
    "the-stage-flag-on-a-dry-run": {
        "argv": [*BASE_ARGV, "--reason", "r", "--dry-run"],
        "env": OFF,
    },
    "without-a-pr": {"argv": _without("--pr"), "env": OFF},
    "without-a-repo": {"argv": _without("--repo"), "env": OFF},
    "without-a-title": {"argv": _without("--title"), "env": OFF},
}

CASES = tuple(CASE_KW)


def stub_bin(base: pathlib.Path) -> str:
    """A directory holding the fake `gh`, prepended to the real PATH.

    PREPENDED rather than curated down to a symlink farm, because both subjects reach for a long tail of coreutils through `common.sh` (dirname, uname, tr, mktemp) plus jq, grep and awk. The safety property is therefore RESOLUTION ORDER, and it is asserted rather than assumed: see `test_the_fake_gh_is_the_gh`.
    """
    stub = base / "bin"
    stub.mkdir(parents=True, exist_ok=True)
    fake = stub / "gh"
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def run(subject: pathlib.Path, base: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    """One subject, once, over this case's own tree."""
    kw = CASE_KW[name]
    base.mkdir(parents=True, exist_ok=True)
    for rel, data in (kw.get("files") or {}).items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
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
    runner = [BASH] if subject.suffix == ".sh" else [PYTHON]
    proc = subprocess.run(
        [*runner, str(subject), *kw["argv"]],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )

    def mask(text: str) -> str:
        return text.replace(str(base), "<case>").replace(str(ROOT), "<repo>")

    body = body_seen.read_text(encoding="utf-8") if body_seen.exists() else ABSENT
    return (
        proc.returncode,
        mask(proc.stdout),
        mask(proc.stderr),
        mask(call_log.read_text(encoding="utf-8")),
        mask(body),
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


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    return run(PORT, tmp_path / name, name)


def lines(calls: str) -> list[str]:
    return [line for line in calls.splitlines() if line]


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    want = recorded(name)
    got = port(tmp_path, name)
    labels = ("exit code", "stdout", "stderr", "the gh CALL LOG", "the body bytes")
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%s\n--- port ---\n%s" % (
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


def test_the_fake_gh_is_the_gh(tmp_path: pathlib.Path) -> None:
    """CONTROL for the whole file. If the stub ever stops winning the PATH lookup, every case above would be talking to the real GitHub CLI and labelling real pull requests."""
    path = stub_bin(tmp_path)
    resolved = shutil.which("gh", path=path)
    assert resolved == str(tmp_path / "bin" / "gh"), (
        "the fake gh does not win the PATH lookup: %r" % resolved
    )


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_the_comment_then_the_label_in_that_order() -> None:
    """The happy path, and THE ORDER IS THE LATCH: an escalation is never latched without the words that say why."""
    code, stdout, stderr, calls, body = recorded("a-comment-then-a-label")
    assert code == 0
    assert stdout == "", "the body leaked onto stdout on a real post"
    assert lines(calls) == [COMMENT_CALL, LABEL_CALL], calls
    assert body.startswith("### Autopilot escalation: the round could not proceed\n\n")
    assert "the validator refused three rounds running\n" in body
    assert "escalation comment posted on PR #42" in stderr
    assert "autopilot-blocked applied to PR #42" in stderr


def test_no_label_posts_the_comment_and_leaves_the_labels_alone() -> None:
    code, _, stderr, calls, _ = recorded("no-label")
    assert code == 0
    assert lines(calls) == [COMMENT_CALL], "the label was applied despite --no-label"
    assert "autopilot-blocked applied" not in stderr


def test_a_failed_comment_never_latches_the_loop() -> None:
    """THE MOST IMPORTANT REFUSAL IN THE FILE. `gh_retry` fails, `set -e` ends the run, and the label write is never reached, so the next round retries instead of the campaign stopping silently behind a wordless label.

    SLOW ON PURPOSE: the retry sleeps are 3s then 6s, and a port that dropped them would stop being a retry past a rate limit.
    """
    code, _, stderr, calls, _ = recorded("a-failing-comment")
    assert code == 1
    assert lines(calls) == [COMMENT_CALL] * 3, "not three attempts, or the label was tried anyway"
    assert LABEL_CALL not in lines(calls), "the loop was latched with no comment explaining it"
    assert stderr.count("retrying...") == 2
    assert "escalation comment: gh failed after 3 attempts (last exit 4)." in stderr
    assert "    gh: fake auth failure" in stderr
    assert "escalation comment posted" not in stderr


def test_the_verdict_reason_becomes_the_body() -> None:
    code, _, _, _, body = recorded("a-verdict-reason")
    assert code == 0
    assert "Round 3. The loop is latched" in body
    assert "the fix does not survive CI\n" in body


def test_a_verdict_with_no_reason_says_so_rather_than_posting_nothing() -> None:
    """`//` treats null AND false as absent; that is jq's rule, not Python's."""
    for name in (
        "a-verdict-with-no-escalation",
        "a-verdict-with-a-null-escalation",
        "a-verdict-with-a-null-reason",
    ):
        assert "The round escalated without recording a reason.\n" in recorded(name)[4], name


def test_the_verdict_wins_over_the_reason_flag() -> None:
    """Both supplied: the twin's `if/elif` took the verdict arm, so a caller that passes both gets the model's words, not the harness's."""
    body = recorded("a-verdict-and-a-reason-flag")[4]
    assert "model words" in body
    assert "harness words" not in body


def test_a_mistyped_verdict_path_is_silent() -> None:
    """PRESERVED DEFECT. `--verdict` is `[[ -n && -s ]]`-checked, never `require_file`-checked, so a path that does not exist falls through to `--reason` and the model's own words go quietly missing. If this ever starts refusing, this test goes red first."""
    code, _, stderr, _, body = recorded("a-mistyped-verdict-path")
    assert code == 0, "the mistyped path was refused; the hazard is fixed, update the port"
    assert "nope.json" not in stderr
    assert "fallback words\n" in body


def test_an_empty_verdict_file_is_also_silent() -> None:
    """`-s` is a SIZE test, which is the right one: an empty file is the shape a failed validator leaves behind."""
    assert "fallback words\n" in recorded("an-empty-verdict-file")[4]


def test_a_malformed_verdict_dies_with_jqs_own_words_and_writes_nothing() -> None:
    code, _, stderr, calls, _ = recorded("a-malformed-verdict")
    assert code == 5, "jq's runtime status is 5"
    assert stderr.startswith("jq: parse error:")
    assert calls == "", "an escalation was posted despite the verdict being unreadable"


def test_the_step_class_names_the_failed_stage() -> None:
    for name, phrase in (
        ("a-failed-restore-step", "the trusted-config assert (wall 4)"),
        ("a-failed-model-step", "the model step itself (turn cap, timeout, or a hard error)"),
        ("a-failed-boundary-step", "the harness boundary"),
        ("a-failed-escalation-step", "posting the escalation comment"),
        ("a-failed-reply-step", "answering and resolving the review threads"),
        ("a-failed-state-step", "the state-comment write"),
        ("a-failed-submodules-step", "the submodule push path"),
    ):
        assert "The round failed in " + phrase in recorded(name)[4], name


def test_an_unknown_step_key_is_reported_by_its_raw_name() -> None:
    """The `*)` arm is deliberate: a new stage is never silently unnameable."""
    assert "The round failed in brandnew.\n" in recorded("an-unknown-step-key")[4]


def test_the_first_failure_wins_and_successes_are_skipped() -> None:
    body = recorded("the-first-failure-wins")[4]
    assert "the model step itself" in body
    assert "the state-comment write" not in body


def test_no_failure_conclusion_is_named_as_such() -> None:
    for name in ("all-steps-successful", "only-empty-step-pairs", "a-cancelled-step"):
        assert (
            "The round failed in an unclassified step "
            "(no step reported a failure conclusion).\n" in recorded(name)[4]
        ), name


def test_a_bare_failure_token_names_itself() -> None:
    """PRESERVED DEFECT. `${pair#*=}` returns the whole token when it holds no `=`, so the bare word `failure` matches the test and is then handed to the class map as a key, which echoes it back. The comment reads "The round failed in failure."."""
    assert "The round failed in failure.\n" in recorded("a-bare-failure-token")[4]


def test_the_step_class_rides_alongside_a_reason() -> None:
    """With a reason present the class is an EXTRA line, not the whole message."""
    body = recorded("a-step-class-alongside-a-reason")[4]
    assert "why\n" in body
    assert "\nFailed step class: the model step itself" in body
    assert body.count("the model step itself") == 1, "the class was printed twice"


def test_a_patch_is_attached_as_data_in_a_fitted_fence() -> None:
    """THE FENCE IS A SECURITY PROPERTY. A patch containing its own ``` run would close a three-backtick fence early and promote the remainder, untrusted model-authored text, from a code block into live markdown."""
    body = recorded("a-patch-with-its-own-fence")[4]
    assert "<details><summary>Proposed patch (data, not applied)</summary>\n\n````diff\n" in body
    assert "\n````\n\n</details>\n" in body
    assert "+```\n" in body, "the patch body was not attached verbatim"


def test_a_patch_with_no_backticks_uses_the_three_fence() -> None:
    """`{ grep -oE '`+' || true; }`: no match is the COMMON case and exits 1; a pipefail-shaped port would turn it into a failed escalation."""
    code, _, _, _, body = recorded("a-patch-with-no-backticks")
    assert code == 0
    assert "\n```diff\n" in body


def test_an_empty_patch_attaches_no_details_block() -> None:
    for name in ("a-verdict-with-no-patch", "a-verdict-with-an-empty-patch"):
        assert "<details>" not in recorded(name)[4], name


def test_the_run_url_is_the_last_line() -> None:
    assert recorded("a-run-url")[4].endswith("\nRun log: https://example.invalid/run/9\n")


def test_dry_run_writes_nothing_and_prints_the_body() -> None:
    """The words an operator reads at the moment a campaign stops, exercisable offline. A body only ever driven against the live API is a body nobody has read."""
    code, stdout, stderr, calls, body = recorded("a-dry-run")
    assert code == 0
    assert calls == "", "a dry run called gh"
    assert body == ABSENT, "a dry run wrote a body file"
    assert stdout.startswith("### Autopilot escalation: the round could not proceed\n")
    assert "dry-run: would comment on PR #42 and apply autopilot-blocked" in stderr
    assert (
        "dry-run: would comment on PR #42 and leave the labels alone"
        in recorded("a-dry-run-with-no-label")[2]
    )


def test_body_bytes_are_not_decoded() -> None:
    """The reason is model-authored and need not be ASCII; a port that mangled it would fail the escalation on a stray byte the twin passed through."""
    code, stdout, _, _, _ = recorded("a-reason-that-is-not-ascii")
    assert code == 0
    assert "café ✓ theory" in stdout


def test_the_stage_flag_fails_closed() -> None:
    """Absent is off; only the exact string `true` arms it. And it is checked BEFORE any network call, so a misconfigured stage cannot even read."""
    for name in (
        "the-stage-flag-empty",
        "the-stage-flag-false",
        "the-stage-flag-uppercase-true",
        "the-stage-flag-one",
    ):
        code, _, stderr, calls, _ = recorded(name)
        assert code == 1, name
        assert "stage-flag-disabled" in stderr
        assert calls == "", "a comment was posted with the stage flag off"


def test_the_stage_flag_is_checked_even_on_a_dry_run() -> None:
    """Unlike `autopilot-push.sh`, this script does NOT exempt a dry run: the flag guards the whole script, not only the write. Pinned so a port cannot improve it into an offline-always tool."""
    code, _, stderr, _, _ = recorded("the-stage-flag-on-a-dry-run")
    assert code == 1
    assert "stage-flag-disabled" in stderr


def test_usage_refusals_come_before_the_stage_flag() -> None:
    """The three required flags, each dropped in turn, with the flag OFF: the usage message must still win, so a broken invocation is diagnosable."""
    for name in ("without-a-pr", "without-a-repo", "without-a-title"):
        code, _, stderr, calls, _ = recorded(name)
        assert code == 2, "%s: expected the usage refusal" % name
        assert "usage: post-escalation.sh" in stderr
        assert "stage-flag-disabled" not in stderr, "the flag was checked before the usage"
        assert calls == ""


def test_pure_helpers_are_exercised_directly() -> None:
    """`failed_class`, `step_class`, `longest_backtick_run` and `fence_for` without a subprocess. BOTH DIRECTIONS: a case that must classify and a case that must not."""
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


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_change_of_the_latch_label_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the section that would otherwise be decoration.

    `autopilot-blocked` is the label the loop watches; applying any other one ends the round having announced a latch that does not latch, and the campaign keeps running until a human notices a label nobody acts on. The fake answers the same bytes either way and the success line is a separate literal, so the exit code, stdout, stderr and the body are identical and only the `--- gh
    calls ---` section sees the change. The mutation runs from a throwaway copy of the module, and the tracked port is never touched.
    """
    # ASSEMBLED, NEVER WRITTEN OUT. `check:ci-label-refs` scans the tree for exactly the shape `labels[]=<name>` and reads every literal it finds as a real label reference, so spelling the mutant's label here would have this instrument file report an undeclared label named after its own plant. The gate solves the same problem for itself the same way, at
    # `label_references.py`'s `SELFTEST_LABEL`.
    latch = "autopilot" + "-blocked"
    other = "bl" + "ocked"
    original = PORT.read_text(encoding="utf-8")
    anchor = '                "labels[]=%s",\n' % latch
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutant_source = original.replace(anchor, '                "labels[]=%s",\n' % other)

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(mutant_source, encoding="utf-8")

    name = "a-comment-then-a-label"
    want = recorded(name)
    assert LABEL_CALL in want[3], "the recorded corpus moved"
    planted = run(mutant, tmp_path / "planted", name)
    assert LABEL_CALL not in planted[3], "the plant did not change the call log"
    assert ("labels[]=%s" % other) in planted[3]
    for index in (0, 1, 2, 4):
        assert planted[index] == want[index], "the plant was supposed to be invisible here"

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original

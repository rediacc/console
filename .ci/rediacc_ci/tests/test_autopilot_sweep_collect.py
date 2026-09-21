"""`rediacc_ci.autopilot.sweep_collect`, driven against the bytes its bash twin produced.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/autopilot/sweep-collect.sh` and the port over one stubbed PATH and compared SIX artifacts per case: exit code, stdout, stderr, the `gh` call SEQUENCE, the whole `--work` tree as bytes per relative path, and the `--out` file.

The ledger `.ci/shadow/w7p6-sweep-collect.observations.jsonl` holds 11 rows of that comparison, recorded in a disposable scratch git repository outside this checkout, since `shadow-gate.ts --record` refuses a dirty tree and this checkout is never clean. Every case now compares against `goldens/sweep-collect/`, which holds the twin's OWN recorded bytes, captured on its last day in
the tree, and each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

SIX ARTIFACTS, SO THE RECORDED SHAPE CARRIES THREE SECTIONS BEYOND THE TWO STREAMS. This script's visible result is neither stdout nor stderr: it is the `--out` file, the `--work` tree (`prs.json`, `label-armed.txt`, `campaign-armed.txt` and one raw plus one transformed dump per PR) under `--- work ---`, and the ordered `gh` invocations under `--- gh calls ---`. A port that printed
the right summary while requesting the wrong pages, or while writing `comments/7.json` with different bytes, would sail past a stream comparison. The work tree is recorded per relative path because the transformed dumps are read by the campaign scanner and their formatting is jq's.

THE CAMPAIGN SCANNER RAN FOR REAL on both sides, unstubbed. It is pure (files in, PR numbers out) and it carries the TRUST RULE this collector depends on: a campaign counts only when the comment's author is the bot AND the body starts with the exact state header. The twin spawned `sweep-campaigns.sh` and the port spawns the sibling port by path, so the fixture comments are shaped
like real state comments and `test_a_lookalike_campaign_comment_is_not_armed` records the untrusted case rather than asserting it about the collector alone.

A RECORDING FAKE `gh` ON A STUB PATH is the whole apparatus: nothing here reaches the network, and the real `gh` on this machine is never on the PATH handed to the subject. `test_the_stub_path_has_no_real_gh` is the control for that claim rather than a comment asserting it.

TWO CASES COST NINE SECONDS EACH AND ARE WORTH IT. `_gh_probe` sleeps 3 then 6 seconds between its three attempts, so a case that drives a `gh` failure to exhaustion takes nine. They are the only cases that prove the retry loop, the final `gh failed after 3 attempts` line and the four-space stderr replay agree, and one of them is also the only case that proves `jq -e`'s null rule:
a body of `null` is UNUSABLE, not an answer.

THE ONE SHAPE-COMPARED CASE is `--out` in a directory that does not exist, where bash's redirection diagnostic carried the twin's own path and line number. Everything else on that stream is compared byte for byte, including the summary line with its EMPTY count, which is defect 2 and would otherwise be the easiest thing in the file to lose.

WHAT IS MASKED, and it is two paths. The case's own directory is its `HOME` and its working directory and is rebuilt under a different tempdir name every run, so it becomes `<case>`; the checkout root becomes `<repo>`, because the shape-compared diagnostic names the twin's own file. Every flag a case passes is RELATIVE on purpose, so `work/prs.json` and `nodir/out.txt` appear in
the recordings exactly as the subject was given them.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.autopilot import sweep_collect as sc
from rediacc_ci.tests import frozen

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "sweep_collect.py"
SLUG = "sweep-collect"

BASH = shutil.which("bash") or "/bin/bash"
PYTHON = sys.executable

CALLS_MARKER = "--- gh calls ---\n"
WORK_MARKER = "--- work ---\n"
OUT_MARKER = "--- out ---\n"
ABSENT = "<absent>"

STATE_HEADER = "### Autopilot state (machine-maintained, do not edit)"
BOT = "autopilot-bot"

# Everything the subject and the sibling it spawns need on PATH. Derived by DRIVING them, not by reading: `tr` is there because `parse_args` shelled out to `to_upper` once per flag, `awk` because the state-comment reader parses the state line with it, and `mktemp`/`rm` because the campaign scanner makes and traps a work directory.
PATH_MINIMUM = (
    "dirname",
    "uname",
    "tr",
    "jq",
    "awk",
    "sort",
    "grep",
    "sed",
    "cat",
    "mktemp",
    "mkdir",
    "rm",
    # `_gh_probe`'s backoff is an external `sleep`, so a PATH without it turned every retry case into a 127 from the twin and a pass from the port.
    "sleep",
)

FAKE_GH = """#!/usr/bin/python3
import json
import os
import sys

argv = sys.argv[1:]
if os.environ.get("FAKE_GH_STDERR"):
    sys.stderr.write(os.environ["FAKE_GH_STDERR"])
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write("\\t".join(argv) + "\\n")

# `pr list ... --jq .[].number`: the label-armed numbers, as plain text.
if argv[:2] == ["pr", "list"] and "--jq" in argv:
    sys.stdout.write(os.environ.get("FAKE_LABEL_ARMED", "10\\n7\\n"))
    sys.exit(int(os.environ.get("FAKE_LABEL_RC", "0")))

# `pr list ... --json number`: the open PR list, as JSON.
if argv[:2] == ["pr", "list"]:
    sys.stdout.write(os.environ.get("FAKE_PRS", '[{"number":7},{"number":10},{"number":9}]'))
    sys.stdout.write("\\n")
    sys.exit(int(os.environ.get("FAKE_PRS_RC", "0")))

# `api repos/<repo>/issues/<n>/comments --paginate --slurp`: PAGES, i.e. an
# array of arrays, which is what --slurp produces and what `.[][]` flattens.
if argv[0] == "api":
    if os.environ.get("FAKE_API_BODY"):
        sys.stdout.write(os.environ["FAKE_API_BODY"] + "\\n")
        sys.exit(int(os.environ.get("FAKE_API_RC", "0")))
    number = argv[1].rsplit("/", 2)[-2]
    armed = os.environ.get("FAKE_CAMPAIGN_OPEN", "9").split(",")
    author = os.environ.get("FAKE_COMMENT_AUTHOR", %(bot)r)
    state = "open" if number in armed else "closed"
    body = (
        %(header)r
        + "\\nstate: fix | round: 1/3 | head: abc | last_run: 1/1 handled | campaign: "
        + state
        + " | model: m | rounds_max: 3 | last_sig: none | sig_count: 0\\n"
    )
    pages = [[{"id": 100 + int(number), "user": {"login": author}, "body": body}]]
    sys.stdout.write(json.dumps(pages) + "\\n")
    sys.exit(int(os.environ.get("FAKE_API_RC", "0")))

sys.stderr.write("fake gh: unexpected call %%r\\n" %% (argv,))
sys.exit(9)
""" % {"bot": BOT, "header": STATE_HEADER}

REQUIRED = {"--repo": "rediacc/console", "--bot": BOT, "--work": "work", "--out": "out.txt"}
ARGV = [token for flag, value in REQUIRED.items() for token in (flag, value)]


def _dropping(flag: str) -> list[str]:
    return [token for key, value in REQUIRED.items() if key != flag for token in (key, value)]


def _emptying(flag: str) -> list[str]:
    argv: list[str] = []
    for key, value in REQUIRED.items():
        argv += [key + "="] if key == flag else [key, value]
    return argv


# name -> argv and the environment the fake `gh` reads its behaviour from
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "the-happy-sweep": {"argv": ARGV},
    "a-union-not-an-intersection": {
        "argv": ARGV,
        "env": {"FAKE_LABEL_ARMED": "7\n", "FAKE_CAMPAIGN_OPEN": "10"},
    },
    "a-lookalike-campaign-comment": {
        "argv": ARGV,
        "env": {
            "FAKE_LABEL_ARMED": "",
            "FAKE_CAMPAIGN_OPEN": "7,9,10",
            "FAKE_COMMENT_AUTHOR": "drive-by-contributor",
        },
    },
    "an-empty-sweep": {
        "argv": ARGV,
        "env": {"FAKE_PRS": "[]", "FAKE_LABEL_ARMED": "", "FAKE_CAMPAIGN_OPEN": ""},
    },
    "without-a-repo": {"argv": _dropping("--repo")},
    "without-a-bot": {"argv": _dropping("--bot")},
    "without-a-work-dir": {"argv": _dropping("--work")},
    "without-an-out-file": {"argv": _dropping("--out")},
    "an-empty-repo": {"argv": _emptying("--repo")},
    "an-empty-bot": {"argv": _emptying("--bot")},
    "an-empty-work-dir": {"argv": _emptying("--work")},
    "an-empty-out-file": {"argv": _emptying("--out")},
    "an-explicit-label": {"argv": [*ARGV, "--label", "sweep-me"]},
    "a-pr-list-that-cannot-be-indexed": {"argv": ARGV, "env": {"FAKE_PRS": '{"pages":1}'}},
    "a-comment-dump-jq-cannot-transform": {"argv": ARGV, "env": {"FAKE_API_BODY": "[1,2]"}},
    "an-out-file-in-a-missing-directory": {
        "argv": [
            "--repo",
            "rediacc/console",
            "--bot",
            BOT,
            "--work",
            "work",
            "--out",
            "nodir/out.txt",
        ]
    },
    "a-failing-gh-retried-three-times": {
        "argv": ARGV,
        "env": {
            "FAKE_PRS_RC": "3",
            "FAKE_GH_STDERR": "gh: HTTP 403 rate limited\nsecond line",
        },
    },
    "a-body-of-null": {"argv": ARGV, "env": {"FAKE_PRS": "null"}},
}

CASES = tuple(CASE_KW)

# The one case whose stderr carries bash's own path and line number. Compared by shape, in its own test.
DIVERGENT = ("an-out-file-in-a-missing-directory",)


def stub_path(base: pathlib.Path, *, with_gh: bool = True) -> str:
    stub = base / "bin"
    stub.mkdir(parents=True, exist_ok=True)
    for name in PATH_MINIMUM:
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        link = stub / name
        if not link.exists():
            link.symlink_to(real)
    if with_gh:
        fake = stub / "gh"
        fake.write_text(FAKE_GH, encoding="utf-8")
        fake.chmod(0o755)
    return str(stub)


def tree(root: pathlib.Path) -> dict[str, str]:
    """Every file under `root`, keyed by POSIX-relative path."""
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def run(
    subject: pathlib.Path, base: pathlib.Path, name: str
) -> tuple[int, str, str, str, str, str]:
    """One subject, once, over its own stub PATH and its own working directory."""
    kw = CASE_KW[name]
    base.mkdir(parents=True, exist_ok=True)
    log = base / "gh-calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": stub_path(base),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GH_LOG": str(log),
    }
    env.update(kw.get("env") or {})
    # `sys.executable`, not "python3": the PATH above is a STUB with thirteen symlinks on it and no interpreter, which is the point of it.
    runner = [BASH] if subject.suffix == ".sh" else [PYTHON]
    proc = subprocess.run(
        [*runner, str(subject), *kw["argv"]],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=180,
    )

    def mask(text: str) -> str:
        return text.replace(str(base), "<case>").replace(str(ROOT), "<repo>")

    out_file = base / "out.txt"
    return (
        proc.returncode,
        mask(proc.stdout),
        mask(proc.stderr),
        mask(log.read_text(encoding="utf-8")),
        mask(json.dumps(tree(base / "work"), indent=2, sort_keys=True)),
        mask(out_file.read_text(encoding="utf-8")) if out_file.is_file() else ABSENT,
    )


def render(code: int, stdout: str, stderr: str, calls: str, work: str, out: str) -> str:
    return "%s%s%s%s%s\n%s%s\n" % (
        frozen.render(code, stdout, stderr),
        CALLS_MARKER,
        calls,
        WORK_MARKER,
        work,
        OUT_MARKER,
        out,
    )


def recorded(name: str) -> tuple[int, str, str, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, rest = rest.split(CALLS_MARKER, 1)
    calls, rest = rest.split(WORK_MARKER, 1)
    work, out = rest.split(OUT_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        calls,
        work.removesuffix("\n"),
        out.removesuffix("\n"),
    )


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str, str]:
    return run(PORT, tmp_path / name, name)


def lines(calls: str) -> list[str]:
    return [line for line in calls.splitlines() if line]


def files(work: str) -> dict[str, str]:
    return json.loads(work)


def mask_redirection(stderr: str) -> str:
    """Replace the failed-redirection diagnostic with a token.

    The twin's was bash's (`<repo>/.ci/scripts/autopilot/sweep-collect.sh: line 64: <file>: ...`) and the port's is its own; both name the same file and the same errno, and every other line on the stream has to match exactly.
    """
    out = []
    for line in stderr.split("\n"):
        if line.endswith("nodir/out.txt: No such file or directory") and not line.startswith(
            "grep: "
        ):
            out.append("<REDIRECTION FAILED>")
        else:
            out.append(line)
    return "\n".join(out)


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str, str]:
    want = recorded(name)
    got = port(tmp_path, name)
    labels = ("exit code", "stdout", "stderr", "the gh call SEQUENCE", "the work tree", "--out")
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%s\n--- port ---\n%s" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_the_stub_path_has_no_real_gh(tmp_path: pathlib.Path) -> None:
    """CONTROL. Every case's claim of "no network" rests on this."""
    without = stub_path(tmp_path, with_gh=False)
    assert shutil.which("gh", path=without) is None, "gh leaked into the stub PATH"
    assert shutil.which("jq", path=without) is not None, "the stub PATH is not usable"


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_the_happy_sweep() -> None:
    """Three open PRs, two label-armed, one campaign-armed, union of three."""
    code, stdout, stderr, calls, work, out = recorded("the-happy-sweep")
    assert code == 0
    assert stdout == ""
    # LEXICOGRAPHIC, not numeric: 10 before 7 before 9. See the port's docstring.
    assert out == "10\n7\n9\n", out
    assert "sweeper: 3 armed PR(s) = 2 label-armed U 1 campaign-armed" in stderr
    assert sorted(files(work)) == [
        "campaign-armed.txt",
        "comments/10.json",
        "comments/10.raw.json",
        "comments/7.json",
        "comments/7.raw.json",
        "comments/9.json",
        "comments/9.raw.json",
        "label-armed.txt",
        "prs.json",
    ], sorted(files(work))
    # One list call, one label call, one comments call per PR, in PR order.
    assert len(lines(calls)) == 5, calls
    assert lines(calls)[2].startswith("api\trepos/rediacc/console/issues/7/comments")
    # The transformed dump is jq's pretty printing, and another program reads it.
    assert json.loads(files(work)["comments/9.json"])[0]["author"] == BOT


def test_the_union_is_a_union_not_an_intersection() -> None:
    """A PR armed ONLY by a campaign, and one armed ONLY by a label, both land.

    This is the defect the twin was written to fix, so it gets a case of its own rather than riding on the happy path's counts.
    """
    _, _, stderr, _, _, out = recorded("a-union-not-an-intersection")
    assert out == "10\n7\n", out
    assert "sweeper: 2 armed PR(s) = 1 label-armed U 1 campaign-armed" in stderr


def test_a_lookalike_campaign_comment_is_not_armed() -> None:
    """NEGATIVE CONTROL, and the security-relevant one. Console is public, so a comment claiming `campaign: open` is the obvious way to make the sweeper dispatch rounds nobody armed. The author check is what makes it fail."""
    _, _, stderr, _, _, out = recorded("a-lookalike-campaign-comment")
    assert out == "", out
    assert "sweeper: 0 armed PR(s) = 0 label-armed U 0 campaign-armed" in stderr


def test_an_empty_sweep_is_normal_and_quiet() -> None:
    _, stdout, stderr, _, _, out = recorded("an-empty-sweep")
    assert (stdout, out) == ("", "")
    assert "sweeper: 0 armed PR(s) = 0 label-armed U 0 campaign-armed" in stderr


def test_usage_refusals() -> None:
    """Each required flag absent, and each present but empty. `--label` is NOT required: it defaults to `autopilot`."""
    for name in (
        "without-a-repo",
        "without-a-bot",
        "without-a-work-dir",
        "without-an-out-file",
        "an-empty-repo",
        "an-empty-bot",
        "an-empty-work-dir",
        "an-empty-out-file",
    ):
        code, _, stderr, calls, _, _ = recorded(name)
        assert code == 2, name
        assert "usage: sweep-collect.sh --repo <owner/name>" in stderr
        assert calls == "", "a usage refusal must not call gh: %r" % calls


def test_the_label_is_a_parameter_and_defaults() -> None:
    """The default reaches `gh` as `--label autopilot`, and an override reaches it verbatim. Read off the recorded call, not off the summary line."""
    for name, want in (("the-happy-sweep", "autopilot"), ("an-explicit-label", "sweep-me")):
        call = lines(recorded(name)[3])[1]
        assert "--label\t%s" % want in call, call


def test_defect_a_prs_json_that_cannot_be_indexed_scans_nothing_and_exits_0() -> None:
    """Defect 1 in the port's docstring, pinned so a fix turns this red.

    `{"pages":1}` satisfies `gh_json` (it parses, and `jq -e` accepts it), then `jq -r '.[].number'` fails inside a PROCESS SUBSTITUTION whose status nothing checks. A bare `{}` is NOT a specimen for this, and finding that out cost this case a run: `.[]` over an empty object yields nothing at all, so jq succeeds silently and the scan is empty for a boring reason.

    Zero comment dumps are written, zero campaigns are found, and the sweep announces success.
    """
    code, _, stderr, calls, work, out = recorded("a-pr-list-that-cannot-be-indexed")
    assert code == 0, "the twin really does succeed here"
    assert [c for c in lines(calls) if c.startswith("api")] == [], calls
    assert [k for k in files(work) if k.startswith("comments/")] == [], sorted(files(work))
    assert 'Cannot index number with string "number"' in stderr, stderr
    assert "sweeper: 2 armed PR(s) = 2 label-armed U 0 campaign-armed" in stderr
    assert out == "10\n7\n", out


def test_a_comment_dump_jq_can_not_transform_kills_the_run() -> None:
    """The other jq, the one whose status IS checked: its exit code becomes the script's, and no `--out` is written at all."""
    code, _, stderr, _, work, out = recorded("a-comment-dump-jq-cannot-transform")
    assert code == 5, code
    assert "Cannot iterate over number" in stderr
    assert out == ABSENT
    assert "comments/7.json" in files(work), sorted(files(work))
    assert files(work)["comments/7.json"] == "", "the redirection truncated it before jq ran"


def test_slow_a_failing_gh_retries_three_times_and_replays_its_stderr() -> None:
    """The only case that proves the whole `_gh_probe` loop: two warnings, the final error with the last exit code, and the captured stderr replayed indented four spaces WITHOUT inventing a final newline."""
    code, _, stderr, calls, work, out = recorded("a-failing-gh-retried-three-times")
    assert code == 1
    assert (
        lines(calls)
        == ["pr\tlist\t--repo\trediacc/console\t--state\topen\t--limit\t50\t--json\tnumber"] * 3
    )
    assert stderr.endswith("    gh: HTTP 403 rate limited\n    second line"), stderr
    assert "gh failed after 3 attempts (last exit 3)." in stderr
    # Truncated by the redirection before the first attempt, and never filled.
    assert files(work) == {"prs.json": ""}, work
    assert out == ABSENT


def test_slow_a_body_of_null_is_unusable_not_an_answer() -> None:
    """`jq -e .` exits 1 on `null`, so `gh_json` retries and then refuses. A port validating with `json.loads` alone would accept it and write `null` into `prs.json`."""
    code, _, stderr, _, work, _ = recorded("a-body-of-null")
    assert code == 1
    assert "sweeper open PR list: gh failed after 3 attempts (last exit 0)." in stderr
    assert files(work) == {"prs.json": ""}, work


def test_pure_helpers_are_exercised_directly() -> None:
    """The helpers, without a subprocess, in BOTH directions."""
    assert sc._json_usable(b'[{"number":1}]') is True
    assert sc._json_usable(b"{}") is True
    assert sc._json_usable(b"null") is False, "jq -e's rule, not json.loads'"
    assert sc._json_usable(b"false") is False
    assert sc._json_usable(b"") is False
    assert sc._json_usable(b"not json") is False
    assert sc._json_usable(b"0") is True, "zero is not false to jq -e"

    assert sc.count_nonempty(b"") == 0
    assert sc.count_nonempty(b"12") == 1, "a file with no final newline still has a line"
    assert sc.count_nonempty(b"12\n") == 1
    assert sc.count_nonempty(b"12\n\n13\n") == 2, "grep -c . skips the empty line"

    assert sc.sort_unique([b"10\n7", b"7\n9\n"]) == [b"10", b"7", b"9"]
    assert sc.sort_unique([b"", b""]) == []
    assert sc.digits_only([b"10", b"9x", b"", b"-1", b"07"]) == [b"10", b"07"]

    argv = sc.campaign_argv()
    assert argv[-1] == str(ROOT / ".ci" / "rediacc_ci" / "autopilot" / "sweep_campaigns.py")
    assert pathlib.Path(argv[-1]).is_file(), "the sibling this port shells out to must exist"
    assert sc.child_env()["PYTHONPATH"] == str(ROOT / ".ci"), "the child cannot import rediacc_ci"


# --------------------------------------------------------------------------- The one divergence, pinned rather than papered over ---------------------------------------------------------------------------


def test_defect_an_unwritable_out_is_announced_as_an_empty_sweep(tmp_path: pathlib.Path) -> None:
    """Defect 2, and the only shape-compared case. bash's redirection diagnostic carried the twin's own path and line number; everything after it is exact."""
    name = "an-out-file-in-a-missing-directory"
    want = recorded(name)
    got = port(tmp_path, name)
    assert want[0] == got[0] == 0, (want[0], got[0])
    assert want[1] == got[1] == "", "neither side writes to stdout here"
    assert want[3] == got[3], "the gh calls still have to agree"
    assert want[4] == got[4], "the work tree still has to agree"
    assert want[5] == got[5] == ABSENT
    for stream in (want[2], got[2]):
        assert "grep: nodir/out.txt: No such file or directory" in stream.split("\n"), stream
        # The count is EMPTY where the total should be. That is the defect.
        assert "sweeper:  armed PR(s) = 2 label-armed U 1 campaign-armed" in stream, stream
    # SHAPE, properly: mask the one line that carries the implementation's own name and compare EVERYTHING else byte for byte, so a port that also moved the message, or lost a line after it, still fails.
    assert mask_redirection(want[2]) == mask_redirection(got[2]), (want[2], got[2])
    assert "<repo>/.ci/scripts/autopilot/sweep-collect.sh" in want[2], "the twin named itself"


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


# A throwaway entry point that loads the real module, drops `--slurp` from every argv it hands its probe, and runs `main`. See the control below for why the plant is a wrapper rather than a copy.
PLANT = """import sys

from rediacc_ci.autopilot import sweep_collect as subject

_probe = subject.gh_probe


def _without_slurp(require_json, what, args, **kw):
    return _probe(require_json, what, [a for a in args if a != "--slurp"], **kw)


subject.gh_probe = _without_slurp
raise SystemExit(subject.main(sys.argv[1:]))
"""


def test_a_planted_drop_of_slurp_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the section that would otherwise be decoration.

    `--slurp` is load-bearing and the twin says why: `--paginate` applies the filter PER PAGE and concatenates, so a PR past 30 comments produces two top-level JSON arrays in one file and every downstream reader sees the second as a separate document. Dropping it leaves this fixture's output unchanged, because the fake answers one page whatever it is asked, so the exit code, both
    streams, the work tree and `--out` are all identical and only the `--- gh calls ---` section sees it.

    THE PLANT IS A WRAPPER, NOT A COPY OF THE FILE, and that is a property of the subject rather than a convenience. The module resolves both the sibling it spawns and that child's `PYTHONPATH` from its OWN location (`campaign_argv`, `child_env`), so a copy at any other path spawns a scanner that is not there and dies at exit 2 before a single `gh` call is made. Measured, and it
    cost this control its first run. The wrapper imports the tracked module unmodified and replaces one attribute in its own process, so the file on disk is never written to at all.
    """
    original = PORT.read_text(encoding="utf-8")
    assert '"--slurp",\n' in original, "the plant's target moved"

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(PLANT, encoding="utf-8")

    name = "the-happy-sweep"
    want = recorded(name)
    assert "--slurp" in want[3], "the recorded corpus moved"
    planted = run(mutant, tmp_path / "planted", name)
    assert "--slurp" not in planted[3], "the plant did not change the call sequence"
    for index in (0, 1, 2, 4, 5):
        assert planted[index] == want[index], "the plant was supposed to be invisible here"

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original

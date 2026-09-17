"""Differential: `rediacc_ci.autopilot.sweep_collect` against its twin
`.ci/scripts/autopilot/sweep-collect.sh`.

A RECORDING FAKE `gh` ON A STUB PATH, and the fake is the whole apparatus:
nothing here reaches the network, and the real `gh` on this machine is never on
the PATH handed to either subject. `test_the_stub_path_has_no_real_gh` is the
control for that claim rather than a comment asserting it.

FIVE ARTIFACTS ARE COMPARED PER CASE, not two. This script's visible result is
neither stdout nor stderr: it is the `--out` file, the whole `--work` tree
(`prs.json`, `label-armed.txt`, `campaign-armed.txt` and one raw plus one
transformed dump per PR), and the SEQUENCE OF `gh` INVOCATIONS. A port that
printed the right summary while requesting the wrong pages, or while writing
`comments/7.json` with different bytes, would sail past a stream comparison.
The work tree is compared as BYTES per relative path, because the transformed
dumps are read by `sweep-campaigns.sh` and their formatting is jq's.

`sweep-campaigns.sh` AND `state-comment.sh` RUN FOR REAL, unstubbed, in both
subjects. They are pure (files in, PR numbers out) and they carry the TRUST
RULE this collector depends on: a campaign counts only when the comment's
author is the bot AND the body starts with the exact state header. So the
fixture comments below are shaped like real state comments, and
`test_a_lookalike_campaign_comment_is_not_armed` drives the untrusted case
through both sides rather than asserting it about the collector alone.

TWO CASES COST NINE SECONDS PER SIDE AND ARE WORTH IT. `_gh_probe` sleeps 3
then 6 seconds between its three attempts, so any case that drives a `gh`
failure to exhaustion takes 18 seconds across the two subjects. They are the
only cases that prove the retry loop, the final `gh failed after 3 attempts`
line and the four-space stderr replay agree, and one of them is also the only
case that proves `jq -e`'s null rule (a body of `null` is UNUSABLE, not an
answer).

THE ONE SHAPE-COMPARED CASE is `--out` in a directory that does not exist:
bash's redirection diagnostic carries the twin's own path and line number. Exit
code, the position of the message and everything after it (including the
summary line with its EMPTY count, which is defect 2) are compared exactly.

K=5 LEDGER: `.ci/shadow/w7p6-sweep-collect.observations.jsonl`, recorded in a
disposable scratch git repository outside this checkout, since
`shadow-gate.ts --record` refuses a dirty tree and this checkout is never
clean.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.autopilot import sweep_collect as sc

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "autopilot" / "sweep-collect.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "autopilot" / "sweep_collect.py"
BASH = shutil.which("bash") or "/bin/bash"

STATE_HEADER = "### Autopilot state (machine-maintained, do not edit)"
BOT = "autopilot-bot"

# Everything the two subjects and the two bash scripts they call need on PATH. Derived by DRIVING them, not by reading: `tr` is there because `parse_args` shells out to `to_upper` once per flag, `awk` because `state-comment.sh` parses the state line with it, and `mktemp`/`rm` because `sweep-campaigns.sh` makes and traps a work directory.
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
    # `_gh_probe`'s backoff is an external `sleep`, so a PATH without it turns every retry case into a 127 from the twin and a pass from the port.
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


def _stub_path(base: pathlib.Path, *, with_gh: bool = True) -> str:
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
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


def _tree(root: pathlib.Path) -> dict[str, bytes]:
    """Every file under `root`, keyed by POSIX-relative path."""
    out: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[path.relative_to(root).as_posix()] = path.read_bytes()
    return out


def _run(subject: pathlib.Path, base: pathlib.Path, argv: list[str], **gh_env: str):
    log = base / "gh-calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": _stub_path(base),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_GH_LOG": str(log),
    }
    env.update(gh_env)
    # `sys.executable`, not "python3": the PATH above is a STUB with twelve symlinks on it and no interpreter, which is the point of it.
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    work = _tree(base / "work") if (base / "work").is_dir() else {}
    out_file = (base / "out.txt").read_bytes() if (base / "out.txt").is_file() else None
    return proc.returncode, proc.stdout, proc.stderr, calls, work, out_file


def _sides(name: str, argv: list[str], *, exact_stderr: bool = True, **gh_env: str):
    with tempfile.TemporaryDirectory() as td:
        results = []
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            results.append(_run(subject, base, argv, **gh_env))
        old, new = results
    assert new[0] == old[0], "%s: exit diverged: %r vs %r\n twin stderr: %r\n port stderr: %r" % (
        name,
        old[0],
        new[0],
        old[2],
        new[2],
    )
    assert new[1] == old[1], "%s: stdout diverged:\nold %r\nnew %r" % (name, old[1], new[1])
    if exact_stderr:
        assert new[2] == old[2], "%s: stderr diverged:\nold %r\nnew %r" % (name, old[2], new[2])
    assert new[3] == old[3], "%s: gh call sequence diverged:\nold %r\nnew %r" % (
        name,
        old[3],
        new[3],
    )
    assert sorted(new[4]) == sorted(old[4]), (
        "%s: the work tree's FILES diverged:\nold %r\nnew %r"
        % (
            name,
            sorted(old[4]),
            sorted(new[4]),
        )
    )
    for rel in sorted(old[4]):
        assert new[4][rel] == old[4][rel], "%s: work/%s diverged:\nold %r\nnew %r" % (
            name,
            rel,
            old[4][rel],
            new[4][rel],
        )
    assert new[5] == old[5], "%s: --out diverged:\nold %r\nnew %r" % (name, old[5], new[5])
    return old


def _mask_redirection(stderr: bytes) -> bytes:
    """Replace the failed-redirection diagnostic with a token.

    The twin's is bash's (`<path>/sweep-collect.sh: line 64: <file>: ...`) and
    the port's is its own; both name the same file and the same errno, and
    every other line on the stream has to match exactly.
    """
    out = []
    for line in stderr.split(b"\n"):
        if line.endswith(b"nodir/out.txt: No such file or directory") and not line.startswith(
            b"grep: "
        ):
            out.append(b"<REDIRECTION FAILED>")
        else:
            out.append(line)
    return b"\n".join(out)


ARGV = ["--repo", "rediacc/console", "--bot", BOT, "--work", "work", "--out", "out.txt"]


def test_the_stub_path_has_no_real_gh() -> None:
    """CONTROL. Every case's claim of "no network" rests on this."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        without = _stub_path(base, with_gh=False)
        assert shutil.which("gh", path=without) is None, "gh leaked into the stub PATH"
        assert shutil.which("jq", path=without) is not None, "the stub PATH is not usable"


def test_the_happy_sweep() -> None:
    """Three open PRs, two label-armed, one campaign-armed, union of three."""
    exit_code, stdout, stderr, calls, work, out = _sides("happy", ARGV)
    assert exit_code == 0
    assert stdout == b""
    # LEXICOGRAPHIC, not numeric: 10 before 7 before 9. See the port's docstring.
    assert out == b"10\n7\n9\n", out
    assert b"sweeper: 3 armed PR(s) = 2 label-armed U 1 campaign-armed" in stderr
    assert sorted(work) == [
        "campaign-armed.txt",
        "comments/10.json",
        "comments/10.raw.json",
        "comments/7.json",
        "comments/7.raw.json",
        "comments/9.json",
        "comments/9.raw.json",
        "label-armed.txt",
        "prs.json",
    ], sorted(work)
    # One list call, one label call, one comments call per PR, in PR order.
    assert len(calls) == 5, calls
    assert calls[2].startswith("api\trepos/rediacc/console/issues/7/comments")
    # The transformed dump is jq's pretty printing, and another script reads it.
    assert json.loads(work["comments/9.json"])[0]["author"] == BOT


def test_the_union_is_a_union_not_an_intersection() -> None:
    """A PR armed ONLY by a campaign, and one armed ONLY by a label, both land.

    This is the defect the twin was written to fix, so it gets a case of its
    own rather than riding on the happy path's counts.
    """
    _, _, stderr, _, _, out = _sides(
        "union",
        ARGV,
        FAKE_LABEL_ARMED="7\n",
        FAKE_CAMPAIGN_OPEN="10",
    )
    assert out == b"10\n7\n", out
    assert b"sweeper: 2 armed PR(s) = 1 label-armed U 1 campaign-armed" in stderr


def test_a_lookalike_campaign_comment_is_not_armed() -> None:
    """NEGATIVE CONTROL, and the security-relevant one. Console is public, so a
    comment claiming `campaign: open` is the obvious way to make the sweeper
    dispatch rounds nobody armed. The author check is what makes it fail."""
    _, _, stderr, _, _, out = _sides(
        "lookalike",
        ARGV,
        FAKE_LABEL_ARMED="",
        FAKE_CAMPAIGN_OPEN="7,9,10",
        FAKE_COMMENT_AUTHOR="drive-by-contributor",
    )
    assert out == b"", out
    assert b"sweeper: 0 armed PR(s) = 0 label-armed U 0 campaign-armed" in stderr


def test_an_empty_sweep_is_normal_and_quiet() -> None:
    _, stdout, stderr, _, _, out = _sides(
        "empty", ARGV, FAKE_PRS="[]", FAKE_LABEL_ARMED="", FAKE_CAMPAIGN_OPEN=""
    )
    assert (stdout, out) == (b"", b"")
    assert b"sweeper: 0 armed PR(s) = 0 label-armed U 0 campaign-armed" in stderr


def test_usage_refusals() -> None:
    """Each required flag absent, and each present but empty. `--label` is NOT
    required: it defaults to `autopilot`."""
    full = {"--repo": "rediacc/console", "--bot": BOT, "--work": "work", "--out": "out.txt"}
    for drop in list(full):
        argv: list[str] = []
        for flag, value in full.items():
            if flag != drop:
                argv += [flag, value]
        exit_code, _, stderr, calls, _, _ = _sides("missing%s" % drop, argv)
        assert exit_code == 2, drop
        assert b"usage: sweep-collect.sh --repo <owner/name>" in stderr
        assert calls == [], "a usage refusal must not call gh: %r" % calls
        empty: list[str] = []
        for flag, value in full.items():
            empty += [flag + "="] if flag == drop else [flag, value]
        assert _sides("empty%s" % drop, empty)[0] == 2, drop


def test_the_label_is_a_parameter_and_defaults() -> None:
    """The default reaches `gh` as `--label autopilot`, and an override reaches
    it verbatim. Read off the recorded call, not off the summary line."""
    for argv, want in ((ARGV, "autopilot"), ([*ARGV, "--label", "sweep-me"], "sweep-me")):
        _, _, _, calls, _, _ = _sides("label-%s" % want, argv)
        assert "--label\t%s" % want in calls[1], calls[1]


def test_defect_a_prs_json_that_cannot_be_indexed_scans_nothing_and_exits_0() -> None:
    """Defect 1 in the port's docstring, pinned so a fix turns this red.

    `{"pages":1}` satisfies `gh_json` (it parses, and `jq -e` accepts it),
    then `jq -r '.[].number'` fails inside a PROCESS SUBSTITUTION whose status
    nothing checks. A bare `{}` is NOT a specimen for this, and finding that
    out cost this case a run: `.[]` over an empty object yields nothing at all,
    so jq succeeds silently and the scan is empty for a boring reason.

    Zero comment dumps are written, zero campaigns are found, and the sweep
    announces success.
    """
    exit_code, _, stderr, calls, work, out = _sides("defect-prs", ARGV, FAKE_PRS='{"pages":1}')
    assert exit_code == 0, "the twin really does succeed here"
    assert [c for c in calls if c.startswith("api")] == [], calls
    assert [k for k in work if k.startswith("comments/")] == [], sorted(work)
    assert b'Cannot index number with string "number"' in stderr, stderr
    assert b"sweeper: 2 armed PR(s) = 2 label-armed U 0 campaign-armed" in stderr
    assert out == b"10\n7\n", out


def test_a_comment_dump_jq_can_not_transform_kills_the_run() -> None:
    """The other jq, the one whose status IS checked: its exit code becomes the
    script's, and no `--out` is written at all."""
    exit_code, _, stderr, _, work, out = _sides("jq-fails", ARGV, FAKE_API_BODY="[1,2]")
    assert exit_code == 5, exit_code
    assert b"Cannot iterate over number" in stderr
    assert out is None
    assert "comments/7.json" in work, sorted(work)
    assert work["comments/7.json"] == b"", "the redirection truncated it before jq ran"


def test_defect_an_unwritable_out_is_announced_as_an_empty_sweep() -> None:
    """Defect 2. Shape-compared, because bash's redirection diagnostic carries
    the twin's own path and line number; everything after it is exact."""
    argv = ["--repo", "rediacc/console", "--bot", BOT, "--work", "work", "--out", "nodir/out.txt"]
    with tempfile.TemporaryDirectory() as td:
        seen = []
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            seen.append(_run(subject, base, argv))
        old, new = seen
    assert old[0] == new[0] == 0, (old[0], new[0])
    assert old[3] == new[3], "the gh calls still have to agree"
    for side in (old, new):
        tail = side[2].split(b"\n")
        assert b"grep: nodir/out.txt: No such file or directory" in tail, side[2]
        # The count is EMPTY where the total should be. That is the defect.
        assert b"sweeper:  armed PR(s) = 2 label-armed U 1 campaign-armed" in side[2], side[2]
    # SHAPE, properly: mask the one line that carries the implementation's own name and compare EVERYTHING else byte for byte, so a port that also moved the message, or lost a line after it, still fails.
    assert _mask_redirection(old[2]) == _mask_redirection(new[2]), (old[2], new[2])


def test_slow_a_failing_gh_retries_three_times_and_replays_its_stderr() -> None:
    """18 seconds, and the only case that proves the whole `_gh_probe` loop:
    two warnings, the final error with the last exit code, and the captured
    stderr replayed indented four spaces WITHOUT inventing a final newline."""
    exit_code, _, stderr, calls, work, out = _sides(
        "gh-fails",
        ARGV,
        FAKE_PRS_RC="3",
        FAKE_GH_STDERR="gh: HTTP 403 rate limited\nsecond line",
    )
    assert exit_code == 1
    assert (
        calls
        == ["pr\tlist\t--repo\trediacc/console\t--state\topen\t--limit\t50\t--json\tnumber"] * 3
    )
    assert stderr.endswith(b"    gh: HTTP 403 rate limited\n    second line"), stderr
    assert b"gh failed after 3 attempts (last exit 3)." in stderr
    # Truncated by the redirection before the first attempt, and never filled.
    assert work == {"prs.json": b""}, work
    assert out is None


def test_slow_a_body_of_null_is_unusable_not_an_answer() -> None:
    """`jq -e .` exits 1 on `null`, so `gh_json` retries and then refuses. A
    port validating with `json.loads` alone would accept it and write `null`
    into `prs.json`."""
    exit_code, _, stderr, _, work, _ = _sides("null-body", ARGV, FAKE_PRS="null")
    assert exit_code == 1
    assert b"sweeper open PR list: gh failed after 3 attempts (last exit 0)." in stderr
    assert work == {"prs.json": b""}, work


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

    assert sc.campaign_script() == ROOT / ".ci" / "scripts" / "autopilot" / "sweep-campaigns.sh"
    assert sc.campaign_script().is_file(), "the twin this port shells out to must exist"

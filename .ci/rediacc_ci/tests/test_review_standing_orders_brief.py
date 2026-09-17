"""Differential: `rediacc_ci.review.standing_orders_brief` against its twin `.claude/lib/standing-orders-brief.sh`.

THE SEAM IS THE CURRENT DIRECTORY, not the subject's own location. Both sides read `.claude/hooks/stop/worklist.py`, `agent/...` and a bare `pwd` relative to wherever they are RUN, so neither has to be copied into the fixture: each case builds a tree, runs the real tracked twin and the real tracked port with `cwd` set to it, and compares. That is a stronger comparison than a copy
would be -- it is the tracked bytes on both sides.

THE WORKLIST IS A CANNED STAND-IN, AND THAT IS THE POINT. The subject here is the BRIEF, not `worklist.py`; the real store is append-only and shared with other live sessions, so driving it would make this suite depend on what a peer did thirty seconds ago. Each case writes a scripted `.claude/hooks/stop/ worklist.py` into the fixture that answers `--list`/`--poll` from a table.
`test_the_real_worklist_answers_the_same_three_verbs` is the anti-vacuity control on that substitution: it drives the REAL tracked `worklist.py` with the brief's own three argument vectors and asserts each one is answered, so the stand-in cannot be standing in for something that no longer exists.

BYTE EQUALITY ON THE REAL TREE, driven before any fixture was written:
`CLAUDE_CODE_SESSION_ID=<id> bash .claude/lib/standing-orders-brief.sh` and
`python3 .ci/rediacc_ci/review/standing_orders_brief.py` produced IDENTICAL merged output in this checkout on 2026-09-10.

TWO THINGS ARE NORMALIZED, and both have a control. The `at <ts>` stamp comes
from `date -u` / `datetime.now`, which advance between the two runs; and
`last grew <n>m ago` is derived from the wall clock the same way. Nothing else is masked -- sizes, counts, branch names, paths and every line of prose are compared verbatim.

K=5 LEDGER: `.ci/shadow/w7p6-standing-orders-brief.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import tempfile
import time

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
TWIN = ROOT / ".claude" / "lib" / "standing-orders-brief.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "review" / "standing_orders_brief.py"
REAL_WORKLIST = ROOT / ".claude" / "hooks" / "stop" / "worklist.py"

ME_FULL = "abcd1234-5555-6666-7777-888899990000"
ME = ME_FULL[:8]

# The shape the real store prints, including the `worker:<bg-id>` ADVICE line whose `<` terminates `grep -o`'s character class and yields a phantom bare `worker:` token. That is the twin's behaviour and it is deliberately here.
RICH_SLICE = """WORKLIST GUIDE (derived from the store, not from memory):
  - [>] #11112222 LEASE DEAD (quiet 104m) something ... LATEST: waiting
        NEXT: finish it and --tick %(me)s 11112222 '<evidence>', or re-lease: --lease %(me)s 11112222 +60 worker:<bg-id>
  - [>] #33334444 (quiet 2m, worker:deadbeefcafe1234, 86m left) campaign ... LATEST: moving
        NEXT: --update %(me)s 33334444 '<one line of what moved>'
  - [?] #55556666 should the driver pick branch A or B? DEFAULT: A
""" % {"me": ME}

QUIET_SLICE = """WORKLIST GUIDE (derived from the store, not from memory):
  - [ ] #77778888 a plain open item with no lease at all
"""

FAKE_WORKLIST = """#!/usr/bin/env python3
import sys
LIST_ALL = %(list_all)r
LIST_MINE = %(list_mine)r
POLL = %(poll)r
STDERR = %(stderr_text)r
RC = %(rc)d
argv = sys.argv[1:]
if STDERR:
    sys.stderr.write(STDERR)
    sys.stderr.flush()
if argv[:2] == ["--list", "--open"]:
    sys.stdout.write(LIST_MINE if len(argv) > 2 else LIST_ALL)
elif argv[:1] == ["--poll"]:
    sys.stdout.write(POLL)
sys.stdout.flush()
sys.exit(RC)
"""


def _fixture(
    base: pathlib.Path,
    *,
    list_all: str = RICH_SLICE + QUIET_SLICE,
    list_mine: str = RICH_SLICE,
    poll: str = "",
    worklist_stderr: str = "",
    worklist_rc: int = 0,
    with_worklist: bool = True,
    with_agent: bool = True,
    with_state: bool = True,
    plan_count: int = 3,
    peer_count: int = 2,
    with_git: bool = False,
    tasks: dict[str, tuple[int, int]] | None = None,
    tasks_dir: bool = True,
) -> pathlib.Path:
    """A tree the brief can be RUN INSIDE. `tasks` maps a worker id to (size in bytes, age in seconds) for its `.output` file."""
    root = base / "tree"
    root.mkdir(parents=True)

    if with_worklist:
        stop = root / ".claude" / "hooks" / "stop"
        stop.mkdir(parents=True)
        (stop / "worklist.py").write_text(
            FAKE_WORKLIST
            % {
                "list_all": list_all,
                "list_mine": list_mine,
                "poll": poll,
                "stderr_text": worklist_stderr,
                "rc": worklist_rc,
            },
            encoding="utf-8",
        )

    if with_agent:
        agent = root / "agent"
        agent.mkdir()
        mine = agent / ME
        mine.mkdir()
        if with_state:
            state = mine / "STATE.md"
            state.write_text("# fixture state\n", encoding="utf-8")
            # A FIXED mtime, so `stat -c %y | cut -d. -f1` is byte-stable across the two runs instead of drifting with the clock.
            os.utime(state, (1_700_000_000, 1_700_000_000))
        for i in range(plan_count):
            (agent / ("PLAN-fixture-%d.md" % i)).write_text("plan\n", encoding="utf-8")
        for i in range(peer_count):
            (agent / ("peer%d" % i)).mkdir()

    if with_git:
        subprocess.run(["git", "-C", str(root), "init", "-b", "fixturebranch", "-q"], check=True)
        # THE SCRATCH-GIT GUARD, asserted rather than assumed: every git call in this file is `git -C <fixture>`, and this proves the -C landed where it was aimed and not in the checkout this test is running from.
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert pathlib.Path(top).resolve() == root.resolve(), (
            "the fixture git repo resolved to %r, not to the fixture" % top
        )

    tmpdir = base / "tmp"
    tmpdir.mkdir()
    if tasks is not None and tasks_dir:
        mangled = "".join(
            ch if (ch.isascii() and ch.isalnum()) else "-" for ch in str(root.resolve())
        )
        td = tmpdir / ("claude-%d" % os.getuid()) / mangled / (ME + "-session") / "tasks"
        td.mkdir(parents=True)
        now = int(time.time())
        for ident, (size, age) in tasks.items():
            out = td / ("%s.output" % ident)
            out.write_bytes(b"x" * size)
            os.utime(out, (now - age, now - age))
    return root


STAMP = re.compile(r"^I am (\S+) on branch (.*) at \d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$", re.MULTILINE)
GREW = re.compile(r"last grew -?\d+m ago")


def _normalize(text: str, root: pathlib.Path, base: pathlib.Path) -> str:
    text = text.replace(str(root.resolve()), "<root>").replace(str(base.resolve()), "<base>")
    text = STAMP.sub(r"I am \1 on branch \2 at <ts>", text)
    return GREW.sub("last grew <n>m ago", text)


def _run(
    which: str,
    root: pathlib.Path,
    base: pathlib.Path,
    *,
    session_id: str | None = ME_FULL,
    port_path: pathlib.Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    if session_id is not None:
        env["CLAUDE_CODE_SESSION_ID"] = session_id
    env["TMPDIR"] = str(base / "tmp")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["TZ"] = "UTC"
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    cmd = (
        ["bash", str(TWIN)]
        if which == "old"
        else ["python3", str(port_path if port_path is not None else PORT)]
    )
    return subprocess.run(
        cmd, cwd=str(root), capture_output=True, text=True, env=env, check=False, timeout=120
    )


CASES: list[tuple[str, dict[str, object]]] = [
    ("rich-slice-tasks-dir-unresolvable", {"tasks": None}),
    (
        "live-worker-with-a-growing-output-file",
        {"tasks": {"deadbeefcafe1234": (4096, 30), "": (12, 30)}},
    ),
    (
        "worker-output-empty-and-cold",
        {"tasks": {"deadbeefcafe1234": (0, 3600), "": (0, 3600)}},
    ),
    (
        "worker-output-empty-but-warm-is-not-flagged",
        {"tasks": {"deadbeefcafe1234": (0, 60), "": (0, 60)}},
    ),
    ("worker-named-but-no-output-stream", {"tasks": {"someone-else": (10, 10)}}),
    ("no-workers-at-all", {"list_mine": QUIET_SLICE, "tasks": {"x": (1, 1)}}),
    ("empty-worklist-output", {"list_all": "", "list_mine": "", "poll": ""}),
    (
        "worklist-writes-to-stderr-and-fails",
        {"worklist_stderr": "Traceback: boom\n", "worklist_rc": 1},
    ),
    ("worklist-script-missing-entirely", {"with_worklist": False}),
    ("poll-has-content", {"poll": "PEER f0f0f0f0 is waiting on #11112222\n"}),
    ("head-60-truncation", {"list_mine": "".join("  - [ ] #%08d line\n" % i for i in range(90))}),
    ("head-30-truncation-on-poll", {"poll": "".join("peer line %d\n" % i for i in range(50))}),
    ("inside-a-git-repo", {"with_git": True}),
    ("no-agent-directory-at-all", {"with_agent": False}),
    ("state-md-missing", {"with_state": False}),
    ("no-plan-files", {"plan_count": 0}),
    ("no-peer-directories", {"peer_count": 0}),
]


@pytest.mark.parametrize(("name", "kwargs"), CASES, ids=[c[0] for c in CASES])
def test_port_and_twin_agree(name: str, kwargs: dict[str, object]) -> None:
    with tempfile.TemporaryDirectory() as td:
        base_a = pathlib.Path(td) / "a"
        base_b = pathlib.Path(td) / "b"
        base_a.mkdir()
        base_b.mkdir()
        root_a = _fixture(base_a, **kwargs)  # type: ignore[arg-type]
        root_b = _fixture(base_b, **kwargs)  # type: ignore[arg-type]
        old = _run("old", root_a, base_a)
        new = _run("new", root_b, base_b)

        assert new.returncode == old.returncode, "%s: exit diverged: %r vs %r\n%s\n%s" % (
            name,
            old.returncode,
            new.returncode,
            old.stderr,
            new.stderr,
        )
        assert _normalize(new.stdout, root_b, base_b) == _normalize(old.stdout, root_a, base_a), (
            "%s: stdout diverged:\n--- twin ---\n%s\n--- port ---\n%s"
            % (name, old.stdout, new.stdout)
        )
        assert _normalize(new.stderr, root_b, base_b) == _normalize(old.stderr, root_a, base_a), (
            "%s: stderr diverged:\n--- twin ---\n%s\n--- port ---\n%s"
            % (name, old.stderr, new.stderr)
        )


def test_the_output_is_not_trivially_short() -> None:
    """ANTI-VACUITY: the comparisons above must be over a real brief, not over two programs that printed a banner and stopped."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td) / "v"
        base.mkdir()
        root = _fixture(base, tasks={"deadbeefcafe1234": (4096, 30), "": (12, 30)})
        out = _run("new", root, base).stdout
    for marker in (
        "MY OPEN SLICE",
        "OWNERSHIP: 4 open in this repo, 3 mine, 1 a peer session's.",
        "OPEN DEFERRALS OF MINE: 1.",
        "ARE MY [>] LEASES BELIEVABLE:",
        "    deadbeefcafe1234: 4096 bytes,",
        "WAITING FOR ME FROM PEER SESSIONS",
        "DURABLE CONTEXT: my STATE.md 2023-11-14 22:13:20; 3 plan file(s) under agent/",
        "  2 peer session folder(s) beside mine under agent/.",
    ):
        assert marker in out, "the brief did not print %r:\n%s" % (marker, out)


def test_the_phantom_worker_token_is_reproduced() -> None:
    """THE SECOND PINNED DEFECT. `grep -o 'worker:[A-Za-z0-9._-]*'` harvests the bare token `worker:` out of the store's own `worker:<bg-id>` advice text, and the brief then reports a lease with an empty id. Both sides do it."""
    with tempfile.TemporaryDirectory() as td:
        base_a = pathlib.Path(td) / "a"
        base_b = pathlib.Path(td) / "b"
        base_a.mkdir()
        base_b.mkdir()
        old = _run("old", _fixture(base_a, tasks=None), base_a)
        new = _run("new", _fixture(base_b, tasks=None), base_b)
    assert "    worker:\n" in old.stdout, "the twin stopped emitting the phantom token"
    assert "    worker:\n" in new.stdout, "the port did not reproduce the phantom token"


def test_unset_session_id_is_a_named_divergence() -> None:
    """THE FIRST PINNED DEFECT, and the one place the two sides differ on purpose.

    With CLAUDE_CODE_SESSION_ID entirely UNSET, `set -u` kills the twin at :21 before the friendly guard on :27-31 can run. Both sides exit 1 and print nothing on stdout; the port names the variable in its own words and does NOT forge bash's `line 21:` prefix.
    """
    with tempfile.TemporaryDirectory() as td:
        base_a = pathlib.Path(td) / "a"
        base_b = pathlib.Path(td) / "b"
        base_a.mkdir()
        base_b.mkdir()
        old = _run("old", _fixture(base_a), base_a, session_id=None)
        new = _run("new", _fixture(base_b), base_b, session_id=None)
    assert old.returncode == 1
    assert new.returncode == 1
    assert old.stdout == ""
    assert new.stdout == ""
    assert "CLAUDE_CODE_SESSION_ID: unbound variable" in old.stderr
    assert "CLAUDE_CODE_SESSION_ID: unbound variable" in new.stderr
    assert "line 21" in old.stderr, "bash stopped naming its own line: %r" % old.stderr
    assert "line 21" not in new.stderr, "the port must not forge a bash line number"


def test_empty_session_id_reaches_the_guard_the_unset_one_cannot() -> None:
    """The CONTROL for the case above: set-but-empty is the only way to reach :27-31, and there both sides agree exactly."""
    with tempfile.TemporaryDirectory() as td:
        base_a = pathlib.Path(td) / "a"
        base_b = pathlib.Path(td) / "b"
        base_a.mkdir()
        base_b.mkdir()
        old = _run("old", _fixture(base_a), base_a, session_id="")
        new = _run("new", _fixture(base_b), base_b, session_id="")
    assert old.returncode == 0
    assert new.returncode == 0
    assert new.stdout == old.stdout
    assert "cannot tell my items from a peer's" in old.stdout


def test_state_age_missing_is_really_reported() -> None:
    """`stat | cut || echo MISSING` only works because of `set -o pipefail`;
    without it `cut` succeeds on empty input and the literal the SUSPECT block tests for never appears. Pinned on both sides."""
    with tempfile.TemporaryDirectory() as td:
        base_a = pathlib.Path(td) / "a"
        base_b = pathlib.Path(td) / "b"
        base_a.mkdir()
        base_b.mkdir()
        old = _run("old", _fixture(base_a, with_state=False), base_a)
        new = _run("new", _fixture(base_b, with_state=False), base_b)
    for label, proc in (("twin", old), ("port", new)):
        assert "DURABLE CONTEXT: my STATE.md MISSING;" in proc.stdout, label
        assert "^ SUSPECT: agent/ holds 3 session dir(s) and" in proc.stdout, label


def test_the_real_worklist_answers_the_same_three_verbs() -> None:
    """ANTI-VACUITY for the canned stand-in: the three argument vectors the brief uses must still be answered by the REAL tracked `worklist.py`, or the fixture would be standing in for something that no longer exists."""
    assert REAL_WORKLIST.is_file(), "the brief's worklist target is gone: %s" % REAL_WORKLIST
    # WORKLIST_SESSION_ID IS DECLARED RATHER THAN THE PREFIX GUESSED. Driven: `worklist.py --list --open zzzzzzzz` under this session exits 1 with
    # "identity mismatch: you passed <me>=zzzzzzzz but this session is ...",
    # because reading as one identity while writing as another gives a session two inboxes. The brief itself never trips this -- it derives the prefix
    # from the very variable the store checks -- but a probe with a synthetic
    # prefix has to say so. Every verb here is READ-ONLY.
    env = dict(os.environ)
    env["WORKLIST_SESSION_ID"] = "zzzzzzzz-0000-0000-0000-000000000000"
    for args in (
        ["--list", "--open"],
        ["--list", "--open", "zzzzzzzz"],
        ["--poll", "zzzzzzzz"],
    ):
        proc = subprocess.run(
            ["python3", str(REAL_WORKLIST), *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            env=env,
        )
        assert proc.returncode == 0, "worklist.py %r exited %d: %s" % (
            args,
            proc.returncode,
            proc.stderr,
        )


# --------------------------------------------------------------------------- The control: a planted defect must turn this differential red ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_this_differential() -> None:
    """"Fix" the phantom-worker regex in a COPY of the port.

    Requiring at least one id character is exactly the change a reader would make on sight, and it is a real divergence from the twin. The mutation is written to a throwaway file; the tracked port is never touched.
    """
    source = PORT.read_text(encoding="utf-8")
    anchor = 'WORKER_RE = re.compile(r"worker:[A-Za-z0-9._-]*")\n'
    assert source.count(anchor) == 1, "the plant's anchor moved"
    broken_src = source.replace(anchor, 'WORKER_RE = re.compile(r"worker:[A-Za-z0-9._-]+")\n')
    assert broken_src != source

    with tempfile.TemporaryDirectory() as td:
        base_a = pathlib.Path(td) / "a"
        base_b = pathlib.Path(td) / "b"
        base_a.mkdir()
        base_b.mkdir()
        root_a = _fixture(base_a, tasks=None)
        root_b = _fixture(base_b, tasks=None)
        broken = pathlib.Path(td) / "standing_orders_brief_broken.py"
        broken.write_text(broken_src, encoding="utf-8")
        old = _run("old", root_a, base_a)
        new = _run("new", root_b, base_b, port_path=broken)
        assert _normalize(new.stdout, root_b, base_b) != _normalize(old.stdout, root_a, base_a), (
            "PLANT DID NOT FIRE: the differential cannot see the phantom worker token"
        )

        # And the real, unmutated file still agrees against the same fixture.
        good = _run("new", root_b, base_b)
        assert _normalize(good.stdout, root_b, base_b) == _normalize(old.stdout, root_a, base_a)

    # The tracked file is byte-identical to what was read at the top.
    assert PORT.read_text(encoding="utf-8") == source

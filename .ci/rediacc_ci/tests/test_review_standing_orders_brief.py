"""`rediacc_ci.review.standing_orders_brief`, driven directly against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED every case below ran the tracked `.claude/lib/standing-orders-brief.sh` and the tracked port over two identical fixture trees and compared exit code, stdout and stderr byte for byte after two normalizations. The K=5 ledger `.ci/shadow/w7p6-standing-orders-brief.observations.jsonl` recorded that verdict over five distinct trees (`npx tsx
scripts/lib/shadow-gate.ts --pair w7p6-standing-orders-brief --assert --k 5` -> "equivalence holds over 5 distinct trees") and licensed the port. W7 P6 then deleted the twin, and the cases that executed it now compare against `goldens/standing-orders-brief/`, which holds the twin's OWN recorded output for each fixture, captured from the tracked script on its last day in the
tree. Nothing here is a hand-written expectation.

THE SEAM IS THE CURRENT DIRECTORY, not the subject's own location. The port reads `.claude/hooks/stop/worklist.py`, `agent/...` and a bare `pwd` relative to wherever it is RUN, so it never has to be copied into the fixture: each case builds a tree and runs the real tracked module with `cwd` set to it.

THE WORKLIST IS A CANNED STAND-IN, AND THAT IS THE POINT. The subject here is the BRIEF, not `worklist.py`; the real store is append-only and shared with other live sessions, so driving it would make this suite depend on what a peer did thirty seconds ago. Each case writes a scripted `.claude/hooks/stop/worklist.py` into the fixture that answers `--list`/`--poll` from a table.
`test_the_real_worklist_answers_the_same_three_verbs` is the anti-vacuity control on that substitution: it drives the REAL tracked `worklist.py` with the brief's own three argument vectors and asserts each one is answered, so the stand-in cannot be standing in for something that no longer exists.

TWO THINGS ARE NORMALIZED, and both have a control. The `at <ts>` stamp comes
from `datetime.now`, which advances between the recording and the run; and
`last grew <n>m ago` is derived from the wall clock the same way. Nothing else is masked: sizes, counts, branch names, paths and every line of prose are compared verbatim.
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
PORT = ROOT / ".ci" / "rediacc_ci" / "review" / "standing_orders_brief.py"
GOLDENS = ROOT / ".ci" / "rediacc_ci" / "tests" / "goldens" / "standing-orders-brief"
REAL_WORKLIST = ROOT / ".claude" / "hooks" / "stop" / "worklist.py"

ME_FULL = "abcd1234-5555-6666-7777-888899990000"
ME = ME_FULL[:8]

# The shape the real store prints, including the `worker:<bg-id>` ADVICE line whose `<` terminates `grep -o`'s character class and yields a phantom bare `worker:` token. That was the twin's behaviour and it is deliberately here.
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
    with_git: bool = False,
    plan_count: int = 3,
    peer_count: int = 2,
    tasks: dict[str, tuple[int, int]] | None = None,
    tasks_dir: bool = True,
) -> pathlib.Path:
    root = base / "tree"
    root.mkdir()

    if with_worklist:
        wl = root / ".claude" / "hooks" / "stop"
        wl.mkdir(parents=True)
        (wl / "worklist.py").write_text(
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
            # A FIXED mtime, so the printed age is byte-stable across the recording and the run instead of drifting with the clock.
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
    cmd = ["python3", str(port_path if port_path is not None else PORT)]
    return subprocess.run(
        cmd, cwd=str(root), capture_output=True, text=True, env=env, check=False, timeout=120
    )


def _render(proc: subprocess.CompletedProcess[str], root: pathlib.Path, base: pathlib.Path) -> str:
    """The recorded shape: one exit line, then the two streams under their own markers."""
    return "exit: %d\n--- stdout ---\n%s--- stderr ---\n%s" % (
        proc.returncode,
        _normalize(proc.stdout, root, base),
        _normalize(proc.stderr, root, base),
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

# The one case outside the table above. A set-but-empty session id is the only way to reach the brief's ownership guard, so it is keyed by a session id rather than by a fixture keyword.
EMPTY_ID_CASE = "session-id-set-but-empty"


@pytest.mark.parametrize(("name", "kwargs"), CASES, ids=[c[0] for c in CASES])
def test_port_matches_the_twins_recorded_output(name: str, kwargs: dict[str, object]) -> None:
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td) / "b"
        base.mkdir()
        root = _fixture(base, **kwargs)  # type: ignore[arg-type]
        actual = _render(_run(root, base), root, base)
    expected = (GOLDENS / ("%s.golden" % name)).read_text(encoding="utf-8")
    assert actual == expected, (
        "%s diverged from the twin's recorded bytes:\n--- twin ---\n%s\n--- port ---\n%s"
        % (name, expected, actual)
    )


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    named = {name for name, _ in CASES} | {EMPTY_ID_CASE}
    on_disk = {p.stem for p in GOLDENS.glob("*.golden")}
    assert named == on_disk, "case names and goldens disagree: only-in-cases=%r only-on-disk=%r" % (
        sorted(named - on_disk),
        sorted(on_disk - named),
    )
    for path in GOLDENS.glob("*.golden"):
        assert path.read_text(encoding="utf-8").startswith("exit: "), (
            "%s is not in the recorded shape" % path.name
        )


def test_the_output_is_not_trivially_short() -> None:
    """ANTI-VACUITY: the comparisons above must be over a real brief, not over a program that printed a banner and stopped."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td) / "v"
        base.mkdir()
        root = _fixture(base, tasks={"deadbeefcafe1234": (4096, 30), "": (12, 30)})
        out = _run(root, base).stdout
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
    """THE SECOND PINNED DEFECT. `grep -o 'worker:[A-Za-z0-9._-]*'` harvested the bare token `worker:` out of the store's own `worker:<bg-id>` advice text, and the brief then reported a lease with an empty id. The port keeps doing it, because the twin did."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td) / "b"
        base.mkdir()
        new = _run(_fixture(base, tasks=None), base)
    assert "    worker:\n" in new.stdout, "the port stopped reproducing the phantom token"


def test_unset_session_id_is_a_named_divergence() -> None:
    """THE FIRST PINNED DEFECT, and the one place the two sides differed on purpose.

    With CLAUDE_CODE_SESSION_ID entirely UNSET, `set -u` killed the twin at its
    `ME="${CLAUDE_CODE_SESSION_ID:0:8}"` line before the friendly guard below it could run, so it exited 1 with empty stdout and `line 21: CLAUDE_CODE_SESSION_ID: unbound variable` on stderr. The port exits 1 and names the same variable in its own words, and must not forge a bash line number that would go stale the first time the twin gained a comment.
    """
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td) / "b"
        base.mkdir()
        new = _run(_fixture(base), base, session_id=None)
    assert new.returncode == 1
    assert new.stdout == ""
    assert "CLAUDE_CODE_SESSION_ID: unbound variable" in new.stderr
    assert "line 21" not in new.stderr, "the port must not forge a bash line number"


def test_empty_session_id_reaches_the_guard_the_unset_one_cannot() -> None:
    """The CONTROL for the case above: set-but-empty is the only way to reach the guard, and the twin's recorded bytes for it are compared here."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td) / "b"
        base.mkdir()
        root = _fixture(base)
        actual = _render(_run(root, base, session_id=""), root, base)
    expected = (GOLDENS / ("%s.golden" % EMPTY_ID_CASE)).read_text(encoding="utf-8")
    assert actual == expected
    assert "cannot tell my items from a peer's" in expected


def test_state_age_missing_is_really_reported() -> None:
    """`stat | cut || echo MISSING` only worked because of `set -o pipefail`;
    without it `cut` succeeds on empty input and the literal the SUSPECT block tests for never appears. The port implements the pipefail-correct branch the twin had."""
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td) / "b"
        base.mkdir()
        new = _run(_fixture(base, with_state=False), base)
    assert "DURABLE CONTEXT: my STATE.md MISSING;" in new.stdout
    assert "^ SUSPECT: agent/ holds 3 session dir(s) and" in new.stdout


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


# --------------------------------------------------------------------------- The control: a planted defect must turn this suite red ---------------------------------------------------------------------------


def test_planted_defect_is_caught_by_the_goldens() -> None:
    """ "Fix" the phantom-worker regex in a COPY of the port.

    Requiring at least one id character is exactly the change a reader would make on sight, and it is a real divergence from what the twin printed. The mutation is written to a throwaway file; the tracked port is never touched.
    """
    source = PORT.read_text(encoding="utf-8")
    anchor = 'WORKER_RE = re.compile(r"worker:[A-Za-z0-9._-]*")\n'
    assert source.count(anchor) == 1, "the plant's anchor moved"
    broken_src = source.replace(anchor, 'WORKER_RE = re.compile(r"worker:[A-Za-z0-9._-]+")\n')
    assert broken_src != source

    expected = (GOLDENS / "rich-slice-tasks-dir-unresolvable.golden").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td) / "b"
        base.mkdir()
        root = _fixture(base, tasks=None)
        broken = pathlib.Path(td) / "standing_orders_brief_broken.py"
        broken.write_text(broken_src, encoding="utf-8")
        assert _render(_run(root, base, port_path=broken), root, base) != expected, (
            "PLANT DID NOT FIRE: the goldens cannot see the phantom worker token"
        )
        # And the real, unmutated file still agrees against the same fixture.
        assert _render(_run(root, base), root, base) == expected

    # The tracked file is byte-identical to what was read at the top.
    assert PORT.read_text(encoding="utf-8") == source

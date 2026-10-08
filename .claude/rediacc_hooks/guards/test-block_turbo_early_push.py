#!/usr/bin/env python3
"""Control harness for block_turbo_early_push (OWN_SUITE: never bash, so no golden), box LF-guard of agent/plans/PLAN-turbo-local-first.md.

REAL REPOSITORIES, one per world, built under a `rediacc_ci.runtmp` run directory by the guard's own `world()` (the same builder its differential `FIXTURES` use, so the suite and the differential judge one shape): a console-shaped checkout on `1008-1` with agent/plans/QUEUE.md, one Promoted plan, `origin/main` at the seed and one unpushed commit. `gh` is stubbed on PATH per case: an open PR, no PR, or down.

BOTH DIRECTIONS. Every refusal has an allow twin that differs by one planted fact: turbo off, every Promoted plan ticked, a valid reason of each kind. Each kind is admitted in its valid case and refused in its invalid one (`backup` under the age threshold, `backup` on `gh pr create`, `red-fix` with no open PR, `ci-cd` naming no plan).

THE LEDGER. An admitted command appends one line per act to agent/ledgers/turbo-push-reasons.jsonl in the world; a refused one, or one whose second act is refused, appends nothing. Both are read back from the file.

THE DEFECT IS PROVEN HERE TOO. The guard's declared `DEFECT` is planted in a copy run through the same payloads, and at least one refusal must flip to allowed; a suite whose green did not depend on the open-plan test would pass that copy too.
"""

import datetime
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_turbo_early_push"
GUARD = HERE / ("%s.py" % STEM)
LEDGER = "agent/ledgers/turbo-push-reasons.jsonl"

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[2] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-turbo-early-push-")

sys.path.insert(0, str(HERE.parents[1]))
_SPEC = importlib.util.spec_from_file_location("turbo_guard_under_test", GUARD)
if _SPEC is None or _SPEC.loader is None:
    raise SystemExit("cannot load %s" % GUARD)
G = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(G)

NOW = datetime.datetime.now(datetime.UTC).isoformat()


def new_dir(prefix):
    return pathlib.Path(tempfile.mkdtemp(prefix=prefix, dir=RUN_TMP)) / "repo"


def world(**kw):
    return G.world(new_dir("world-"), **kw)


def stub(body):
    d = pathlib.Path(tempfile.mkdtemp(prefix="stub-", dir=RUN_TMP))
    (d / "gh").write_text(body, encoding="utf-8")
    (d / "gh").chmod(0o755)
    return str(d)


GH_OPEN = stub("#!/bin/sh\necho 599\n")
GH_NONE = stub("#!/bin/sh\nexit 0\n")
GH_DOWN = stub("#!/bin/sh\necho 'gh: offline' >&2\nexit 1\n")

OPEN_OLD = world()
OPEN_FRESH = world(date=NOW)
DONE = world(box="- [x] FX1 a ticked box\n")
OFF = world(turbo="off")

# Backup valve off: `backup_push_h: 0`.
VALVE_OFF = world()
(VALVE_OFF / "agent/plans/QUEUE.md").write_text(
    (G.FIXTURE_QUEUE % "on").replace("backup_push_h: 4", "backup_push_h: 0"), encoding="utf-8"
)
# Already pushed: origin/1008-1 sits at HEAD, so nothing is unpushed and a backup has nothing to save.
PUSHED = world()
G._git(PUSHED, "update-ref", "refs/remotes/origin/1008-1", "HEAD")
# A moved stub whose target is all ticked (allowed) and one whose target is open (refused).
STUB_DONE = world()
STUB_OPEN = world()
for root, box in ((STUB_DONE, "- [x] FX1 ticked\n"), (STUB_OPEN, "- [ ] FX1 still open\n")):
    (root / "agent/plans/_done").mkdir(parents=True)
    (root / "agent/plans/_done/PLAN-fx-a.md").write_text(G.FIXTURE_PLAN % box, encoding="utf-8")
    (root / "agent/plans/PLAN-fx-a.md").write_text(
        "# PLAN: fx\n\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-fx-a.md\n", encoding="utf-8"
    )
# The Promoted file is gone from agent/plans/ altogether and lives only under _done/, open.
GONE_OPEN = world()
(GONE_OPEN / "agent/plans/_done").mkdir(parents=True)
(GONE_OPEN / "agent/plans/PLAN-fx-a.md").rename(GONE_OPEN / "agent/plans/_done/PLAN-fx-a.md")
# A QUEUE.md that cannot be read as text: fail open, loudly.
UNREADABLE = world()
(UNREADABLE / "agent/plans/QUEUE.md").write_bytes(b"\xff\xfe\x00turbo: on\n")
# A submodule-shaped nested repository under private/.
WITH_SUB = world()
G.world(WITH_SUB / "private" / "renet")
# A repository outside the console.
OUTSIDE = world()

WHY = "PLAN-fx-a FX1 needs the VM E2E matrix that only CI runs"
R = "TURBO_PUSH_REASON='%s' "
PUSH = "git push -u origin 1008-1"

CASES = [
    # (name, command, root, gh, expect_blocked, stderr needle) ---- the three conditions
    ("turbo off: a bare push", PUSH, OFF, GH_NONE, False, ""),
    ("turbo off: gh pr create", "gh pr create --draft -t x -b y", OFF, GH_NONE, False, ""),
    ("every Promoted plan ticked: a bare push", PUSH, DONE, GH_NONE, False, ""),
    ("open box, no reason: a bare push", PUSH, OPEN_OLD, GH_NONE, True, "Open Promoted plans:"),
    ("open box, no reason: gh pr create", "gh pr create --draft", OPEN_OLD, GH_NONE, True, ""),
    ("open box: an implicit push", "git push", OPEN_OLD, GH_NONE, True, ""),
    ("open box: a -C push", "git -C . push origin 1008-1", OPEN_OLD, GH_NONE, True, ""),
    ("open box: an sh -c payload", "sh -c 'git push origin 1008-1'", OPEN_OLD, GH_NONE, True, ""),
    ("open box: a submodule push", "git -C private/renet push", WITH_SUB, GH_NONE, True, ""),
    ("open box: cd into a submodule", "cd private/renet && git push", WITH_SUB, GH_NONE, True, ""),
    # ---- not this guard's business
    ("a dry run", "git push --dry-run origin 1008-1", OPEN_OLD, GH_NONE, False, ""),
    ("a delete push", "git push origin --delete 1007-1", OPEN_OLD, GH_NONE, False, ""),
    ("an empty-source delete", "git push origin :1007-1", OPEN_OLD, GH_NONE, False, ""),
    (
        "the mirror push of main",
        "git push gitlab main:main --follow-tags",
        OPEN_OLD,
        GH_NONE,
        False,
        "",
    ),
    ("prose naming a push", "echo 'git push origin 1008-1'", OPEN_OLD, GH_NONE, False, ""),
    ("a heredoc body", "cat > n.md <<'EOF'\ngit push\nEOF", OPEN_OLD, GH_NONE, False, ""),
    (
        "a repository outside",
        "git -C %s push origin 1008-1" % OUTSIDE,
        OPEN_OLD,
        GH_NONE,
        False,
        "",
    ),
    ("an empty command", "", OPEN_OLD, GH_NONE, False, ""),
    # ---- the reason's grammar
    (
        "an unknown kind",
        (R % ("because: " + WHY)) + PUSH,
        OPEN_OLD,
        GH_NONE,
        True,
        "must be one of",
    ),
    ("a short why", (R % "deadline: soon") + PUSH, OPEN_OLD, GH_NONE, True, "at least 20"),
    ("a bare kind", (R % "deadline") + PUSH, OPEN_OLD, GH_NONE, True, "must be one of"),
    ("an empty reason", "TURBO_PUSH_REASON= " + PUSH, OPEN_OLD, GH_NONE, True, ""),
    (
        "the reason in prose only",
        "echo \"TURBO_PUSH_REASON='deadline: %s'\"; %s" % (WHY, PUSH),
        OPEN_OLD,
        GH_NONE,
        True,
        "",
    ),
    (
        "an exported reason",
        "export TURBO_PUSH_REASON='ci-cd: %s'; %s" % (WHY, PUSH),
        OPEN_OLD,
        GH_NONE,
        False,
        "",
    ),
    (
        "env NAME=value",
        "env TURBO_PUSH_REASON='ci-cd: %s' %s" % (WHY, PUSH),
        OPEN_OLD,
        GH_NONE,
        False,
        "",
    ),
    (
        "an unset reason",
        "export TURBO_PUSH_REASON='ci-cd: %s'; unset TURBO_PUSH_REASON; %s" % (WHY, PUSH),
        OPEN_OLD,
        GH_NONE,
        True,
        "",
    ),
    # ---- ci-cd
    ("ci-cd naming the plan", (R % ("ci-cd: " + WHY)) + PUSH, OPEN_OLD, GH_NONE, False, ""),
    (
        "ci-cd naming the basename",
        (R % "ci-cd: PLAN-fx-a.md box FX1 needs the VM matrix") + PUSH,
        OPEN_OLD,
        GH_NONE,
        False,
        "",
    ),
    (
        "ci-cd naming no plan",
        (R % "ci-cd: the batch needs the VM matrix to run") + PUSH,
        OPEN_OLD,
        GH_NONE,
        True,
        "names no open Promoted plan",
    ),
    # ---- red-fix
    (
        "red-fix with an open PR",
        (R % "red-fix: lint red on the live PR, fixed here") + PUSH,
        OPEN_OLD,
        GH_OPEN,
        False,
        "",
    ),
    (
        "red-fix with no open PR",
        (R % "red-fix: lint red on the live PR, fixed here") + PUSH,
        OPEN_OLD,
        GH_NONE,
        True,
        "has no open PR",
    ),
    (
        "red-fix, gh down (fails open)",
        (R % "red-fix: lint red on the live PR, fixed here") + PUSH,
        OPEN_OLD,
        GH_DOWN,
        False,
        "UNVERIFIED",
    ),
    # ---- deadline
    (
        "deadline",
        (R % "deadline: the 03:00Z CD run needs this fix in") + PUSH,
        OPEN_OLD,
        GH_NONE,
        False,
        "",
    ),
    (
        "deadline on gh pr create",
        (R % "deadline: the 03:00Z CD run needs this fix in") + "gh pr create --draft",
        OPEN_OLD,
        GH_NONE,
        False,
        "",
    ),
    # ---- backup
    (
        "backup, oldest commit far past the threshold",
        (R % "backup: hours of local commits, no PR") + PUSH,
        OPEN_OLD,
        GH_NONE,
        False,
        "",
    ),
    (
        "backup under the threshold",
        (R % "backup: hours of local commits, no PR") + PUSH,
        OPEN_FRESH,
        GH_NONE,
        True,
        "under `backup_push_h: 4`",
    ),
    (
        "backup on gh pr create",
        (R % "backup: hours of local commits, no PR") + "gh pr create --draft",
        OPEN_OLD,
        GH_NONE,
        True,
        "never opens a PR",
    ),
    (
        "backup with the valve off",
        (R % "backup: hours of local commits, no PR") + PUSH,
        VALVE_OFF,
        GH_NONE,
        True,
        "turns the valve off",
    ),
    (
        "backup with nothing unpushed",
        (R % "backup: hours of local commits, no PR") + PUSH,
        PUSHED,
        GH_NONE,
        True,
        "nothing to back up",
    ),
    # ---- two acts: both must be admitted
    (
        "a reasoned push then a bare one",
        (R % ("ci-cd: " + WHY)) + PUSH + "; git push origin 1008-1",
        OPEN_OLD,
        GH_NONE,
        True,
        "",
    ),
    # ---- resolving Promoted entries, and failing open
    ("a moved stub, target ticked", PUSH, STUB_DONE, GH_NONE, False, ""),
    ("a moved stub, target open", PUSH, STUB_OPEN, GH_NONE, True, ""),
    ("an entry only under _done/, open", PUSH, GONE_OPEN, GH_NONE, True, ""),
    # plan_gate._read reads a non-UTF-8 QUEUE.md as absent, so settings fall back to turbo off and the push passes with no note.
    ("an unreadable QUEUE.md reads as turbo off", PUSH, UNREADABLE, GH_NONE, False, ""),
]

BROKEN_RUNNER = (
    "import sys; sys.path.insert(0, %r)\n"
    "from rediacc_hooks import hookio\n"
    "src = open(%r, encoding='utf-8').read()\n"
    "old, new = %r\n"
    "import ast\n"
    "cut = [n for n in ast.parse(src).body if isinstance(n, ast.Assign)"
    " and any(isinstance(t, ast.Name) and t.id == 'DEFECT' for t in n.targets)]\n"
    "outside = '\\n'.join(l for i, l in enumerate(src.split('\\n'), 1)"
    " if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut))\n"
    "assert cut and old in outside, 'DEFECT no longer applies outside its own declaration'\n"
    "ns = {'__name__': 'broken', '__file__': %r}\n"
    "exec(compile(src.replace(old, new), 'broken', 'exec'), ns)\n"
    "ev = hookio.Event(sys.stdin.read())\n"
    "rc = ns['run'](ev)\n"
    "sys.stderr.write(ev.result(rc)[2])\n"
    "sys.exit(rc)\n"
)


def ledger_lines(root):
    path = pathlib.Path(root) / LEDGER
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


def run(command, root, gh, broken=False):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root), PATH="%s:%s" % (gh, os.environ["PATH"]))
    env.pop("TURBO_PUSH_REASON", None)
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(root)}
    )
    if broken:
        argv = [
            sys.executable,
            "-c",
            BROKEN_RUNNER % (str(HERE.parents[1]), str(GUARD), G.DEFECT, str(GUARD)),
        ]
    else:
        argv = [sys.executable, DISPATCH, STEM]
    proc = subprocess.run(argv, input=payload, capture_output=True, text=True, check=False, env=env)
    if proc.returncode not in (0, 2):
        raise SystemExit(
            "%s runner crashed (rc %d): %s"
            % ("broken" if broken else "guard", proc.returncode, proc.stderr[-800:])
        )
    return proc.returncode == 2, proc.stderr


fails = 0
blocked = 0
for name, command, root, gh, want, needle in CASES:
    before = len(ledger_lines(root))
    got, err = run(command, root, gh)
    after = ledger_lines(root)
    blocked += got
    ok = got == want and (not needle or needle in err)
    # The ledger moves exactly when a reasoned command is admitted.
    reasoned = "TURBO_PUSH_REASON='" in command and "echo" not in command
    grew = len(after) > before
    if got and grew:
        ok = False
        print("    a refused command wrote %d ledger line(s)" % (len(after) - before))
    if not got and reasoned and root not in (OFF, DONE, UNREADABLE) and not grew:
        ok = False
        print("    an admitted reason wrote no ledger line")
    fails += not ok
    print(
        "%-52s want=%-8s got=%-8s %s"
        % (
            name,
            "BLOCKED" if want else "allowed",
            "BLOCKED" if got else "allowed",
            "ok" if ok else "*** FAIL ***",
        )
    )
    if not ok:
        print("    needle %r; stderr: %s" % (needle, err.strip().splitlines()[:6]))

# The shape of one ledger line.
rows = [json.loads(line) for line in ledger_lines(OPEN_OLD)]
want_keys = {"ts", "branch", "repo", "act", "kind", "why", "head", "open_promoted"}
if not rows:
    print("*** FAIL *** no ledger line was written in the open-box world")
    fails += 1
else:
    last = rows[-1]
    bad = [
        what
        for what, cond in (
            ("keys", set(last) == want_keys),
            ("branch", last.get("branch") == "1008-1"),
            ("repo", last.get("repo") == "."),
            ("open_promoted", last.get("open_promoted") == 1),
            ("head", len(last.get("head", "")) == 40),
        )
        if not cond
    ]
    if bad:
        print("*** FAIL *** ledger line %r is wrong in: %s" % (last, ", ".join(bad)))
        fails += 1
    else:
        print(
            "ledger: %d line(s) in the open-box world, last %s/%s"
            % (len(rows), last["act"], last["kind"])
        )

print()
flipped = [n for n, c, r, g, w, _ in CASES if w and not run(c, r, g, broken=True)[0]]
if flipped:
    print(
        "DEFECT control: planted %r; %d refusal(s) flipped to allowed, e.g. %r"
        % (G.DEFECT, len(flipped), flipped[0])
    )
else:
    print("*** FAIL *** DEFECT control: with %r planted, every refusal still refused" % (G.DEFECT,))
    fails += 1

if blocked in (0, len(CASES)):
    print("*** FAIL *** the guard answered the same way on every case")
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)

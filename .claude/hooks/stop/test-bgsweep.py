#!/usr/bin/env python3
"""Controls for wl_bgsweep: anchor resolution, the sibling-leak safety proof, age classification.

Run: python3 .claude/hooks/stop/test-bgsweep.py
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import time
from typing import Any

import wl_bgsweep as B
import wl_roster as R


class Tally:
    count = 0
    fails = 0


def ck(name, cond, detail=""):
    Tally.count += 1
    if cond:
        print("  PASS  %s" % name)
    else:
        Tally.fails += 1
        print("  FAIL  %s%s" % (name, ("  -- " + str(detail)) if detail else ""))


print("== 1. ANCHOR RESOLUTION ==")
os.environ["WORKLIST_HARNESS_PID"] = "4242"
ck("override wins outright", B.resolve_anchor([]) == 4242)
del os.environ["WORKLIST_HARNESS_PID"]

table = [(100, 1, "init"), (200, 100, "claude"), (300, 200, "sh")]
os.environ["CLAUDE_PID"] = "200"
orig_getpid, orig_comm = os.getpid, B._read_comm
os.getpid = lambda: 300
B._read_comm = lambda pid: "claude" if pid == 200 else ""
ck("CLAUDE_PID agrees with the comm-walk -> resolves", B.resolve_anchor(table) == 200)

os.environ["CLAUDE_PID"] = "999"
ck("CLAUDE_PID disagrees with the comm-walk -> refuses", B.resolve_anchor(table) is None)

del os.environ["CLAUDE_PID"]
ck("neither resolves -> refuses", B.resolve_anchor(table) is None)
os.getpid, B._read_comm = orig_getpid, orig_comm

print("== 2. THE SIBLING-LEAK SAFETY PROOF (RED/GREEN pair) ==")
# grandparent(1)=anchor's sibling, anchor(10), anchor's real child(11), sibling under grandparent but NOT under anchor(20)
fake_table_with_age = [
    (1, 0, "grandparent", 10000),
    (10, 1, "anchor", 9000),
    (11, 10, "anchor-child", 30 * 60),
    (20, 1, "sibling-under-grandparent", 30 * 60),
]
rooted_at_anchor = B.descendants(10, fake_table_with_age)
ck(
    "GREEN: rooted at the anchor, the real child is found",
    any(r[0] == 11 for r in rooted_at_anchor),
)
ck(
    "GREEN: rooted at the anchor, the sibling under the grandparent is NEVER found",
    not any(r[0] == 20 for r in rooted_at_anchor),
    rooted_at_anchor,
)
rooted_at_grandparent = B.descendants(1, fake_table_with_age)
ck(
    "RED CONTROL: rooting at the grandparent instead DOES leak the sibling -- proving the "
    "anchor choice is load-bearing, not just tidy",
    any(r[0] == 20 for r in rooted_at_grandparent),
)

print("== 3. AGE CLASSIFICATION ==")
os.environ["WORKLIST_HARNESS_PID"] = "1"
below = [(1, 0, "anchor", 0), (2, 1, "young", B.BGSWEEP_AGE_MIN * 60 - 1)]
ck(
    "just under the threshold: not flagged",
    B.sweep(below, [(p, pp, c) for p, pp, c, _a in below]) == [],
)
at = [(1, 0, "anchor", 0), (2, 1, "boundary", B.BGSWEEP_AGE_MIN * 60)]
ck(
    "exactly at the threshold: flagged (boundary)",
    any(r[0] == 2 for r in B.sweep(at, [(p, pp, c) for p, pp, c, _a in at])),
)
unknown = [(1, 0, "anchor", 0), (2, 1, "unaged", None)]
result = B.sweep(unknown, [(p, pp, c) for p, pp, c, _a in unknown])
ck(
    "an unreadable start time is flagged as unknown, never silently dropped, never zero",
    len(result) == 1 and result[0][0] == 2 and result[0][1] is None,
    result,
)
os.environ.pop("WORKLIST_HARNESS_PID", None)

print("== 4. THE _proc_table_with_age_ps() FALLBACK ==")
_orig_run = subprocess.run


class _FakeCompleted:
    returncode = 0
    stdout = (
        "  100     1  36000 claude --resume x\n"
        "  200   100    600 sh -c sleep\n"
        "  300   200  bogus /bin/bash -c broken-etimes\n"
    )


_sp: Any = subprocess
_sp.run = lambda *_a, **_k: _FakeCompleted()
rows = B._proc_table_with_age_ps()
subprocess.run = _orig_run
by_pid = {r[0]: r for r in rows}
ck("a well-formed etimes field parses to an int age", by_pid.get(200, (None,) * 4)[3] == 600)
ck(
    "an unparseable etimes field degrades to age=None, not a crash and not zero",
    300 in by_pid and by_pid[300][3] is None,
    by_pid.get(300),
)

print("== 5. REAL SMOKE TEST: a genuine child, real /proc arithmetic, a mocked clock ==")
proc = subprocess.Popen(["sleep", "2"])
try:
    os.environ["WORKLIST_HARNESS_PID"] = str(os.getpid())
    real_table = B.proc_table_with_age()
    real_child = next((r for r in real_table if r[0] == proc.pid), None)
    ck("the real child is visible in a real /proc walk", real_child is not None, real_table[:3])
    if real_child is not None:
        # Inject an artificially large uptime so the SAME real starttime arithmetic reports the
        # child as 25 minutes old, without an actual 25-minute wait.
        with open("/proc/uptime", encoding="utf-8") as f:
            real_uptime = float(f.read().split()[0])
        aged_table = B._proc_table_with_age_linux(real_uptime + 25 * 60)
        aged_row = next((r for r in aged_table if r[0] == proc.pid), None)
        ck(
            "the SAME real starttime, read again, ages past threshold under an injected clock",
            aged_row is not None and aged_row[3] >= B.BGSWEEP_AGE_MIN * 60,
            aged_row,
        )
        anchor_table = [(p, pp, c) for p, pp, c, _a in aged_table]
        flagged = B.sweep(aged_table, anchor_table)
        ck(
            "sweep() finds the real child once its (mocked-clock) age clears the threshold",
            any(r[0] == proc.pid for r in flagged),
            flagged,
        )
finally:
    proc.wait()
    os.environ.pop("WORKLIST_HARNESS_PID", None)

print("== 7. A LISTED TASK'S PROCESS TREE IS BOOKKEPT ==")
os.environ["WORKLIST_HARNESS_PID"] = "1"
old_age = B.BGSWEEP_AGE_MIN * 60 + 60
tree = [
    (1, 0, "anchor", 0),
    (2, 1, "bash (task bgtask01)", old_age),
    (3, 2, "run-legacy.sh", old_age),
    (4, 3, "docker exec", old_age),
    (5, 1, "bash (forgotten)", old_age),
]
fake_stdout = {2: "bgtask01", 5: "gonetask"}.get
anchors = [(p, pp, c) for p, pp, c, _a in tree]
listed = B.sweep(tree, anchors, live_ids={"bgtask01"}, stdout_task=fake_stdout)
ck(
    "a running task's shell and every descendant are not orphans (2026-09-24: 21 false rows)",
    sorted(r[0] for r in listed) == [5],
    repr(listed),
)
ck(
    "RED CONTROL: without the live task ids the same tree is flagged, collapsed to each subtree's top",
    sorted(r[0] for r in B.sweep(tree, anchors, live_ids=None, stdout_task=fake_stdout)) == [2, 5],
)
ck(
    "a shell writing to a task the harness no longer lists is still an orphan",
    5 in [r[0] for r in listed],
)
os.environ.pop("WORKLIST_HARNESS_PID", None)

print("== 8. THE COMMAND AS TYPED, AND THE PURE WAIT LOOP SHAPE ==")
WRAP = (
    "/bin/bash -B -c source /home/u/.claude/shell-snapshots/snap.sh 2>/dev/null || true && "
    "eval '%s' < /dev/null && pwd -P >| /tmp/claude-1a2b-cwd /bin/bash"
)
POLL = "until [ -s /tmp/claude-1000/p/s/tasks/bd6uzch6r.output ]; do sleep 15; done"
ck("the harness wrapper is peeled to the typed command", B.inner_command(WRAP % POLL) == POLL)
ck(
    "the wrapper's quote escape is undone",
    B.inner_command(WRAP % "echo '\"'\"'hi'\"'\"'") == "echo 'hi'",
    B.inner_command(WRAP % "echo '\"'\"'hi'\"'\"'"),
)
ck("no wrapper: the cmdline itself", B.inner_command("node stub.mjs") == "node stub.mjs")
for cmd in (
    POLL,
    POLL + "; cat /tmp/claude-1000/p/s/tasks/bd6uzch6r.output",
    "cd /tmp && while ! curl -s localhost:8080; do sleep 2; done",
    "while true; do if [ -s /tmp/x ]; then break; fi; sleep 5; done",
    "until test -f /tmp/done\ndo\n  sleep 9\ndone",
    "until [ -s /tmp/ms-render-ar.log ]; do sleep 5; done",
    "until [ -s /tmp/pytest-of-developer/pytest-9/out.txt ]; do sleep 5; done; cat out.txt",
):
    ck("a pure wait loop: %r" % cmd[:60], B.wait_target(cmd) != "", cmd)
for cmd in (
    "until [ -s /tmp/x ]; do sleep 5; done; npm run build",
    "while read l; do process $l; done < list",
    "for l in ar de; do ./run.sh www tutorials video t --lang $l; done",
    "until [ -s /tmp/x ]; do make; sleep 5; done",
    "until python3 .ci/scripts/ci-trace.py --wait 123; do sleep 5; done",
    "python3 .claude/hooks/stop/wl_wake.py d778be9d --minutes 30",
    "sleep 7",
):
    ck(
        "NOT a pure wait loop (control): %r" % cmd[:60],
        B.wait_target(cmd) == "",
        B.wait_target(cmd),
    )
for cmd, name in (
    ("python3 .claude/hooks/stop/wl_wake.py d778be9d --minutes 30", "wake timer"),
    ("python3 .ci/scripts/ci-trace.py 123 --wait", "ci-trace --wait"),
    ("python3 .claude/hooks/stop/wl_prreview.py --check 9 --wait", "wl_prreview --wait"),
    ("python3 .claude/hooks/stop/wl_wait.py --timeout 60", "wl_wait"),
    ("./run.sh www tutorials video t --lang ar", "render"),
    ("python3 -m pytest .claude/rediacc_hooks/tests -q", "test run"),
):
    ck("the exemption is named: %s" % name, B.long_work(cmd) == name, B.long_work(cmd))
ck("control: a stub server is not long work", B.long_work("cd /tmp/pxprobe && node stub.mjs") == "")

print("== 9. DECLARED SHELLS: WAIT LOOPS, DUPLICATES, FINISHED AGENTS, EXEMPTIONS ==")
os.environ["WORKLIST_HARNESS_PID"] = "1"
LIM = B.BGSWEEP_AGE_MIN * 60


def run(rows, stdout, live, owners=None):
    table = [(1, 0, "claude", 0), *rows]
    return B.findings(
        table,
        [(p, pp, c) for p, pp, c, _a in table],
        live_ids=live,
        stdout_task=stdout.get,
        owners=owners,
        pgid_of=lambda _p: None,
        target_note=lambda _t: "target note",
    )


def kinds(found):
    return sorted((f.pid, f.kind) for f in found)


got = run([(2, 1, WRAP % POLL, LIM + 60), (3, 2, "sleep 15", 5)], {2: "bpoll1"}, {"bpoll1"})
ck(
    "a DECLARED pure wait loop past the threshold is reported (the 2026-10-24 gap)",
    kinds(got) == [(2, B.WAIT_LOOP)],
    got,
)
ck(
    "its target rides the finding",
    bool(got) and got[0].target.endswith("bd6uzch6r.output ]"),
    got,
)
ck(
    "RED CONTROL: the old sweep() still excuses the same declared loop",
    B.sweep(
        [(1, 0, "claude", 0), (2, 1, WRAP % POLL, LIM + 60)],
        [(1, 0, "claude"), (2, 1, "x")],
        live_ids={"bpoll1"},
        stdout_task={2: "bpoll1"}.get,
    )
    == [],
)
got = run(
    [(2, 1, "bashcov-sup -- " + WRAP % POLL, LIM + 60), (3, 2, WRAP % POLL, LIM + 60)],
    {2: "bpoll1", 3: "bpoll1"},
    {"bpoll1"},
)
ck(
    "a bash shim layer writing the same task is one finding, at its top",
    kinds(got) == [(2, B.WAIT_LOOP)],
    got,
)
got = run(
    [(2, 1, "python3 holder.py", 5), (3, 2, WRAP % POLL, LIM + 60)],
    {2: "bother", 3: "bpoll1"},
    {"bother", "bpoll1"},
)
ck(
    "a declared task below another task's process is still judged",
    kinds(got) == [(3, B.WAIT_LOOP)],
    got,
)
got = run([(2, 1, WRAP % POLL, LIM - 60)], {2: "bpoll1"}, {"bpoll1"})
ck("control: a lone wait loop under the threshold is not reported", got == [], got)
REN = WRAP % "./run.sh www tutorials video t --lang ar >/tmp/r.log 2>&1"
got = run([(2, 1, REN, LIM * 9)], {2: "brend1"}, {"brend1"})
ck("control: a declared render hours old is not reported", got == [], got)

# Ten waiters on one 0-byte file (3 min to 2h20m old) and a finished writer's stub: the 2026-10-24 shell list.
ages = [3, 9, 15, 19, 25, 40, 61, 90, 115, 140]
rows = [(10 + i, 1, WRAP % POLL, a * 60) for i, a in enumerate(ages)]
stdout = {10 + i: "bw%02d" % i for i in range(len(ages))}
rows.append((50, 1, WRAP % "cd /tmp/pxprobe && node stub.mjs", 102 * 60))
stdout[50] = "bstub1"
calls: list[dict] = []


def owners(ages_by_task):
    calls.append(dict(ages_by_task))
    return {"bstub1": "awriter1"}, {"awriter1"}, {"awriter1": 98}


got = run(rows, stdout, set(stdout.values()), owners)
k = dict(kinds(got))
ck(
    "every waiter past the threshold is a wait-loop",
    sorted(p for p, v in k.items() if v == B.WAIT_LOOP) == [14, 15, 16, 17, 18, 19],
    k,
)
ck(
    "every younger waiter but the newest is a duplicate-wait",
    sorted(p for p, v in k.items() if v == B.DUPLICATE_WAIT) == [11, 12, 13],
    k,
)
ck("control: the newest waiter alone is not reported", 10 not in k, k)
ck("the finished writer's stub is a finished-agent shell", k.get(50) == B.FINISHED_AGENT, k)
ck("the owner lookup was asked about the stub alone", calls == [{"bstub1": 102 * 60}], calls)
f50 = next((f for f in got if f.pid == 50), None)
ck(
    "the finding names the agent and its quiet time",
    f50 is not None and "awriter1" in B.describe(f50) and "98 min" in B.describe(f50),
    f50,
)
got = run(
    [(2, 1, WRAP % POLL, 60), (3, 1, WRAP % POLL.replace("bd6uzch6r", "other1"), 120)],
    {2: "ba", 3: "bb"},
    {"ba", "bb"},
)
ck("control: two young waiters on different targets are not duplicates", got == [], got)

stub = [(50, 1, WRAP % "cd /tmp/pxprobe && node stub.mjs", 102 * 60)]
got = run(stub, {50: "bstub1"}, {"bstub1"}, lambda _a: ({"bstub1": "awriter1"}, set(), {}))
ck("control: the same stub under an agent that is still live is not reported", got == [], got)
got = run(stub, {50: "bstub1"}, {"bstub1"}, lambda _a: ({}, set(), {}))
ck(
    "control: a shell no agent launched (the lead's own) is not a finished-agent shell",
    got == [],
    got,
)
PYT = WRAP % "python3 -m pytest .claude/rediacc_hooks/tests -q"
calls.clear()
got = run([(50, 1, PYT, 102 * 60)], {50: "bt1"}, {"bt1"}, owners)
ck(
    "control: a finished agent's test run is exempt, and no transcript is read",
    got == [] and calls == [],
    (got, calls),
)

WAKE = WRAP % "python3 .claude/hooks/stop/wl_wake.py d778be9d --minutes 30"
got = run([(2, 1, WAKE, LIM * 2)], {2: "bwake1"}, set())
ck(
    "the wake timer is never an orphan (the hook splits it out of the declared ids)",
    got == [],
    got,
)
got = run([(2, 1, WRAP % "tail -f /dev/null", LIM * 2)], {2: "bgone1"}, set())
ck(
    "control: the same undeclared shape that is not the timer is an orphan",
    kinds(got) == [(2, B.ORPHAN)],
    got,
)
LONGRUN = WRAP % "python3 .ci/scripts/ci-trace.py 123 --wait"
got = run([(2, 1, LONGRUN, LIM * 2), (3, 2, "sleep 15", LIM * 2)], {}, set())
ck(
    "an UNDECLARED LONG_WORK run, and its sleep child, are not orphans (8b10b204.1)",
    got == [],
    got,
)
ck(
    "a redirecting echo does not make a pure wait loop (8b10b204.4)",
    B.wait_target("until [ -s /tmp/x ]; do echo tick >> /tmp/log; sleep 5; done") == "",
)
ck(
    "control: a plain echo in the body still does",
    B.wait_target("until [ -s /tmp/x ]; do echo tick; sleep 5; done") != "",
)

print("== 10. THE KILL COMMAND AND THE TARGET NOTE ==")
F = B.Finding
ck(
    "a group leader is killed by group",
    B.kill_command(F(77, 77, 30.0, "x", B.WAIT_LOOP, "", "")) == "kill -- -77",
)
ck(
    "control: a non-leader is killed by pid",
    B.kill_command(F(77, 70, 30.0, "x", B.WAIT_LOOP, "", "")) == "kill 77",
)
ck(
    "control: an unknown group is killed by pid",
    B.kill_command(F(77, None, 30.0, "x", B.ORPHAN, "", "")) == "kill 77",
)
with tempfile.TemporaryDirectory() as d:
    empty = os.path.join(d, "tasks", "bd6uzch6r.output")
    os.makedirs(os.path.dirname(empty))
    open(empty, "w").close()
    note = B._target_note("[ -s %s ]" % empty, now=os.stat(empty).st_mtime + 7200)
    ck(
        "the note says the polled file is empty and unchanged",
        note == "%s: 0 bytes, unchanged 120 min" % empty,
        note,
    )
    ck(
        "control: a missing file says absent",
        B._target_note("[ -s %s/nope ]" % d).endswith("absent"),
    )
os.environ.pop("WORKLIST_HARNESS_PID", None)

print("== 11. THE OWNER LINK READS THE AGENT TRANSCRIPT ==")
with tempfile.TemporaryDirectory() as d:
    sub = pathlib.Path(d)
    done = sub / "agent-adone.jsonl"
    done.write_text('{"toolUseResult":{"backgroundTaskId":"bstub1"}}\n', encoding="utf-8")
    live = sub / "agent-alive.jsonl"
    live.write_text('{"toolUseResult":{"backgroundTaskId":"blive1"}}\n', encoding="utf-8")
    old = time.time() - 60 * 60
    os.utime(done, (old, old))
    os.utime(live, (old, old))
    saved = (R.load_metas, R.session_subagents_dir, R.proven_finished)
    R.session_subagents_dir = lambda _c, _s: sub
    R.load_metas = lambda _d: {
        "adone": {"jsonl": done, "name": ""},
        "alive": {"jsonl": live, "name": ""},
    }
    R.proven_finished = lambda *_a, **_k: True
    try:
        ev = {"background_tasks": [{"id": "alive", "type": "subagent", "status": "running"}]}
        own, fin, quiet = B.owner_context(ev, d, "s", {"bstub1": 7200, "blive1": 7200})
        ck(
            "each shell maps to the agent whose transcript launched it",
            own == {"bstub1": "adone", "blive1": "alive"},
            own,
        )
        ck("an agent the event lists as running is not finished (control)", fin == {"adone"}, fin)
        ck("the quiet time is the transcript's", quiet.get("adone") == 60, quiet)
        own, fin, quiet = B.owner_context(ev, d, "s", {"bstub1": 600})
        ck(
            "control: a transcript older than the shell is never read as its launcher",
            own == {},
            own,
        )
    finally:
        R.load_metas, R.session_subagents_dir, R.proven_finished = saved

print()
if Tally.count < 60:
    print("VACUOUS: only %d checks ran; this suite has 60+" % Tally.count)
    Tally.fails += 1
print("%d checks, %d failures" % (Tally.count, Tally.fails))
sys.exit(1 if Tally.fails else 0)

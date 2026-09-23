#!/usr/bin/env python3
"""Controls for wl_bgsweep: anchor resolution, the sibling-leak safety proof, age classification.

Run: python3 .claude/hooks/stop/test-bgsweep.py
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import wl_bgsweep as B


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
ck("just under the threshold: not flagged", B.sweep(below, [(p, pp, c) for p, pp, c, _a in below]) == [])
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


subprocess.run = lambda *a, **k: _FakeCompleted()
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

print()
if Tally.count < 12:
    print("VACUOUS: only %d checks ran; this suite has 12+" % Tally.count)
    Tally.fails += 1
print("%d checks, %d failures" % (Tally.count, Tally.fails))
sys.exit(1 if Tally.fails else 0)

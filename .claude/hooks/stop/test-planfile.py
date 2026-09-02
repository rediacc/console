#!/usr/bin/env python3
"""Controls for wl_planfile -- agent/PLAN-*.md checkboxes versus the worklist.

    python3 .claude/hooks/stop/test-planfile.py

Run by `.claude/hooks/test-hooks.sh` beside the other stop-hook selftests. That
wiring is not optional and not discovered: the suite runs an EXPLICIT list, and
its own comment records that omitting a block once meant "WITHOUT THIS BLOCK
THOSE CONTROLS RAN NOWHERE".

EVERY CASE HERE IS A PAIR, for the reason the sibling control file states: a
check with only positive cases will happily flag the whole tree, and a matcher
that returns None for everything produces output indistinguishable from a real
finding. So each "this must be reported" is followed by a "this must be SILENT"
built from the same fixture with one thing changed.

The two assertions at the end are about the CALL SITE rather than the module,
and they are the ones that matter most. This check must never become a `vadd`:
the plan it was written for carries 18 open tasks, and 18 blocking items would
refuse every turn of every session in this repo until a multi-week migration
finished. A regression from `outq_add` to `vadd` would look like a tightening
and would wedge the repo, so it is pinned in source.
"""

import ast
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import wl_checks as K  # noqa: E402
import wl_planfid as P  # noqa: E402
import wl_planfile as F  # noqa: E402


class Tally:
    fails = 0
    count = 0


def control(label, got, want):
    Tally.count += 1
    if got != want:
        Tally.fails += 1
        print("FAIL  %s: got %r, wanted %r" % (label, got, want), file=sys.stderr)


def truthy(label, got):
    Tally.count += 1
    if not got:
        Tally.fails += 1
        print("FAIL  %s: got %r, wanted something truthy" % (label, got), file=sys.stderr)


class FakeFold:
    """The two attributes wl_planfile.item_rows touches, and nothing else."""

    def __init__(self, items):
        self.items = items


def item(iid, state, text):
    return {"id": iid, "state": state, "owner": None, "text": text, "basetext": text}


# Plans under MIN_PLAN_CHARS are not read at all, so every on-disk fixture is
# padded. The padding is prose, deliberately NOT bullets, so it cannot become a
# task and quietly change what the fixtures assert.
PAD = (
    "\n\nContext paragraph that exists only to carry this fixture past the "
    "MIN_PLAN_CHARS floor so that read_plan does not discard it. " * 6
)

TASK_A = "Rename every console occurrence onto the agreed convention in a single commit"
TASK_B = "Regenerate the secret reachability baseline with the org admin token"
TASK_C = "Delete the old GitHub org secrets once CI reads from the vault"


def plan_body(status="ready", owner=None, open_tasks=(), done_tasks=(), extra=""):
    head = "Status: %s\n" % status
    if owner:
        head += "Owner: %s\n" % owner
    body = head + "\n# PLAN: a fixture\n\n## Tasks\n\n"
    body += "".join("- [ ] %s\n" % t for t in open_tasks)
    body += "".join("- [x] %s\n" % t for t in done_tasks)
    body += extra
    return body + PAD


def on_disk(body, name="PLAN-fixture.md"):
    """(root, recs) with the fixture written where plan_records will find it."""
    td = tempfile.TemporaryDirectory()
    root = pathlib.Path(td.name)
    (root / "agent").mkdir()
    (root / "agent" / name).write_text(body, encoding="utf-8")
    return td, root, K.plan_records(root)


MINE = "a276391d-41b0-440c-9c6b-868f2f69fecd"

# ---------------------------------------------------------------------------
# 1. THE OPEN/DONE SPLIT, derived from wl_planfid.plan_tasks by set difference
#    rather than by a forked parser. Each assertion has its opposite beside it.
# ---------------------------------------------------------------------------
body = "# P\n\n## Tasks\n\n- [ ] %s\n- [x] %s\n" % (TASK_A, TASK_B)
opens, dones = F.plan_boxes(body)
control("an unticked box is OPEN", opens, [TASK_A])
control("PAIR: a ticked box is DONE, not open", dones, [TASK_B])

# The states wl_planfid deliberately does not count. They are bullets, so under
# an action heading BULLET_RE would otherwise pull them in; the set-difference
# split excludes them for free because they survive both deletions.
q = "# P\n\n## Tasks\n\n- [?] %s\n- [>] %s\n- [ ] %s\n" % (TASK_A, TASK_B, TASK_C)
qo, qd = F.plan_boxes(q)
control("CONTROL: `- [?]` is not an open task", TASK_A in qo, False)
control(
    "CONTROL: `- [>]` is not a task in either set", (TASK_B in qo, TASK_B in qd), (False, False)
)
control("PAIR: the real `- [ ]` beside them still counts", qo, [TASK_C])

# A plain bullet under an action heading IS a wl_planfid task, but it is not a
# checkbox, and the contract this check enforces is about checkbox lines.
pb = "# P\n\n## Tasks\n\n- %s\n- [ ] %s\n" % (TASK_A, TASK_C)
po, pd = F.plan_boxes(pb)
control("CONTROL: a plain bullet is in NEITHER set", (TASK_A in po, TASK_A in pd), (False, False))
control("PAIR: the checkbox beside it is open", po, [TASK_C])

fenced = "# P\n\n## Tasks\n\n```\n- [ ] %s\n```\n- [ ] %s\n" % (TASK_A, TASK_C)
fo, _fd = F.plan_boxes(fenced)
control("CONTROL: a box inside a fence is not a task", fo, [TASK_C])

control(
    "CONTROL: a plan with no boxes yields nothing", F.plan_boxes("# P\n\njust prose\n"), ([], [])
)

# 1b. THE ANTI-VACUITY COUNTER, which is what makes 'no findings' mean anything.
control("raw_box_counts sees the raw lines", F.raw_box_counts(body), (1, 1))
control("CONTROL: raw_box_counts ignores [?] and [>]", F.raw_box_counts(q), (1, 0))

# ---------------------------------------------------------------------------
# 2. MATCHING. Generous on purpose (a false "untracked" makes someone add a
#    duplicate item), so the pair here is the one that keeps it honest.
# ---------------------------------------------------------------------------
rows = F.prepare([("aa11", " ", TASK_A + " (a276391d)")])
control("a verbatim item matches its task", F.match_item(TASK_A, rows), ("aa11", " "))
short = F.prepare([("bb22", " ", " ".join(TASK_A.split()[:8]))])
control(
    "PAIR: an 8-word quote of the task still matches", F.match_item(TASK_A, short), ("bb22", " ")
)
noise = F.prepare([("cc33", " ", "fix the German translation artifacts in the de catalog")])
control("CONTROL: an unrelated item does NOT match", F.match_item(TASK_A, noise), None)
control("CONTROL: no items at all matches nothing", F.match_item(TASK_A, []), None)
control(
    "CONTROL: a task too short to fingerprint matches nothing", F.match_item("do it", rows), None
)
# The matcher must not be satisfied by connective tissue alone.
generic = F.prepare([("dd44", " ", "in a single commit on the agreed convention")])
control("CONTROL: shared filler words alone do not match", F.match_item(TASK_B, generic), None)

# ---------------------------------------------------------------------------
# 3. RECONCILE, all three findings and the silence beside each.
# ---------------------------------------------------------------------------
un, stale, reop = F.reconcile([TASK_A, TASK_B], [], [])
control(
    "both open tasks are untracked when nothing tracks them", (len(un), stale, reop), (2, [], 0)
)
un, stale, reop = F.reconcile([TASK_A, TASK_B], [], [("a", " ", TASK_A), ("b", " ", TASK_B)])
control("PAIR: fully tracked reports nothing", (un, stale, reop), ([], [], 0))

un, stale, reop = F.reconcile([TASK_A], [], [("a", "x", TASK_A)])
control("an open box whose item is TICKED is stale", (un, stale, reop), ([], [(TASK_A, "a")], 0))
un, stale, reop = F.reconcile([TASK_A], [], [("a", "?", TASK_A)])
control("PAIR: a DEFERRED item leaves the box legitimately open", (un, stale, reop), ([], [], 0))
un, stale, reop = F.reconcile([TASK_A], [], [("a", ">", TASK_A)])
control("PAIR: a LEASED item leaves the box legitimately open", (un, stale, reop), ([], [], 0))

un, stale, reop = F.reconcile([], [TASK_A], [("a", " ", TASK_A)])
control("a ticked box whose item is still open is counted", (un, stale, reop), ([], [], 1))
un, stale, reop = F.reconcile([], [TASK_A], [("a", "x", TASK_A)])
control("PAIR: ticked box, ticked item, nothing to say", (un, stale, reop), ([], [], 0))
un, stale, reop = F.reconcile([], [TASK_A], [])
control("PAIR: a ticked box nothing tracks is NOT a finding", (un, stale, reop), ([], [], 0))


# ---------------------------------------------------------------------------
# 4. END TO END over a real file on disk, through the real plan_records and
#    plan_owner. This is the plant: an untracked open task must be REPORTED.
# ---------------------------------------------------------------------------
def rows_for(body, fold_items, session=MINE, name="PLAN-fixture.md"):
    td, root, recs = on_disk(body, name)
    try:
        rows, unread = F.plan_rows(root, recs, FakeFold(fold_items), session, K.plan_owner)
        # The read cap must never bite on a one-plan fixture. Asserted here so a
        # cap regression shows up as a failing control rather than as findings
        # quietly going missing.
        control("  (read cap does not truncate a one-plan fixture)", unread, 0)
        return rows
    finally:
        td.cleanup()


live = plan_body(open_tasks=[TASK_A, TASK_B, TASK_C])
got = rows_for(live, [])
control("THE PLANT: an untracked open task is reported", len(got), 1)
control("  and it names all three", len(got[0]["untracked"]) if got else None, 3)
control("  and it prints the shape", (got[0]["n_open"], got[0]["n_done"]) if got else None, (3, 0))
truthy("  and renders a body", F.render(got[0]) if got else "")

# THE PAIR. Same plan, every task tracked: SILENT. Without this the plant above
# would pass for a check that reports every plan it can read.
tracked = [item("i%d" % n, " ", t) for n, t in enumerate((TASK_A, TASK_B, TASK_C))]
control("CONTROL: the same plan fully tracked is SILENT", rows_for(live, tracked), [])

# One item removed: the count must fall to exactly one, not to zero and not
# stay at three. A matcher stuck on either extreme fails here.
# Indexed defensively: a mutation that empties the row list must be REPORTED as
# a failed control, not raised as an IndexError that skips every case below it
# (including the count floor at the end). That happened on the first mutation
# run and is exactly the "a control that cannot fire" shape in miniature.
_partial = rows_for(live, tracked[:2])
control(
    "PAIR: drop one item and exactly one task is untracked",
    len(_partial[0]["untracked"]) if _partial else "no row at all",
    1,
)

# ---------------------------------------------------------------------------
# 5. SCOPE. Each exemption gets a pair, because an exemption that swallows
#    everything is the quietest possible way for this check to stop existing.
# ---------------------------------------------------------------------------
for st in ("done", "superseded", "landed", "implemented"):
    control(
        "CONTROL: a %s plan is history, not checked" % st,
        rows_for(plan_body(status=st, open_tasks=[TASK_A]), []),
        [],
    )
for st in ("draft", "proposal", "design"):
    control(
        "CONTROL: a %s plan is a proposal, not checked" % st,
        rows_for(plan_body(status=st, open_tasks=[TASK_A]), []),
        [],
    )
# PAIR for both blocklists: the in-scope statuses, INCLUDING words the parser
# does not recognise. The blocklist design means a new status is noisy, never
# invisible -- copying plan_drift's executing-only whitelist would have made
# this check vacuous on the `Status: ready` plan it was written for.
for st in ("ready", "executing", "approved", "accepted", "in-flight"):
    truthy(
        "PAIR: a %s plan IS checked" % st, rows_for(plan_body(status=st, open_tasks=[TASK_A]), [])
    )
truthy(
    "PAIR: a plan with NO parseable status is checked, not skipped",
    rows_for("# PLAN: a fixture\n\n## Tasks\n\n- [ ] %s\n%s" % (TASK_A, PAD), []),
)

control(
    "CONTROL: a PEER-owned plan is never this session's business",
    rows_for(plan_body(owner="9d92d9b6", open_tasks=[TASK_A]), []),
    [],
)
truthy(
    "PAIR: a plan owned by ME is checked",
    rows_for(plan_body(owner="a276391d", open_tasks=[TASK_A]), []),
)
truthy(
    "PAIR: an UNOWNED plan stays in scope, like an untagged item",
    rows_for(plan_body(open_tasks=[TASK_A]), []),
)

# ---------------------------------------------------------------------------
# 6. DEGRADING. Most sessions have no plan at all, and the Stop hook is what
#    lets every session in this repo end a turn, so none of this may raise.
# ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    empty = pathlib.Path(td)
    control("CONTROL: no agent/ directory at all yields nothing", K.plan_records(empty), [])
    control(
        "CONTROL: and plan_rows over it is silent",
        F.plan_rows(empty, [], FakeFold([]), MINE, K.plan_owner),
        ([], 0),
    )
    # A record naming a file that is not there must be skipped, not raised.
    control(
        "CONTROL: a vanished plan file does not raise",
        F.plan_rows(empty, [("agent/PLAN-gone.md", "ready", 9)], FakeFold([]), MINE, K.plan_owner),
        ([], 0),
    )

control(
    "CONTROL: a plan under MIN_PLAN_CHARS is not read",
    rows_for("Status: ready\n\n## Tasks\n\n- [ ] %s\n" % TASK_A, []),
    [],
)
truthy(
    "PAIR: the same plan padded past the floor IS read",
    rows_for("Status: ready\n\n## Tasks\n\n- [ ] %s\n%s" % (TASK_A, PAD), []),
)

# BLINDNESS IS A FINDING. Raw boxes the parser cannot resolve must be named,
# never counted as clean -- otherwise 'no untracked tasks' and 'saw nothing at
# all' print identically.
blind = rows_for(plan_body(open_tasks=["ab", "cd"]), [])
control("a plan whose boxes the parser cannot resolve is reported BLIND", len(blind), 1)
truthy("  and says so in the body", "CANNOT SEE" in F.render(blind[0]) if blind else False)
control(
    "PAIR: a plan whose boxes DO parse is not called blind", rows_for(live, [])[0]["blind"], None
)

# ---------------------------------------------------------------------------
# 7. THE CAP. Eighteen quoted lines every stop is the wall that gets a check
#    switched off; a silent cap is worse still, because it reads as "that is
#    all of them".
# ---------------------------------------------------------------------------
_WORDS = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
many = [
    "Wave %d: rename the %s namespace across every workflow file" % (i, w)
    for i, w in enumerate(_WORDS)
]
big = rows_for(plan_body(open_tasks=many), [])
text = F.render(big[0]) if big else ""
control("all eight are COUNTED", "8 open task(s) have NO worklist item" in text, True)
control("only PLAN_TASK_SHOW are quoted", text.count("worklist.py --add"), F.PLAN_TASK_SHOW)
control(
    "and the remainder is named, not dropped",
    "+ %d more open task(s)" % (8 - F.PLAN_TASK_SHOW) in text,
    True,
)
control("CONTROL: render of nothing is the empty string", F.render(None), "")
control(
    "CONTROL: a row with three findings needs no '+ N more' tail",
    "+ 0 more" in (F.render(rows_for(live, [])[0]) or ""),
    False,
)

# ---------------------------------------------------------------------------
# 8. THE CALL SITE. The module could be perfect and wired as a block, which
#    would wedge every session in the repo. Pinned in source, per the docstring.
# ---------------------------------------------------------------------------
src = (HERE / "wl_checks.py").read_text(encoding="utf-8")
tree = ast.parse(src)
calls = [
    n
    for n in ast.walk(tree)
    if isinstance(n, ast.Call)
    and isinstance(n.func, ast.Attribute)
    and isinstance(n.func.value, ast.Name)
    and n.func.value.id == "wl_planfile"
]
control("wl_checks calls wl_planfile at all", len(calls) >= 1, True)
control("wl_checks imports wl_planfile", "\nimport wl_planfile\n" in src, True)
outq = [
    n
    for n in ast.walk(tree)
    if isinstance(n, ast.Call)
    and isinstance(n.func, ast.Name)
    and n.func.id == "outq_add"
    and n.args
    and isinstance(n.args[3], ast.Constant)
    and n.args[3].value == "plan-tasks"
]
control("the finding is queued as an ADVISORY, exactly once", len(outq), 1)
control(
    "at priority 2, below a blocked peer and above the agent hint",
    outq[0].args[5].value if outq else None,
    2,
)
vadds = [
    n
    for n in ast.walk(tree)
    if isinstance(n, ast.Call)
    and isinstance(n.func, ast.Name)
    and n.func.id == "vadd"
    and n.args
    and isinstance(n.args[0], ast.Constant)
    and n.args[0].value == "plan-tasks"
]
control(
    "CONTROL: it is NOT a vadd -- 18 plan tasks as blocking items would wedge "
    "every session in this repo",
    vadds,
    [],
)

# ---------------------------------------------------------------------------
# 9. THE CONTROL FOR THE CONTROLS. A green run over fixtures that produced no
#    tasks proves nothing at all -- this is assertion 5 of test-always-tier.py
#    in a different suit.
# ---------------------------------------------------------------------------
control("the fixtures really do parse as tasks", len(P.plan_tasks(live)), 3)
truthy(
    "wl_planfid's calibration is what is being reused", P.TASK_MATCH > 0 and P.MIN_MATCH_TOKENS > 0
)
if Tally.count < 45:
    Tally.fails += 1
    print(
        "FAIL  only %d control(s) ran; the file is not being executed as written" % Tally.count,
        file=sys.stderr,
    )

if Tally.fails:
    print("FAIL: %d of %d control(s) failed" % (Tally.fails, Tally.count), file=sys.stderr)
    sys.exit(1)
print("%d control(s) passed" % Tally.count)

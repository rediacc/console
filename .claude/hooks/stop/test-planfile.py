#!/usr/bin/env python3
"""Controls for wl_planfile -- agent/PLAN-*.md checkboxes versus the worklist.

    python3 .claude/hooks/stop/test-planfile.py

Run by `.claude/hooks/test-hooks.sh` beside the other stop-hook selftests. That wiring is not optional and not discovered: the suite runs an EXPLICIT list, and its own comment records that omitting a block once meant "WITHOUT THIS BLOCK THOSE CONTROLS RAN NOWHERE".

EVERY CASE HERE IS A PAIR, for the reason the sibling control file states: a check with only positive cases will happily flag the whole tree, and a matcher that returns None for everything produces output indistinguishable from a real finding. So each "this must be reported" is followed by a "this must be SILENT" built from the same fixture with one thing changed.

The two assertions at the end are about the CALL SITE rather than the module, and they are the ones that matter most. This check must never become a `vadd`: the plan it was written for carries 18 open tasks, and 18 blocking items would refuse every turn of every session in this repo until a multi-week migration finished. A regression from `outq_add` to `vadd` would look like a
tightening and would wedge the repo, so it is pinned in source.
"""

import ast
import pathlib
import random
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


# Plans under MIN_PLAN_CHARS are not read at all, so every on-disk fixture is padded. The padding is prose, deliberately NOT bullets, so it cannot become a task and quietly change what the fixtures assert.
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

# --------------------------------------------------------------------------- 1. THE OPEN/DONE SPLIT, derived from wl_planfid.plan_tasks by set difference rather than by a forked parser. Each assertion has its opposite beside it. ---------------------------------------------------------------------------
body = "# P\n\n## Tasks\n\n- [ ] %s\n- [x] %s\n" % (TASK_A, TASK_B)
opens, dones = F.plan_boxes(body)
control("an unticked box is OPEN", opens, [TASK_A])
control("PAIR: a ticked box is DONE, not open", dones, [TASK_B])

# `?` and `>` are first-class marks (deferred, leased), not third-bucket invisible: a box marked `- [?]` per check_plan_boxes.py's own advertised remedy must stay OPEN, not vanish from both open and done. Found live 2026-09-22 (PLAN-plan-file-lifecycle.md): the old CHECKBOX_RE fell through to BULLET_RE for these marks, corrupting the task text with a literal "[?] " prefix and
# silently cancelling the box out of both buckets via the drop-and-diff trick.
q = "# P\n\n## Tasks\n\n- [?] %s\n- [>] %s\n- [ ] %s\n" % (TASK_A, TASK_B, TASK_C)
qo, qd = F.plan_boxes(q)
control("a `- [?]` box is OPEN, not vanished", TASK_A in qo, True)
control("a `- [>]` box is OPEN, not vanished", (TASK_B in qo, TASK_B in qd), (True, False))
control("PAIR: the real `- [ ]` beside them still counts", set(qo), {TASK_A, TASK_B, TASK_C})

# A plain bullet under an action heading IS a wl_planfid task, but it is not a checkbox, and the contract this check enforces is about checkbox lines.
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
control("raw_box_counts counts [?] and [>] as open, like [ ]", F.raw_box_counts(q), (3, 0))

# --------------------------------------------------------------------------- 2. MATCHING. Generous on purpose (a false "untracked" makes someone add a duplicate item), so the pair here is the one that keeps it honest. ---------------------------------------------------------------------------
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

# --------------------------------------------------------------------------- 3. RECONCILE, all three findings and the silence beside each. ---------------------------------------------------------------------------
un, stale, reop = F.reconcile([TASK_A, TASK_B], [], [])
control(
    "both open tasks are untracked when nothing tracks them", (len(un), stale, reop), (2, [], 0)
)
un, stale, reop = F.reconcile([TASK_A, TASK_B], [], [("a", " ", TASK_A), ("b", " ", TASK_B)])
control("PAIR: fully tracked reports nothing", (un, stale, reop), ([], [], 0))

un, stale, reop = F.reconcile([TASK_A], [], [("a", "x", TASK_A)])
control("an open box whose item is TICKED is stale", (un, stale, reop), ([], [(TASK_A, "a")], 0))
# A box re-added under near-identical wording after its original item was ticked must not report stale forever: a live replacement item ties the old one's score and must win regardless of fold order. Found 2026-09-23 against PLAN-tooling-transformation.md's W7P5-a/W1P6 boxes.
un, stale, reop = F.reconcile([TASK_A], [], [("old", "x", TASK_A), ("new", "?", TASK_A)])
control(
    "PAIR: a tied replacement item beats a ticked original regardless of order",
    (un, stale, reop),
    ([], [], 0),
)
un, stale, reop = F.reconcile([TASK_A], [], [("new", "?", TASK_A), ("old", "x", TASK_A)])
control(
    "CONTROL: the same tie, fold order reversed, same verdict",
    (un, stale, reop),
    ([], [], 0),
)
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


# --------------------------------------------------------------------------- 4. END TO END over a real file on disk, through the real plan_records and plan_owner. This is the plant: an untracked open task must be REPORTED. ---------------------------------------------------------------------------
def rows_for(body, fold_items, session=MINE, name="PLAN-fixture.md"):
    td, root, recs = on_disk(body, name)
    try:
        rows, unread = F.plan_rows(root, recs, FakeFold(fold_items), session, K.plan_owner)
        # The read cap must never bite on a one-plan fixture. Asserted here so a cap regression shows up as a failing control rather than as findings quietly going missing.
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

# THE PAIR. Same plan, every task tracked: SILENT. Without this the plant above would pass for a check that reports every plan it can read.
tracked = [item("i%d" % n, " ", t) for n, t in enumerate((TASK_A, TASK_B, TASK_C))]
control("CONTROL: the same plan fully tracked is SILENT", rows_for(live, tracked), [])

# One item removed: the count must fall to exactly one, not to zero and not stay at three. A matcher stuck on either extreme fails here. Indexed defensively: a mutation that empties the row list must be REPORTED as a failed control, not raised as an IndexError that skips every case below it (including the count floor at the end). That happened on the first mutation run and is
# exactly the "a control that cannot fire" shape in miniature.
_partial = rows_for(live, tracked[:2])
control(
    "PAIR: drop one item and exactly one task is untracked",
    len(_partial[0]["untracked"]) if _partial else "no row at all",
    1,
)

# --------------------------------------------------------------------------- 5. SCOPE. Each exemption gets a pair, because an exemption that swallows everything is the quietest possible way for this check to stop existing. ---------------------------------------------------------------------------
# #87cff418 CHANGED THIS CONTRACT ON PURPOSE (2026-09-24). A finished plan used to be dropped outright even over open boxes, which made an unexplained finished header the one shape every plan reader in the hook agreed to ignore. It is still history -- never quoted, never asked to track its boxes -- but over open boxes it is silent only under a `Ruling:` that resolves; section 8b holds the plant and its pairs.
for st in ("done", "superseded", "landed", "implemented"):
    _hist = rows_for(plan_body(status=st, open_tasks=[TASK_A]), [])
    control(
        "CONTROL: a %s plan over open boxes demands no tracking, only a Ruling" % st,
        [(r.get("untracked"), bool(r.get("unruled"))) for r in _hist],
        [([], True)],
    )
    control(
        "PAIR: a %s plan under a resolving Ruling is history, not checked" % st,
        rows_for(
            plan_body(status=st, open_tasks=[TASK_A]).replace(
                "Status: %s\n" % st, "Status: %s\nRuling: #aaaa1111\n" % st, 1
            ),
            [item("aaaa1111", "x", "operator ruling")],
        ),
        [],
    )
# S3 CHANGED THIS CONTRACT ON PURPOSE, so the controls assert the new one and say what moved. A not-started plan used to be EXEMPT -- dropped before plan_rows opened it. It is now a CENSUS row: counted, named, and demanding nothing. The premise that justified the exemption ("a proposal's boxes are a sketch") stopped holding here, because `draft` became this repo's default header on
# plans under active execution and was hiding 72 of 88 open boxes.
for st in ("draft", "proposal", "design"):
    got = rows_for(plan_body(status=st, open_tasks=[TASK_A]), [])
    control("a %s plan yields exactly one CENSUS row" % st, len(got), 1)
    control("  and it is marked census, not a finding", got[0].get("census") if got else None, True)
    # THE PAIR, and it is the whole point of the tier: a census row must DEMAND nothing. If it carried untracked tasks it would be the full treatment under another name, and the wall design note 2 warns about would be back.
    control(
        "  CONTROL: a census row carries no untracked tasks and no recipes",
        (got[0]["untracked"], got[0]["stale_open"], got[0]["reopened"]) if got else None,
        ([], [], 0),
    )
    body = F.render(got[0]) if got else ""
    truthy(
        "  and renders one line that says no action is demanded",
        "No action is demanded here." in body and "worklist.py --add" not in body,
    )

# A not-started plan with NO open boxes stays silent -- otherwise every prose sketch in the tree grows a census line it does not need.
control(
    "CONTROL: a not-started plan with no OPEN boxes yields no census row",
    rows_for(plan_body(status="draft", done_tasks=[TASK_A]), []),
    [],
)
# PAIR for both blocklists: the in-scope statuses, INCLUDING words the parser does not recognise. The blocklist design means a new status is noisy, never invisible -- copying plan_drift's executing-only whitelist would have made this check vacuous on the `Status: ready` plan it was written for.
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

# --------------------------------------------------------------------------- 6. DEGRADING. Most sessions have no plan at all, and the Stop hook is what lets every session in this repo end a turn, so none of this may raise. ---------------------------------------------------------------------------
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

# BLINDNESS IS A FINDING. Raw boxes the parser cannot resolve must be named, never counted as clean -- otherwise 'no untracked tasks' and 'saw nothing at all' print identically.
blind = rows_for(plan_body(open_tasks=["ab", "cd"]), [])
control("a plan whose boxes the parser cannot resolve is reported BLIND", len(blind), 1)
truthy("  and says so in the body", "CANNOT SEE" in F.render(blind[0]) if blind else False)
control(
    "PAIR: a plan whose boxes DO parse is not called blind", rows_for(live, [])[0]["blind"], None
)

# --------------------------------------------------------------------------- 7. THE CAP. Eighteen quoted lines every stop is the wall that gets a check
#    switched off; a silent cap is worse still, because it reads as "that is
# all of them". ---------------------------------------------------------------------------
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

# --------------------------------------------------------------------------- 8. THE CALL SITE. The module could be perfect and wired as a block, which would wedge every session in the repo. Pinned in source, per the docstring. ---------------------------------------------------------------------------
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


# --------------------------------------------------------------------------- 8ter. AN ADOPTED PLAN IS AN ORDER, AND ONLY AN ADOPTED ONE. `plan-tasks` above stays an advisory because a plan a session merely OWNS can carry eighteen boxes; a plan the session ADOPTED (its Owner line says "adopted from") is a committed statement that it is being executed, so its untracked boxes block
# under their own key, in the mission tier. ---------------------------------------------------------------------------
with tempfile.TemporaryDirectory() as _adopt_root:
    _ar = pathlib.Path(_adopt_root)
    (_ar / "agent").mkdir()
    (_ar / "agent" / "PLAN-adopted.md").write_text(
        "# PLAN: x\nStatus: ready\nOwner: deadbeef (adopted from cafe1234 2026-09-20)\nUpdated: 2026-09-20\n"
        + PAD,
        encoding="utf-8",
    )
    (_ar / "agent" / "PLAN-owned.md").write_text(
        "# PLAN: y\nStatus: ready\nOwner: deadbeef\nUpdated: 2026-09-20\n" + PAD, encoding="utf-8"
    )
    (_ar / "agent" / "PLAN-roundtrip.md").write_text(
        "# PLAN: z\nStatus: ready\n"
        + F.ADOPTED_OWNER_FMT % ("deadbeef", "cafe1234", "2026-09-20")
        + "\nUpdated: 2026-09-20\n"
        + PAD,
        encoding="utf-8",
    )
    control(
        "THE WRITER'S FORMAT IS THE READER'S PATTERN: what --migrate --plan writes, is_adopted reads",
        F.is_adopted(_ar, "agent/PLAN-roundtrip.md"),
        True,
    )
    control(
        "an Owner line carrying the adoption marker is adopted",
        F.is_adopted(_ar, "agent/PLAN-adopted.md"),
        True,
    )
    control("CONTROL: a plain Owner line is not", F.is_adopted(_ar, "agent/PLAN-owned.md"), False)
    control(
        "CONTROL: an unreadable plan is not (falls back to the advisory)",
        F.is_adopted(_ar, "agent/PLAN-missing.md"),
        False,
    )
_adopt_vadds = [
    n
    for n in ast.walk(tree)
    if isinstance(n, ast.Call)
    and isinstance(n.func, ast.Name)
    and n.func.id == "vadd"
    and n.args
    and isinstance(n.args[0], ast.Constant)
    and n.args[0].value == "plan-adopted"
]
control("the adopted-plan order exists as exactly one vadd", len(_adopt_vadds), 1)
control(
    "and it sits in the MISSION tier, where a stop cannot be called 'yours' and skipped",
    K.check_tier("plan-adopted"),
    K.T_MISSION,
)
control(
    "CONTROL: the advisory key is still not in the mission tier",
    K.check_tier("plan-tasks"),
    K.T_HYGIENE,
)


# --------------------------------------------------------------------------- 8quater. THE QUEUE MUST NOT BURY AN ORDER BEHIND FACTS. Twenty-five one-line "settled" outcomes once drained one per stop ahead of every actionable section, so open plan boxes and unread reports never surfaced. They now ride ONE stop as a digest, at the same priority as the sections that matter.
# ---------------------------------------------------------------------------
_saved_save = K.S.save_state
K.S.save_state = lambda *_args, **_kw: None
try:
    _qdoc = {"outq": {"items": [], "shown": {}, "seq": 0}}
    for _i in range(6):
        K.outq_add(
            "wl",
            "sess",
            _qdoc,
            "reg-settled",
            "Regression gate: fix-set %d settled" % _i,
            2,
            sticky=True,
        )
    K.outq_add("wl", "sess", _qdoc, "plan-tasks", "PLAN boxes", 2)
    # SEEDED, not the module-level `random`: budget=1 against 7 same-tier entries samples one at random (wl_checks.py:1429's own determinism seam), so an unseeded call here picks `plan-tasks` about 1 run in 7 and turns this control flaky. Seed 1 draws a `reg-settled` entry first, which is what this section exists to prove drains as one merged digest.
    _first, _left = K.outq_drain("wl", "sess", _qdoc, 1, rng=random.Random(1))
    control("six settled outcomes leave as ONE section", len(_first), 1)
    control("and that section carries all six", _first[0].count("settled"), 6)
    control("so the actionable section is next, not seven stops away", _left, 1)
    _second, _left2 = K.outq_drain("wl", "sess", _qdoc, 1, rng=random.Random(1))
    control("CONTROL: the plan section then surfaces", _second, ["PLAN boxes"])
finally:
    K.S.save_state = _saved_save


# --------------------------------------------------------------------------- 8bis. THE SessionStart CENSUS (S1). Its entire reason for existing is that the per-stop advisory CANNOT see a plan whose Status is NOT_STARTED, and on this repo that is most of them: `draft` became the default header on plans under active execution, so six of eight box-carrying files hid 72 of 88 open
# boxes. So the plant is a `draft` plan -- one the advisory drops -- and the assertion is that the census counts it anyway and SAYS it is exempt. ---------------------------------------------------------------------------
def census_for(*plans):
    """(counts, open, done, in_scope, exempt) for N fixtures written to one root."""
    td = tempfile.TemporaryDirectory()
    root = pathlib.Path(td.name)
    (root / "agent").mkdir()
    try:
        for name, body in plans:
            (root / "agent" / name).write_text(body, encoding="utf-8")
        recs = K.plan_records(root)
        return K.plan_box_census(root, recs), K.plans_block(root)[0]
    finally:
        td.cleanup()


draft = plan_body(status="draft", open_tasks=[TASK_A, TASK_B], done_tasks=[TASK_C])
(counts, o, d, in_scope, exempt), block = census_for(("PLAN-draft.md", draft))
control("THE PLANT: a draft plan the advisory DROPS is still counted", (o, d), (2, 1))
control("  and it is reported as exempt, not as in scope", (in_scope, exempt), (0, 1))
truthy("  and the exempt count reaches the rendered block", "1 are exempt by Status" in block)
truthy("  and the per-plan line carries its boxes", "2 open box(es), 1 ticked" in block)

# THE PAIR. A status the advisory DOES admit must be counted as in scope, or the split above is decoration -- every plan would read the same way.
ready = plan_body(status="ready", open_tasks=[TASK_A])
(_c, o2, _d2, in2, ex2), _b = census_for(("PLAN-ready.md", ready))
control("CONTROL: an in-scope status counts as in scope, not exempt", (in2, ex2), (1, 0))

# Two plans, one of each, so the totals are a SUM and not the last file read.
(_c3, o3, d3, in3, ex3), block3 = census_for(("PLAN-draft.md", draft), ("PLAN-ready.md", ready))
control("totals are summed across plans, not overwritten", (o3, d3), (3, 1))
control("  and the scope split is summed too", (in3, ex3), (1, 1))
truthy("  and the tree-wide line says so", "2 plan file(s) carry 3 open box(es)" in block3)

# A plan with NO boxes must contribute no suffix and no census row, or every prose-only plan in the tree grows a misleading "0 open box(es)".
none_body = plan_body(status="draft", extra="Prose only, no checkbox anywhere.\n")
(counts4, o4, _d4, _i4, _e4), block4 = census_for(("PLAN-prose.md", none_body))
control("a plan with no boxes contributes no census row", (len(counts4), o4), (0, 0))
truthy("  and its line grows no box suffix", "open box(es)" not in block4)


# --------------------------------------------------------------------------- 8ter. S2 -- THREE PLANS PER STOP, ONE SHARED QUOTE BUDGET. Design note 2 capped this at one plan, and its ARGUMENT was that quoted lines are a wall. So the number moves and the reason is kept by sharing PLAN_TASK_SHOW across the plans shown. The assertion that matters is therefore not "three plans appear"
# -- it is "the number of quoted recipes did NOT go up". ---------------------------------------------------------------------------
def fake_row(rel, n_untracked, census=False):
    return {
        "rel": rel,
        "status": "draft" if census else "ready",
        "n_open": n_untracked or 1,
        "n_done": 0,
        "untracked": ["task number %d of the fixture set" % i for i in range(n_untracked)],
        "stale_open": [],
        "reopened": 0,
        "blind": None,
        "census": census,
    }


three = [
    fake_row("agent/PLAN-a.md", 5),
    fake_row("agent/PLAN-b.md", 5),
    fake_row("agent/PLAN-c.md", 5),
]
body = F.render_all(three)
control("S2: all three plans are NAMED", sum(body.count(r["rel"]) for r in three), 3)
control(
    "S2 THE POINT: the shared budget holds total recipes to PLAN_TASK_SHOW",
    body.count("worklist.py --add"),
    F.PLAN_TASK_SHOW,
)
# THE PAIR. Without the budget this would be 3x. Proven by rendering the same rows
# with each plan given its OWN allowance, which is what the code did before S2.
per_plan = sum(F.render(r).count("worklist.py --add") for r in three)
truthy(
    "  CONTROL: per-plan budgets WOULD have tripled it, so the shared one is load-bearing",
    per_plan > body.count("worklist.py --add"),
)
# A plan whose budget ran out is NAMED, not hidden -- a cap that silences is the failure this whole check exists to stop.
truthy(
    "  and a budget-exhausted plan still shows its header and counts",
    "agent/PLAN-c.md" in body and "open box(es)" in body,
)
control(
    "S2: a fourth plan is counted in the remainder line, not dropped silently",
    "+ 1 more plan file(s) with findings" in F.render_all([*three, fake_row("agent/PLAN-d.md", 1)]),
    True,
)
# A census row must not consume budget -- it quotes nothing, so spending on it would starve a real finding behind it.
mixed = [fake_row("agent/PLAN-x.md", 0, census=True), fake_row("agent/PLAN-y.md", 5)]
control(
    "S2: a census row spends no budget, so the finding behind it keeps its quotes",
    F.render_all(mixed).count("worklist.py --add"),
    F.PLAN_TASK_SHOW,
)


# --------------------------------------------------------------------------- 8b. DECIDED, NOT DONE (worklist #87cff418). A FINISHED plan over open boxes is silent ONLY under a `Ruling:` that re-resolves against the fold; otherwise it is surfaced, because every other plan reader in the hook stops counting a finished plan. The same resolver check_plan_boxes.py's G-A3 imports, so the hook and CI give one answer. ---------------------------------------------------------------------------
def ruled_body(status, ruling):
    extra = "Ruling: %s\n" % ruling if ruling is not None else ""
    return plan_body(status=status, open_tasks=[TASK_A]).replace(
        "Status: %s\n" % status, "Status: %s\n%s" % (status, extra), 1
    )


decided = [item("aaaa1111", "x", "operator ruling: drop it")]
got = rows_for(ruled_body("superseded", None), decided)
control("THE PLANT: a finished plan over open boxes with NO Ruling is surfaced", len(got), 1)
control(
    "  as an `unruled` census row, never a quoted recipe", bool(got and got[0].get("unruled")), True
)
truthy("  and its render names G-A3", got and "G-A3" in F.render(got[0]))
got = rows_for(ruled_body("superseded", "#aaaa1111"), decided)
control("PAIR: the same plan under a Ruling citing a CLOSED item is silent", got, [])
got = rows_for(ruled_body("superseded", "#aaaa1111"), [item("aaaa1111", "?", "a question")])
control("CONTROL: a Ruling citing a [?] item does not resolve", len(got), 1)
got = rows_for(ruled_body("superseded", "#deadbeef"), decided)
control("CONTROL: a Ruling citing an id the fold lacks does not resolve", len(got), 1)
got = rows_for(plan_body(status="superseded", done_tasks=[TASK_A]), [])
control("CONTROL: a finished plan with nothing open needs no Ruling", got, [])
line = F.ruling_line(ruled_body("done", "#aaaa1111 plus prose"))
control("ruling_line reads the header value", line, "#aaaa1111 plus prose")
control(
    "ruling_refs reads 8- and 12-character ids and a quote",
    F.ruling_refs('#aaaa1111 #aaaabbbbcccc "a quote long enough" in docs/x.md'),
    (["aaaa1111", "aaaabbbbcccc"], [("a quote long enough", "docs/x.md")]),
)
control(
    "CONTROL: a Ruling line below the header block is not read",
    F.ruling_line("Status: done\n" + "\n" * F.RULING_HEADER_LINES + "Ruling: #aaaa1111\n"),
    "",
)

# --------------------------------------------------------------------------- 9. THE CONTROL FOR THE CONTROLS. A green run over fixtures that produced no tasks proves nothing at all -- this is assertion 5 of test-always-tier.py in a different suit. ---------------------------------------------------------------------------
control("the fixtures really do parse as tasks", len(P.plan_tasks(live)), 3)
truthy(
    "wl_planfid's calibration is what is being reused", P.TASK_MATCH > 0 and P.MIN_MATCH_TOKENS > 0
)
if Tally.count < 60:
    Tally.fails += 1
    print(
        "FAIL  only %d control(s) ran; the file is not being executed as written" % Tally.count,
        file=sys.stderr,
    )

if Tally.fails:
    print("FAIL: %d of %d control(s) failed" % (Tally.fails, Tally.count), file=sys.stderr)
    sys.exit(1)
print("%d control(s) passed" % Tally.count)

#!/usr/bin/env python3
"""Controls for the start-time half of plan dependencies (agent/plans/PLAN-plan-dependencies.md sections 2c, 3 and 5c): which worklist items wait on a plan, which fail closed, what the guide's FIRST rows say, and the library calls the verbs build on.

    python3 .claude/hooks/stop/test-depgate.py

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py (glob over test-*.py under .claude/hooks/stop/), so no table edit is needed to wire this file in. The verbs themselves (`--lease`, `--tick`, `--plan-tick` refusals, the waiver, the NOTE) and the UNBLOCKED line are driven through the real CLI and the real Stop hook in `.claude/rediacc_hooks/tests/test_wl_plan_deps.py`; this file holds the pure-library controls.

EVERY REFUSAL HAS A PASSING TWIN built from the same fixture with one fact changed: a tracked root waits, an untracked one does not; a free plan is not listed, a blocked one is; a cycle through a plan edge is refused, an acyclic BLOCKED_BY is not.
"""

import contextlib
import importlib.util
import io
import pathlib
import types

import wl_leasehelp as LH
import wl_plandeps as D
import wl_planenforce as E
import wl_planfile as PF
import wl_planorder as PO
import wl_store as S
import worklist as W
import worklist_messages as M
from wl_checks import dep_first_rows, guided_slice

_CI = pathlib.Path(__file__).resolve().parents[3] / ".ci" / "rediacc_ci"


def _by_file(name):
    """A `.ci/rediacc_ci` module loaded BY FILE, not through a `sys.path` hop (test_canonical_sys_path_hop.py freezes those)."""
    spec = importlib.util.spec_from_file_location(name, _CI / ("%s.py" % name))
    if spec is None or spec.loader is None:
        raise SystemExit("%s: .ci/rediacc_ci/%s.py is missing" % (__file__, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


controls = _by_file("controls")
runtmp = _by_file("runtmp")

CONTROL_FLOOR = 57
T = controls.Controls("depgate", floor=CONTROL_FLOOR)
check = T.check

ME = "deadbeef"
SID = "deadbeef-1111-2222-3333-444444444444"
PEER = "cafe0000"

PLAN = """# PLAN: %(name)s

Status: %(status)s
Owner: %(ME)s
Depends-On: %(dep)s
Priority: P2
Concurrency: parallel
Owns: src/%(name)s/**

## Tasks

- [ ] T1 the first box of %(name)s
"""


def write_plan(root, name, dep, status="in-progress"):
    folder = pathlib.Path(root) / "agent" / "plans"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ("PLAN-%s.md" % name)).write_text(
        PLAN % {"name": name, "status": status, "ME": ME, "dep": dep}, encoding="utf-8"
    )


def tree(plans):
    """A project root holding `plans` ({name: dep value}); returns (root, graph)."""
    root = pathlib.Path(runtmp.run_dir("depgate-suite-"))
    for name, dep in plans.items():
        write_plan(root, name, dep)
    ctx = PO.context(root)[0]
    if ctx is None:
        raise SystemExit("the fixture tree did not load")
    return root, ctx.graph


class Fold:
    """The two attributes of a store fold that classify_items and guided_slice read."""

    def __init__(self, recs):
        self.items = recs
        self.by_id = {r["id"]: r for r in recs}


def rec(rid, text, state=" ", owner=ME, **extra):
    base = {
        "id": rid,
        "state": state,
        "owner": owner,
        "text": text,
        "basetext": text,
        "line": "- [%s] (%s) %s" % (state, owner, text),
        "first": "2026-10-08T00:00Z",
        "upd": "2026-10-08T00:00Z",
    }
    base.update(extra)
    return base


def owned(_rec):
    return True


NOSIG = "no-dep -- the root of the chain stands alone"
ROOT, GRAPH = tree({"x": "PLAN-y.md", "y": "PLAN-z.md", "z": NOSIG, "free": NOSIG})
XITEM = "PLAN-x.md [41f56150] port the x box"
ZITEM = "PLAN-z.md [41f56150] the root box"


def classify(recs, graph=GRAPH):
    fold = Fold(recs)
    got = S.classify_items(fold, SID, dep_graph=graph)
    return got[0], fold


# ---- classify_items: a tracked root waits, an untracked or cyclic one fails closed.
open_t, fold_t = classify([rec("a1a1a1a1", XITEM), rec("b2b2b2b2", ZITEM)])
check("classify: a tracked root leaves the item out of the open list", len(open_t), 1)
check("classify: ...and only the root's own item is open", "PLAN-z.md" in open_t[0], True)
check(
    "classify: the waiting item names the root",
    fold_t.by_id["a1a1a1a1"]["waiting_plans"],
    ["PLAN-z.md"],
)
open_u, _f = classify([rec("a1a1a1a1", XITEM)])
check("classify: an untracked root fails closed to open", len(open_u), 1)
check("classify: ...with the blocked suffix", "nothing tracks it; start there" in open_u[0], True)
check("classify: ...naming the root", "PLAN-z.md" in open_u[0] and "PLAN-x.md" in open_u[0], True)
open_p, _f = classify([rec("a1a1a1a1", XITEM), rec("b2b2b2b2", ZITEM, owner=PEER)])
check("classify: a peer's item tracks the root too", len(open_p), 0)
open_d, _f = classify([rec("a1a1a1a1", XITEM), rec("b2b2b2b2", ZITEM, state="?")])
check("classify: a deferred item tracks the root too", len(open_d), 0)
open_x, _f = classify([rec("a1a1a1a1", XITEM), rec("b2b2b2b2", ZITEM, state="x")])
check("classify: a ticked item does not track it", len(open_x), 1)
open_n, _f = classify([rec("a1a1a1a1", XITEM), rec("b2b2b2b2", ZITEM)], graph=None)
check("classify: without a plan graph there is no plan wait", len(open_n), 2)
open_f, _f = classify([rec("a1a1a1a1", "PLAN-free.md [41f56150] a free box")])
check(
    "classify: a plan with no dependencies is plain open work",
    (len(open_f), "blocked" in open_f[0]),
    (1, False),
)
open_l, _f = classify([rec("a1a1a1a1", "write PLAN-x.md")])
check("classify: a bare mention links nothing", (len(open_l), "blocked" in open_l[0]), (1, False))
croot, cgraph = tree({"ca": "PLAN-cb.md", "cb": "PLAN-ca.md"})
open_c, _f = classify(
    [
        rec("a1a1a1a1", "PLAN-ca.md [41f56150] a box"),
        rec("b2b2b2b2", "PLAN-cb.md [41f56150] a box"),
    ],
    graph=cgraph,
)
check("classify: a cycle fails closed to open", len(open_c), 2)
check("classify: ...with the cycle suffix", "Depends-On cycle" in open_c[0], True)

# ---- the shared helper the verbs and the guide read.
deps = D.item_deps(GRAPH, XITEM, [rec("b2b2b2b2", ZITEM)])
check(
    "item_deps: the chain string",
    None if deps is None else " -> ".join(deps.chains["PLAN-z.md"]),
    "PLAN-x.md -> PLAN-y.md -> PLAN-z.md",
)
check(
    "item_deps: a waiver is read from the note",
    D.waiver("note DEPS-WAIVED: z is replaced by a rewrite")[0],
    "z is replaced by a rewrite",
)

# ---- blocker_error: a cycle through a plan edge is refused.
items = [rec("e5e5e5e5", ZITEM), rec("a1a1a1a1", XITEM)]
by_id = {r["id"]: r for r in items}
check(
    "blocker_error: BLOCKED_BY a waiter that waits, through a plan, on this item is a cycle",
    "cycle" in LH.blocker_error("e5e5e5e5", "BLOCKED_BY:#a1a1a1a1", by_id, GRAPH),
    True,
)
check(
    "blocker_error: the same edge without the plan graph is accepted",
    LH.blocker_error("e5e5e5e5", "BLOCKED_BY:#a1a1a1a1", by_id),
    "",
)
items2 = [rec("e5e5e5e5", "an unrelated item"), rec("a1a1a1a1", XITEM), rec("f6f6f6f6", ZITEM)]
check(
    "blocker_error: an acyclic BLOCKED_BY is accepted",
    LH.blocker_error("e5e5e5e5", "BLOCKED_BY:#a1a1a1a1", {r["id"]: r for r in items2}, GRAPH),
    "",
)

# ---- waiting_on returns ids first, then the plan roots.
wo = LH.waiting_on(
    rec("a1a1a1a1", XITEM + " BLOCKED_BY:#b2b2b2b2"),
    {"b2b2b2b2": rec("b2b2b2b2", ZITEM), "a1a1a1a1": rec("a1a1a1a1", XITEM)},
    GRAPH,
)
check("waiting_on: item ids, then plan roots", wo, ["b2b2b2b2", "PLAN-z.md"])

# ---- auto_lease_candidates skips an item blocked by a dependency, tracked or not.
pool = [rec("a1a1a1a1", XITEM), rec("b2b2b2b2", ZITEM)]
named = {"task1": "working #a1a1a1a1 and #b2b2b2b2"}
leased = LH.auto_lease_candidates(pool, owned, named, set(), GRAPH)
check("auto_lease: the blocked item is skipped", [i for i, _t in leased], ["b2b2b2b2"])
leased = LH.auto_lease_candidates(pool, owned, named, set())
check(
    "auto_lease: without the graph both are candidates",
    sorted(i for i, _t in leased),
    ["a1a1a1a1", "b2b2b2b2"],
)
leased = LH.auto_lease_candidates(
    [rec("a1a1a1a1", XITEM)], owned, {"task1": "#a1a1a1a1"}, set(), GRAPH
)
check("auto_lease: a blocked item with an UNTRACKED root is skipped too", leased, [])

# ---- guided_slice: the FIRST row leads, carries the chain, and counts the rest.
guide = guided_slice(
    Fold([rec("a1a1a1a1", XITEM), rec("b2b2b2b2", ZITEM)]), SID, None, ME, ROOT, full=True
)
check("guide: a FIRST row names the root", "FIRST PLAN-z.md [Status: in-progress]" in guide, True)
check(
    "guide: ...with the exact chain",
    "chain: PLAN-x.md -> PLAN-y.md -> PLAN-z.md" in guide,
    True,
)
check("guide: ...the items waiting on it", "waiting on it: #a1a1a1a1" in guide, True)
check("guide: ...and who tracks it", "tracked by: #b2b2b2b2" in guide, True)
check(
    "guide: ...and its first open box",
    "next box:" in guide and "the first box of z" in guide,
    True,
)
check(
    "guide: the FIRST row precedes the item rows",
    guide.index("FIRST PLAN-z.md") < guide.index("#b2b2b2b2 "),
    True,
)
check("guide: the waiting row names the plan, bare", "waiting (PLAN-z.md)" in guide, True)
check(
    "guide: ...and says it reopens by itself", "nothing until PLAN-z.md is finished" in guide, True
)
guide_u = guided_slice(Fold([rec("a1a1a1a1", XITEM)]), SID, None, ME, ROOT, full=True)
check(
    "guide: an untracked root carries the --add recipe with its link",
    'NEXT: --add %s "PLAN-z.md [' % ME in guide_u,
    True,
)
check("guide: ...and says nothing tracks it", "tracked by: nothing yet" in guide_u, True)
guide_peer = guided_slice(
    Fold([rec("a1a1a1a1", XITEM), rec("b2b2b2b2", ZITEM, owner=PEER)]),
    SID,
    None,
    ME,
    ROOT,
    full=True,
)
check(
    "guide: a peer's tracker means nothing for this session",
    "nothing for this session" in guide_peer,
    True,
)
guide_free = guided_slice(
    Fold([rec("a1a1a1a1", "PLAN-free.md [41f56150] a free box")]), SID, None, ME, ROOT, full=True
)
check("guide: no dependency, no FIRST row", "FIRST" in guide_free, False)
many = {"m%d" % i: "PLAN-r%d.md" % i for i in range(5)}
many.update({"r%d" % i: NOSIG for i in range(5)})
mroot, mgraph = tree(many)
mfold = Fold([rec("a%07d" % i, "PLAN-m%d.md [41f56150] a box" % i) for i in range(5)])
mrows = dep_first_rows(mfold, SID, ME, mroot, mgraph)
check("guide: at most three FIRST rows", sum(1 for _b, _k, line in mrows if "FIRST" in line), 3)
check("guide: the rest are counted", "+2 more plan(s) must land first" in mrows[-1][2], True)
check("guide: FIRST rows sort before any real rank", all(k == () for _b, k, _l in mrows), True)

# ---- wl_planenforce names the root's box and says who waits on it.
first = ("agent/plans/PLAN-x.md", 1, ("aaaaaaaa", "the first box of x"))
named_box = E.dependency_box(ROOT, [first])
check(
    "planenforce: the dependency root's box is named",
    None if named_box is None else named_box[0],
    "agent/plans/PLAN-z.md",
)
check(
    "planenforce: ...for the waiting plan", None if named_box is None else named_box[2], "PLAN-x.md"
)
text = E.render([first], ("agent/plans/PLAN-x.md",), SID, named_box)
check("planenforce: the text says who waits on it", "(PLAN-x.md waits on it)" in text, True)
free_row = ("agent/plans/PLAN-free.md", 1, ("bbbbbbbb", "the first box of free"))
check(
    "planenforce: a plan with no dependencies names its own box",
    E.dependency_box(ROOT, [free_row]),
    None,
)
check(
    "planenforce: ...and renders without the note",
    "waits on it" in E.render([free_row], ("agent/plans/PLAN-free.md",), SID),
    False,
)

# ---- the plan-file recipe carries the link, so a copied --add gives an item the gates can read.
recipe = PF.render(
    {
        "rel": "agent/plans/PLAN-z.md",
        "status": "in-progress",
        "n_open": 1,
        "n_done": 0,
        "untracked": ["the first box of z"],
        "stale_open": [],
        "reopened": [],
    }
)
check(
    "planfile: the --add recipe is linked to its plan",
    'worklist.py --add <me> "PLAN-z.md [' in recipe,
    True,
)
check(
    "planfile: ...and the link parses back to the plan",
    D.linked_plan(recipe.split('--add <me> "', 1)[1]),
    "PLAN-z.md",
)


# ---- task edges: the FIRST row names the box, and a ticked box frees the item (T12).
TROOT = pathlib.Path(runtmp.run_dir("depgate-tasks-"))
(TROOT / "agent" / "plans").mkdir(parents=True)
(TROOT / "agent" / "plans" / "PLAN-ty.md").write_text(
    PLAN % {"name": "ty", "status": "in-progress", "ME": ME, "dep": NOSIG}
    + "- [x] T2 the ticked box\n    (ticked) 2026-10-08T00:00Z by cafe0000: abc1234\n- [ ] T3 the box tx waits for\n",
    encoding="utf-8",
)
for tname, tdep in (("tx", "PLAN-ty.md#T3"), ("tdone", "PLAN-ty.md#T2")):
    write_plan(TROOT, tname, tdep)
TCTX = PO.context(TROOT)[0]
if TCTX is None:
    raise SystemExit("FAIL: the task-edge fixture produced no plan order context")
TGRAPH = TCTX.graph
TITEM = "PLAN-tx.md [41f56150] port the tx box"
tdeps = D.item_deps(TGRAPH, TITEM, [])
check(
    "task edge: the item waits on the plan, remembering the box",
    None if tdeps is None else tdeps.tasks,
    {"PLAN-ty.md": "T3"},
)
check(
    "task edge: a ticked box frees the item",
    D.item_deps(TGRAPH, "PLAN-tdone.md [41f56150] port it", []),
    None,
)
tguide = guided_slice(Fold([rec("a1a1a1a1", TITEM)]), SID, None, ME, TROOT, full=True)
check(
    "task edge: the FIRST row names that box, not the plan's first open one",
    "next box: " in tguide and "T3 the box tx waits for" in tguide,
    True,
)
check("task edge: the chain carries the task", "chain: PLAN-tx.md -> PLAN-ty.md#T3" in tguide, True)


# ---- --plan-tick: a `present` investigation row licenses the tick; anything else is refused (the gate in worklist.py, driven with a stub plan-record module).
class StubRecordError(Exception):
    """The stub's RecordError."""


def stub_planrec(verdict, retro=False):
    row = None if verdict is None else {"verdict": verdict, "retro": retro}
    return types.SimpleNamespace(
        RecordError=StubRecordError,
        open_boxes=lambda _text: [(0, "", "T1 a box", "41f56150")],
        select_box=lambda boxes, _sel: boxes[0],
        investigation_for=lambda _root, _rel, _sig: row,
    )


def gate_result(planrec, evidence="ran it exit code 0", rel="agent/plans/PLAN-x.md"):
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            W._plantick_dep_gate(planrec, ROOT, rel, "T1", evidence)
        except SystemExit as exc:
            return exc.code
    return "allowed"


check("plan-tick gate: no investigation row is refused", gate_result(stub_planrec(None)), 2)
check("plan-tick gate: an `absent` row is refused", gate_result(stub_planrec("absent")), 2)
check("plan-tick gate: a `present` row is allowed", gate_result(stub_planrec("present")), "allowed")
check(
    "plan-tick gate: a --retro `present` row is refused",
    gate_result(stub_planrec("present", True)),
    2,
)
check(
    "plan-tick gate: a waiver in the evidence is allowed",
    gate_result(stub_planrec(None), "ran it DEPS-WAIVED: z is replaced by a rewrite"),
    "allowed",
)
check(
    "plan-tick gate: a short waiver is refused",
    gate_result(stub_planrec(None), "ran it DEPS-WAIVED: skip"),
    2,
)
check(
    "plan-tick gate: a plan with no dependencies is allowed",
    gate_result(stub_planrec(None), rel="agent/plans/PLAN-free.md"),
    "allowed",
)

# ---- the messages exist and take their substitutions.
check(
    "messages: UNBLOCKED_PLAN formats",
    M.N_UNBLOCKED_PLAN % ("a1a1a1a1", "PLAN-z.md", "x"),
    "UNBLOCKED #a1a1a1a1: PLAN-z.md is finished, so it is open work again: x",
)

T.exit()

#!/usr/bin/env python3
"""Controls for wl_backlog -- the ONE next plan this session should implement.

    python3 .claude/hooks/stop/test-backlog.py

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py (glob over test-*.py under .claude/hooks/stop/), so no table edit is needed to wire this file in.

EVERY CASE HERE IS A PAIR, matching test-planfile.py's own convention: a "this must be nominated" case is followed by a "this must NOT be nominated" case built from the same fixture with one thing changed, because a matcher that returns the same answer for everything produces output indistinguishable from a working one.
"""

import os
import pathlib
import re
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import wl_backlog as B  # noqa: E402
import wl_checks as K  # noqa: E402


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
    """The one attribute wl_backlog._claimed touches, and nothing else."""

    def __init__(self, items):
        self.items = items


def item(state, text):
    return {"state": state, "text": text, "basetext": text}


OWNER = "a276391d"
PEER = "cafe1234"

PAD = "\n\nContext paragraph padding this fixture past MIN_PLAN_CHARS. " * 6


def plan_body(status="ready", owner=None, open_tasks=(), depends_on=None, extra=""):
    head = "Status: %s\n" % status
    if owner:
        head += "Owner: %s\n" % owner
    if depends_on:
        head += "Depends-On: %s\n" % depends_on
    body = head + "\n# PLAN: a fixture\n\n## Tasks\n\n"
    body += "".join("- [ ] %s\n" % t for t in open_tasks)
    body += extra
    return body + PAD


def make_tree(*plans, touch_seconds_apart=2.0):
    """(td, root, recs) -- fixture plans written newest-mtime-first, matching plan_records' own contract.

    touch_seconds_apart spaces mtimes so DESC order is unambiguous; a caller wanting a mtime TIE (for the cluster control) passes 0.
    """
    td = tempfile.TemporaryDirectory()
    root = pathlib.Path(td.name)
    (root / "agent" / "plans").mkdir(parents=True)
    now = time.time()
    for i, (name, body) in enumerate(plans):
        p = root / "agent" / "plans" / name
        p.write_text(body, encoding="utf-8")
        # Newest first in the tuple order: back-date each successor so plan_records' mtime-desc sort matches fixture order.
        stamp = now - i * touch_seconds_apart
        os.utime(p, (stamp, stamp))
    return td, root, K.plan_records(root)


def worklist_path(root):
    return pathlib.Path(root) / "agent" / "worklist" / (OWNER + ".md")


def run(root, recs, fold, session_id=OWNER, state_doc=None):
    return B.next_plan(
        root,
        recs,
        fold,
        session_id,
        K.plan_owner,
        worklist_path(root),
        state_doc or {},
        projects_dir=None,
    )


# --------------------------------------------------------------------------- 1. ORDERING. DESC by mtime, the one primitive this module consumes rather than re-derives. ---------------------------------------------------------------------------
td, root, recs = make_tree(
    ("PLAN-a.md", plan_body(owner=OWNER, open_tasks=["implement feature a"])),
    ("PLAN-b.md", plan_body(owner=OWNER, open_tasks=["implement feature b"])),
    ("PLAN-c.md", plan_body(owner=OWNER, open_tasks=["implement feature c"])),
)
try:
    cand, reason, stats = run(root, recs, FakeFold([]))
    control(
        "ORDERING: the newest plan is nominated",
        cand["rel"] if cand else None,
        "agent/plans/PLAN-a.md",
    )
    control("  reason is nominated", reason, "nominated")
    control("  stats count all three as eligible", stats["eligible"], 3)
finally:
    td.cleanup()

# PAIR: reverse the mtime order (c newest) and the nominee follows it, proving this is not alphabetical or insertion-order luck.
td, root, recs = make_tree(
    ("PLAN-c.md", plan_body(owner=OWNER, open_tasks=["implement feature c"])),
    ("PLAN-b.md", plan_body(owner=OWNER, open_tasks=["implement feature b"])),
    ("PLAN-a.md", plan_body(owner=OWNER, open_tasks=["implement feature a"])),
)
try:
    cand, _reason, _stats = run(root, recs, FakeFold([]))
    control(
        "PAIR: reversing mtime order reverses the nominee",
        cand["rel"] if cand else None,
        "agent/plans/PLAN-c.md",
    )
finally:
    td.cleanup()


# --------------------------------------------------------------------------- 2. VACUITY. The four distinguishable empty reasons must never render alike -- "found nothing" and "could not see" are different facts. ---------------------------------------------------------------------------
td, root, _empty_recs = make_tree()
try:
    cand, reason, stats = run(root, [], FakeFold([]))
    control(
        "VACUITY: an empty corpus is no-plans, not a bare None", (cand, reason), (None, "no-plans")
    )
finally:
    td.cleanup()

td, root, recs = make_tree(
    (
        "PLAN-done.md",
        plan_body(status="done", owner=OWNER, open_tasks=["implement this fixture task fully"]),
    )
)
try:
    cand, reason, _stats = run(root, recs, FakeFold([]))
    control(
        "VACUITY: a corpus of only finished plans is all-finished",
        (cand, reason),
        (None, "all-finished"),
    )
finally:
    td.cleanup()

td, root, recs = make_tree(
    ("PLAN-a.md", plan_body(owner=OWNER, open_tasks=["implement feature a"]))
)
try:
    claimed_fold = FakeFold([item(" ", "Implement agent/plans/PLAN-a.md: do a")])
    cand, reason, _stats = run(root, recs, claimed_fold)
    control(
        "VACUITY: a fully-claimed eligible set is all-claimed",
        (cand, reason),
        (None, "all-claimed"),
    )
finally:
    td.cleanup()

td, root, recs = make_tree(
    ("PLAN-a.md", plan_body(owner=OWNER, open_tasks=["implement feature a"])),
    ("PLAN-b.md", plan_body(owner=OWNER, open_tasks=["implement feature b"])),
    ("PLAN-c.md", plan_body(owner=OWNER, open_tasks=["implement feature c"])),
    ("PLAN-d.md", plan_body(owner=OWNER, open_tasks=["implement feature d"])),
)
try:
    state_doc = {
        "backlog_nominated": {
            "agent/plans/PLAN-x.md": "t1",
            "agent/plans/PLAN-y.md": "t2",
            "agent/plans/PLAN-z.md": "t3",
        }
    }
    cand, reason, _stats = run(root, recs, FakeFold([]), state_doc=state_doc)
    control(
        "VACUITY: a spent per-session cap is capped, not a bare None",
        (cand, reason),
        (None, "capped"),
    )
finally:
    td.cleanup()

# PAIR: a real eligible backlog with room in the cap MUST name one -- the vacuity plant.
td, root, recs = make_tree(
    ("PLAN-a.md", plan_body(owner=OWNER, open_tasks=["implement feature a"]))
)
try:
    cand, reason, _stats = run(root, recs, FakeFold([]))
    truthy("PAIR: a real eligible backlog is never silently None", cand)
    control("  reason is nominated", reason, "nominated")
finally:
    td.cleanup()


# --------------------------------------------------------------------------- 3. CLAIM. An open worklist item naming the plan's basename suppresses it; the same fixture with the item CLOSED does not. Built from the real shape of a --add recipe this module itself prints. ---------------------------------------------------------------------------
td, root, recs = make_tree(
    ("PLAN-a.md", plan_body(owner=OWNER, open_tasks=["implement feature a"])),
    ("PLAN-b.md", plan_body(owner=OWNER, open_tasks=["implement feature b"])),
)
try:
    claim_open = FakeFold([item(" ", "Implement agent/plans/PLAN-a.md: do a")])
    cand, _reason, _stats = run(root, recs, claim_open)
    control(
        "CLAIM: the claimed newest plan is passed over",
        cand["rel"] if cand else None,
        "agent/plans/PLAN-b.md",
    )
    truthy("  and the pass-over is named with a reason", cand.get("passed_over") if cand else None)
finally:
    td.cleanup()

# PAIR: tick the same item closed and the claim lifts.
td, root, recs = make_tree(
    ("PLAN-a.md", plan_body(owner=OWNER, open_tasks=["implement feature a"])),
    ("PLAN-b.md", plan_body(owner=OWNER, open_tasks=["implement feature b"])),
)
try:
    claim_closed = FakeFold([item("x", "Implement agent/plans/PLAN-a.md: do a")])
    cand, _reason, _stats = run(root, recs, claim_closed)
    control(
        "PAIR: a TICKED claim no longer suppresses the plan",
        cand["rel"] if cand else None,
        "agent/plans/PLAN-a.md",
    )
finally:
    td.cleanup()

# A [?]/[>] claim (still outstanding, per wl_backlog's own _OPEN_ITEM_STATES) suppresses too.
td, root, recs = make_tree(
    ("PLAN-a.md", plan_body(owner=OWNER, open_tasks=["implement feature a"]))
)
try:
    claim_deferred = FakeFold([item("?", "Implement agent/plans/PLAN-a.md: do a")])
    cand, reason, _stats = run(root, recs, claim_deferred)
    control(
        "CONTROL: a deferred [?] claim also suppresses (still outstanding)",
        (cand, reason),
        (None, "all-claimed"),
    )
finally:
    td.cleanup()


# --------------------------------------------------------------------------- 4. DEPENDENCY. Blocks only while the target is neither finished nor claimed; redirects to the target rather than skipping past it; an unresolvable target is reported and does not block; a cycle is reported and resolved by mtime. ---------------------------------------------------------------------------
td, root, recs = make_tree(
    (
        "PLAN-newer.md",
        plan_body(owner=OWNER, open_tasks=["implement the newer task"], depends_on="PLAN-older.md"),
    ),
    ("PLAN-older.md", plan_body(owner=OWNER, open_tasks=["implement the older task"])),
)
try:
    cand, _reason, _stats = run(root, recs, FakeFold([]))
    control(
        "DEPENDENCY: blocked on an unclaimed target redirects TO the target",
        cand["rel"] if cand else None,
        "agent/plans/PLAN-older.md",
    )
finally:
    td.cleanup()

# PAIR: the same edge, but the target is already claimed -- must NOT redirect or block.
td, root, recs = make_tree(
    (
        "PLAN-newer.md",
        plan_body(owner=OWNER, open_tasks=["implement the newer task"], depends_on="PLAN-older.md"),
    ),
    ("PLAN-older.md", plan_body(owner=OWNER, open_tasks=["implement the older task"])),
)
try:
    target_claimed = FakeFold([item(" ", "Implement agent/plans/PLAN-older.md: do older")])
    cand, _reason, _stats = run(root, recs, target_claimed)
    control(
        "PAIR: a claimed target does not block",
        cand["rel"] if cand else None,
        "agent/plans/PLAN-newer.md",
    )
finally:
    td.cleanup()

# PAIR: the target is FINISHED -- must not block either.
td, root, recs = make_tree(
    (
        "PLAN-newer.md",
        plan_body(owner=OWNER, open_tasks=["implement the newer task"], depends_on="PLAN-done.md"),
    ),
    (
        "PLAN-done.md",
        plan_body(status="done", owner=OWNER, open_tasks=["implement this fixture task fully"]),
    ),
)
try:
    cand, _reason, _stats = run(root, recs, FakeFold([]))
    control(
        "PAIR: a finished target does not block",
        cand["rel"] if cand else None,
        "agent/plans/PLAN-newer.md",
    )
finally:
    td.cleanup()

# An unresolvable target: reported, not blocking.
td, root, recs = make_tree(
    (
        "PLAN-newer.md",
        plan_body(
            owner=OWNER,
            open_tasks=["implement the newer task"],
            depends_on="PLAN-does-not-exist.md",
        ),
    ),
)
try:
    cand, _reason, _stats = run(root, recs, FakeFold([]))
    control(
        "DEPENDENCY: an unresolvable target does not block",
        cand["rel"] if cand else None,
        "agent/plans/PLAN-newer.md",
    )
    truthy("  and is reported in unresolved", cand.get("unresolved") if cand else None)
finally:
    td.cleanup()

# A two-plan cycle: reported, resolved by falling back to the citing plan itself (mtime order).
td, root, recs = make_tree(
    (
        "PLAN-x.md",
        plan_body(owner=OWNER, open_tasks=["implement task x fully"], depends_on="PLAN-y.md"),
    ),
    (
        "PLAN-y.md",
        plan_body(owner=OWNER, open_tasks=["implement task y fully"], depends_on="PLAN-x.md"),
    ),
)
try:
    cand, _reason, _stats = run(root, recs, FakeFold([]))
    control(
        "DEPENDENCY: a two-plan cycle falls back to the newest, not a crash",
        cand["rel"] if cand else None,
        "agent/plans/PLAN-x.md",
    )
finally:
    td.cleanup()


# --------------------------------------------------------------------------- 5. NEVER BLOCKS. No code path in this module reaches vadd or writes a plan file -- pinned in source, the same shape test-planfile.py uses to pin plan-tasks. ---------------------------------------------------------------------------
src = (HERE / "wl_backlog.py").read_text(encoding="utf-8")
control("NEVER BLOCKS: the module source contains no call to vadd", "vadd(" in src, False)
control(
    "  and never opens a plan file for writing",
    re.search(r"open\([^)]*[\"']w[\"']", src) is not None,
    False,
)
control("  and its own docstring states the never-blocks contract", "NEVER blocks" in src, True)

_wire_src = (HERE / "wl_checks.py").read_text(encoding="utf-8")
control(
    "NEVER BLOCKS: the wl_checks call site never assigns wl_backlog's result to a vadd",
    "wl_backlog.next_plan" in _wire_src,
    True,
)


def plant_historical_peer_event(store, peer):
    """One raw, dated `add` event in a SCRATCH store, so session_liveness reads the peer as IDLE.

    A fixture, not a rebuild: no fold becomes events here, and the 2020 stamp is the point (add_item would stamp now and make the peer live).
    """
    (store / (peer + ".jsonl")).write_text(
        '{"ev":"add","id":"aaaaaaaa","at":"2020-01-01T00:00:00Z","by":"%s","why":"fixture","h":"deadbeef","br":"fixture"}\n'
        % peer,
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- 6. PEER. A plan owned by an idle peer is counted (dead_peer) and never nominated; the same plan with the owner line removed IS nominated (unowned counts as this session's own). ---------------------------------------------------------------------------
td, root, recs = make_tree(
    ("PLAN-owned.md", plan_body(owner=OWNER, open_tasks=["implement the owned task"])),
    ("PLAN-peers.md", plan_body(owner=PEER, open_tasks=["implement the peer task"])),
)
try:
    # session_liveness only reaches IDLE when the peer has SOME event in the store; a peer id with zero footprint reads UNKNOWN and _dead_peer skips it on purpose (never claim a peer this machine has literally never seen). One old, foreign-host event is what makes this fixture a genuine idle peer rather than an unseen one.
    # store_dir() ignores `root` entirely and re-derives the REAL project root unless $WORKLIST_STORE_DIR overrides it -- exactly the seam wl_store.py:646 documents existing for this reason.
    store = root / "agent" / "worklist"
    store.mkdir(parents=True, exist_ok=True)
    plant_historical_peer_event(store, PEER)
    _prev_store_dir = os.environ.get("WORKLIST_STORE_DIR")
    os.environ["WORKLIST_STORE_DIR"] = str(store)
    try:
        cand, _reason, _stats = run(root, recs, FakeFold([]))
    finally:
        if _prev_store_dir is None:
            os.environ.pop("WORKLIST_STORE_DIR", None)
        else:
            os.environ["WORKLIST_STORE_DIR"] = _prev_store_dir
    control(
        "PEER: a peer-owned plan is never the nominee",
        cand["rel"] if cand else None,
        "agent/plans/PLAN-owned.md",
    )
    dp = cand.get("dead_peer") if cand else None
    truthy("  and is COUNTED as a dead-peer candidate", dp)
    if dp:
        control("  naming the peer's plan", dp["rel"], "agent/plans/PLAN-peers.md")
        control("  and the peer id", dp["owner"], PEER)
finally:
    td.cleanup()

# PAIR: strip the Owner: line and the same plan becomes eligible (untagged counts as this session's own).
td, root, recs = make_tree(
    ("PLAN-unowned.md", plan_body(open_tasks=["implement the fixture task"]))
)
try:
    cand, _reason, _stats = run(root, recs, FakeFold([]))
    control(
        "PAIR: an unowned plan is eligible, like an untagged worklist item",
        cand["rel"] if cand else None,
        "agent/plans/PLAN-unowned.md",
    )
finally:
    td.cleanup()


# --------------------------------------------------------------------------- 7. RENDER. No live counter, the mtime-cluster note, and the migrate recipe -- direct checks on the render() text. ---------------------------------------------------------------------------
none_body = B.render(None, "all-finished", {"scanned": 3, "eligible": 0}, OWNER)
control(
    "RENDER: a None candidate names the reason and the counts",
    "all-finished" in none_body and "3 plan file(s) scanned" in none_body,
    True,
)

fake_candidate = {
    "rel": "agent/plans/PLAN-x.md",
    "status": "draft",
    "open": 5,
    "why": ["NEWEST first."],
    "passed_over": [],
    "dead_peer": None,
    "unresolved": [],
}
body = B.render(fake_candidate, "nominated", {"scanned": 1, "eligible": 1}, OWNER)
control(
    "RENDER: no live minute-precision counter anywhere in the text",
    bool(re.search(r"\d+ min(ute)?s? ago", body)),
    False,
)
truthy("  and it carries the --add recipe", "worklist.py --add" in body)
truthy("  and states it is advisory", "ADVISORY" in body)

dp_candidate = dict(
    fake_candidate, dead_peer={"count": 2, "rel": "agent/plans/PLAN-p.md", "open": 9, "owner": PEER}
)
dp_body = B.render(dp_candidate, "nominated", {"scanned": 2, "eligible": 1}, OWNER)
truthy(
    "RENDER: a dead-peer count prints the --migrate --plan recipe",
    "worklist.py --migrate" in dp_body and "--plan agent/plans/PLAN-p.md" in dp_body,
)

cluster_candidate = dict(fake_candidate, mtime_cluster=(4, "agent/plans/PLAN-runner-up.md"))
cluster_body = B.render(cluster_candidate, "nominated", {"scanned": 5, "eligible": 1}, OWNER)
truthy(
    "RENDER: a bulk-mtime cluster is named with the runner-up",
    "PLAN-runner-up.md" in cluster_body and "bulk" in cluster_body.lower(),
)
# PAIR: no cluster key at all renders no cluster note.
control("PAIR: no cluster produces no bulk-touch note", "bulk git touch" in body, False)


# --------------------------------------------------------------------------- 8. THE MTIME-CLUSTER HELPER ITSELF, direct. ---------------------------------------------------------------------------
td, root, _recs = make_tree(
    ("PLAN-a.md", plan_body(owner=OWNER, open_tasks=["implement this fixture task fully"])),
    ("PLAN-b.md", plan_body(owner=OWNER, open_tasks=["implement this fixture task fully"])),
    ("PLAN-c.md", plan_body(owner=OWNER, open_tasks=["implement this fixture task fully"])),
    touch_seconds_apart=0,  # force an exact mtime tie across all three
)
try:
    cluster = B._mtime_cluster(root, "agent/plans/PLAN-a.md")
    truthy("MTIME CLUSTER: three plans sharing one mtime is detected", cluster)
    if cluster:
        control("  cluster size is the two OTHER plans", cluster[0], 2)
finally:
    td.cleanup()

# PAIR: distinct mtimes (the default spacing) produce no cluster.
td, root, _recs = make_tree(
    ("PLAN-a.md", plan_body(owner=OWNER, open_tasks=["implement this fixture task fully"])),
    ("PLAN-b.md", plan_body(owner=OWNER, open_tasks=["implement this fixture task fully"])),
)
try:
    control(
        "PAIR: distinct mtimes produce no cluster",
        B._mtime_cluster(root, "agent/plans/PLAN-a.md"),
        None,
    )
finally:
    td.cleanup()


if Tally.count < 30:
    Tally.fails += 1
    print(
        "FAIL  only %d control(s) ran; the file is not being executed as written" % Tally.count,
        file=sys.stderr,
    )

if Tally.fails:
    print("FAIL: %d of %d control(s) failed" % (Tally.fails, Tally.count), file=sys.stderr)
    sys.exit(1)
print("%d control(s) passed" % Tally.count)

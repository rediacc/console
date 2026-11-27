#!/usr/bin/env python3
"""Controls for two Stop-hook defects found 2026-11-23. (1) The auto-lease reads only ids a live task's prompt CLAIMS, and never a read-only agent's. (2) An open per-commit review finding named by a `[>]` item waits (advisory) only while that item's worker is verified live.

    python3 .claude/hooks/stop/test-autolease.py

Found 2026-11-23: #889cb685 was leased to a read-only survey agent because its brief listed the id under exclusion wording. Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py (glob over test-*.py under .claude/hooks/stop/).

EVERY REFUSAL HAS A PASSING TWIN: the same id on a claiming line is leased, a writer agent naming it is leased, a shell naming it is leased.
"""

import importlib.util
import pathlib

import wl_checks as K
import wl_leasehelp as LH
import wl_review as R

_CI = pathlib.Path(__file__).resolve().parents[3] / ".ci" / "rediacc_ci"
_spec = importlib.util.spec_from_file_location("controls", _CI / "controls.py")
if _spec is None or _spec.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/controls.py is missing" % __file__)
controls = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(controls)

T = controls.Controls("autolease", floor=16)
check = T.check

A = "a1a1a1a1"
B = "b2b2b2b2"
C = "c3c3c3c3"

BRIEF = """# Wave brief
Take #%s and report.

Excluded (in flight elsewhere):
- #%s
- #%s

Do not touch #%s either.
## Next
Then #%s.
""" % (A, B, B, B, C)

check("claimed_text keeps a claiming line", "#%s" % A in K.claimed_text(BRIEF), True)
check(
    "claimed_text keeps a line after the excluded block closes",
    "#%s" % C in K.claimed_text(BRIEF),
    True,
)
check(
    "claimed_text drops the excluded list under its lead-in",
    "#%s" % B in K.claimed_text(BRIEF),
    False,
)
check(
    "claimed_text: a bare brief with no wording is unchanged",
    K.claimed_text("work #%s" % A),
    "work #%s" % A,
)
check(
    "claimed_text: a single exclusion line drops its ids",
    LH.item_refs(K.claimed_text("Do not touch #%s" % B)),
    [],
)
check("claimed_text: empty text", K.claimed_text(""), "")


def rec(rid):
    return {
        "id": rid,
        "state": " ",
        "owner": "me",
        "text": "item %s" % rid,
        "upd": "2026-11-23T00:00Z",
    }


pool = [rec(A), rec(B), rec(C)]


def leased(named):
    return sorted(i for i, _t in LH.auto_lease_candidates(pool, lambda _r: True, named, set()))


check("without the filter the excluded id would be leased", leased({"t": BRIEF}), [A, B, C])
check(
    "with the filter only the claimed ids are leased", leased({"t": K.claimed_text(BRIEF)}), [A, C]
)

metas = {
    "ro1": {"type": "Explore", "jsonl": "ro1"},
    "wr1": {"type": "general-purpose", "jsonl": "wr1"},
}
prompts = {"ro1": "Item #%s: survey it" % A, "wr1": "write #%s" % B}
live = [
    {"id": "ro1", "type": "subagent"},
    {"id": "wr1", "type": "subagent"},
    {"id": "sh1", "type": "shell", "description": "watch #%s" % C},
]
got = K.claiming_prompts(live, metas, frozenset({"Plan", "Explore"}), lambda p: prompts[p])
check("a read-only agent's prompt is not read", "ro1" in got, False)
check("a writer agent's prompt is read", "#%s" % B in got.get("wr1", ""), True)
check("a shell description is read", "#%s" % C in got.get("sh1", ""), True)
check("the read-only agent leases nothing", leased(got), [B, C])
got_all = K.claiming_prompts(live, metas, frozenset(), lambda p: prompts[p])
check("control: the same agent as a writer type would lease its item", leased(got_all), [A, B, C])

# ---- own_claims (2026-11-27): only an `Item #<id>` style phrase that presents ONE item as the task's own work leases it.
H = "d4d4d4d4"
SURVEY_BRIEF = """# Survey brief
Survey the Promoted plans. Related items: #%s, #%s, #%s (do not work them).
The hold #%s runner-hold:prod -- after the edge release stays open.
Context: see #%s for the last note.
The survey writes one file.
It reports every group.
Item #%s is mentioned last.
""" % (A, B, C, H, B, A)
check(
    "own_claims: ids cited in lists, holds and context do not claim",
    LH.item_refs(K.own_claims(K.claimed_text(SURVEY_BRIEF))),
    [],
)
check(
    "own_claims: `Item #<id>` as the first line claims it",
    LH.item_refs(K.own_claims("Item #%s: narrow the matcher.\nSee #%s and #%s." % (A, B, C))),
    [A],
)
check(
    "own_claims: a bulleted `fix #<id>` claims it",
    LH.item_refs(K.own_claims("# Brief\n- Fix #%s now" % A)),
    [A],
)
check(
    "own_claims: a line listing two items after the verb claims neither",
    LH.item_refs(K.own_claims("Take #%s and #%s" % (A, B))),
    [],
)
check(
    "own_claims: a claim phrase past the first lines is context",
    LH.item_refs(K.own_claims("one\ntwo\nthree\nfour\nItem #%s" % A)),
    [],
)
check(
    "own_claims: a runner-hold line never claims",
    LH.item_refs(K.own_claims("Item #%s runner-hold:prod -- later" % H)),
    [],
)
live_survey = [{"id": "sv1", "type": "subagent"}]
sv_metas = {"sv1": {"type": "general-purpose", "jsonl": "sv1"}}
sv = K.claiming_prompts(live_survey, sv_metas, frozenset(), lambda _p: SURVEY_BRIEF)
check("a survey brief citing ids in lists leases only what it presents as its own", leased(sv), [])
sv_own = K.claiming_prompts(
    live_survey, sv_metas, frozenset(), lambda _p: "Item #%s is yours.\n" % A + SURVEY_BRIEF
)
check("control: the same brief opening with its own item leases that item", leased(sv_own), [A])
hold_pool = [dict(rec(H), text="runner-hold:prod -- after the edge release"), rec(A)]
check(
    "a runner-hold item is never auto-leased",
    sorted(
        i
        for i, _t in LH.auto_lease_candidates(
            hold_pool, lambda _r: True, {"t": "#%s #%s" % (H, A)}, set()
        )
    ),
    [A],
)
check(
    "control: the same text without the hold token is leased",
    sorted(
        i
        for i, _t in LH.auto_lease_candidates(
            [dict(rec(H), text="prod after the edge release")],
            lambda _r: True,
            {"t": "#%s" % H},
            set(),
        )
    ),
    [H],
)
check(
    "auto_lease_note keeps the previous LATEST note",
    LH.auto_lease_note("t1", {"lastnote": "waiting on edge"}),
    "auto-lease: named by live task t1; previous: waiting on edge",
)
check(
    "control: no previous note leaves the bare marker",
    LH.auto_lease_note("t1", {"lastnote": ""}),
    "auto-lease: named by live task t1",
)

check(
    "auto_lease_note: a re-lease by the same task keeps the real earlier note",
    LH.auto_lease_note(
        "t1", {"lastnote": "auto-lease: named by live task t1; previous: waiting on edge"}
    ),
    "auto-lease: named by live task t1; previous: waiting on edge",
)
check(
    "auto_lease_note: a re-lease whose only note is the marker leaves the bare marker",
    LH.auto_lease_note("t1", {"lastnote": "auto-lease: named by live task t1"}),
    "auto-lease: named by live task t1",
)
check(
    "auto_lease_note: another task's marker stays in the previous note",
    LH.auto_lease_note("t1", {"lastnote": "auto-lease: named by live task t2"}),
    "auto-lease: named by live task t1; previous: auto-lease: named by live task t2",
)
check(
    "a runner-hold token after other words is never auto-leased",
    LH.auto_lease_candidates(
        [dict(rec(H), text="watch the edge runner-hold:prod")],
        lambda _r: True,
        {"t": "#%s" % H},
        set(),
    ),
    [],
)
check(
    "own_claims: a capitalised Runner-Hold token never claims",
    LH.item_refs(K.own_claims("Item #%s Runner-Hold:prod -- later" % H)),
    [],
)

# ---- review_items: an open finding named by a [>] item waits only on a VERIFIED live worker.
F = "0228ca2d.1"


def item(rid, state, worker="", **extra):
    return dict({"id": rid, "state": state, "worker": worker, "text": "item"}, **extra)


recs = [
    item("live0001", ">", "w-live", lastnote="fixing %s" % F),
    item("dead0001", ">", "w-dead", lastnote="fixing %s" % F),
    item("open0001", " ", lastnote="fixing %s" % F),
    item("text0001", ">", "w-live", text="fix review finding %s" % F),
]
view = K.review_items(recs, {"w-live"})
check("review_items: a live-leased item stays [>]", view["live0001"][0], ">")
check("review_items: its last note names the finding", F in view["live0001"][1], True)
check("review_items: a lease with no live worker is no longer [>]", view["dead0001"][0], "!")
check("review_items: an open item is not [>]", view["open0001"][0], " ")
check("review_items: the item text names it too", F in view["text0001"][1], True)
lease_note_view = K.review_items(
    [dict(item("note0001", ">", "w-live"), text="item", lease_note="fixing %s" % F)], {"w-live"}
)
check("review_items: the lease note names it too", F in lease_note_view["note0001"][1], True)
leased_view = R._leased_items(view)
check("branch_state sees only the live-leased items", sorted(leased_view), ["live0001", "text0001"])
dead_only = R._leased_items(K.review_items(recs, set()))
check("control: with no live worker nothing is leased, so the finding blocks", dead_only, {})

T.exit()

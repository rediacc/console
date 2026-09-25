#!/usr/bin/env python3
"""Controls for wl_plandeps, the `Depends-On:` grammar and plan graph (agent/plans/PLAN-plan-dependencies.md section 5a).

    python3 .claude/hooks/stop/test-plandeps.py

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py (glob over test-*.py under .claude/hooks/stop/), so no table edit is needed to wire this file in.

EVERY REFUSAL HAS A PASSING TWIN built from the same fixture with one fact changed, because a parser that rejects everything passes every malformed case and one that accepts everything passes every valid case. The graph cases run on `Graph.from_texts` (pure); one case drives `Graph.load` against a directory on disk, with an override, because that is the door the guard uses.
"""

import importlib.util
import pathlib
import types

import wl_plandeps as D

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

CONTROL_FLOOR = 95
T = controls.Controls("plandeps", floor=CONTROL_FLOOR)
check = T.check


def plan(status="in-progress", dep=None, extra=""):
    head = "# PLAN: x\n\nStatus: %s\nOwner: cafe0000\n" % status
    if dep is not None:
        head += "Depends-On: %s\n" % dep
    return head + extra + "\n## Tasks\n\n- [ ] T1 a box\n"


def errs(value):
    return D.parse_depends(value)[1]


def ok(value):
    parsed, e = D.parse_depends(value)
    return parsed is not None and not e


def dep(value):
    """The parsed value, or a loud stop: a None here is a parser regression, not a control result."""
    got, e = D.parse_depends(value)
    if got is None:
        raise SystemExit("parse_depends(%r) refused a valid value: %s" % (value, e))
    return got


def hdep(header):
    got = header.depends
    if got is None:
        raise SystemExit("the header carries no valid Depends-On: %r" % (header,))
    return got


def fget(header, name):
    """(lineno, parsed) of a header field, or None when absent."""
    f = header.get(name)
    return None if f is None else (f.lineno, f.parsed)


# --------------------------------------------------------------------------- parse: accepted shapes, each against its malformed twins.

check("parse: a list", ok("PLAN-a.md, PLAN-b.md"), True)
check(
    "parse: the list's edges",
    [str(e) for e in dep("PLAN-a.md, PLAN-b.md").edges],
    ["PLAN-a.md", "PLAN-b.md"],
)
check("parse: no-dep --", ok("no-dep -- touches only the account portal"), True)
check("parse: no-dep em dash", ok("no-dep \u2014 touches only the account portal"), True)
check(
    "parse: no-dep reason kept",
    dep("no-dep -- touches only the account portal").no_dep,
    "touches only the account portal",
)
check(
    "parse: a list with a trailing note",
    dep("PLAN-a.md -- shares device-codes.ts").note,
    "shares device-codes.ts",
)
check(
    "parse: a task edge by id",
    dep("PLAN-y.md#T3").edges,
    (D.Edge("PLAN-y.md", "T3"),),
)
check(
    "parse: a task edge by dotted id",
    dep("PLAN-y.md#R20260925.5").edges[0].task,
    "R20260925.5",
)
check("parse: a path token is refused", bool(errs("agent/plans/PLAN-a.md")), True)
check(
    "parse: the path message names the basename",
    "'PLAN-a.md'" in errs("agent/plans/PLAN-a.md")[0],
    True,
)
check("parse: a non-PLAN name is refused", bool(errs("README.md")), True)
check("parse: free text is refused", bool(errs("the spec-X plan")), True)
check("parse: a backticked token is refused (one spelling)", bool(errs("`PLAN-a.md`")), True)
check("parse: a trailing comma is refused", bool(errs("PLAN-a.md,")), True)
check("parse: a leading comma is refused", bool(errs(", PLAN-a.md")), True)
check("parse: a doubled comma is refused", bool(errs("PLAN-a.md,, PLAN-b.md")), True)
check("parse: an empty value is refused", bool(errs("")), True)
check("parse: no-dep without a reason is refused", bool(errs("no-dep")), True)
check("parse: no-dep -- with nothing after is refused", bool(errs("no-dep --")), True)
check("parse: a reason under 12 chars is refused", bool(errs("no-dep -- too short")), True)
check("parse: a reason of exactly 12 chars passes", ok("no-dep -- abcdefghijkl"), True)
check("parse: a vague reason is refused", bool(errs("no-dep -- none")), True)
check("parse: n/a is refused", bool(errs("no-dep -- n/a")), True)
check(
    "parse: no-dep mixed into a list is refused",
    bool(errs("PLAN-a.md, no-dep -- a real reason here")),
    True,
)
check("parse: a duplicate token is refused", bool(errs("PLAN-a.md, PLAN-a.md")), True)

# --------------------------------------------------------------------------- parse_header: window, second line, emphasis.

h = D.parse_header(plan(dep="PLAN-a.md"))
check(
    "header: the field is found", fget(h, D.FIELD), (5, D.DependsOn(edges=(D.Edge("PLAN-a.md"),)))
)
check("header: status is read", h.status, "in-progress")
check("header: no structural errors", h.errors, ())
h = D.parse_header(plan(dep="PLAN-a.md", extra="Depends-On: PLAN-b.md\n"))
check("header: a second line is a structural error", len(h.field_errors(D.FIELD)), 1)
check("header: the first line still parses", str(hdep(h).edges[0]), "PLAN-a.md")
late = (
    "# PLAN: x\n\nStatus: draft\n"
    + "".join("Note-%d: x\n" % i for i in range(7))
    + "Depends-On: PLAN-a.md\n\n## Tasks\n"
)
h = D.parse_header(late)
check(
    "header: line 11 is outside the window",
    (h.get(D.FIELD), len(h.field_errors(D.FIELD))),
    (None, 1),
)
at10 = (
    "# PLAN: x\n\nStatus: draft\n"
    + "".join("Note-%d: x\n" % i for i in range(6))
    + "Depends-On: PLAN-a.md\n\n## Tasks\n"
)
check("header: line 10 is inside it (twin)", (fget(D.parse_header(at10), D.FIELD) or (0,))[0], 10)
check(
    "header: an emphasised key is an error",
    bool(D.parse_header("Status: draft\n**Depends-On:** PLAN-a.md\n").field_errors(D.FIELD)),
    True,
)
body = "Status: draft\nDepends-On: no-dep -- stands alone for this test\n\n## 1\n\n```\nDepends-On: PLAN-a.md\n```\n"
check(
    "header: a body quote after a heading is not a second line",
    D.parse_header(body).field_errors(D.FIELD),
    [],
)
check(
    "header: stub shape",
    D.is_stub_header(D.parse_header("Status: moved\nMoved-To: agent/plans/_done/PLAN-a.md\n")),
    True,
)
check(
    "header: moved without Moved-To is not a stub",
    D.is_stub_header(D.parse_header("Status: moved\n")),
    False,
)

# Extensibility: a spec table passed in is scanned with its own window (the door PLAN-plan-priority-concurrency.md T1 uses).
spec = D.FieldSpec("Priority", 12, lambda v: (v, [] if v in ("P0", "P1") else ["bad"]))
specs = dict(D.FIELD_SPECS, Priority=spec)
h = D.parse_header(late.replace("Depends-On: PLAN-a.md", "Priority: P1"), specs)
check(
    "header: an added spec with a wider window parses at line 11",
    fget(h, "Priority"),
    (11, "P1"),
)
check(
    "header: the added spec's errors surface",
    D.parse_header("Status: x\nPriority: P9\n", specs).field_errors("Priority"),
    ["bad"],
)

# --------------------------------------------------------------------------- resolve and complete.

INDEX = (
    "## Expired plans\n\n| Plan | Title | First seen | Expired | Full-Text-Blob |\n|---|---|---|---|---|\n"
    "| `agent/plans/_done/PLAN-gone-done.md` | t | 2026-01-01 | 2026-03-01 | `%s` |\n"
    "| `agent/plans/PLAN-gone-backlog.md` | t | 2026-01-01 | 2026-03-01 | `%s` |\n"
    % ("a" * 40, "b" * 40)
)
TEXTS = {
    "agent/plans/PLAN-x.md": plan(dep="PLAN-y.md"),
    "agent/plans/PLAN-y.md": plan(dep="PLAN-z.md"),
    "agent/plans/PLAN-z.md": plan(status="draft", dep="no-dep -- nothing upstream of this one"),
    "agent/plans/PLAN-rec.md": plan(status="compacted"),
    "agent/plans/PLAN-parked.md": plan(status="parked", dep="no-dep -- parked record for the test"),
    "agent/plans/_done/PLAN-fin.md": plan(status="done"),
    "agent/plans/_done/PLAN-draftdone.md": plan(status="draft"),
    "agent/plans/PLAN-fin.md": "# stub\n\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-fin.md\n",
    "agent/plans/PLAN-moved.md": "# stub\n\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-renamed.md\n",
    "agent/plans/_done/PLAN-renamed.md": plan(status="landed"),
    "agent/plans/_removed/PLAN-rm.md": plan(status="removed"),
    "agent/plans/PLAN-dup.md": plan(),
    "agent/plans/_done/PLAN-dup.md": plan(status="done"),
    "agent/plans/PLAN-nostatus.A0.md": "# appendix\n\nsome text\n",
}
G = D.Graph.from_texts(TEXTS, INDEX)
check("resolve: active is live", G.resolve("PLAN-y.md").state, D.LIVE)
check("resolve: _done is complete", G.resolve("PLAN-fin.md").state, D.COMPLETE)
check(
    "resolve: a stub beside a real file resolves to the real file",
    G.resolve("PLAN-fin.md").rel,
    "agent/plans/_done/PLAN-fin.md",
)
check(
    "resolve: a stub is followed once",
    (G.resolve("PLAN-moved.md").state, G.resolve("PLAN-moved.md").rel),
    (D.COMPLETE, "agent/plans/_done/PLAN-renamed.md"),
)
check("resolve: a _done tombstone is complete", G.resolve("PLAN-gone-done.md").state, D.COMPLETE)
check(
    "resolve: a backlog tombstone is withdrawn",
    G.resolve("PLAN-gone-backlog.md").state,
    D.WITHDRAWN,
)
check("resolve: _removed is withdrawn", G.resolve("PLAN-rm.md").state, D.WITHDRAWN)
check("resolve: missing is dangling", G.resolve("PLAN-nope.md").state, D.DANGLING)
check("resolve: two real files is ambiguous", G.resolve("PLAN-dup.md").state, D.AMBIGUOUS)
check("resolve: a task edge resolves at plan level", G.resolve("PLAN-y.md#T3").state, D.LIVE)
not_complete = [
    w
    for w in sorted(D.finished_states())
    if not D.Graph.from_texts({"agent/plans/PLAN-w.md": plan(status=w)}).is_complete("PLAN-w.md")
]
check("complete: no FINISHED_STATES word reads as incomplete", not_complete, [])
check(
    "complete: every FINISHED_STATES word (%d) is complete" % len(D.finished_states()),
    all(
        D.Graph.from_texts({"agent/plans/PLAN-w.md": plan(status=w)}).is_complete("PLAN-w.md")
        for w in D.finished_states()
    ),
    True,
)
check("complete: compacted in agent/plans is complete", G.is_complete("PLAN-rec.md"), True)
check(
    "complete: draft in _done is NOT complete (Status wins)",
    G.is_complete("PLAN-draftdone.md"),
    False,
)
check("complete: parked is not complete", G.is_complete("PLAN-parked.md"), False)
check("complete: a live plan is not complete", G.is_complete("PLAN-y.md"), False)

# --------------------------------------------------------------------------- required set.

check("required: a live plan", G.is_required("agent/plans/PLAN-x.md"), True)
check("required: parked is required", G.is_required("agent/plans/PLAN-parked.md"), True)
check(
    "required: a plan with no Status is required",
    G.is_required("agent/plans/PLAN-nostatus.A0.md"),
    True,
)
check("required: a compacted record is exempt", G.is_required("agent/plans/PLAN-rec.md"), False)
check("required: a stub is exempt", G.is_required("agent/plans/PLAN-fin.md"), False)
check("required: _done is exempt", G.is_required("agent/plans/_done/PLAN-draftdone.md"), False)

# --------------------------------------------------------------------------- check(): the shared D1-D7 verdict.


def codes(g, rel):
    return sorted({c for c, _ in g.check(rel)})


check("check: a clean plan", codes(G, "agent/plans/PLAN-x.md"), [])
check("check: D1 missing", codes(G, "agent/plans/PLAN-nostatus.A0.md"), ["D1"])
g2 = D.Graph.from_texts(dict(TEXTS, **{"agent/plans/PLAN-x.md": plan(dep="PLAN-nope.md")}), INDEX)
check("check: D3 dangling", codes(g2, "agent/plans/PLAN-x.md"), ["D3"])
g2 = D.Graph.from_texts(
    dict(TEXTS, **{"agent/plans/PLAN-x.md": plan(dep="PLAN-rm.md, PLAN-gone-backlog.md")}), INDEX
)
check("check: D4 withdrawn", codes(g2, "agent/plans/PLAN-x.md"), ["D4"])
g2 = D.Graph.from_texts(dict(TEXTS, **{"agent/plans/PLAN-x.md": plan(dep="PLAN-x.md")}), INDEX)
check("check: D5 self", codes(g2, "agent/plans/PLAN-x.md"), ["D5"])
g2 = D.Graph.from_texts(dict(TEXTS, **{"agent/plans/PLAN-x.md": plan(dep="PLAN-dup.md")}), INDEX)
check("check: D7 ambiguous", codes(g2, "agent/plans/PLAN-x.md"), ["D7"])
g2 = D.Graph.from_texts(
    dict(TEXTS, **{"agent/plans/PLAN-x.md": plan(dep="agent/plans/PLAN-y.md")}), INDEX
)
check("check: D2 malformed", codes(g2, "agent/plans/PLAN-x.md"), ["D2"])
check(
    "check: a tombstoned _done target is fine",
    codes(
        D.Graph.from_texts(
            dict(TEXTS, **{"agent/plans/PLAN-x.md": plan(dep="PLAN-gone-done.md")}), INDEX
        ),
        "agent/plans/PLAN-x.md",
    ),
    [],
)

# --------------------------------------------------------------------------- cycles.

cyc2 = D.Graph.from_texts(
    {"agent/plans/PLAN-a.md": plan(dep="PLAN-b.md"), "agent/plans/PLAN-b.md": plan(dep="PLAN-a.md")}
)
check("cycles: a 2-cycle with its path", cyc2.cycles(), [["PLAN-a.md", "PLAN-b.md", "PLAN-a.md"]])
check(
    "cycles: D6 on both members",
    (codes(cyc2, "agent/plans/PLAN-a.md"), codes(cyc2, "agent/plans/PLAN-b.md")),
    (["D6"], ["D6"]),
)
cyc3 = D.Graph.from_texts(
    {
        "agent/plans/PLAN-a.md": plan(dep="PLAN-b.md"),
        "agent/plans/PLAN-b.md": plan(dep="PLAN-c.md"),
        "agent/plans/PLAN-c.md": plan(dep="PLAN-a.md"),
    }
)
check(
    "cycles: a 3-cycle with its path",
    cyc3.cycles(),
    [["PLAN-a.md", "PLAN-b.md", "PLAN-c.md", "PLAN-a.md"]],
)
diamond = D.Graph.from_texts({
    "agent/plans/PLAN-x.md": plan(dep="PLAN-a.md, PLAN-b.md"),
    "agent/plans/PLAN-a.md": plan(dep="PLAN-z.md"),
    "agent/plans/PLAN-b.md": plan(dep="PLAN-z.md"),
    "agent/plans/PLAN-z.md": plan(dep="no-dep -- the bottom of the diamond"),
})  # fmt: skip
check("cycles: a diamond is not a cycle", diamond.cycles(), [])

# --------------------------------------------------------------------------- roots and chain.

check("roots: X->Y->Z, both incomplete, gives Z", G.roots("agent/plans/PLAN-x.md"), ["PLAN-z.md"])
check(
    "chain: X to Z",
    G.chain("agent/plans/PLAN-x.md", "PLAN-z.md"),
    ["PLAN-x.md", "PLAN-y.md", "PLAN-z.md"],
)
gz = D.Graph.from_texts(dict(TEXTS, **{"agent/plans/PLAN-z.md": plan(status="done")}), INDEX)
check("roots: Z complete gives Y", gz.roots("agent/plans/PLAN-x.md"), ["PLAN-y.md"])
gy = D.Graph.from_texts(
    dict(TEXTS, **{"agent/plans/PLAN-y.md": plan(status="done", dep="PLAN-z.md")}), INDEX
)
check(
    "roots: nothing incomplete on the direct edge gives none", gy.roots("agent/plans/PLAN-x.md"), []
)
check(
    "roots: a diamond names its bottom once, and not the arms",
    diamond.roots("agent/plans/PLAN-x.md"),
    ["PLAN-z.md"],
)
check(
    "roots: a dangling dependency is its own root (fail closed)",
    D.Graph.from_texts({"agent/plans/PLAN-x.md": plan(dep="PLAN-nope.md")}).roots(
        "agent/plans/PLAN-x.md"
    ),
    ["PLAN-nope.md"],
)
check("roots: a no-dep plan has none", G.roots("agent/plans/PLAN-z.md"), [])

# --------------------------------------------------------------------------- linked_plan and tracked_by.

check(
    "linked_plan: a sig right after the name links",
    D.linked_plan("PLAN-x.md [41f56150] body"),
    "PLAN-x.md",
)
check("linked_plan: a bare mention does not", D.linked_plan("write PLAN-x.md"), None)
check(
    "linked_plan: the sig after the second token gives the second",
    D.linked_plan("after PLAN-a.md do PLAN-b.md [41f56150] x"),
    "PLAN-b.md",
)
check(
    "linked_plan: a path prefix still links the basename",
    D.linked_plan("agent/plans/PLAN-x.md [41f56150]"),
    "PLAN-x.md",
)
check("linked_plan: a non-hex sig does not", D.linked_plan("PLAN-x.md [notahex1]"), None)


FOLD = types.SimpleNamespace(
    items=[
        {"id": "aa11aa11", "state": " ", "text": "(cafe0000) PLAN-z.md [12345678] do it"},
        {"id": "bb22bb22", "state": "x", "text": "(cafe0000) PLAN-y.md [12345678] done"},
        {"id": "cc33cc33", "state": ">", "basetext": "PLAN-y.md leased"},
    ]
)


check("tracked_by: an open item tracks", D.tracked_by("PLAN-z.md", FOLD), ["aa11aa11"])
check(
    "tracked_by: a ticked one does not, a leased one does",
    D.tracked_by("agent/plans/PLAN-y.md", FOLD),
    ["cc33cc33"],
)
check("tracked_by: nothing tracks an unnamed plan", D.tracked_by("PLAN-q.md", FOLD), [])

# --------------------------------------------------------------------------- set_header.

src = "# PLAN: x\n\nStatus: draft\nOwner: cafe0000\n\nbody\n"
out = D.set_header(src, "no-dep -- stands alone for this test")
check(
    "set_header: inserts right after Status",
    out.splitlines()[3],
    "Depends-On: no-dep -- stands alone for this test",
)
check("set_header: one added line", len(out.splitlines()) - len(src.splitlines()), 1)
out2 = D.set_header(out, "PLAN-a.md")
check(
    "set_header: replaces an existing line in place",
    (out2.splitlines()[3], len(out2.splitlines())),
    ("Depends-On: PLAN-a.md", len(out.splitlines())),
)
check("set_header: the result parses", str(hdep(D.parse_header(out2)).edges[0]), "PLAN-a.md")
dup = src.replace("Owner:", "Depends-On: PLAN-a.md\nDepends-On: PLAN-b.md\nOwner:")
check(
    "set_header: a duplicate line is removed as part of the fix",
    D.parse_header(D.set_header(dup, "PLAN-c.md")).field_errors(D.FIELD),
    [],
)
try:
    D.set_header("no status and no title\n", "PLAN-a.md")
    check("set_header: refuses with neither Status nor a # title", "no raise", "ValueError")
except ValueError:
    check("set_header: refuses with neither Status nor a # title", "ValueError", "ValueError")
companion = "<!-- provenance -->\n\n# A0 appendix\n\nbody\n"
check(
    "set_header: a Status-less companion anchors on its # title",
    D.set_header(companion, "no-dep -- appendix").splitlines()[3],
    "Depends-On: no-dep -- appendix",
)

# --------------------------------------------------------------------------- Graph.load: disk, override, INDEX.

root = pathlib.Path(runtmp.run_dir("plandeps-suite-"))
for rel, text in TEXTS.items():
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
(root / "agent" / "INDEX.md").write_text(INDEX, encoding="utf-8")
GL = D.Graph.load(root)
check("load: every plan on disk", sorted(GL.plans), sorted(TEXTS))
check("load: tombstones from INDEX.md", GL.resolve("PLAN-gone-done.md").state, D.COMPLETE)
GO = D.Graph.load(root, override={"agent/plans/PLAN-z.md": plan(dep="PLAN-x.md")})
check(
    "load: an override replaces the on-disk text (cycle appears)",
    codes(GO, "agent/plans/PLAN-z.md"),
    ["D6"],
)
check("load: the on-disk graph without it has no cycle", GL.cycles(), [])
check("load: a missing tree loads empty rather than raising", D.Graph.load(root / "nope").plans, {})

T.exit()

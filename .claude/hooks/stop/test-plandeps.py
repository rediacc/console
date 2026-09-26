#!/usr/bin/env python3
"""Controls for wl_plandeps, the `Depends-On:` grammar and plan graph (agent/plans/PLAN-plan-dependencies.md section 5a).

    python3 .claude/hooks/stop/test-plandeps.py

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py (glob over test-*.py under .claude/hooks/stop/), so no table edit is needed to wire this file in.

EVERY REFUSAL HAS A PASSING TWIN built from the same fixture with one fact changed, because a parser that rejects everything passes every malformed case and one that accepts everything passes every valid case. The graph cases run on `Graph.from_texts` (pure); one case drives `Graph.load` against a directory on disk, with an override, because that is the door the guard uses.
"""

import importlib.util
import pathlib

import wl_planconc as X
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

CONTROL_FLOOR = 216  # 90 before PLAN-plan-priority-concurrency T1/T2 added the X grammar, set_x, linked_plan (now read by wl_planconc.item_plan), the overlap table, spawn_verdict and order_key controls
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


def some[V](value: V | None) -> V:
    """The parsed value, or a loud stop: a None here is a parser regression, not a control result (the shape of `dep` above, typed so the checker sees the narrowing)."""
    if value is None:
        raise SystemExit("expected a parsed value, got None")
    return value


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

# --------------------------------------------------------------------------- X grammar (PLAN-plan-priority-concurrency.md section 1).


def px(value):
    return D.parse_priority(value)


check("x: P0-P3 parse", [some(px("P%d" % n)[0]).level for n in range(4)], [0, 1, 2, 3])
check("x: the operator marker", px("P1 (operator)")[0], D.Priority(1, True, ""))
check(
    "x: marker and reason",
    px("P1 (operator) -- ruled 2026-09-25")[0],
    D.Priority(1, True, "ruled 2026-09-25"),
)
check("x: an AI reason", px("P2 -- proposed by AI")[0], D.Priority(2, False, "proposed by AI"))
check("x: an em-dash reason", some(px("P2 \u2014 proposed by AI")[0]).reason, "proposed by AI")
check("x: P4 is refused", bool(px("P4")[1]), True)
check("x: a period separator is refused", bool(px("P0. an operator ruling")[1]), True)
check("x: another marker is refused", bool(px("P1 (lead)")[1]), True)
check("x: a lowercase level is refused", bool(px("p1")[1]), True)
check("x: str round-trips", str(px("P1 (operator) -- why")[0]), "P1 (operator) -- why")
check("x: parallel", D.parse_concurrency("parallel")[0], D.Concurrency("parallel", ""))
check(
    "x: parallel with a reason",
    some(D.parse_concurrency("parallel -- four writers")[0]).reason,
    "four writers",
)
check("x: exclusive needs a reason", bool(D.parse_concurrency("exclusive")[1]), True)
check(
    "x: exclusive with a short reason is refused",
    bool(D.parse_concurrency("exclusive -- too short")[1]),
    True,
)
check(
    "x: exclusive with a placeholder is refused",
    bool(D.parse_concurrency("exclusive -- none")[1]),
    True,
)
check(
    "x: exclusive with a reason",
    some(D.parse_concurrency("exclusive -- regenerates every golden")[0]).exclusive,
    True,
)
check("x: an unknown mode is refused", bool(D.parse_concurrency("serial")[1]), True)
check("x: owns list", some(D.parse_owns("a/**, b/*.py")[0]).globs, ("a/**", "b/*.py"))
check(
    "x: owns keeps braces whole", some(D.parse_owns("a/{b,c}.py, d")[0]).globs, ("a/{b,c}.py", "d")
)
check(
    "x: owns strips a note",
    (
        some(D.parse_owns("x.ts (one mount line, only), y")[0]).globs,
        some(D.parse_owns("x.ts (one mount line, only)")[0]).notes,
    ),
    (("x.ts", "y"), (("x.ts", "one mount line, only"),)),
)
check(
    "x: owns none with a reason",
    some(D.parse_owns("none -- an operator-action plan")[0]).none,
    "an operator-action plan",
)
check("x: owns none without a reason is refused", bool(D.parse_owns("none")[1]), True)
check("x: owns empty item is refused", bool(D.parse_owns("a,,b")[1]), True)
check("x: owns two globs without a comma is refused", bool(D.parse_owns("a/** b/**")[1]), True)
check("x: owns duplicate is refused", bool(D.parse_owns("a, a")[1]), True)
check(
    "x: owns none mixed into a list is refused",
    bool(D.parse_owns("a, none -- whatever it is")[1]),
    True,
)

xh = D.parse_header(
    "# P\n\nStatus: draft\nOwner: x\nDepends-On: no-dep -- the fixture stands alone\n"
    "Priority: P1 (operator)\nConcurrency: parallel\nOwns: a/**\n\n## Tasks\n"
)
check(
    "x: header carries the triple",
    (some(xh.priority).level, some(xh.concurrency).mode, some(xh.owns).globs),
    (1, "parallel", ("a/**",)),
)
check("x: the triple sits at 6-8", [some(xh.get(n)).lineno for n in D.X_FIELDS], [6, 7, 8])
at12 = "Status: draft\n" + "".join("N%d: x\n" % i for i in range(10)) + "Priority: P1\n"
check("x: line 12 is inside the X window", fget(D.parse_header(at12), D.PRIORITY)[0], 12)
at13 = "Status: draft\n" + "".join("N%d: x\n" % i for i in range(11)) + "Priority: P1\n"
check(
    "x: line 13 is outside it",
    (D.parse_header(at13).priority, len(D.parse_header(at13).field_errors(D.PRIORITY))),
    (None, 1),
)

# --------------------------------------------------------------------------- set_x: append after the header block, replace in place.

base = "# PLAN: x\nStatus: draft\nDepends-On: no-dep -- stands alone for this test\nOwner: cafe\nScope: wrapped\ncontinued here\n\n## Tasks\n"
out = D.set_x(base, {"Priority": "P2", "Concurrency": "parallel", "Owns": "a/**"})
check(
    "set_x: three lines after the block, continuation kept whole",
    out.splitlines()[5:9],
    ["continued here", "Priority: P2", "Concurrency: parallel", "Owns: a/**"],
)
check("set_x: every old line keeps its number", out.splitlines()[:6], base.splitlines()[:6])
check("set_x: exactly three added", len(out.splitlines()) - len(base.splitlines()), 3)
out2 = D.set_x(out, {"Priority": "P1 -- moved up"})
check(
    "set_x: replaces in place",
    (out2.splitlines()[6], len(out2.splitlines())),
    ("Priority: P1 -- moved up", len(out.splitlines())),
)
dupx = out.replace("Owns: a/**\n", "Owns: a/**\n**Priority:** P3\n")
check(
    "set_x: an emphasised duplicate is removed",
    D.parse_header(D.set_x(dupx, {"Priority": "P0"})).field_errors(D.PRIORITY),
    [],
)
record = (
    "# rec\nStatus: parked\nDepends-On: no-dep -- cites no other plan\nFirst-Seen: x\nOwner: y\nFull-Text: abc1234 p\nFull-Text-Blob: %s\nRecord-Sig: 823c73dd\n\n## Why\n"
    % ("0" * 40)
)
rout = D.set_x(
    record, {"Priority": "P3", "Concurrency": "parallel", "Owns": "none -- a parked record here"}
)
check("set_x: a record's spine stays at lines 1-8", rout.splitlines()[:8], record.splitlines()[:8])
check(
    "set_x: its fields land at 9-11",
    [some(D.parse_header(rout).get(n)).lineno for n in D.X_FIELDS],
    [9, 10, 11],
)
long_head = "Status: d\n" + "".join("N%d: x\n" % i for i in range(10)) + "\nbody\n"
try:
    D.set_x(long_head, {"Priority": "P1", "Concurrency": "parallel"})
    check("set_x: refuses to write past the window", "no raise", "ValueError")
except ValueError:
    check("set_x: refuses to write past the window", "ValueError", "ValueError")
try:
    D.set_x(base, {"Depends-On": "x"})
    check("set_x: refuses a non-X field", "no raise", "ValueError")
except ValueError:
    check("set_x: refuses a non-X field", "ValueError", "ValueError")
check("linked_plan: the item convention", D.linked_plan("do PLAN-a.md [41f56150] box"), "PLAN-a.md")
check("linked_plan: a bare mention links nothing", D.linked_plan("see PLAN-a.md for why"), None)

# --------------------------------------------------------------------------- owns_overlap: the unit table (section 8), a witness for every yes.

TABLE = [
    ("a/*.py", "a/b.py", True),
    ("a/**", "a/b/c.ts", True),
    ("a/*.py", "a/b/c.py", False),
    ("**/*.md", "docs/x.ts", False),
    ("{x,y}/z", "y/*", True),
    ("wl_[a-c]*.py", "wl_roster.py", False),
    ("wl_[p-s]*.py", "wl_roster.py", True),
    ("dir/", "dir/f", True),
    ("a/?.py", "a/bc.py", False),
    ("a/?.py", "a/[bc].py", True),
    ("a/[!b].py", "a/b.py", False),
    ("**", "anything/at/all", True),
    ("a/**/z.py", "a/b/c/z.py", True),
    ("a/**/z.py", "a/b/c/y.py", False),
    ("*.md", "x/y.md", False),
]
for ga, gb, want in TABLE:
    hits = X.owns_overlap([ga], [gb])
    check("overlap: %s vs %s" % (ga, gb), bool(hits), want)
    if hits:
        w = hits[0][2]
        check(
            "overlap: %s vs %s witness %r matches both" % (ga, gb, w),
            bool(X.glob_regex(hits[0][0]).match(w) and X.glob_regex(hits[0][1]).match(w)),
            True,
        )
check("overlap: symmetric", bool(X.owns_overlap(["a/b.py"], ["a/*.py"])), True)
check(
    "overlap: verb-written state is ignored",
    X.owns_overlap(["agent/worklist/**"], ["agent/**"]),
    [],
)
check(
    "overlap: a STATE.md cursor is ignored",
    X.owns_overlap(["agent/*/STATE.md"], ["agent/*/STATE.md"]),
    [],
)
check("normalize: a trailing slash", X.normalize_owns(["dir/"])[0], ["dir/**"])
check("normalize: ./ and // dropped", X.normalize_owns(["./a//b"])[0], ["a/b"])
for bad in ("/etc/x", "a/../b", "!a", "a\\b", "{a,b}/{c,d}/{e,f}/{g,h}/{i,j}/{k,l}", "a/{b"):
    check("normalize: refuses %r" % bad, bool(X.normalize_owns([bad])[1]), True)
check(
    "normalize: 32 expansions pass", len(X.normalize_owns(["{a,b}/{c,d}/{e,f}/{g,h}/{i,j}"])[0]), 32
)
check("universal: **", X.is_universal("**"), True)
check("universal: a/** is not", X.is_universal("a/**"), False)
check(
    "materialise",
    X.materialise(["a/**", "b/*.py"], ["a/x/y", "b/q.py", "b/c/q.py"]),
    ["a/x/y", "b/q.py"],
)

# --------------------------------------------------------------------------- item_plan / spawn_plans / declared_owns (section 3).

ITEM = {
    "id": "abcd1234",
    "text": "(cafe) do it PLAN-e.md [41f56150]",
    "basetext": "do it PLAN-e.md [41f56150]",
}
TRI = {
    "id": "beef5678",
    "text": "a finding",
    "triage": {"v": "plan-subagent", "plan": "agent/plans/PLAN-t.md"},
}
BY_ID: dict[str, dict] = {
    "abcd1234": ITEM,
    "beef5678": TRI,
    "00001111": {"id": "00001111", "text": "unlinked"},
}
check("item_plan: the link", X.item_plan(ITEM), "PLAN-e.md")
check("item_plan: the triage plan", X.item_plan(TRI), "PLAN-t.md")
check(
    "item_plan: a non-plan triage is none",
    X.item_plan({"text": "x", "triage": {"v": "inline", "plan": "agent/plans/PLAN-t.md"}}),
    None,
)
check("item_plan: unlinked", X.item_plan(BY_ID["00001111"]), None)
check(
    "spawn_plans: an explicit Plan: line wins",
    X.spawn_plans("Plan: PLAN-a.md, PLAN-b.md\n#abcd1234", BY_ID),
    {"PLAN-a.md", "PLAN-b.md"},
)
check(
    "spawn_plans: #refs resolve through items",
    X.spawn_plans("work #abcd1234 and #beef5678", BY_ID),
    {"PLAN-e.md", "PLAN-t.md"},
)
check("spawn_plans: an unlinked ref serves nothing", X.spawn_plans("work #00001111", BY_ID), set())
check("spawn_plans: a bare link token", X.spawn_plans("PLAN-z.md [0badcafe]"), {"PLAN-z.md"})
check("spawn_plans: a bare mention is nothing", X.spawn_plans("read PLAN-z.md first"), set())
check("declared_owns: a prompt line", X.declared_owns("do x\nOwns: a/**, b.py\n"), ("a/**", "b.py"))
check("declared_owns: none declared", X.declared_owns("do x"), None)

# --------------------------------------------------------------------------- spawn_verdict (section 5a), pure.


def px_(base, excl=False, owns=("src/%s/**",), none=False):
    return X.PlanX(
        base,
        exclusive=excl,
        reason="regenerates every golden" if excl else "",
        owns=None if owns is None else tuple(o % base[5:-3] if "%s" in o else o for o in owns),
        owns_none=none,
    )


XI = {
    "PLAN-e.md": px_("PLAN-e.md", excl=True),
    "PLAN-f.md": px_("PLAN-f.md"),
    "PLAN-g.md": px_("PLAN-g.md", owns=("src/f/b.py",)),
    "PLAN-h.md": px_("PLAN-h.md", owns=None),
    "PLAN-n.md": px_("PLAN-n.md", owns=(), none=True),
}
xi = XI.__getitem__


def sv(serving, live, declared=None, required=True):
    return X.spawn_verdict(serving, live, xi, declared, required)


LIVE_E = {"PLAN-e.md": ["writer a1b2c3d4 (general-purpose)"]}
LIVE_F = {"PLAN-f.md": ["lease #abcd1234 worker:w1"]}
check("verdict m1: a live exclusive refuses another plan", sv({"PLAN-f.md"}, LIVE_E).kind, "mutex")
check(
    "verdict m1: the refusal names the holder",
    "a1b2c3d4" in sv({"PLAN-f.md"}, LIVE_E).lines[0],
    True,
)
check("verdict m1c: nothing live allows", sv({"PLAN-f.md"}, {}).allow, True)
check(
    "verdict m1d: a second writer for the exclusive plan itself",
    sv({"PLAN-e.md"}, LIVE_E).allow,
    True,
)
check(
    "verdict m2: exclusive cannot start while another is live",
    sv({"PLAN-e.md"}, LIVE_F).kind,
    "mutex-own",
)
check("verdict v1: overlapping Owns refuse", sv({"PLAN-g.md"}, LIVE_F).kind, "overlap")
check(
    "verdict v1: the witness is printed", "src/f/b.py" in sv({"PLAN-g.md"}, LIVE_F).lines[1], True
)
check("verdict v1c: disjoint Owns allow", sv({"PLAN-g.md"}, {"PLAN-n.md": ["x"]}).allow, True)
check(
    "verdict n1: a plan with no Owns fails closed once required",
    sv({"PLAN-h.md"}, {}).kind,
    "no-owns",
)
check(
    "verdict n1: before the migration it is not judged",
    (
        sv({"PLAN-h.md"}, LIVE_F, required=False).allow,
        bool(sv({"PLAN-h.md"}, LIVE_F, required=False).note),
    ),
    (True, True),
)
check(
    "verdict n1: a live plan with no Owns is ** once required",
    sv({"PLAN-g.md"}, {"PLAN-h.md": ["x"]}).kind,
    "overlap",
)
check("verdict n1: Owns none refuses a writer", sv({"PLAN-n.md"}, {}).kind, "owns-none")
check(
    "verdict D4: planless, nothing declared, no exclusive: allow with a note",
    (sv(set(), LIVE_F).allow, bool(sv(set(), LIVE_F).note)),
    (True, True),
)
check(
    "verdict D4: planless under a live exclusive, nothing declared", sv(set(), LIVE_E).kind, "mutex"
)
check(
    "verdict D4: planless, declared Owns overlapping",
    sv(set(), LIVE_F, declared=("src/f/x.py",)).kind,
    "overlap",
)
check(
    "verdict D4: planless, declared Owns disjoint",
    sv(set(), LIVE_F, declared=("docs/y.md",)).allow,
    True,
)

# --------------------------------------------------------------------------- rank and order_key (section 2).


def rp(pri, dep="no-dep -- the fixture stands alone", status="in-progress"):
    return plan(status=status, dep=dep, extra="Priority: %s\n" % pri)


RG = D.Graph.from_texts({
    "agent/plans/PLAN-x.md": rp("P0 (operator)", dep="PLAN-y.md"),
    "agent/plans/PLAN-y.md": rp("P3"),
    "agent/plans/PLAN-z.md": rp("P1"),
    "agent/plans/PLAN-a.md": rp("P2 (operator)"),
    "agent/plans/PLAN-b.md": rp("P0"),
    "agent/plans/PLAN-bad.md": rp("P9"),
})  # fmt: skip
check("rank: operator is (n, 4)", X.rank("agent/plans/PLAN-a.md", RG), (2, 4))
check("rank: AI is (4, n)", X.rank("agent/plans/PLAN-b.md", RG), (4, 0))
check("rank: malformed is (4, 4)", X.rank("agent/plans/PLAN-bad.md", RG), (4, 4))
check(
    "rank: a dependency inherits its dependent's rank", X.rank("agent/plans/PLAN-y.md", RG), (0, 4)
)
CTX = X.order_ctx(RG)


def item(plan_base, first):
    return {
        "id": plan_base[5:9] or "none",
        "text": "t %s [41f56150]" % plan_base if plan_base else "t",
        "first": first,
    }


keys = sorted(
    [
        item("PLAN-x.md", "1"),
        item("PLAN-y.md", "2"),
        item("PLAN-z.md", "3"),
        item("", "4"),
        item("PLAN-a.md", "5"),
        item("PLAN-b.md", "6"),
    ],
    key=lambda r: X.order_key(r, CTX),
)
check(
    "order: deps, then operator, then AI, then age",
    [X.item_plan(r) or "unlinked" for r in keys],
    ["PLAN-y.md", "PLAN-a.md", "PLAN-b.md", "PLAN-z.md", "unlinked", "PLAN-x.md"],
)
check(
    "order o1: the blocked plan sorts after its unblocked dependency",
    X.order_key(item("PLAN-x.md", "1"), CTX)[0],
    1,
)
check(
    "order o1: the dependency is unblocked and inherits P0 op",
    X.order_key(item("PLAN-y.md", "2"), CTX)[:3],
    (0, 0, 4),
)
check(
    "order o2: an operator P2 beats an AI P0",
    X.order_key(item("PLAN-a.md", "9"), CTX) < X.order_key(item("PLAN-b.md", "0"), CTX),
    True,
)
check(
    "order o3: equal rank, the older first wins",
    X.order_key(item("PLAN-z.md", "1"), CTX) < X.order_key(item("PLAN-z.md", "2"), CTX),
    True,
)
check("order o4: an unlinked item is an AI P2", X.order_key(item("", "1"), CTX)[:3], (0, 4, 2))
check(
    "order o4: between an AI P1 and an AI P3",
    X.order_key(item("PLAN-z.md", "9"), CTX)
    < X.order_key(item("", "1"), CTX)
    < X.order_key({"text": "PLAN-bad.md [41f56150]", "first": "0"}, CTX),
    True,
)
check("order: a picker's own age term", X.order_key(item("", "1"), CTX, age=-5)[3], -5)
check("label: operator", X.rank_label(1, 4), "[P1 op]")
check("label: AI", X.rank_label(4, 3), "[P3]")
check("label: unranked", X.rank_label(4, 4), "[P-]")

# --------------------------------------------------------------------------- x_findings (section 6b), the shared verdict.


def xcodes(text):
    return sorted({f.code for f in X.x_findings(D.parse_header(text), text)})


GOOD = "# P\nStatus: draft\nOwner: x\nPriority: P2\nConcurrency: parallel\nOwns: a/**\n\n## T\n"
check("x_findings: a valid triple", xcodes(GOOD), [])
check(
    "x_findings: D10 missing, flagged missing",
    [(f.code, f.missing) for f in X.x_findings(D.parse_header(GOOD.replace("Priority: P2\n", "")))],
    [("D10", True)],
)
check("x_findings: D15 universal parallel", xcodes(GOOD.replace("Owns: a/**", "Owns: **")), ["D15"])
check("x_findings: D14 a bad glob", xcodes(GOOD.replace("Owns: a/**", "Owns: ../a")), ["D14"])

T.exit()

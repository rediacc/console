#!/usr/bin/env python3
"""Controls for wl_defersettle: the fact-grounded accept/reject classifier for `[?]` deferrals.

Design: agent/plans/PLAN-defer-settle-classifier.md, section 8. Same shape as test-judge-schema.py: no pytest, a Tally, `control(label, got, want)`, and the model seam stubbed at `wl_judge.wl_proc.run` (or `wl_judge._run_structured` for the creation-time call), so no control ever spends a real judge budget.

Every control is a PAIR: a positive case that proves the mechanism acts, and a negative case that proves it does NOT act where it must not. A classifier that settled everything would pass every positive half; only the negative halves tell it apart from a correct one.
"""

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import types
from typing import Any, cast

HERE = pathlib.Path(__file__).resolve().parent
# ONE PRIVATE TMPDIR, removed at exit whatever happens: run_judge creates `$TMPDIR/claude-worklist/.judge`, and test_hooks_delegates fails any standalone suite that leaves an entry behind.
# `rediacc_ci.runtmp`, loaded BY FILE rather than through a `sys.path` hop (test_canonical_sys_path_hop.py freezes those): a pid-stamped run directory, removed at exit and swept by the next run when this one was killed before `atexit` could fire, which is how /tmp hit its inode cap on 2026-09-24.
_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[2] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit(
        "%s: .ci/rediacc_ci/runtmp.py is missing; this suite cannot make its run dir" % __file__
    )
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
_TMP = runtmp.run_dir("ds-test-")
os.environ["TMPDIR"] = _TMP
tempfile.tempdir = _TMP
sys.path.insert(0, str(HERE))

import wl_checks  # noqa: E402
import wl_core  # noqa: E402
import wl_defersettle as DS  # noqa: E402
import wl_judge  # noqa: E402
import wl_proc  # noqa: E402
import wl_store  # noqa: E402


class Tally:
    fails = 0
    count = 0


def control(label, got, want):
    Tally.count += 1
    if got == want:
        return
    Tally.fails += 1
    print(f"  FAIL {label}: got {got!r}, want {want!r}", file=sys.stderr)


SECRET = "xxxxSECRETVALUE9f3a"  # noqa: S105 -- a planted fixture value, asserted never to leak
BB_QUOTE = DS.CATALOG[0]["quote"]
MR_QUOTE = DS.CATALOG[1]["quote"]


def make_root(env_key=True, script=True):
    root = pathlib.Path(tempfile.mkdtemp(prefix="ds-root-"))
    (root / "CLAUDE.md").write_text(
        "# fixture\n\nline three\n- rule: %s: park it.\n- routing: %s -- not a port.\n"
        % (BB_QUOTE, MR_QUOTE),
        encoding="utf-8",
    )
    scripts = {"check:other": "true"}
    if script:
        scripts["check:xyz"] = "tsx scripts/xyz.ts"
    (root / "package.json").write_text(
        json.dumps({"name": "fixture", "scripts": scripts}, indent=2) + "\n", encoding="utf-8"
    )
    (root / ".ci" / "config").mkdir(parents=True)
    lines = ["{", '  "secrets": {', '    "UNRELATED_KEY": {"id": "abc"}']
    if env_key:
        # The fixture SECRET stands in as the entry's id: nothing from the map, value or id, may reach a fact.
        lines[-1] += ","
        lines.append('    "CLOUDFLARE_R2_ACCESS_KEY_ID": {"id": "%s"}' % SECRET)
    lines += ["  }", "}"]
    (root / ".ci" / "config" / "bws-secret-map.json").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    (root / ".ci" / "policy").mkdir(parents=True)
    (root / ".ci" / "policy" / ".dead-bash-allowlist").write_text(
        "# a\n# b\nsome/path.sh\n", encoding="utf-8"
    )
    return root


def rec(
    rid,
    text,
    why="R2 credentials are an operator-only external account",
    how="operator says yes or no, or provides the key",
    upd="2026-09-24T08:00Z",
):
    return {
        "id": rid,
        "text": text,
        "line": "- [?] (d5e7aaaa) %s" % text,
        "upd": upd,
        "just": {"why": why, "how": how},
    }


def rows(*entries):
    return {"verdict": "stop", "reason": "fine", "next_action": "", "defer_settle": list(entries)}


def entry(rid, verdict, fact_used="1", reason="r"):
    return {"id": rid, "verdict": verdict, "reason": reason, "fact_used": fact_used}


class Writes:
    """Records every store write apply_stop makes, instead of touching a real store."""

    def __init__(self):
        self.calls = []

    def __call__(self, _worklist, by, item_id, state, note="", _extra=None):
        self.calls.append({"by": by, "id": item_id, "s": state, "note": note})


R2_TEXT = (
    "does the operator want to provide the CLOUDFLARE_R2_ACCESS_KEY_ID, or should we skip "
    "R2-backed backup tests DEFAULT: skip R2-backed tests"
)
BB_TEXT = (
    "should this be one PR or split into three separate PRs DEFAULT: fix the cluster this session"
)
BB_NOVEL = "should the wording go in the glossary or in the style guide DEFAULT: glossary"
XYZ_TEXT = "file an issue asking whether we need a `check:xyz` regression gate for this DEFAULT: file the issue"

# ---------------------------------------------------------------- CLASS 1: credential availability
root = make_root()
r2 = rec("a1b2c3d4", R2_TEXT)
facts = DS.gather_facts(root, r2)
env = [f for f in facts if f.kind == "env_key_present"]
control("class1: one env fact for the present key", len(env), 1)
control(
    "class1: its citation is the key's own line",
    env[0].cite if env else None,
    ".ci/config/bws-secret-map.json:4",
)
control("class1: a Fact has no value field at all", "value" in DS.Fact._fields, False)
control("class1: the fact never carries the value", any(SECRET in repr(f) for f in facts), False)
section = DS.prompt_section([(r2, facts)])
control("class1: the prompt carries the marker", DS.DEFER_SETTLE_MARKER in section, True)
control("class1: the prompt never carries the value", SECRET in section, False)

state: dict[Any, Any] = {}
w = Writes()
batch = [(r2, facts)]
out1 = rows(entry(r2["id"], "settled"))
DS.apply_stop(out1, batch, state, str(root), None, run_id="run1", set_state=w)
control("class1: first sight banks and writes nothing", w.calls, [])
control(
    "class1: the bank is un-corroborated",
    state["defer_settle"]["items"][r2["id"]].get("corroborated"),
    None,
)
DS.apply_stop(
    rows(entry(r2["id"], "settled")), batch, state, str(root), None, run_id="run2", set_state=w
)
control("class1: a second agreeing stop ticks exactly once", len(w.calls), 1)
tick = w.calls[0] if w.calls else {}
control("class1: the tick is by the reserved actor", tick.get("by"), DS.ACTOR)
control("class1: and it is a tick", tick.get("s"), "x")
control(
    "class1: the evidence passes the real --tick gate",
    DS._default_gate(str(root), tick.get("note", "")),
    True,
)
control("class1: the evidence never carries the value", SECRET in tick.get("note", ""), False)
control(
    "class1: the evidence carries the machine marker",
    tick.get("note", "").startswith("MACHINE-CLASSIFIED (%s)" % DS.ACTOR),
    True,
)
control("class1: the corroborated item is not re-asked", DS.build_batch(root, state, [r2]), [])

root_nokey = make_root(env_key=False)
nf = DS.gather_facts(root_nokey, r2)
control("class1 control: no key, no env fact", [f for f in nf if f.kind == "env_key_present"], [])
control("class1 control: only present facts are ever emitted", nf, [])
control(
    "class1 control: an item with no fact never enters the batch",
    DS.build_batch(root_nokey, {}, [r2]),
    [],
)

# ---------------------------------------------------------------- CLASS 2: standing-rule packaging
bb = rec(
    "b2c3d4e5",
    BB_TEXT,
    why="packaging is the operator's call",
    how="operator picks one",
    upd=wl_core.stamp_now(),
)
bf = DS.gather_facts(root, bb)
control("class2: the big-bang rule matches", [f.subject for f in bf], ["big-bang-packaging"])
control(
    "class2: cited at the line holding the verbatim quote",
    bf[0].cite if bf else None,
    "CLAUDE.md:4",
)
state, w = {}, Writes()
for run in ("s1", "s2"):
    DS.apply_stop(
        rows(entry(bb["id"], "execute_default")),
        [(bb, bf)],
        state,
        str(root),
        None,
        run_id=run,
        set_state=w,
    )
control(
    "class2: the item is still inside its DEFER_WINDOW_MIN",
    (wl_core.stamp_age_min(bb["upd"]) or 0) < wl_store.DEFER_WINDOW_MIN,
    True,
)
control(
    "class2: a corroborated execute_default joins the expired demand before its window",
    [r["id"] for r in DS.accelerated(state, [bb], [])],
    [bb["id"]],
)
control("class2: and it never writes a tick", w.calls, [])
control(
    "class2: an item already in the expired list is not duplicated",
    DS.accelerated(state, [bb], [bb]),
    [],
)
control(
    "class2: a moved item (new stamp) is no longer accelerated",
    DS.accelerated(state, [dict(bb, upd="2026-09-24T00:01Z")], []),
    [],
)
novel = rec("c3d4e5f6", BB_NOVEL, why="the operator owns the glossary", how="operator picks one")
control(
    "class2 control: a novel packaging question matches no rule", DS.gather_facts(root, novel), []
)
state_n: dict[Any, Any] = {}
DS.apply_stop(
    rows(entry(novel["id"], "execute_default")), [], state_n, str(root), None, set_state=w
)
control("class2 control: nothing is accelerated for it", DS.accelerated(state_n, [novel], []), [])
root_drift = make_root()
(root_drift / "CLAUDE.md").write_text("# the rule was reworded\n", encoding="utf-8")
control(
    "class2 control: a drifted quote emits no rule fact",
    [f for f in DS.gather_facts(root_drift, bb) if f.kind == "standing_rule_match"],
    [],
)

# ---------------------------------------------------------------- CLASS 3: artifact already exists
xyz = rec(
    "d4e5f6a7", XYZ_TEXT, why="whether a gate is needed is a policy call", how="operator says yes"
)
xf = DS.gather_facts(root, xyz)
control("class3: the registered script is a fact", [f.subject for f in xf], ["check:xyz"])
state, w = {}, Writes()
for run in ("t1", "t2"):
    DS.apply_stop(
        rows(entry(xyz["id"], "settled")),
        [(xyz, xf)],
        state,
        str(root),
        None,
        run_id=run,
        set_state=w,
    )
control("class3: two agreeing stops tick it", [c["id"] for c in w.calls], [xyz["id"]])
control(
    "class3: evidence cites the scripts entry",
    "package.json:" in (w.calls[0]["note"] if w.calls else ""),
    True,
)
control(
    "class3: and passes the real gate",
    DS._default_gate(str(root), w.calls[0]["note"]) if w.calls else False,
    True,
)
root_noscript = make_root(script=False)
control(
    "class3 control: an unregistered script is no fact", DS.gather_facts(root_noscript, xyz), []
)
plain = rec(
    "e5f6a7b8",
    "see .claude/x.py for context DEFAULT: nothing",
    why="a design question",
    how="operator decides",
)
control(
    "class3 control: a path in an item not about existence is no fact",
    DS.gather_facts(root, plain),
    [],
)

(root / "agent" / "plans").mkdir(parents=True)
(root / "agent" / "plans" / "PLAN-x.md").write_text("# plan\n", encoding="utf-8")
(root / "scripts").mkdir()
(root / "scripts" / "xyz.ts").write_text("export {}\n", encoding="utf-8")
own = rec(
    "a7b8c9d0",
    "whether agent/plans/PLAN-x.md needs a box DEFAULT: add it",
    why="a design question",
    how="operator decides",
)
control("class3 control: a deferral's own plan file is no fact", DS.gather_facts(root, own), [])
built = rec(
    "b8c9d0e1",
    "whether scripts/xyz.ts needs to be built DEFAULT: build it",
    why="a design question",
    how="operator decides",
)
control(
    "class3: an existing repo file the item asks about is a fact",
    [f.cite for f in DS.gather_facts(root, built)],
    ["scripts/xyz.ts:1"],
)

# ---------------------------------------------------------------- PAIR: fail-safe direction
state, w = {}, Writes()
out = rows()  # the judge answered the stop but left defer_settle empty
DS.apply_stop(out, [(r2, facts)], state, str(root), None, run_id="f1", set_state=w)
control("failsafe: a missing entry does not force a block", out["verdict"], "stop")
control("failsafe: it is reported on the reason", "[defer-settle not judged" in out["reason"], True)
control("failsafe: nothing banked for the unanswered item", state["defer_settle"]["items"], {})
out = {"verdict": "stop", "reason": "r", "next_action": ""}
DS.apply_stop(out, [(r2, facts)], state, str(root), None, run_id="f2", set_state=w)
control("failsafe: an absent array degrades, never blocks", (out["verdict"], w.calls), ("stop", []))
out = rows(entry(r2["id"], "settled", fact_used="7"))
DS.apply_stop(out, [(r2, facts)], state, str(root), None, run_id="f3", set_state=w)
control(
    "failsafe: a settled citing no given fact acts on nothing",
    state["defer_settle"]["items"][r2["id"]]["verdict"],
    "uncertain",
)
# Whole-call failure: run_judge fails, so wl_checks never reaches apply_stop; the item is untouched by construction. Pinned through the real transport.


class _TimedOut:
    returncode = wl_proc.TIMEOUT_RC
    stdout = ""
    stderr = ""
    timed_out = True


CAPTURED: dict[str, Any] = {}


def _fake_run(cmd, **_kw):
    CAPTURED["prompt"] = cmd[cmd.index("-p") + 1]
    CAPTURED["schema"] = json.loads(cmd[cmd.index("--json-schema") + 1])
    ans = CAPTURED.get("answer")
    if ans == "timeout":
        return _TimedOut()
    return types.SimpleNamespace(
        returncode=0,
        stderr="",
        timed_out=False,
        stdout=json.dumps({"is_error": False, "structured_output": ans}),
    )


cast("Any", wl_judge).wl_proc = types.SimpleNamespace(
    run=_fake_run, TIMEOUT_RC=wl_proc.TIMEOUT_RC, SPAWN_FAILED_RC=wl_proc.SPAWN_FAILED_RC
)
wl_judge.resolve_claude = lambda: "/bin/sh"
CAPTURED["answer"] = "timeout"
v, err = wl_judge.run_judge(["- [?] x"], 0, "m", 0, "none", extra=DS.prompt_section([(r2, facts)]))
control(
    "failsafe: a timed-out judge call returns an error, no verdict", (v, bool(err)), (None, True)
)
CAPTURED["answer"] = rows(entry(r2["id"], "settled"))
v, err = wl_judge.run_judge(["- [?] x"], 0, "m", 0, "none", extra=DS.prompt_section([(r2, facts)]))
control(
    "e2e: the schema requires defer_settle when asked",
    "defer_settle" in CAPTURED["schema"]["required"],
    True,
)
control("e2e: the secret never reaches the judge prompt", SECRET in CAPTURED["prompt"], False)
control(
    "e2e: the verdict carries the array through",
    (v or {}).get("defer_settle", [{}])[0].get("verdict"),
    "settled",
)
v, err = wl_judge.run_judge(["- [?] x"], 0, "m", 0, "none", extra="")
control(
    "e2e control: an ordinary stop does not require it",
    "defer_settle" in CAPTURED["schema"]["required"],
    False,
)

# ---------------------------------------------------------------- PAIR: no corroboration
two = rec(
    "f6a7b8c9",
    R2_TEXT + " and whether `check:xyz` is needed",
    why="R2 credentials are an operator-only account",
    how="operator decides",
)
tf = DS.gather_facts(root, two)
control("nocorr: the fixture carries two distinct facts", len(tf), 2)
state, w = {}, Writes()
DS.apply_stop(
    rows(entry(two["id"], "settled", "1")),
    [(two, tf)],
    state,
    str(root),
    None,
    run_id="n1",
    set_state=w,
)
DS.apply_stop(
    rows(entry(two["id"], "settled", "2")),
    [(two, tf)],
    state,
    str(root),
    None,
    run_id="n2",
    set_state=w,
)
control("nocorr: settled twice on DIFFERENT facts does not tick", w.calls, [])
state, w = {}, Writes()
DS.apply_stop(
    rows(entry(two["id"], "settled", "1")),
    [(two, tf)],
    state,
    str(root),
    None,
    run_id="same",
    set_state=w,
)
DS.apply_stop(
    rows(entry(two["id"], "settled", "1")),
    [(two, tf)],
    state,
    str(root),
    None,
    run_id="same",
    set_state=w,
)
control("nocorr: the same run read twice is one sample, not two", w.calls, [])
state, w = {}, Writes()
DS.apply_stop(
    rows(entry(two["id"], "settled", "1")),
    [(two, tf)],
    state,
    str(root),
    None,
    run_id="m1",
    set_state=w,
)
DS.apply_stop(
    rows(entry(two["id"], "settled", "1")),
    [(dict(two, upd="2026-09-24T09:00Z"), tf)],
    state,
    str(root),
    None,
    run_id="m2",
    set_state=w,
)
control("nocorr: an item that moved between samples does not tick", w.calls, [])
state, w = {}, Writes()
DS.apply_stop(
    rows(entry(two["id"], "settled", "1")),
    [(two, tf)],
    state,
    str(root),
    None,
    run_id="p1",
    set_state=w,
)
DS.apply_stop(
    rows(entry(two["id"], "settled", "1")),
    [(two, tf)],
    state,
    str(root),
    None,
    run_id="p2",
    set_state=w,
)
control("nocorr control: the same fact twice DOES tick", len(w.calls), 1)

# ---------------------------------------------------------------- PAIR: evidence gate (hard limit 3)
state, w = {}, Writes()
for run in ("g1", "g2"):
    DS.apply_stop(
        rows(entry(r2["id"], "settled")),
        [(r2, facts)],
        state,
        str(root),
        None,
        run_id=run,
        set_state=w,
        gate=lambda _r, _e: False,
    )
control("gate: a refusing evidence gate means no tick", w.calls, [])
control(
    "gate: recorded as a refusal",
    state["defer_settle"]["items"][r2["id"]].get("outcome"),
    "refused-evidence-gate",
)
control(
    "gate control: issue-only evidence is refused by the default gate",
    DS._default_gate(str(root), "filed https://github.com/o/r/issues/5"),
    False,
)

# ---------------------------------------------------------------- PAIR: cap (hard limit 6)
state, w = {}, Writes()
many = [(rec("%08x" % (0xAB000 + i), XYZ_TEXT), xf) for i in range(DS.SETTLE_CAP + 1)]
notes = []
for run in ("c1", "c2"):
    notes = DS.apply_stop(
        rows(*[entry(r["id"], "settled") for r, _f in many]),
        many,
        state,
        str(root),
        None,
        run_id=run,
        set_state=w,
    )
control("cap: exactly SETTLE_CAP items are auto-settled", len(w.calls), DS.SETTLE_CAP)
control(
    "cap: the next one is reported, not acted on", any("NOT auto-settled" in n for n in notes), True
)
control(
    "cap: and recorded as capped",
    state["defer_settle"]["items"][many[-1][0]["id"]].get("outcome"),
    "capped",
)

# ---------------------------------------------------------------- PAIR: catalog forbidden orders (hard limit 2)
DS.check_catalog(wl_judge.FORBIDDEN_ORDERS)
control("catalog: the shipped catalog passes the scan", True, True)
_saved = DS.CATALOG
cast("Any", DS).CATALOG = (dict(_saved[0], action="merge the open PRs and cut the release"),)
try:
    DS.check_catalog(wl_judge.FORBIDDEN_ORDERS)
    refused = False
except AssertionError:
    refused = True
finally:
    DS.CATALOG = _saved
control("catalog control: an entry ordering a merge is refused", refused, True)

# ---------------------------------------------------------------- PAIR: nested dotfile citations resolve
control(
    "cite: a nested dotfile line is evidence",
    wl_checks.completion_evidence(str(root), "see .ci/policy/.dead-bash-allowlist:3"),
    True,
)
control(
    "cite control: a fabricated nested dotfile is not",
    wl_checks.completion_evidence(str(root), "see .ci/nowhere/.dead-bash-allowlist:3"),
    False,
)

# ---------------------------------------------------------------- CREATION TIME and the reserved actor, through worklist._item_cli
SID = "d5e7a9c1-0000-4000-8000-000000000000"
ME = SID[:8]
os.environ["WORKLIST_SESSION_ID"] = SID
os.environ["CLAUDE_PROJECT_DIR"] = str(root)
os.environ.pop("WORKLIST_JUDGE", None)
import worklist as WL  # noqa: E402

store_dir = pathlib.Path(tempfile.mkdtemp(prefix="ds-store-"))
WLPATH = store_dir / "wl.md"


def cli(*argv):
    err = io.StringIO()
    code: Any = 0
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        try:
            WL._item_cli(list(argv), WLPATH)
        except SystemExit as exc:
            code = exc.code
    return code, err.getvalue()


def state_of(rid):
    return wl_store.load(WLPATH, sync=False).by_id[rid]["state"]


R2_DEFER = (
    R2_TEXT
    + " WHY: R2 credentials are an operator-only external account HOW: operator provides the key"
)
real_rs = wl_judge._run_structured
wl_judge._run_structured = lambda *_a, **_k: (
    [entry("new", "settled", "1", "the key is already there")],
    None,
)
rid = wl_store.add_item(WLPATH, ME, "decide on R2 tests")
code, msg = cli("--defer", ME, rid, R2_DEFER)
control("create: a confident settled refuses the --defer", code, 1)
control(
    "create: the refusal names the fact, not the value",
    ("CLOUDFLARE_R2_ACCESS_KEY_ID" in msg, SECRET in msg),
    (True, False),
)
control("create: the item is not deferred", state_of(rid), " ")
wl_judge._run_structured = lambda *_a, **_k: (None, "claude CLI not found")
code, msg = cli("--defer", ME, rid, R2_DEFER)
control(
    "create control: a classifier error falls through to creation", (code, state_of(rid)), (0, "?")
)
wl_judge._run_structured = lambda *_a, **_k: ([entry("new", "uncertain", "", "not sure")], None)
rid2 = wl_store.add_item(WLPATH, ME, "decide on R2 tests again")
code, _msg = cli("--defer", ME, rid2, R2_DEFER)
control(
    "create control: an uncertain verdict creates the deferral", (code, state_of(rid2)), (0, "?")
)


def _boom(*_a, **_k):
    raise RuntimeError("planted")


wl_judge._run_structured = _boom
rid3 = wl_store.add_item(WLPATH, ME, "decide on R2 tests a third time")
code, _msg = cli("--defer", ME, rid3, R2_DEFER)
control("create control: a classifier that raises still creates", (code, state_of(rid3)), (0, "?"))
wl_judge._run_structured = real_rs

rid4 = wl_store.add_item(WLPATH, ME, "tick me")
code, msg = cli("--tick", DS.ACTOR, rid4, "done, see package.json:1")
control(
    "reserved: the defer-settle actor is refused as <me>",
    (code, "reserved actor" in msg),
    (1, True),
)
control("reserved: and nothing was written", state_of(rid4), " ")
# THE CASE check_me CANNOT CATCH: a terminal with no session id accepts any shape-valid <me>, so only the reservation stands between it and a forged machine tick.
_saved_sid = os.environ.pop("WORKLIST_SESSION_ID")
_saved_cc = os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
unowned = wl_store.add_item(WLPATH, "operator", "an operator-terminal item")
code, msg = cli("--tick", DS.ACTOR, unowned, "done, see package.json:1")
control(
    "reserved: refused even where identity cannot be verified",
    (code, "reserved actor" in msg, state_of(unowned)),
    (1, True, " "),
)
os.environ["WORKLIST_SESSION_ID"] = _saved_sid
if _saved_cc is not None:
    os.environ["CLAUDE_CODE_SESSION_ID"] = _saved_cc
code, _msg = cli("--tick", ME, rid4, "done, see package.json:1")
control("reserved control: an ordinary session id ticks", (code, state_of(rid4)), (0, "x"))

# ---------------------------------------------------------------- STOP WIRING in wl_checks (structural: the call sites exist, in order)
_src = (HERE / "wl_checks.py").read_text(encoding="utf-8")
control(
    "wiring: the batch is built beside defer_audit's", "wl_defersettle.build_batch(" in _src, True
)
control(
    "wiring: its section rides the judge's extra", "wl_defersettle.prompt_section(" in _src, True
)
control("wiring: the verdict is applied", "wl_defersettle.apply_stop(" in _src, True)
control(
    "wiring: execute_default reaches the expired demand",
    "wl_defersettle.accelerated(" in _src,
    True,
)
control(
    "wiring: the cached stop verdict is bypassed while a settle question is pending",
    "not audit_batch and not settle_batch" in _src,
    True,
)

for d in (root, root_nokey, root_drift, root_noscript, store_dir):
    shutil.rmtree(d, ignore_errors=True)

if Tally.fails:
    print(f"FAIL: {Tally.fails} of {Tally.count} control(s) failed", file=sys.stderr)
    sys.exit(1)
print(f"{Tally.count} control(s) passed")

#!/usr/bin/env python3
"""Control harness for block_plan_concurrency, the spawn-time half of plan concurrency (agent/plans/PLAN-plan-priority-concurrency.md section 8).

BOTH DIRECTIONS. A guard that refused every spawn would pass the refusal cases and one that refused none would pass the allow cases, so each refusal has an allow twin differing by one planted fact: the holder finished, the lease expired, the Owns are disjoint, the spawn serves the exclusive plan itself.

LOAD-BEARING, NOT OPTIONAL. The guard declares `OWN_SUITE = True`, so `test_guards_differential.py` requires this file beside it, and `test_hooks_delegates.py` discovers and runs it.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER against a real fixture on disk, in ONE pid-stamped directory removed on exit: a plan tree (`CLAUDE_PROJECT_DIR`), a projects store with this session's live and finished writers (`CLAUDE_CONFIG_DIR`), a worklist store with this session's and a peer's items and leases (`WORKLIST_STORE_DIR`), and a TMPDIR.

BEFORE AND AFTER THE MIGRATION. The "plan with no Owns" cases follow `wl_plandeps.X_FIELDS_REQUIRED`, read from its source: not judged (allowed with a note) while it is False, refused (fail closed as `**`) once T11 sets it to True.

THE DEFECT IS PROVEN HERE TOO. The guard's declared `DEFECT` is planted in-process and run on the same payloads; at least one answer must change.
"""

import atexit
import datetime
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
GUARD = HERE / "block_plan_concurrency.py"
DISPATCH = str(HERE.parent / "dispatch.py")
SID = "cafe0000-1111-2222-3333-444444444444"
PEER = "0fee0fee"
BASE = pathlib.Path(tempfile.gettempdir()) / ("planconc-guard-%d" % os.getpid())
atexit.register(shutil.rmtree, BASE, ignore_errors=True)
SOURCE = GUARD.read_text(encoding="utf-8")
XREQ = bool(
    re.search(
        r"^X_FIELDS_REQUIRED = True$",
        (HERE.parents[1] / "hooks" / "stop" / "wl_plandeps.py").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
)

PLAN = "# PLAN: {n}\n\nStatus: in-progress\nOwner: cafe0000\nDepends-On: no-dep -- a fixture plan for the concurrency suite\nPriority: P2\n{x}\n## Tasks\n\n- [ ] T1 a box\n"


def munged(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def stamp(minutes):
    t = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%MZ")


def world(plans, writers=(), finished=(), items=(), leases=()):
    """A fresh fixture. `plans` maps a name to its X lines (without Priority); `writers`/`finished` are first prompts of this session's live/finished general-purpose agents; `items` are (id, owner, text); `leases` are (id, owner, worker, minutes ahead)."""
    if BASE.exists():
        shutil.rmtree(BASE)
    proj = BASE / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / "agent" / "plans").mkdir(parents=True)
    (BASE / "tmp").mkdir()
    (BASE / "store").mkdir()
    for name, x in plans.items():
        (proj / "agent" / "plans" / ("PLAN-%s.md" % name)).write_text(
            PLAN.format(n=name, x=x), encoding="utf-8"
        )
    sub = BASE / "claude" / "projects" / munged(proj.resolve()) / SID / "subagents"
    sub.mkdir(parents=True)
    working = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}}
    done = {
        "type": "assistant",
        "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}]},
    }
    n = 0
    for prompts, last in ((writers, working), (finished, done)):
        for prompt in prompts:
            n += 1
            aid = "a%016d" % n
            (sub / ("agent-%s.meta.json" % aid)).write_text(
                json.dumps(
                    {
                        "agentType": "general-purpose",
                        "description": "fixture %d" % n,
                        "spawnDepth": 1,
                    }
                ),
                encoding="utf-8",
            )
            tx = sub / ("agent-%s.jsonl" % aid)
            first = {"type": "user", "message": {"content": prompt}}
            tx.write_text(json.dumps(first) + "\n" + json.dumps(last) + "\n", encoding="utf-8")
            old = time.time() - 10
            os.utime(tx, (old, old))
    at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = [
        {"ev": "add", "id": i, "at": at, "by": o, "s": " ", "o": o, "t": "(%s) %s" % (o, t)}
        for i, o, t in items
    ]
    rows += [
        {
            "ev": "lease",
            "id": i,
            "at": at,
            "by": o,
            "until": stamp(m),
            "worker": w,
            "note": "",
            "worker_verified": True,
        }
        for i, o, w, m in leases
    ]
    (BASE / "store" / "fixture.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    return proj


def env_for(proj):
    env = {k: v for k, v in os.environ.items() if not k.startswith("WORKLIST_")}
    env.update(
        {
            "CLAUDE_CONFIG_DIR": str(BASE / "claude"),
            "CLAUDE_PROJECT_DIR": str(proj),
            "TMPDIR": str(BASE / "tmp"),
            "WORKLIST_STORE_DIR": str(BASE / "store"),
        }
    )
    return env


def payload(prompt, kind="general-purpose", session=SID, tool="Agent"):
    return {
        "tool_name": tool,
        "session_id": session,
        "cwd": str(BASE / "proj"),
        "tool_input": {"subagent_type": kind, "description": "probe", "prompt": prompt},
    }


def run_case(proj, doc):
    proc = subprocess.run(
        [sys.executable, DISPATCH, "block_plan_concurrency"],
        input=json.dumps(doc),
        capture_output=True,
        text=True,
        check=False,
        env=env_for(proj),
    )
    return proc.returncode, proc.stderr


EXCL = "Concurrency: exclusive -- regenerates every golden file\nOwns: docs/e/**\n"
PAR_F = "Concurrency: parallel\nOwns: docs/f/**\n"
PAR_A = "Concurrency: parallel\nOwns: a/**\n"
PAR_AB = "Concurrency: parallel\nOwns: a/b.py\n"
PAR_C = "Concurrency: parallel\nOwns: c/**\n"
NO_OWNS = "Concurrency: parallel\n"
NONE = "Concurrency: parallel\nOwns: none -- an operator-action fixture plan\n"
BASIC = {"e": EXCL, "f": PAR_F}
E_ITEM = ("e0e0e0e0", SID[:8], "regenerate PLAN-e.md [e1e1e1e1]")
P_ITEM = ("a0a0a0a0", PEER, "edit a PLAN-p.md [a1a1a1a1]")

# (name, world kwargs, payload, want_rc, stderr needles)
CASES = [
    (
        "m1 a live exclusive writer refuses another plan",
        {"plans": BASIC, "writers": ["Plan: PLAN-e.md"]},
        payload("Plan: PLAN-f.md"),
        2,
        ["PLAN-e.md is exclusive", "writer a0000000000000001", "worker:queue"],
    ),
    (
        "m1 the holder is found through its #item",
        {"plans": BASIC, "writers": ["work #e0e0e0e0"], "items": [E_ITEM]},
        payload("Plan: PLAN-f.md"),
        2,
        ["PLAN-e.md is exclusive"],
    ),
    (
        "m1 the spawn is found through its #item",
        {
            "plans": BASIC,
            "writers": ["Plan: PLAN-e.md"],
            "items": [("f0f0f0f0", SID[:8], "docs PLAN-f.md [f1f1f1f1]")],
        },
        payload("do #f0f0f0f0"),
        2,
        ["PLAN-e.md is exclusive"],
    ),
    (
        "m1c the exclusive writer finished",
        {"plans": BASIC, "finished": ["Plan: PLAN-e.md"]},
        payload("Plan: PLAN-f.md"),
        0,
        [],
    ),
    (
        "m1d a second writer for the exclusive plan itself",
        {"plans": BASIC, "writers": ["Plan: PLAN-e.md"]},
        payload("Plan: PLAN-e.md"),
        0,
        [],
    ),
    (
        "m2 an exclusive plan cannot start while another is live",
        {"plans": BASIC, "writers": ["Plan: PLAN-f.md"]},
        payload("Plan: PLAN-e.md"),
        2,
        ["cannot start while other plans are live"],
    ),
    (
        "m2c nothing live, the exclusive plan starts",
        {"plans": BASIC},
        payload("Plan: PLAN-e.md"),
        0,
        [],
    ),
    (
        "v1 overlapping Owns refuse, with the witness",
        {"plans": {"p": PAR_A, "q": PAR_AB}, "writers": ["Plan: PLAN-p.md"]},
        payload("Plan: PLAN-q.md"),
        2,
        ["both claim `a/b.py`", "--set-x"],
    ),
    (
        "v1c disjoint Owns allow",
        {"plans": {"p": PAR_A, "q": PAR_C}, "writers": ["Plan: PLAN-p.md"]},
        payload("Plan: PLAN-q.md"),
        0,
        [],
    ),
    (
        "v2 a peer's fresh lease is live",
        {
            "plans": {"p": PAR_A, "q": PAR_AB},
            "items": [P_ITEM],
            "leases": [("a0a0a0a0", PEER, "b9b9b9b9", 60)],
        },
        payload("Plan: PLAN-q.md"),
        2,
        ["lease #a0a0a0a0 worker:b9b9b9b9 (session 0fee0fee)"],
    ),
    (
        "v2c a peer's expired lease is not",
        {
            "plans": {"p": PAR_A, "q": PAR_AB, "zz": PAR_C},
            "items": [P_ITEM],
            "leases": [("a0a0a0a0", PEER, "b9b9b9b9", -5)],
            "writers": ["Plan: PLAN-zz.md"],
        },
        payload("Plan: PLAN-q.md"),
        0,
        [],
    ),
    (
        "v2c a queue lease is no holder",
        {
            "plans": {"p": PAR_A, "q": PAR_AB, "zz": PAR_C},
            "items": [P_ITEM],
            "leases": [("a0a0a0a0", PEER, "queue", 60)],
            "writers": ["Plan: PLAN-zz.md"],
        },
        payload("Plan: PLAN-q.md"),
        0,
        [],
    ),
    (
        "n1 a plan with no Owns",
        {"plans": {"h": NO_OWNS, "f": PAR_F}, "writers": ["Plan: PLAN-f.md"]},
        payload("Plan: PLAN-h.md"),
        2 if XREQ else 0,
        ["declares no valid Owns"] if XREQ else ["declares no Owns yet"],
    ),
    (
        "n1 a live writer on a plan with no file is ** once required",
        {"plans": {"q": PAR_AB}, "writers": ["Plan: PLAN-gone.md"]},
        payload("Plan: PLAN-q.md"),
        2 if XREQ else 0,
        ["PLAN-gone.md is parallel and live"] if XREQ else [],
    ),
    (
        "n1 Owns none refuses a writer",
        {"plans": {"n": NONE}},
        payload("Plan: PLAN-n.md"),
        2,
        ["`Owns: none`"],
    ),
    (
        "n1 a planless spawn with no Owns is allowed with a note",
        {"plans": {"f": PAR_F}, "writers": ["Plan: PLAN-f.md"]},
        payload("fix a typo"),
        0,
        ["declares no `Owns:` line"],
    ),
    (
        "n1 a planless spawn with overlapping Owns",
        {"plans": {"f": PAR_F}, "writers": ["Plan: PLAN-f.md"]},
        payload("fix a typo\nOwns: docs/f/x.md"),
        2,
        ["both claim `docs/f/x.md`"],
    ),
    (
        "n1 a planless spawn under a live exclusive, nothing declared",
        {"plans": BASIC, "writers": ["Plan: PLAN-e.md"]},
        payload("fix a typo"),
        2,
        ["PLAN-e.md is exclusive"],
    ),
    (
        "n1c a planless spawn with no exclusive anywhere takes the cheap path",
        {"plans": {"f": PAR_F}},
        payload("fix a typo"),
        0,
        ["declares no `Owns:` line"],
    ),
    (
        "a reader under a live exclusive",
        {"plans": BASIC, "writers": ["Plan: PLAN-e.md"]},
        payload("Plan: PLAN-f.md", kind="Explore"),
        0,
        [],
    ),
    (
        "not a spawn",
        {"plans": BASIC, "writers": ["Plan: PLAN-e.md"]},
        {"tool_name": "Bash", "tool_input": {"command": "true"}},
        0,
        [],
    ),
    (
        "blind: no session directory and no lease",
        {"plans": BASIC},
        payload("Plan: PLAN-f.md", session="zz-no-such-session"),
        0,
        ["ALLOWED unchecked"],
    ),
]


def f1_unimportable():
    """f1: a copy of the guard whose stop directory does not exist must fail OPEN and say so."""
    fake = BASE / "fake" / ".claude" / "rediacc_hooks" / "guards"
    fake.mkdir(parents=True)
    copy = fake / "block_plan_concurrency.py"
    copy.write_text(SOURCE, encoding="utf-8")
    script = (
        "import json, sys, importlib.util\n"
        "sys.path.insert(0, %r)\n"
        "from rediacc_hooks import hookio\n"
        "spec = importlib.util.spec_from_file_location('g', %r)\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "ev = hookio.Event(json.dumps(%r), cwd=%r)\n"
        "rc = m.run(ev)\n"
        "print(rc, ev.result(rc)[2].replace(chr(10), ' '))\n"
    ) % (str(HERE.parents[1]), str(copy), payload("Plan: PLAN-f.md"), str(BASE))
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=env_for(BASE / "proj"),
    )
    return proc.stdout.strip(), proc.stderr.strip()


def main():
    fails = 0
    refused = 0
    for name, kw, doc, want, needles in CASES:
        proj = world(**kw)
        rc, err = run_case(proj, doc)
        refused += rc == 2
        ok = rc == want and all(n in err for n in needles)
        fails += not ok
        print("%-72s want=%d got=%d %s" % (name, want, rc, "ok" if ok else "*** FAIL ***"))
        if not ok:
            print("    stderr: %s" % err.strip()[:600])

    world(plans=BASIC)
    out, err = f1_unimportable()
    ok = out.startswith("0 ") and "ALLOWED unchecked" in out
    fails += not ok
    print(
        "%-72s %s"
        % (
            "f1 an unimportable stop dir fails open, loudly",
            "ok" if ok else "*** FAIL *** %r %r" % (out, err[-300:]),
        )
    )

    # ---- the DEFECT, planted and run in-process on the same payloads ----
    _spec = importlib.util.spec_from_file_location(
        "rediacc_hooks", HERE.parent / "__init__.py", submodule_search_locations=[str(HERE.parent)]
    )
    if _spec is None or _spec.loader is None:
        raise SystemExit("cannot load the rediacc_hooks package from %s" % HERE.parent)
    _pkg = importlib.util.module_from_spec(_spec)
    sys.modules["rediacc_hooks"] = _pkg
    _spec.loader.exec_module(_pkg)
    from rediacc_hooks import hookio  # noqa: PLC0415 -- the package is registered just above

    good: dict = {"__name__": "good_guard", "__file__": str(GUARD)}
    exec(compile(SOURCE, str(GUARD), "exec"), good)  # noqa: S102
    old, new = good["DEFECT"]
    if old not in SOURCE:
        print("*** FAIL *** the declared DEFECT no longer applies to the guard: %r" % old)
        fails += 1
    else:
        bad: dict = {"__name__": "broken_guard", "__file__": str(GUARD)}
        exec(compile(SOURCE.replace(old, new), str(GUARD), "exec"), bad)  # noqa: S102
        changed = 0
        saved = dict(os.environ)
        try:
            for _name, kw, doc, _want, _needles in CASES:
                proj = world(**kw)
                os.environ.clear()
                os.environ.update(env_for(proj))
                answers = [
                    ns["run"](hookio.Event(json.dumps(doc), cwd=str(proj))) for ns in (good, bad)
                ]
                changed += answers[0] != answers[1]
        finally:
            os.environ.clear()
            os.environ.update(saved)
        print("DEFECT planted: %d of %d answer(s) changed" % (changed, len(CASES)))
        if changed == 0:
            print(
                "*** FAIL *** the planted DEFECT changed no answer, so this suite does not depend on the mutex line"
            )
            fails += 1

    print()
    if refused in (0, len(CASES)):
        print(
            "*** FAIL *** %d of %d cases refused: the guard answered the same way on every input"
            % (refused, len(CASES))
        )
        fails += 1
    print(
        "block_plan_concurrency: %d case(s), %d refused, X fields %s, %d failure(s)"
        % (len(CASES), refused, "required" if XREQ else "optional", fails)
    )
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

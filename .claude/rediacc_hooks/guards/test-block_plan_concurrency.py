#!/usr/bin/env python3
"""Control harness for block_plan_concurrency, the spawn-time half of plan concurrency (agent/plans/PLAN-plan-priority-concurrency.md section 8).

BOTH DIRECTIONS. A guard that refused every spawn would pass the refusal cases and one that refused none would pass the allow cases, so each refusal has an allow twin differing by one planted fact: the holder finished, the lease expired, the Owns are disjoint, the spawn serves the exclusive plan itself.

LOAD-BEARING, NOT OPTIONAL. The guard declares `OWN_SUITE = True`, so `test_guards_differential.py` requires this file beside it, and `test_hooks_delegates.py` discovers and runs it.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER against a real fixture on disk, in ONE pid-stamped directory removed on exit: a plan tree (`CLAUDE_PROJECT_DIR`), a projects store with this session's live and finished writers (`CLAUDE_CONFIG_DIR`), a worklist store with this session's and a peer's items and leases (`WORKLIST_STORE_DIR`), and a TMPDIR.

THE X FIELDS ARE MANDATORY (PLAN-plan-priority-concurrency.md T11). A plan with no Owns is refused, fail closed as `**`.

THE DEFECT IS PROVEN HERE TOO. The guard's declared `DEFECT` is planted in-process and run on the same payloads; at least one answer must change.

ISOLATION (W12 of the lease plan). An overlap from a spawn the harness isolates is a stderr note naming the witness; every other refusal stands. The value is read from the guard's `ISOLATED_SPAWN`: this file's event rows sit beside that word's verb on a pre-bash arm that refuses a dirty script naming both. i0 pins the value against /writers-now.

SAME-MESSAGE SPAWNS (W13, #105d59a7). `SEQUENCES` drives several spawns against one world with nothing between them, so only the claim file can carry a sibling. `CLAIM_READ_DEFECT` removes the read and the 2026-11-04 shape must stop being refused.
"""

import ast
import atexit
import datetime
import fcntl
import importlib
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
import typing

HERE = pathlib.Path(__file__).resolve().parent
GUARD = HERE / "block_plan_concurrency.py"
DISPATCH = str(HERE.parent / "dispatch.py")
SID = "cafe0000-1111-2222-3333-444444444444"
PEER = "0fee0fee"
BASE = pathlib.Path(tempfile.gettempdir()) / ("planconc-guard-%d" % os.getpid())
atexit.register(shutil.rmtree, BASE, ignore_errors=True)
SOURCE = GUARD.read_text(encoding="utf-8")

_ISOLATED = re.search(r'^ISOLATED_SPAWN = "([^"]+)"$', SOURCE, re.MULTILINE)
if _ISOLATED is None:
    raise SystemExit("*** FAIL *** the guard declares no ISOLATED_SPAWN")
ISOLATED = _ISOLATED.group(1)
WRITERS_NOW = HERE.parents[1] / "commands" / "writers-now.md"

PLAN = "# PLAN: {n}\n\nStatus: in-progress\nOwner: cafe0000\nDepends-On: no-dep -- a fixture plan for the concurrency suite\nPriority: P2\n{x}\n## Tasks\n\n- [ ] T1 a box\n"


def munged(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def stamp(minutes):
    t = datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%MZ")


def world(plans, writers=(), finished=(), items=(), leases=(), cap=None):
    """A fresh fixture. `plans` maps a name to its X lines (without Priority); `writers`/`finished` are first prompts of this session's live/finished general-purpose agents; `items` are (id, owner, text); `leases` are (id, owner, worker, minutes ahead)."""
    if BASE.exists():
        shutil.rmtree(BASE)
    proj = BASE / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / "agent" / "plans").mkdir(parents=True)
    (BASE / "tmp").mkdir()
    (BASE / "store").mkdir()
    if cap is not None:
        (proj / "agent" / "plans" / "QUEUE.md").write_text(
            "# Plan queue\n\n## Settings\n\n```stop-hook\nwriter_cap: %d\n```\n\n## Promoted\n"
            % cap,
            encoding="utf-8",
        )
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


def payload(
    prompt, kind="general-purpose", session=SID, tool="Agent", isolation=None, desc="probe"
):
    tool_input = {"subagent_type": kind, "description": desc, "prompt": prompt}
    if isolation is not None:
        tool_input["isolation"] = isolation
    return {
        "tool_name": tool,
        "session_id": session,
        "cwd": str(BASE / "proj"),
        "tool_input": tool_input,
    }


GUARD_ARGV = [sys.executable, DISPATCH, "block_plan_concurrency"]
CHAIN_ARGV = [sys.executable, DISPATCH, "--chain", "pre-agent"]


def run_case(proj, doc, argv=None):
    proc = subprocess.run(
        argv or GUARD_ARGV,
        input=json.dumps(doc),
        capture_output=True,
        text=True,
        check=False,
        env=env_for(proj),
    )
    return proc.returncode, proc.stderr


EXCL = "Concurrency: exclusive -- regenerates every golden file\nOwns: docs/e/**\n"
PAR_F = "Concurrency: parallel\nOwns: docs/f/**\n"
PAR_EO = "Concurrency: parallel\nOwns: docs/e/one.md\n"
PAR_A = "Concurrency: parallel\nOwns: a/**\n"
PAR_AB = "Concurrency: parallel\nOwns: a/b.py\n"
PAR_C = "Concurrency: parallel\nOwns: c/**\n"
PAR_AZ = "Concurrency: parallel\nOwns: a/b.py, z/**\n"
PAR_Z = "Concurrency: parallel\nOwns: z/y.py\n"
NO_OWNS = "Concurrency: parallel\n"
NONE = "Concurrency: parallel\nOwns: none -- an operator-action fixture plan\n"
BASIC = {"e": EXCL, "f": PAR_F, "o": PAR_EO}
E_ITEM = ("e0e0e0e0", SID[:8], "regenerate PLAN-e.md [e1e1e1e1]")
P_ITEM = ("a0a0a0a0", PEER, "edit a PLAN-p.md [a1a1a1a1]")

# (name, world kwargs, payload, want_rc, stderr needles)
# (name, world kwargs, spawn payload, expected rc, stderr needles)
CASES: list[tuple[str, dict[str, typing.Any], typing.Any, int, typing.Any]] = [
    (
        "m1 a live exclusive writer refuses a plan whose Owns overlap its own",
        {"plans": BASIC, "writers": ["Plan: PLAN-e.md"]},
        payload("Plan: PLAN-o.md"),
        2,
        ["PLAN-e.md is exclusive", "writer a0000000000000001", "worker:queue"],
    ),
    (
        "m1 the holder is found through its #item",
        {"plans": BASIC, "writers": ["work #e0e0e0e0"], "items": [E_ITEM]},
        payload("Plan: PLAN-o.md"),
        2,
        ["PLAN-e.md is exclusive"],
    ),
    (
        "m1 the spawn is found through its #item",
        {
            "plans": BASIC,
            "writers": ["Plan: PLAN-e.md"],
            "items": [("f0f0f0f0", SID[:8], "docs PLAN-o.md [f1f1f1f1]")],
        },
        payload("do #f0f0f0f0"),
        2,
        ["PLAN-e.md is exclusive"],
    ),
    (
        "m1b a live exclusive writer admits a plan whose Owns are disjoint (operator ruling 2026-10-28)",
        {"plans": BASIC, "writers": ["Plan: PLAN-e.md"]},
        payload("Plan: PLAN-f.md"),
        0,
        [],
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
        2,
        ["declares no valid Owns"],
    ),
    (
        "n1 a live writer on a plan with no file is ** once required",
        {"plans": {"q": PAR_AB}, "writers": ["Plan: PLAN-gone.md"]},
        payload("Plan: PLAN-q.md"),
        2,
        ["PLAN-gone.md is parallel and live"],
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
        "i1 an isolated spawn overlapping a live plan is admitted with a note",
        {"plans": {"p": PAR_A, "q": PAR_AB}, "writers": ["Plan: PLAN-p.md"]},
        payload("Plan: PLAN-q.md", isolation=ISOLATED),
        0,
        ["isolated", "both claim `a/b.py`", "PLAN-p.md"],
    ),
    (
        "i1c another isolation value is no isolation",
        {"plans": {"p": PAR_A, "q": PAR_AB}, "writers": ["Plan: PLAN-p.md"]},
        payload("Plan: PLAN-q.md", isolation="remote"),
        2,
        ["both claim `a/b.py`"],
    ),
    (
        "i1d an isolated spawn overlapping a peer's lease is admitted with a note",
        {
            "plans": {"p": PAR_A, "q": PAR_AB},
            "items": [P_ITEM],
            "leases": [("a0a0a0a0", PEER, "b9b9b9b9", 60)],
        },
        payload("Plan: PLAN-q.md", isolation=ISOLATED),
        0,
        ["both claim `a/b.py`"],
    ),
    (
        "i2 a live exclusive plan refuses an isolated overlap",
        {"plans": BASIC, "writers": ["Plan: PLAN-e.md"]},
        payload("Plan: PLAN-o.md", isolation=ISOLATED),
        2,
        ["PLAN-e.md is exclusive"],
    ),
    (
        "i3 an isolated exclusive plan cannot start while another is live",
        {"plans": BASIC, "writers": ["Plan: PLAN-f.md"]},
        payload("Plan: PLAN-e.md", isolation=ISOLATED),
        2,
        ["cannot start while other plans are live"],
    ),
    (
        "i4 isolation does not excuse a plan with no Owns",
        {"plans": {"h": NO_OWNS, "f": PAR_F}, "writers": ["Plan: PLAN-f.md"]},
        payload("Plan: PLAN-h.md", isolation=ISOLATED),
        2,
        ["declares no valid Owns"],
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


TWO = {"p": PAR_A, "q": PAR_AB}
THREE = {"p": PAR_A, "q": PAR_C, "e": EXCL}
SHAPE_2026_11_04 = [
    (payload("Plan: PLAN-p.md"), 0, []),
    (payload("Plan: PLAN-q.md"), 0, []),
    (payload("Plan: PLAN-e.md"), 2, ["cannot start while other plans are live", "spawn claim"]),
]
PEER_SID = "0fee0fee-1111-2222-3333-444444444444"

# (name, world kwargs, argv, [(spawn payload, expected rc, stderr needles), ...]); no Stop event and no agent meta between the steps.
SEQUENCES: list[tuple[str, dict[str, typing.Any], list[str], list[tuple[dict, int, list[str]]]]] = [
    ("w1 three spawns, the third's plan exclusive", {"plans": THREE}, GUARD_ARGV, SHAPE_2026_11_04),
    (
        "w2 the measured overlap, second spawn refused with its witness",
        {"plans": TWO},
        GUARD_ARGV,
        [
            (payload("Plan: PLAN-p.md"), 0, []),
            (payload("Plan: PLAN-q.md"), 2, ["both claim `a/b.py`", "spawn claim"]),
        ],
    ),
    (
        "w2c disjoint siblings all start",
        {"plans": {"p": PAR_A, "q": PAR_C, "z": PAR_Z}},
        GUARD_ARGV,
        [
            (payload("Plan: PLAN-p.md"), 0, []),
            (payload("Plan: PLAN-q.md"), 0, []),
            (payload("Plan: PLAN-z.md"), 0, []),
        ],
    ),
    (
        "w3 an exclusive sibling holds its files, and only its files",
        {"plans": BASIC},
        GUARD_ARGV,
        [
            (payload("Plan: PLAN-e.md"), 0, []),
            (payload("Plan: PLAN-o.md"), 2, ["PLAN-e.md is exclusive"]),
            (payload("Plan: PLAN-f.md"), 0, []),
        ],
    ),
    (
        "w4 siblings of one plan are not refused against each other",
        {"plans": TWO},
        GUARD_ARGV,
        [(payload("Plan: PLAN-p.md"), 0, []), (payload("Plan: PLAN-p.md"), 0, [])],
    ),
    (
        "w5 isolated siblings overlap with a note",
        {"plans": TWO},
        GUARD_ARGV,
        [
            (payload("Plan: PLAN-p.md", isolation=ISOLATED), 0, []),
            (payload("Plan: PLAN-q.md", isolation=ISOLATED), 0, ["both claim `a/b.py`"]),
        ],
    ),
    (
        "w5b an isolated sibling still meets an exclusive claim",
        {"plans": BASIC},
        GUARD_ARGV,
        [
            (payload("Plan: PLAN-e.md", isolation=ISOLATED), 0, []),
            (payload("Plan: PLAN-o.md", isolation=ISOLATED), 2, ["PLAN-e.md is exclusive"]),
        ],
    ),
    (
        "w5c a plain spawn after an isolated sibling is still refused on the overlap",
        {"plans": TWO},
        GUARD_ARGV,
        [
            (payload("Plan: PLAN-p.md", isolation=ISOLATED), 0, []),
            (payload("Plan: PLAN-q.md"), 2, ["both claim `a/b.py`"]),
        ],
    ),
    (
        "w6 a declared Owns narrows the claim",
        {"plans": TWO},
        GUARD_ARGV,
        [
            (payload("Plan: PLAN-p.md\nOwns: a/other.py"), 0, []),
            (payload("Plan: PLAN-q.md"), 0, []),
        ],
    ),
    (
        "w7 a reader claims nothing",
        {"plans": TWO},
        GUARD_ARGV,
        [(payload("Plan: PLAN-p.md", kind="Explore"), 0, []), (payload("Plan: PLAN-q.md"), 0, [])],
    ),
    (
        "w8 a refused spawn claims nothing",
        {"plans": {"p": PAR_A, "az": PAR_AZ, "z": PAR_Z}},
        GUARD_ARGV,
        [
            (payload("Plan: PLAN-p.md"), 0, []),
            (payload("Plan: PLAN-az.md"), 2, ["both claim `a/b.py`"]),
            (payload("Plan: PLAN-z.md"), 0, []),
        ],
    ),
    (
        "w9 a peer session's claim holds the files",
        {"plans": TWO},
        GUARD_ARGV,
        [
            (payload("Plan: PLAN-p.md"), 0, []),
            (payload("Plan: PLAN-q.md", session=PEER_SID), 2, ["session cafe0000"]),
        ],
    ),
    (
        "w10 a blind estimate still sees a claim",
        {"plans": TWO},
        GUARD_ARGV,
        [
            (payload("Plan: PLAN-p.md", session="zz-no-such-session"), 0, ["ALLOWED unchecked"]),
            (payload("Plan: PLAN-q.md", session="zz-no-such-session"), 2, ["both claim `a/b.py`"]),
        ],
    ),
    (
        "w10b a blind estimate that judged a claim says so, not unchecked",
        {"plans": {"p": PAR_A, "q": PAR_C}},
        GUARD_ARGV,
        [
            (payload("Plan: PLAN-p.md", session="zz-no-such-session"), 0, ["ALLOWED unchecked"]),
            (
                payload("Plan: PLAN-q.md", session="zz-no-such-session"),
                0,
                ["judged against the 1 unexpired sibling claim(s) only"],
            ),
        ],
    ),
    (
        "c1 a cap of 1 refuses the second same-message writer",
        {"plans": {"p": PAR_A, "q": PAR_C}, "cap": 1},
        CHAIN_ARGV,
        [
            (payload("Plan: PLAN-p.md"), 0, []),
            (payload("Plan: PLAN-q.md"), 2, ["writer_cap 1", "1 same-message"]),
        ],
    ),
    (
        "c1b a planless writer counts toward the cap too",
        {"plans": {}, "cap": 1},
        CHAIN_ARGV,
        [
            (payload("fix a typo"), 0, ["declares no `Owns:` line"]),
            (payload("fix a typo"), 2, ["writer_cap 1"]),
        ],
    ),
    (
        "c2 a cap of 2 admits the second and refuses the third",
        {"plans": {"p": PAR_A, "q": PAR_C, "z": PAR_Z}, "cap": 2},
        CHAIN_ARGV,
        [
            (payload("Plan: PLAN-p.md"), 0, []),
            (payload("Plan: PLAN-q.md"), 0, []),
            (payload("Plan: PLAN-z.md"), 2, ["writer_cap 2", "2 same-message"]),
        ],
    ),
    (
        "c3 a reader never reaches the cap",
        {"plans": {"p": PAR_A}, "cap": 1},
        CHAIN_ARGV,
        [
            (payload("Plan: PLAN-p.md"), 0, []),
            (payload("Plan: PLAN-p.md", kind="Explore"), 0, []),
        ],
    ),
    (
        "c4 the cap is per session, as the roster's count is",
        {"plans": {"p": PAR_A, "q": PAR_C}, "cap": 1},
        CHAIN_ARGV,
        [
            (payload("Plan: PLAN-p.md"), 0, []),
            (payload("Plan: PLAN-q.md", session=PEER_SID), 0, []),
        ],
    ),
]


class NoClaimFileError(RuntimeError):
    """No claim file where one must be: a red control, never a skipped one."""


def run_sequence(kw, argv, steps):
    """Every step's (ok, rc, stderr) against one world."""
    proj = world(**kw)
    out = []
    for doc, want, needles in steps:
        rc, err = run_case(proj, doc, argv)
        out.append((rc == want and all(n in err for n in needles), rc, err))
    return out


def claim_file():
    """The one claim file of the fixture; refusing a miss keeps a rewrite below from passing on nothing."""
    hits = sorted((BASE / "tmp" / "claude-worklist").glob("*.spawnclaims"))
    if len(hits) != 1:
        raise NoClaimFileError("expected one claim file, found %r" % hits)
    return hits[0]


def claim_rows():
    return [json.loads(ln) for ln in claim_file().read_text(encoding="utf-8").splitlines()]


def _lock_or_none():
    try:
        return claim_lock().open("a", encoding="utf-8")
    except NoClaimFileError:
        return open(os.devnull, "a", encoding="utf-8")


def claim_lock():
    return claim_file().with_name(claim_file().name + ".lock")


def c_expired():
    """A claim past its expiry holds nothing; rewriting only `until` is the one difference from w2."""
    proj = world(plans=TWO)
    rc1, _ = run_case(proj, payload("Plan: PLAN-p.md"))
    rows = claim_rows()
    for row in rows:
        row["until"] = time.time() - 1
    claim_file().write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    rc2, err = run_case(proj, payload("Plan: PLAN-q.md"))
    return rc1 == 0 and rc2 == 0 and len(rows) == 1 and len(claim_rows()) == 1, (rc1, rc2, err)


def c_started(sibling="the sibling"):
    """A sibling whose meta now exists is the roster's to count: its claim stops holding, and a finished one frees the slot. A sibling spawned with no description is claimed with an empty one and stops holding the same way."""
    proj = world(plans={"p": PAR_A, "q": PAR_AB}, cap=1)
    rc1, _ = run_case(proj, payload("Plan: PLAN-p.md", desc=sibling), CHAIN_ARGV)
    sub = BASE / "claude" / "projects" / munged(proj.resolve()) / SID / "subagents"
    (sub / "agent-a0000000000000099.meta.json").write_text(
        json.dumps({"agentType": "general-purpose", "description": sibling, "spawnDepth": 1}),
        encoding="utf-8",
    )
    done = {
        "type": "assistant",
        "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}]},
    }
    first = {"type": "user", "message": {"content": "Plan: PLAN-p.md"}}
    tx = sub / "agent-a0000000000000099.jsonl"
    tx.write_text(json.dumps(first) + "\n" + json.dumps(done) + "\n", encoding="utf-8")
    old = time.time() - 10
    os.utime(tx, (old, old))
    rc2, err = run_case(proj, payload("Plan: PLAN-q.md", desc="the next one"), CHAIN_ARGV)
    return rc1 == 0 and rc2 == 0, (rc1, rc2, err)


def c_torn():
    """A torn line reads as nothing, and the claim beside it still holds."""
    proj = world(plans=TWO)
    rc1, _ = run_case(proj, payload("Plan: PLAN-p.md"))
    with claim_file().open("a", encoding="utf-8") as fh:
        fh.write('{"until": 99999')
    rc2, err = run_case(proj, payload("Plan: PLAN-q.md"))
    return rc1 == 0 and rc2 == 2 and "both claim" in err, (rc1, rc2, err)


def c_unreadable():
    """A claim path it cannot read fails open loudly, and a live writer is still judged."""
    proj = world(plans=TWO)
    run_case(proj, payload("Plan: PLAN-p.md"))
    path = claim_file()
    path.unlink()
    path.mkdir()
    rc1, err1 = run_case(proj, payload("Plan: PLAN-q.md"))
    needle = "same-message siblings"
    first = rc1 == 0 and needle in err1

    proj = world(plans=TWO, writers=["Plan: PLAN-p.md"])
    run_case(proj, payload("Plan: PLAN-p.md"))
    path = claim_file()
    path.unlink()
    path.mkdir()
    rc2, err2 = run_case(proj, payload("Plan: PLAN-q.md"))
    return first and rc2 == 2 and "both claim" in err2, (rc1, err1, rc2, err2)


def _stdin(proc):
    if proc.stdin is None:
        raise RuntimeError("a Popen without a stdin pipe")
    return proc.stdin


def c_race(rounds=5):
    """Two processes released on one stdin instant, on one mutex: exactly one starts, every round."""
    seen = []
    for _ in range(rounds):
        proj = world(plans=BASIC)
        procs = [
            subprocess.Popen(
                GUARD_ARGV,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                env=env_for(proj),
            )
            for _p in range(2)
        ]
        time.sleep(0.25)
        pipes = [_stdin(proc) for proc in procs]
        for pipe, plan in zip(pipes, ("PLAN-e.md", "PLAN-o.md"), strict=True):
            pipe.write(json.dumps(payload("Plan: %s" % plan)))
        for pipe in pipes:
            pipe.close()
        seen.append(sorted(proc.wait(timeout=60) for proc in procs))
    return all(s == [0, 2] for s in seen), seen


def c_decides_under_lock():
    """The whole decision waits for the lock: while it is held the second spawn has no answer, and once released it is refused."""
    proj = world(plans=TWO)
    run_case(proj, payload("Plan: PLAN-p.md"))
    with claim_lock().open("a", encoding="utf-8") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        proc = subprocess.Popen(
            GUARD_ARGV,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            env=env_for(proj),
        )
        pipe = _stdin(proc)
        pipe.write(json.dumps(payload("Plan: PLAN-q.md")))
        pipe.close()
        time.sleep(1.5)
        waiting = proc.poll() is None
    rc = proc.wait(timeout=60)
    return waiting and rc == 2, (waiting, rc)


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
        # PYTHONPATH is dropped: a caller that puts the stop directory on it (pytest run with PYTHONPATH=.:hooks/stop) makes wl_core importable from the fake tree, the guard takes its normal path, and the case reads silence as a defect it is not testing.
        env={k: v for k, v in env_for(BASE / "proj").items() if k != "PYTHONPATH"},
    )
    return proc.stdout.strip(), proc.stderr.strip()


# The read of the claim file, and the lock budget short enough to test, both planted on an in-process copy.
CLAIM_READ_DEFECT = ("pending = X.unconsumed(claims, metas, session_id)", "pending = []")
LOCK_BUDGET_PLANT = ("LOCK_WAIT_S = 30", "LOCK_WAIT_S = 0.2")


def _outside_defect(src: str, *names: str) -> str:
    """`src` with every top-level `DEFECT` (or named) assignment removed, so a needle search cannot be satisfied by the declaration that names it.

    `old in src` alone stays true after the guarded line is deleted, because the declaration itself contains the text it plants (measured 2026-10-05).
    """
    wanted = names or ("DEFECT",)
    cut = [
        n
        for n in ast.parse(src).body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in wanted for t in n.targets)
    ]
    return "\n".join(
        line
        for i, line in enumerate(src.split("\n"), 1)
        if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut)
    )


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

    for name, kw, argv, steps in SEQUENCES:
        got = run_sequence(kw, argv, steps)
        ok = all(g[0] for g in got)
        fails += not ok
        print("%-72s rcs=%s %s" % (name, [g[1] for g in got], "ok" if ok else "*** FAIL ***"))
        for g in got:
            if not g[0]:
                print("    stderr: %s" % g[2].strip()[:600])

    ok = ('isolation: "%s"' % ISOLATED) in WRITERS_NOW.read_text(encoding="utf-8")
    fails += not ok
    print(
        "%-72s %s"
        % (
            "i0 the isolation value is the one /writers-now names",
            "ok" if ok else "*** FAIL *** %r" % ISOLATED,
        )
    )

    # A disjoint isolated spawn has nothing to note.
    proj = world(plans={"p": PAR_A, "q": PAR_C}, writers=["Plan: PLAN-p.md"])
    rc, err = run_case(proj, payload("Plan: PLAN-q.md", isolation=ISOLATED))
    ok = rc == 0 and "isolated" not in err
    fails += not ok
    print(
        "%-72s %s"
        % (
            "i5 a disjoint isolated spawn says nothing",
            "ok" if ok else "*** FAIL *** %d %r" % (rc, err),
        )
    )

    # w8's control on the file itself, with both directions on the row count.
    proj = world(plans=TWO)
    run_case(proj, payload("Plan: PLAN-p.md"))
    run_case(proj, payload("Plan: PLAN-q.md"))
    try:
        rows = claim_rows()
    except NoClaimFileError as exc:
        rows = [str(exc)]
    ok = (
        len(rows) == 1
        and isinstance(rows[0], dict)
        and rows[0]["plans"] == ["PLAN-p.md"]
        and rows[0]["entered"] <= rows[0]["at"]
    )
    fails += not ok
    print(
        "%-72s %s"
        % ("w8b the file holds the admitted spawn alone", "ok" if ok else "*** FAIL *** %r" % rows)
    )

    for name, control in (
        ("e1 an expired claim counts for nothing", c_expired),
        ("e2 a started sibling's claim stops holding", c_started),
        ("e2b a started sibling with no description stops holding", lambda: c_started("")),
        ("e3 a torn claim line is skipped", c_torn),
        ("e4 an unreadable claim file fails open loudly", c_unreadable),
        ("r1 two processes racing on one mutex leave exactly one admitted", c_race),
        ("r2 the decision sits inside the lock", c_decides_under_lock),
    ):
        try:
            ok, detail = control()
        except NoClaimFileError as exc:
            ok, detail = False, str(exc)
        fails += not ok
        print("%-72s %s" % (name, "ok" if ok else "*** FAIL *** %r" % (detail,)))

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
    hookio = importlib.import_module("rediacc_hooks.hookio")

    good: dict = {"__name__": "good_guard", "__file__": str(GUARD)}
    exec(compile(SOURCE, str(GUARD), "exec"), good)
    old, new = good["DEFECT"]
    if old not in _outside_defect(SOURCE):
        print(
            "*** FAIL *** the declared DEFECT no longer applies to the guard outside its own declaration: %r"
            % old
        )
        fails += 1
    else:
        bad: dict = {"__name__": "broken_guard", "__file__": str(GUARD)}
        exec(compile(SOURCE.replace(old, new), str(GUARD), "exec"), bad)
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

    # ---- the claim read, planted away: the 2026-11-04 shape must stop being refused ----
    def in_process(source, kw, steps):
        proj = world(**kw)
        ns: dict = {"__name__": "guard_copy", "__file__": str(GUARD)}
        exec(compile(source, str(GUARD), "exec"), ns)
        saved = dict(os.environ)
        answers = []
        try:
            os.environ.clear()
            os.environ.update(env_for(proj))
            for step in steps:
                ev = hookio.Event(json.dumps(step), cwd=str(proj))
                rc = ns["run"](ev)
                answers.append((rc, ev.result(rc)[2]))
        finally:
            os.environ.clear()
            os.environ.update(saved)
        return answers

    shape = [s[0] for s in SHAPE_2026_11_04]
    old, new = CLAIM_READ_DEFECT
    if old not in SOURCE:
        print("*** FAIL *** CLAIM_READ_DEFECT no longer applies to the guard: %r" % old)
        fails += 1
    else:
        whole = [a[0] for a in in_process(SOURCE, {"plans": THREE}, shape)]
        blind = [a[0] for a in in_process(SOURCE.replace(old, new), {"plans": THREE}, shape)]
        ok = whole == [0, 0, 2] and blind == [0, 0, 0]
        fails += not ok
        print(
            "%-72s %s"
            % (
                "d1 the claim read removed, w1 stops refusing",
                "ok" if ok else "*** FAIL *** whole=%r blind=%r" % (whole, blind),
            )
        )

    # ---- a lock held past the budget fails open loudly, on a copy with a short budget ----
    old, new = LOCK_BUDGET_PLANT
    if old not in SOURCE:
        print("*** FAIL *** LOCK_BUDGET_PLANT no longer applies to the guard: %r" % old)
        fails += 1
    else:
        proj = world(plans=TWO)
        run_case(proj, payload("Plan: PLAN-p.md"))
        with _lock_or_none() as held:
            fcntl.flock(held, fcntl.LOCK_EX)
            ns: dict = {"__name__": "guard_copy", "__file__": str(GUARD)}
            exec(compile(SOURCE.replace(old, new), str(GUARD), "exec"), ns)
            saved = dict(os.environ)
            try:
                os.environ.clear()
                os.environ.update(env_for(proj))
                ev = hookio.Event(json.dumps(payload("Plan: PLAN-q.md")), cwd=str(proj))
                rc = ns["run"](ev)
                err = ev.result(rc)[2]
            finally:
                os.environ.clear()
                os.environ.update(saved)
        ok = rc == 0 and "same-message siblings" in err
        fails += not ok
        print(
            "%-72s %s"
            % (
                "f2 a lock held past the budget fails open loudly",
                "ok" if ok else "*** FAIL *** %d %r" % (rc, err),
            )
        )

    print()
    if refused in (0, len(CASES)):
        print(
            "*** FAIL *** %d of %d cases refused: the guard answered the same way on every input"
            % (refused, len(CASES))
        )
        fails += 1
    print(
        "block_plan_concurrency: %d case(s), %d sequence(s), %d refused, X fields required, %d failure(s)"
        % (len(CASES), len(SEQUENCES), refused, fails)
    )
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

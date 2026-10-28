#!/usr/bin/env python3
"""Control harness for block_plan_without_depends, the write-time half of agent/plans/PLAN-plan-dependencies.md (section 5b).

BOTH DIRECTIONS. A guard that refused every plan edit passes the refusal cases and one that refused none passes the allow cases, so each refusal has an allow twin differing by one planted fact.

LOAD-BEARING, NOT OPTIONAL. The guard declares `OWN_SUITE = True`, so `test_guards_differential.py` requires this file beside it, and `test_hooks_delegates.py` discovers and runs it.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER against plan trees built on disk in ONE pid-stamped directory removed on exit. The guard finds the tree from the edited file's own path (`<tree>/agent/plans/PLAN-x.md`), so a fixture tree is a real tree to it, cycles and tombstones included.

THE DEFECT IS PROVEN HERE TOO. After the cases, the guard's source is loaded with its declared `DEFECT` planted and run in-process on the same payloads; at least one answer must change, or this suite's green does not depend on the verdict line.

PRE-BACKFILL RATCHET. The expectation of "an Edit to a plan that already lacks the field" follows the guard's `PRE_BACKFILL_RATCHET` constant, read from its source: ALLOWED with a warning while it is True, REFUSED once T10 sets it to False.

THE LIVE-PROOF LINE (agent/plans/PLAN-tested-on-bench.md V3). A new plan whose Owns hit a surface of `.ci/config/proof-tiers.json` is refused without the line; a malformed, emphasised, out-of-window or rulingless line is refused, and so is a `none` citing an open or unknown item or an absent quote, each with an allow twin (a target declared, a closed item, a committed quote, line 12, Owns hitting no surface, only test files, a bare pointer, an untouched existing line). The fixture tree carries a worklist store and a quote file for the waiver; `LIVE_DEFECT` is planted like the other two.

THE X FIELDS AND THE OPERATOR FREEZE (agent/plans/PLAN-plan-priority-concurrency.md section 8, T4). Every fixture plan carries a valid Priority/Concurrency/Owns triple unless a case is about its absence, and the absence cases are always refused: the X fields are mandatory (T11). The freeze cases run against an on-disk `(operator)` plan, and the escape against transcript fixtures whose operator turn (or AskUserQuestion answer) names the plan and the level. BOTH declared defects are planted: `DEFECT` (the freeze) and `VERDICT_DEFECT` (the D1-D7 verdict); each must change at least one answer.
"""

import ast
import atexit
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
GUARD = HERE / "block_plan_without_depends.py"
DISPATCH = str(HERE.parent / "dispatch.py")
ARGV = [sys.executable, DISPATCH, "block_plan_without_depends"]
BASE = pathlib.Path(tempfile.gettempdir()) / ("plandeps-guard-%d" % os.getpid())
atexit.register(shutil.rmtree, BASE, ignore_errors=True)

SOURCE = GUARD.read_text(encoding="utf-8")
RATCHET = bool(re.search(r"^PRE_BACKFILL_RATCHET = True$", SOURCE, re.MULTILINE))
X_OK = "Priority: P2 -- a fixture plan\nConcurrency: parallel\nOwns: docs/fixture/**\n"
# PLAN-tested-on-bench V3: X lines whose Owns hit the renet surface of .ci/config/proof-tiers.json, and the worklist items and quote file a `Live-Proof: none` may cite.
X_RENET = "Priority: P2 -- a fixture plan\nConcurrency: parallel\nOwns: private/renet/cmd/**\n"
CLOSED_ITEM = "c1c1c1c1"
OPEN_ITEM = "0b0b0b0b"
QUOTE = "Yes, bench + hostinger via eu-bench"
QUOTE_FILE = "agent/rulings/fixture.md"
STORE_EVENTS = [
    {
        "ev": "add",
        "id": CLOSED_ITEM,
        "at": "2026-10-01T00:00:00Z",
        "by": "cafe0000",
        "s": "x",
        "o": "cafe0000",
        "t": "(cafe0000) a closed ruling",
    },
    {
        "ev": "add",
        "id": OPEN_ITEM,
        "at": "2026-10-01T00:00:01Z",
        "by": "cafe0000",
        "s": " ",
        "o": "cafe0000",
        "t": "(cafe0000) an open question",
    },
]


def xlp(owns="private/renet/cmd/**", live=None, filler=0):
    """X lines with the given Owns, `filler` neutral header lines, then an optional `Live-Proof:` value."""
    out = "Priority: P2 -- a fixture plan\nConcurrency: parallel\nOwns: %s\n" % owns
    out += "".join("Note-%d: filler\n" % i for i in range(filler))
    if live is not None:
        out += "%s\n" % live
    return out


DEP = "no-dep -- a live-proof fixture plan"
OP = "Priority: P1 (operator) -- ruled by the operator\n"


def plan(status="in-progress", dep=None, body="- [ ] T1 a box\n", x=X_OK):
    text = "# PLAN: x\n\nStatus: %s\nOwner: cafe0000\n" % status
    if dep is not None:
        text += "Depends-On: %s\n" % dep
    return text + (x or "") + "\n## Tasks\n\n" + body


def xop(pri=OP):
    return pri + "Concurrency: parallel\nOwns: docs/op/**\n"


def transcript(name, records):
    path = BASE / name
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return str(path)


def said(text):
    return {"type": "user", "message": {"content": text}}


def asked_and_answered(answer):
    return [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "tu1", "name": "AskUserQuestion", "input": {}}
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "tu1", "content": answer}]
            },
        },
    ]


def with_transcript(payload, name, records):
    """The payload with a transcript fixture; written when the case runs (the tree is rebuilt per case)."""
    return dict(payload, _transcript=(name, records))


INDEX = (
    "## Expired plans\n\n| Plan | Title | First seen | Expired | Full-Text-Blob |\n|---|---|---|---|---|\n"
    "| `agent/plans/_done/PLAN-gone.md` | t | 2026-01-01 | 2026-03-01 | `%s` |\n" % ("a" * 40)
)


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


def tree():
    """A fresh fixture tree: a conforming chain y -> z, a plan lacking the field, a _done and a _removed plan."""
    if BASE.exists():
        shutil.rmtree(BASE)
    files = {
        "agent/plans/PLAN-y.md": plan(dep="PLAN-z.md"),
        "agent/plans/PLAN-z.md": plan(dep="no-dep -- the bottom of the fixture chain"),
        "agent/plans/PLAN-bare.md": plan(),
        "agent/plans/PLAN-op.md": plan(dep="no-dep -- the operator-ranked fixture plan", x=xop()),
        "agent/plans/PLAN-nox.md": plan(dep="no-dep -- a fixture plan without X lines", x=""),
        "agent/plans/PLAN-mal.md": plan(
            dep="no-dep -- a fixture with a malformed X line",
            x="Priority: P0. an operator ruling\nConcurrency: parallel\nOwns: docs/mal/**\n",
        ),
        "agent/plans/_done/PLAN-fin.md": plan(status="done"),
        "agent/plans/_removed/PLAN-rm.md": plan(status="removed"),
        "agent/INDEX.md": INDEX,
        # PLAN-tested-on-bench V3: on-disk plans whose Owns hit a surface, one without the line (pre-V7), one with a broken line, one with a `none` citing an open item.
        "agent/plans/PLAN-surf.md": plan(dep=DEP, x=X_RENET),
        "agent/plans/PLAN-lpbad.md": plan(
            dep=DEP, x=xlp(live="Live-Proof: edge -- the edge rollout check")
        ),
        "agent/plans/PLAN-lpopen.md": plan(
            dep=DEP, x=xlp(live="Live-Proof: none -- ruled in #%s, still open" % OPEN_ITEM)
        ),
        "agent/plans/PLAN-lpok.md": plan(
            dep=DEP, x=xlp(live="Live-Proof: none -- tooling only, ruled in #%s" % CLOSED_ITEM)
        ),
        QUOTE_FILE: "The operator answered: %s.\n" % QUOTE,
        "agent/worklist/cafe0000.jsonl": "".join(json.dumps(e) + "\n" for e in STORE_EVENTS),
    }
    for rel, text in files.items():
        p = BASE / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    # A directory symlink into agent/plans (#bc7d998c): a write through it lands in the plan folder.
    (BASE / "linkedplans").symlink_to(BASE / "agent" / "plans", target_is_directory=True)
    # A link then `..` (review 9c6817f3.1-.4 sweep): the kernel follows the link first. `out/l` points INTO the guarded directory, `esc` points OUT of it.
    (BASE / "agent" / "plans" / "sub").mkdir()
    (BASE / "out").mkdir()
    (BASE / "out" / "l").symlink_to(BASE / "agent" / "plans" / "sub", target_is_directory=True)
    (BASE / "agent" / "plans" / "esc").symlink_to(BASE / "out", target_is_directory=True)
    return BASE


def fp(rel):
    return str(BASE / rel)


def write(rel, content):
    return {"tool_name": "Write", "tool_input": {"file_path": fp(rel), "content": content}}


def relative(rel, content):
    """A Write whose path is RELATIVE to the payload's own cwd, the fixture tree; this process runs somewhere else."""
    if pathlib.Path.cwd().resolve() == BASE.resolve():
        raise RuntimeError("this process runs in the fixture tree; the row would prove nothing")
    return {
        "tool_name": "Write",
        "cwd": str(BASE),
        "tool_input": {"file_path": rel, "content": content},
    }


def edit(rel, old, new, replace_all=False):
    return {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": fp(rel),
            "old_string": old,
            "new_string": new,
            "replace_all": replace_all,
        },
    }


NEW = "agent/plans/PLAN-new.md"

CASES = [
    # ---- refusals ----
    ("a Write without the field", write(NEW, plan()), True),
    # Judged where the write LANDS (#bc7d998c): each refusal was allowed (rc 0) before.
    (
        "a Write without the field through a .. detour",
        write("agent/plans/x/../PLAN-new.md", plan()),
        True,
    ),
    ("a Write without the field through a symlink", write("linkedplans/PLAN-new.md", plan()), True),
    ("a .. detour out of the plan folder", write("agent/plans/../PLAN-new.md", plan()), False),
    # A link then `..` is judged where the kernel writes, and a NUL path writes nothing (review 9c6817f3.5: it raised, rc 1).
    ("a link into the plan folder, then ..", write("out/l/../PLAN-new.md", plan()), True),
    (
        "a link out of the plan folder, then ..",
        write("agent/plans/esc/../PLAN-new.md", plan()),
        False,
    ),
    (
        "a NUL in a plan-shaped path is judged by its text",
        write("agent/plans/PLAN-n\x00.md", plan()),
        True,
    ),
    ("a NUL in a path that is no plan", write("docs/n\x00.md", plan()), False),
    # Review 3c0094e0.2: a RELATIVE NUL path is read against the payload's cwd, not this process's. The dependency exists only in the fixture tree, so the plan conforms there and dangles anywhere else.
    (
        "a relative NUL plan path, its dependency missing in the payload cwd",
        relative("agent/plans/PLAN-n\x00.md", plan(dep="PLAN-nowhere.md")),
        True,
    ),
    (
        "a relative NUL plan path, its tree read from the payload cwd",
        relative("agent/plans/PLAN-n\x00.md", plan(dep="PLAN-z.md")),
        False,
    ),
    ("a malformed value", write(NEW, plan(dep="agent/plans/PLAN-y.md")), True),
    ("a dangling token", write(NEW, plan(dep="PLAN-nowhere.md")), True),
    ("a _removed target", write(NEW, plan(dep="PLAN-rm.md")), True),
    ("a self-dependency", write(NEW, plan(dep="PLAN-new.md")), True),
    (
        "a cycle against an on-disk plan",
        edit("agent/plans/PLAN-z.md", "no-dep -- the bottom of the fixture chain", "PLAN-y.md"),
        True,
    ),
    (
        "an Edit deleting the line",
        edit("agent/plans/PLAN-y.md", "Depends-On: PLAN-z.md\n", ""),
        True,
    ),
    (
        "a MultiEdit whose second edit breaks the value",
        {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": fp("agent/plans/PLAN-y.md"),
                "edits": [
                    {"old_string": "T1 a box", "new_string": "T1 the box"},
                    {"old_string": "PLAN-z.md", "new_string": "PLAN-nowhere.md"},
                ],
            },
        },
        True,
    ),
    (
        "an Edit adding a NEW finding to a plan lacking the field",
        edit("agent/plans/PLAN-bare.md", "Owner:", "Depends-On: no-dep -- n/a\nOwner:"),
        True,
    ),
    (
        "an Edit to a plan that lacks it",
        edit("agent/plans/PLAN-bare.md", "T1 a box", "T1 the box"),
        not RATCHET,
    ),
    # ---- allows ----
    ("a valid list", write(NEW, plan(dep="PLAN-y.md, PLAN-fin.md")), False),
    ("a tombstoned _done target", write(NEW, plan(dep="PLAN-gone.md")), False),
    ("a task edge", write(NEW, plan(dep="PLAN-y.md#T1")), False),
    ("no-dep with a reason", write(NEW, plan(dep="no-dep -- stands alone in the fixture")), False),
    (
        "a stub",
        write(NEW, "# s\n\nStatus: moved\nMoved-To: agent/plans/_done/PLAN-new.md\n"),
        False,
    ),
    ("a finished record", write(NEW, plan(status="compacted")), False),
    ("a _done/ path", write("agent/plans/_done/PLAN-new.md", plan()), False),
    ("a .claude/plans file", write(".claude/plans/x.md", plan()), False),
    ("a non-plan doc", write("docs/x.md", plan()), False),
    (
        "a prose Edit to a conforming plan",
        edit("agent/plans/PLAN-y.md", "T1 a box", "T1 the box"),
        False,
    ),
    (
        "an Edit that adds the missing field",
        edit("agent/plans/PLAN-bare.md", "Owner:", "Depends-On: PLAN-y.md\nOwner:"),
        False,
    ),
    (
        "an Edit whose old_string is absent (the tool fails)",
        edit("agent/plans/PLAN-y.md", "not in the file", "x"),
        False,
    ),
    (
        "an Edit to a missing plan (the tool fails)",
        edit("agent/plans/PLAN-missing.md", "a", "b"),
        False,
    ),
    ("an empty payload", {}, False),
    # ---- the Live-Proof line (PLAN-tested-on-bench V3) ----
    ("a new surface plan without Live-Proof", write(NEW, plan(dep=DEP, x=X_RENET)), True),
    (
        "a new cli-remote plan without Live-Proof",
        write(NEW, plan(dep=DEP, x=xlp(owns="packages/cli/src/remote/ssh.ts"))),
        True,
    ),
    (
        "a new account plan (braced glob) without Live-Proof",
        write(NEW, plan(dep=DEP, x=xlp(owns="private/account/{src,web}/**"))),
        True,
    ),
    (
        "a new plan with a malformed Live-Proof (edge)",
        write(NEW, plan(dep=DEP, x=xlp(live="Live-Proof: edge -- the edge rollout check"))),
        True,
    ),
    (
        "a new plan with a reasonless Live-Proof",
        write(NEW, plan(dep=DEP, x=xlp(live="Live-Proof: bench"))),
        True,
    ),
    (
        "a new plan with an emphasised Live-Proof",
        write(
            NEW, plan(dep=DEP, x=xlp(live="**Live-Proof:** hostinger -- the renet binary check"))
        ),
        True,
    ),
    (
        "a new plan with Live-Proof outside the window",
        write(
            NEW,
            plan(dep=DEP, x=xlp(filler=4, live="Live-Proof: hostinger -- the renet binary check")),
        ),
        True,
    ),
    (
        "a new plan with a rulingless none",
        write(NEW, plan(dep=DEP, x=xlp(live="Live-Proof: none -- a write-up only, no code ships"))),
        True,
    ),
    (
        "a new plan with a none citing an open item",
        write(NEW, plan(dep=DEP, x=xlp(live="Live-Proof: none -- ruled in #%s" % OPEN_ITEM))),
        True,
    ),
    (
        "a new plan with a none citing an unknown item",
        write(NEW, plan(dep=DEP, x=xlp(live="Live-Proof: none -- ruled in #deadbeef"))),
        True,
    ),
    (
        "a new plan with a none quoting what nobody said",
        write(
            NEW,
            plan(
                dep=DEP,
                x=xlp(live='Live-Proof: none -- "nobody ever said this" in %s' % QUOTE_FILE),
            ),
        ),
        True,
    ),
    (
        "a new no-surface plan with a malformed Live-Proof",
        write(
            NEW,
            plan(dep=DEP, x=xlp(owns="docs/fixture/**", live="Live-Proof: stable -- the release")),
        ),
        True,
    ),
    (
        "an Edit introducing a malformed Live-Proof",
        edit(
            "agent/plans/PLAN-surf.md",
            "Owns: private/renet/cmd/**\n",
            "Owns: private/renet/cmd/**\nLive-Proof: bench, edge -- the two rollouts\n",
        ),
        True,
    ),
    (
        "an Edit pointing a valid none at an open item",
        edit("agent/plans/PLAN-lpok.md", "#%s" % CLOSED_ITEM, "#%s" % OPEN_ITEM),
        True,
    ),
    (
        "a new renet plan declaring only bench (not admissible for renet)",
        write(
            NEW, plan(dep=DEP, x=xlp(live="Live-Proof: bench -- the cli against bench.rediacc.com"))
        ),
        True,
    ),
    (
        "a new account plan declaring bench",
        write(
            NEW,
            plan(
                dep=DEP,
                x=xlp(
                    owns="private/account/src/**",
                    live="Live-Proof: bench -- the account worker on bench",
                ),
            ),
        ),
        False,
    ),
    (
        "a new account plan declaring only hostinger (not admissible for account)",
        write(
            NEW,
            plan(
                dep=DEP,
                x=xlp(
                    owns="private/account/src/**",
                    live="Live-Proof: hostinger -- the account worker there",
                ),
            ),
        ),
        True,
    ),
    (
        "a new renet plan declaring bench and hostinger (bench admissible for no touched surface)",
        write(
            NEW,
            plan(dep=DEP, x=xlp(live="Live-Proof: bench, hostinger -- the cli and renet halves")),
        ),
        True,
    ),
    (
        "a new surface plan declaring hostinger",
        write(
            NEW, plan(dep=DEP, x=xlp(live="Live-Proof: hostinger -- the renet binary served there"))
        ),
        False,
    ),
    (
        "a new surface plan declaring both targets",
        write(
            NEW,
            plan(
                dep=DEP,
                x=xlp(
                    owns="private/renet/cmd/**, private/account/src/**",
                    live="Live-Proof: bench, hostinger -- the account and renet halves",
                ),
            ),
        ),
        False,
    ),
    (
        "a new plan with a none citing a closed item",
        write(NEW, plan(dep=DEP, x=xlp(live="Live-Proof: none -- ruled in #%s" % CLOSED_ITEM))),
        False,
    ),
    (
        "a new plan with a none quoting a committed ruling",
        write(
            NEW,
            plan(
                dep=DEP,
                x=xlp(live='Live-Proof: none -- operator: "%s" in %s' % (QUOTE, QUOTE_FILE)),
            ),
        ),
        False,
    ),
    (
        "Live-Proof at line 12 is inside the window",
        write(
            NEW,
            plan(dep=DEP, x=xlp(filler=3, live="Live-Proof: hostinger -- the renet binary check")),
        ),
        False,
    ),
    (
        "a new plan whose Owns hit no surface needs no line",
        write(NEW, plan(dep=DEP, x=xlp(owns="docs/fixture/**, .ci/rediacc_ci/proof/**"))),
        False,
    ),
    (
        "a new plan owning only surface test files needs no line",
        write(NEW, plan(dep=DEP, x=xlp(owns="packages/cli/src/**/*.test.ts"))),
        False,
    ),
    (
        "a new plan owning only a bare submodule pointer needs no line",
        write(NEW, plan(dep=DEP, x=xlp(owns="private/renet"))),
        False,
    ),
    (
        "a new plan owning a submodule directory (trailing slash) needs the line",
        write(NEW, plan(dep=DEP, x=xlp(owns="private/renet/"))),
        True,
    ),
    (
        "a prose Edit to an existing surface plan without the line (V7 migrates it)",
        edit("agent/plans/PLAN-surf.md", "T1 a box", "T1 the box"),
        False,
    ),
    (
        "a prose Edit keeping a broken Live-Proof line it had",
        edit("agent/plans/PLAN-lpbad.md", "T1 a box", "T1 the box"),
        False,
    ),
    (
        "a prose Edit keeping a none whose item is open",
        edit("agent/plans/PLAN-lpopen.md", "T1 a box", "T1 the box"),
        False,
    ),
    (
        "an Edit closing the gap with a valid line",
        edit("agent/plans/PLAN-lpbad.md", "edge -- the edge", "hostinger -- the hostinger"),
        False,
    ),
    # ---- the X fields ----
    ("a new plan without X lines", write(NEW, plan(dep="PLAN-y.md", x="")), True),
    (
        "a prose Edit to a plan without X lines",
        edit("agent/plans/PLAN-nox.md", "T1 a box", "T1 the box"),
        True,
    ),
    ("a malformed Priority", write(NEW, plan(dep="PLAN-y.md", x="Priority: P7\n")), True),
    (
        "exclusive without a reason",
        write(NEW, plan(dep="PLAN-y.md", x="Concurrency: exclusive\n")),
        True,
    ),
    (
        "an escaping Owns glob",
        write(NEW, plan(dep="PLAN-y.md", x=X_OK.replace("docs/fixture/**", "../x"))),
        True,
    ),
    (
        "a parallel plan claiming **",
        write(NEW, plan(dep="PLAN-y.md", x=X_OK.replace("docs/fixture/**", "**"))),
        True,
    ),
    (
        "Owns none with a reason",
        write(
            NEW,
            plan(
                dep="PLAN-y.md",
                x="Priority: P3\nConcurrency: parallel\nOwns: none -- an operator-action plan\n",
            ),
        ),
        False,
    ),
    (
        "a prose Edit keeping a malformed X line it had",
        edit("agent/plans/PLAN-mal.md", "T1 a box", "T1 the box"),
        True,
    ),
    (
        "an Edit adding a NEW malformed X line",
        edit("agent/plans/PLAN-mal.md", "Concurrency: parallel", "Concurrency: sometimes"),
        True,
    ),
    (
        "an AI re-rank P2 to P1",
        edit("agent/plans/PLAN-y.md", "Priority: P2", "Priority: P1"),
        False,
    ),
    # ---- the operator freeze ----
    (
        "an Edit changing an operator level",
        edit("agent/plans/PLAN-op.md", "P1 (operator)", "P0 (operator)"),
        True,
    ),
    (
        "an Edit dropping the operator marker",
        edit("agent/plans/PLAN-op.md", "P1 (operator)", "P1"),
        True,
    ),
    (
        "an Edit changing the operator reason",
        edit("agent/plans/PLAN-op.md", "ruled by the operator", "ruled by the AI"),
        True,
    ),
    (
        "a Write omitting the operator line",
        write(
            "agent/plans/PLAN-op.md",
            plan(dep="no-dep -- the operator-ranked fixture plan", x=xop(pri="")),
        ),
        True,
    ),
    (
        "the AI introducing (operator) with no operator turn",
        edit(
            "agent/plans/PLAN-y.md",
            "Priority: P2 -- a fixture plan",
            "Priority: P2 (operator) -- a fixture plan",
        ),
        True,
    ),
    (
        "a prose Edit to the operator plan",
        edit("agent/plans/PLAN-op.md", "T1 a box", "T1 the box"),
        False,
    ),
    (
        "an Owns Edit to the operator plan",
        edit("agent/plans/PLAN-op.md", "docs/op/**", "docs/op2/**"),
        False,
    ),
    (
        "a whitespace-only reason change",
        edit("agent/plans/PLAN-op.md", "ruled by the operator", "ruled by  the operator"),
        False,
    ),
    (
        "an operator-directed change",
        with_transcript(
            edit("agent/plans/PLAN-op.md", "P1 (operator)", "P0 (operator)"),
            "t1.jsonl",
            [said("make PLAN-op.md P0 now")],
        ),
        False,
    ),
    (
        "an operator-directed change by slug",
        with_transcript(
            edit("agent/plans/PLAN-op.md", "P1 (operator)", "P3 (operator)"),
            "t2.jsonl",
            [said("op should be P3")],
        ),
        False,
    ),
    (
        "an AskUserQuestion answer naming plan and level",
        with_transcript(
            edit("agent/plans/PLAN-op.md", "P1 (operator)", "P0 (operator)"),
            "t3.jsonl",
            [said("rank them"), *asked_and_answered("PLAN-op.md: P0")],
        ),
        False,
    ),
    (
        "an operator turn naming another level",
        with_transcript(
            edit("agent/plans/PLAN-op.md", "P1 (operator)", "P0 (operator)"),
            "t4.jsonl",
            [said("make PLAN-op.md P2")],
        ),
        True,
    ),
    (
        "an operator turn naming no plan",
        with_transcript(
            edit("agent/plans/PLAN-op.md", "P1 (operator)", "P0 (operator)"),
            "t5.jsonl",
            [said("make it P0")],
        ),
        True,
    ),
    (
        "an older operator turn does not count",
        with_transcript(
            edit("agent/plans/PLAN-op.md", "P1 (operator)", "P0 (operator)"),
            "t6.jsonl",
            [said("make PLAN-op.md P0"), said("thanks, carry on")],
        ),
        True,
    ),
    (
        "an operator-directed change that drops the marker",
        with_transcript(
            edit("agent/plans/PLAN-op.md", "P1 (operator)", "P0"),
            "t7.jsonl",
            [said("make PLAN-op.md P0")],
        ),
        True,
    ),
    (
        "an operator turn marks a new value",
        with_transcript(
            edit(
                "agent/plans/PLAN-y.md",
                "Priority: P2 -- a fixture plan",
                "Priority: P1 (operator) -- a fixture plan",
            ),
            "t8.jsonl",
            [said("PLAN-y.md is P1, mark it")],
        ),
        False,
    ),
]


def materialize(payload):
    """Write a case's transcript fixture into the fresh tree and point the payload at it."""
    if "_transcript" not in payload:
        return payload
    name, records = payload["_transcript"]
    out = {k: v for k, v in payload.items() if k != "_transcript"}
    out["transcript_path"] = transcript(name, records)
    return out


def run_case(payload):
    proc = subprocess.run(
        ARGV, input=json.dumps(materialize(payload)), capture_output=True, text=True, check=False
    )
    return proc.returncode, proc.stderr


def main():
    fails = 0
    blocked = 0
    for name, payload, want in CASES:
        tree()
        rc, err = run_case(payload)
        got = rc == 2
        if rc not in (0, 2):
            print("    unexpected rc %d: %s" % (rc, err.strip().splitlines()[-3:]))
        blocked += got
        ok = got == want and rc in (0, 2)
        fails += not ok
        print(
            "%-62s want=%-8s got=%-8s %s"
            % (
                name,
                "BLOCKED" if want else "allowed",
                "BLOCKED" if got else "allowed",
                "ok" if ok else "*** FAIL ***",
            )
        )
        if not ok and err:
            print("    stderr: %s" % err.strip().splitlines()[:4])

    # The refusal names its codes and the draft verb; the ratchet allow says why it allowed.
    tree()
    _rc, err = run_case(write(NEW, plan(dep="PLAN-nowhere.md")))
    for needle in (
        "D3",
        "Depends-On: no-dep -- <reason",
        "check_plan_deps.py --draft agent/plans/PLAN-new.md",
    ):
        if needle not in err:
            print("*** FAIL *** the refusal message lacks %r" % needle)
            fails += 1
    # The Live-Proof refusal names its code, the surfaces it found and the accepted shapes.
    tree()
    _rc, err = run_case(write(NEW, plan(dep=DEP, x=X_RENET)))
    for needle in ("LP1", "surfaces: renet", "Live-Proof: bench|hostinger"):
        if needle not in err:
            print("*** FAIL *** the Live-Proof refusal lacks %r" % needle)
            fails += 1
    tree()
    _rc, err = run_case(
        write(NEW, plan(dep=DEP, x=xlp(live="Live-Proof: none -- ruled in #%s" % OPEN_ITEM)))
    )
    if "LP2" not in err or "Live-Proof: none" not in err:
        print("*** FAIL *** the waiver refusal does not name LP2 and the field: %r" % err[-300:])
        fails += 1

    if RATCHET:
        tree()
        _rc, err = run_case(edit("agent/plans/PLAN-bare.md", "T1 a box", "T1 the box"))
        if "allowed only until the backfill" not in err:
            print("*** FAIL *** the ratchet allow did not say so on stderr")
            fails += 1

    # ---- both declared defects, planted and run in-process on the same payloads ----
    _spec = importlib.util.spec_from_file_location(
        "rediacc_hooks", HERE.parent / "__init__.py", submodule_search_locations=[str(HERE.parent)]
    )
    if _spec is None or _spec.loader is None:
        raise SystemExit("cannot load the rediacc_hooks package from %s" % HERE.parent)
    _pkg = importlib.util.module_from_spec(_spec)
    sys.modules["rediacc_hooks"] = _pkg
    _spec.loader.exec_module(_pkg)
    hookio = importlib.import_module("rediacc_hooks.hookio")

    _good_ns: dict = {"__name__": "good_guard", "__file__": str(GUARD)}
    exec(compile(SOURCE, str(GUARD), "exec"), _good_ns)
    for label in ("DEFECT", "VERDICT_DEFECT", "LIVE_DEFECT"):
        old, new = _good_ns[label]
        if old not in _outside_defect(SOURCE, "DEFECT", "VERDICT_DEFECT", "LIVE_DEFECT"):
            print(
                "*** FAIL *** the declared %s no longer applies to the guard outside its declaration: %r"
                % (label, old)
            )
            fails += 1
            continue
        _bad_ns: dict = {"__name__": "broken_guard", "__file__": str(GUARD)}
        exec(compile(SOURCE.replace(old, new), str(GUARD), "exec"), _bad_ns)
        changed = 0
        for _name, payload, _want in CASES:
            tree()
            real = materialize(payload)
            answers = []
            for ns in (_good_ns, _bad_ns):
                ev = hookio.Event(json.dumps(real), cwd=str(BASE), env=dict(os.environ))
                answers.append(ns["run"](ev))
            changed += answers[0] != answers[1]
        print("%s planted: %d of %d answer(s) changed" % (label, changed, len(CASES)))
        if changed == 0:
            print(
                "*** FAIL *** the planted %s changed no answer, so this suite does not depend on it"
                % label
            )
            fails += 1

    print()
    if blocked == 0 or blocked == len(CASES):
        print(
            "*** FAIL *** %d of %d cases blocked: the guard answered the same way on every input"
            % (blocked, len(CASES)),
            file=sys.stderr,
        )
        fails += 1
    print(
        "%d case(s), %d blocked, %d allowed (ratchet %s, X fields required)"
        % (
            len(CASES),
            blocked,
            len(CASES) - blocked,
            "on" if RATCHET else "off",
        )
    )
    print("FAILURES: %d" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

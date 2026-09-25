#!/usr/bin/env python3
"""Control harness for block_plan_without_depends, the write-time half of agent/plans/PLAN-plan-dependencies.md (section 5b).

BOTH DIRECTIONS. A guard that refused every plan edit passes the refusal cases and one that refused none passes the allow cases, so each refusal has an allow twin differing by one planted fact.

LOAD-BEARING, NOT OPTIONAL. The guard declares `OWN_SUITE = True`, so `test_guards_differential.py` requires this file beside it, and `test_hooks_delegates.py` discovers and runs it.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER against plan trees built on disk in ONE pid-stamped directory removed on exit. The guard finds the tree from the edited file's own path (`<tree>/agent/plans/PLAN-x.md`), so a fixture tree is a real tree to it, cycles and tombstones included.

THE DEFECT IS PROVEN HERE TOO. After the cases, the guard's source is loaded with its declared `DEFECT` planted and run in-process on the same payloads; at least one answer must change, or this suite's green does not depend on the verdict line.

PRE-BACKFILL RATCHET. The expectation of "an Edit to a plan that already lacks the field" follows the guard's `PRE_BACKFILL_RATCHET` constant, read from its source: ALLOWED with a warning while it is True, REFUSED once T10 sets it to False.
"""

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


def plan(status="in-progress", dep=None, body="- [ ] T1 a box\n"):
    text = "# PLAN: x\n\nStatus: %s\nOwner: cafe0000\n" % status
    if dep is not None:
        text += "Depends-On: %s\n" % dep
    return text + "\n## Tasks\n\n" + body


INDEX = (
    "## Expired plans\n\n| Plan | Title | First seen | Expired | Full-Text-Blob |\n|---|---|---|---|---|\n"
    "| `agent/plans/_done/PLAN-gone.md` | t | 2026-01-01 | 2026-03-01 | `%s` |\n" % ("a" * 40)
)


def tree():
    """A fresh fixture tree: a conforming chain y -> z, a plan lacking the field, a _done and a _removed plan."""
    if BASE.exists():
        shutil.rmtree(BASE)
    files = {
        "agent/plans/PLAN-y.md": plan(dep="PLAN-z.md"),
        "agent/plans/PLAN-z.md": plan(dep="no-dep -- the bottom of the fixture chain"),
        "agent/plans/PLAN-bare.md": plan(),
        "agent/plans/_done/PLAN-fin.md": plan(status="done"),
        "agent/plans/_removed/PLAN-rm.md": plan(status="removed"),
        "agent/INDEX.md": INDEX,
    }
    for rel, text in files.items():
        p = BASE / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return BASE


def fp(rel):
    return str(BASE / rel)


def write(rel, content):
    return {"tool_name": "Write", "tool_input": {"file_path": fp(rel), "content": content}}


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
]


def run_case(payload):
    proc = subprocess.run(
        ARGV, input=json.dumps(payload), capture_output=True, text=True, check=False
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
    if RATCHET:
        tree()
        _rc, err = run_case(edit("agent/plans/PLAN-bare.md", "T1 a box", "T1 the box"))
        if "allowed only until the backfill" not in err:
            print("*** FAIL *** the ratchet allow did not say so on stderr")
            fails += 1

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

    _good_ns: dict = {"__name__": "good_guard", "__file__": str(GUARD)}
    exec(compile(SOURCE, str(GUARD), "exec"), _good_ns)  # noqa: S102
    old, new = _good_ns["DEFECT"]
    if old not in SOURCE:
        print("*** FAIL *** the declared DEFECT no longer applies to the guard: %r" % old)
        fails += 1
    else:
        _bad_ns: dict = {"__name__": "broken_guard", "__file__": str(GUARD)}
        exec(compile(SOURCE.replace(old, new), str(GUARD), "exec"), _bad_ns)  # noqa: S102
        changed = 0
        for _name, payload, _want in CASES:
            tree()
            answers = []
            for ns in (_good_ns, _bad_ns):
                ev = hookio.Event(json.dumps(payload), cwd=str(BASE), env=dict(os.environ))
                answers.append(ns["run"](ev))
            changed += answers[0] != answers[1]
        print("DEFECT planted: %d of %d answer(s) changed" % (changed, len(CASES)))
        if changed == 0:
            print(
                "*** FAIL *** the planted DEFECT changed no answer, so this suite does not depend on the verdict"
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
        "%d case(s), %d blocked, %d allowed (ratchet %s)"
        % (len(CASES), blocked, len(CASES) - blocked, "on" if RATCHET else "off")
    )
    print("FAILURES: %d" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

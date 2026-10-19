#!/usr/bin/env python3
"""Control harness for block_plan_box_rewrite, the commit-time half of `check:ci-plan-boxes` (G-A1) and of `check:ci-plan-record`'s QUEUE checks.

BOTH DIRECTIONS. A guard that refused every plan commit passes the refusal cases and one that refused none passes the allow cases, so each refusal has an allow twin differing by one planted fact: the evidence appended to the box versus indented below it, a `_done/` copy that rewrites a box versus one that only flips brackets, a sliced QUEUE.md versus an edited one.

LOAD-BEARING, NOT OPTIONAL. The guard declares `OWN_SUITE = True`, so `test_guards_differential.py` requires this file beside it, and `test_hooks_delegates.py` discovers and runs it.

IT DRIVES THE LIVE GUARD THROUGH THE DISPATCHER against a real git checkout built per case in ONE pid-stamped directory removed on exit: HEAD holds the plans as committed, the working tree (or the index) holds what the commit would write, and `CLAUDE_PROJECT_DIR` names the checkout. The incident's two shapes are reproduced line for line: `- [ ] T16 Retarget writers:` ticked as `- [x] T16 Retarget writers: (done ...)` across a `check_plan_folders.py --move`, and QUEUE.md spliced from `## Promoted` to the FIRST `## Generated`, which sits in prose above it.

THE DEFECT IS PROVEN HERE TOO. After the cases, the guard's source is loaded with its declared `DEFECT` planted and run in-process on the same worlds; at least one answer must change, and every refusal case must turn into an allow, or this suite's green does not depend on the verdict line.
"""

import ast
import atexit
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
GUARD = HERE / "block_plan_box_rewrite.py"
DISPATCH = str(HERE.parent / "dispatch.py")
ARGV = [sys.executable, DISPATCH, "block_plan_box_rewrite"]
BASE = pathlib.Path(tempfile.gettempdir()) / ("planbox-guard-%d" % os.getpid())
atexit.register(shutil.rmtree, BASE, ignore_errors=True)
SOURCE = GUARD.read_text(encoding="utf-8")

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)
for _k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
    GIT_ENV.pop(_k, None)


def plan(slug, boxes, status="in-progress", extra=""):
    return (
        "# PLAN: %s\n\nStatus: %s\nOwner: cafe0000\nDepends-On: no-dep -- a fixture\n%s\n"
        "## Tasks\n\n%s" % (slug, status, extra, "".join("- [ ] %s\n" % b for b in boxes))
    )


def stub(slug, folder="_done"):
    return (
        "# PLAN: %s (moved)\nStatus: moved\nMoved-To: agent/plans/%s/PLAN-%s.md\n\n"
        "This plan moved.\n" % (slug, folder, slug)
    )


T16 = "T16 Retarget writers:"
EVID = " (done 2026-10-08: c2ca68dfe with private/account 65b2332)"
TICK_LINE = "    (ticked) 2026-10-08 by d778be9d: c2ca68dfe with private/account 65b2332\n"
# Long enough that the evidence falls past the 120 normalised characters `sig` reads, so the gate does not see it either.
LONG = (
    "T3 Retarget `scripts/dev/bws-rotate.py` to write the token file atomically at mode 0600, "
    "and update the rotation notice sections five and six to name that file"
)
A = "agent/plans/PLAN-a.md"
B = "agent/plans/PLAN-b.md"
DONE_A = "agent/plans/_done/PLAN-a.md"
Q = "agent/plans/QUEUE.md"

QUEUE = (
    "# Plan queue\n\nThe list below `## Generated` is rendered; the Promoted list is by hand.\n\n"
    "## Settings\n\n```stop-hook\nturbo: off\n```\n\n"
    "## In flight\n\n<!-- queue:inflight:begin -->\n- Mode: x\n<!-- queue:inflight:end -->\n\n"
    "## Promoted\n\n1. agent/plans/PLAN-a.md\n\n"
    "## Generated\n\n<!-- queue:generated:begin -->\n1. agent/plans/PLAN-b.md\n"
    "<!-- queue:generated:end -->\n"
)


def sliced(text):
    """The incident's splice, as the guard's own fixture spells it."""
    start = text.index("\n## Promoted") + 1
    end = text.index("## Generated")
    if end >= start:
        raise SystemExit("the fixture lost the prose `## Generated` the incident needs")
    return text[:start] + "## Promoted\n\n1. agent/plans/PLAN-b.md\n\n" + text[end:]


PLAN_A = plan("a", [T16, "T17 Delete the env files"])
PLAN_B = plan("b", ["T1 Something else entirely"])
HEAD = {A: PLAN_A, B: PLAN_B, Q: QUEUE, "docs/x.md": "seed\n"}


def commit(*paths):
    return "git commit -F m -- " + " ".join(paths)


def world(head=None, work=None, staged=None):
    """(head files, working-tree changes, index changes); None as a value deletes."""
    return {"head": head or HEAD, "work": work or {}, "staged": staged or {}}


def build(spec):
    if BASE.exists():
        shutil.rmtree(BASE)
    BASE.mkdir(parents=True)

    def git(*args):
        subprocess.run(["git", *args], cwd=str(BASE), check=True, capture_output=True, env=GIT_ENV)

    def put(rel, text):
        p = BASE / rel
        if text is None:
            if p.exists():
                p.unlink()
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    git("init", "-q", "--initial-branch=1008-1")
    # No detached maintenance after a commit: it holds .git/objects/maintenance.lock past `commit`'s return, and the next build()'s rmtree raced it on CI run 39177571049 (FileNotFoundError: 'maintenance.lock'); the same switch test_wl_scratch.py documents.
    git("config", "maintenance.auto", "false")
    git("config", "gc.auto", "0")
    for rel, text in spec["head"].items():
        put(rel, text)
    git("add", "-A")
    git("commit", "-q", "-m", "seed")
    for rel, text in spec["staged"].items():
        put(rel, text)
        git("add", "-A", "--", rel)
    for rel, text in spec["work"].items():
        put(rel, text)
    return BASE


def payload(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


REWRITTEN_A = PLAN_A.replace("- [ ] " + T16, "- [x] " + T16 + EVID)
TICKED_A = PLAN_A.replace("- [ ] %s\n" % T16, "- [x] %s\n%s" % (T16, TICK_LINE))

CASES = [
    # ---- the incident, plan arm ----
    ("a tick that appends evidence to the box", world(work={A: REWRITTEN_A}), commit(A), True),
    (
        "the correct tick: bracket flip, evidence indented",
        world(work={A: TICKED_A}),
        commit(A),
        False,
    ),
    (
        "the incident: --move, then the _done copy rewrites the box",
        world(work={A: stub("a"), DONE_A: REWRITTEN_A}),
        commit(A, DONE_A),
        True,
    ),
    (
        "a move into _done with only bracket flips",
        world(work={A: stub("a"), DONE_A: PLAN_A.replace("[ ]", "[x]")}),
        commit(A, DONE_A),
        False,
    ),
    (
        "a move into _done with the indented (ticked) form",
        world(work={A: stub("a"), DONE_A: TICKED_A}),
        commit(A, DONE_A),
        False,
    ),
    (
        "the _done copy alone, rewritten, is judged against HEAD's old path",
        world(work={A: stub("a"), DONE_A: REWRITTEN_A}),
        commit(DONE_A),
        True,
    ),
    (
        "a stub committed without its untracked target",
        world(work={A: stub("a"), DONE_A: PLAN_A}),
        commit(A),
        True,
    ),
    (
        "a move into _removed with brackets flipped",
        world(
            work={
                A: stub("a", "_removed"),
                "agent/plans/_removed/PLAN-a.md": PLAN_A.replace("[ ]", "[x]"),
            }
        ),
        commit(A, "agent/plans/_removed/PLAN-a.md"),
        False,
    ),
    # ---- the other ways a box disappears ----
    (
        "a deleted box line",
        world(work={A: PLAN_A.replace("- [ ] %s\n" % T16, "")}),
        commit(A),
        True,
    ),
    (
        "an un-checkboxed line",
        world(work={A: PLAN_A.replace("- [ ] " + T16, T16)}),
        commit(A),
        True,
    ),
    ("a plan deleted wholesale", world(work={A: None}), commit(A), True),
    (
        "a box fenced into a code sample",
        world(work={A: PLAN_A.replace("- [ ] " + T16, "```\n- [ ] " + T16 + "\n```")}),
        commit(A),
        True,
    ),
    # ---- what G-A1 itself lets through ----
    (
        "a blocked box marked [?]",
        world(work={A: PLAN_A.replace("[ ] T16", "[?] T16")}),
        commit(A),
        False,
    ),
    (
        "a box moved unchanged into a plan in the same commit",
        world(
            work={
                A: PLAN_A.replace("- [ ] %s\n" % T16, ""),
                B: PLAN_B + "- [ ] %s\n" % T16,
            }
        ),
        commit(A, B),
        False,
    ),
    (
        "a box that also lives, unchanged, in a plan the commit leaves at HEAD",
        world(
            head=dict(HEAD, **{B: PLAN_B + "- [ ] %s\n" % T16}),
            work={A: PLAN_A.replace("- [ ] %s\n" % T16, "")},
        ),
        commit(A),
        False,
    ),
    (
        "a citation re-spelled by a file move (loose_sig)",
        world(
            head=dict(HEAD, **{A: plan("a", ["T5 Port scripts/check-x.ts to the gate"])}),
            work={A: plan("a", ["T5 Port scripts/gates/check-x.ts to the gate"])},
        ),
        commit(A),
        False,
    ),
    (
        "evidence appended past the 120 characters the signature reads",
        world(
            head=dict(HEAD, **{A: plan("a", [LONG])}),
            work={A: plan("a", [LONG]).replace("- [ ] " + LONG, "- [x] " + LONG + EVID)},
        ),
        commit(A),
        False,
    ),
    (
        "a finished plan closed under a Ruling at HEAD",
        world(
            head=dict(
                HEAD,
                **{A: plan("a", [T16], status="done", extra="Ruling: #deadbeef closed it\n")},
            ),
            work={A: plan("a", [], status="done", extra="Ruling: #deadbeef closed it\n")},
        ),
        commit(A),
        False,
    ),
    ("a new box added", world(work={A: PLAN_A + "- [ ] T18 A brand new task\n"}), commit(A), False),
    (
        "a prose edit",
        world(work={A: PLAN_A.replace("## Tasks", "## Tasks\n\nProse.")}),
        commit(A),
        False,
    ),
    # ---- the index, when the commit names no path ----
    (
        "an amend commits the index: a staged rewrite",
        world(staged={A: REWRITTEN_A}),
        "git commit --amend --no-edit",
        True,
    ),
    (
        "an amend whose index holds the correct tick (the tree is not read)",
        world(staged={A: TICKED_A}, work={A: REWRITTEN_A}),
        "git commit --amend --no-edit",
        False,
    ),
    (
        "a directory pathspec reaches the plan",
        world(work={A: REWRITTEN_A}),
        commit("agent/plans/"),
        True,
    ),
    # ---- the incident, QUEUE arm ----
    ("the incident: QUEUE.md spliced end < start", world(work={Q: sliced(QUEUE)}), commit(Q), True),
    (
        "a QUEUE.md Promoted edit",
        world(work={Q: QUEUE.replace("1. agent/plans/PLAN-a.md", "1. agent/plans/PLAN-b.md")}),
        commit(Q),
        False,
    ),
    (
        "a second stop-hook fence outside Settings",
        world(work={Q: QUEUE + "\n```stop-hook\nturbo: on\n```\n"}),
        commit(Q),
        True,
    ),
    (
        "a bad settings value",
        world(work={Q: QUEUE.replace("turbo: off", "turbo: onn")}),
        commit(Q),
        True,
    ),
    (
        "a duplicate heading inside a code fence is not a heading",
        world(work={Q: QUEUE + "\n```\n## Settings\n```\n"}),
        commit(Q),
        False,
    ),
    (
        "a duplicate already at HEAD does not block an unrelated edit",
        world(
            head=dict(HEAD, **{Q: QUEUE + "\n## Promoted\n"}),
            work={Q: QUEUE + "\n## Promoted\n\nA line.\n"},
        ),
        commit(Q),
        False,
    ),
    # ---- not this guard's business ----
    (
        "a commit touching no plan",
        world(work={A: REWRITTEN_A, "docs/x.md": "y\n"}),
        commit("docs/x.md"),
        False,
    ),
    ("a git log of a plan", world(work={A: REWRITTEN_A}), "git log -- " + A, False),
    ("prose naming a plan commit", world(work={A: REWRITTEN_A}), "echo '%s'" % commit(A), False),
    ("an empty command", world(), "", False),
]


def run_case(cmd, root):
    proc = subprocess.run(
        ARGV,
        input=json.dumps(payload(cmd)),
        capture_output=True,
        text=True,
        check=False,
        env=dict(GIT_ENV, CLAUDE_PROJECT_DIR=str(root)),
    )
    return proc.returncode, proc.stderr


def _outside_defect(src):
    """`src` with the top-level `DEFECT` assignment removed, so the needle search cannot be satisfied by the declaration itself."""
    cut = [
        n
        for n in ast.parse(src).body
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "DEFECT" for t in n.targets)
    ]
    return "\n".join(
        line
        for i, line in enumerate(src.split("\n"), 1)
        if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut)
    )


def main():
    fails = 0
    blocked = 0
    for name, spec, cmd, want in CASES:
        root = build(spec)
        rc, err = run_case(cmd, root)
        got = rc == 2
        if rc not in (0, 2):
            print("    unexpected rc %d: %s" % (rc, err.strip().splitlines()[-3:]))
        if "UNEXAMINED" in err:
            print("    the guard failed open: %s" % err.strip()[:300])
            fails += 1
        blocked += got
        ok = got == want and rc in (0, 2)
        fails += not ok
        print(
            "%-72s want=%-8s got=%-8s %s"
            % (
                name,
                "BLOCKED" if want else "allowed",
                "BLOCKED" if got else "allowed",
                "ok" if ok else "*** FAIL ***",
            )
        )
        if not ok and err:
            print("    stderr: %s" % err.strip().splitlines()[:6])

    # The refusal quotes HEAD's line and the line it became, and writes the remedy out.
    root = build(world(work={A: stub("a"), DONE_A: REWRITTEN_A}))
    _rc, err = run_case(commit(A, DONE_A), root)
    for needle in (
        "at HEAD: - [ ] T16 Retarget writers:",
        "now:     - [x] T16 Retarget writers: (done 2026-10-08",
        "(ticked) <YYYY-MM-DD> by <session>: <evidence>",
        "`- [?]`",
        "into a live plan",
        "agent/plans/PLAN-a.md",
    ):
        if needle not in err:
            print("*** FAIL *** the plan refusal lacks %r" % needle)
            fails += 1
    root = build(world(work={Q: sliced(QUEUE)}))
    _rc, err = run_case(commit(Q), root)
    for needle in (
        "the heading `## Settings` appears 2 times",
        "the heading `## In flight` appears 2 times",
        "RQ-SETTINGS: agent/plans/QUEUE.md: a `stop-hook` fence outside `## Settings`",
    ):
        if needle not in err:
            print("*** FAIL *** the QUEUE refusal lacks %r" % needle)
            fails += 1

    # ---- the declared defect, planted and run in-process on the same worlds ----
    spec_ = importlib.util.spec_from_file_location(
        "rediacc_hooks", HERE.parent / "__init__.py", submodule_search_locations=[str(HERE.parent)]
    )
    if spec_ is None or spec_.loader is None:
        raise SystemExit("cannot load the rediacc_hooks package from %s" % HERE.parent)
    pkg = importlib.util.module_from_spec(spec_)
    sys.modules["rediacc_hooks"] = pkg
    spec_.loader.exec_module(pkg)
    hookio = importlib.import_module("rediacc_hooks.hookio")

    good: dict = {"__name__": "good_guard", "__file__": str(GUARD)}
    exec(compile(SOURCE, str(GUARD), "exec"), good)
    # 2eaeda7b.1: a git error while reading the corpus must raise (the outer handler warns UNEXAMINED and allows), never read as an empty corpus.
    root = build(world())
    env_ = dict(GIT_ENV, CLAUDE_PROJECT_DIR=str(root))
    saved_env = dict(os.environ)
    os.environ.clear()
    os.environ.update(env_)
    real_run = subprocess.run
    try:
        control = good["_head_corpus"](str(root), set())
        if not control:
            print("*** FAIL *** CONTROL: _head_corpus read no plan from a healthy checkout")
            fails += 1
        for label, failure in (
            ("rc 1", lambda a_, _k: subprocess.CompletedProcess(a_, 1, b"", b"fatal")),
            ("OSError", None),
            ("timeout", "timeout"),
        ):

            def flaky(argv, *a_, _f=failure, **k_):
                if list(argv[:2]) != ["git", "cat-file"]:
                    return real_run(argv, *a_, **k_)
                if _f is None:
                    raise OSError("no git")
                if _f == "timeout":
                    raise subprocess.TimeoutExpired(argv, 30)
                return _f(argv, k_)

            # mock.patch.object, not setattr: typed, self-restoring, and no inline suppression needed.
            try:
                with mock.patch.object(subprocess, "run", flaky):
                    got_ = good["_head_corpus"](str(root), set())
            except RuntimeError:
                print("%-72s ok" % ("_head_corpus raises RuntimeError on a git error (%s)" % label))
            else:
                print("*** FAIL *** _head_corpus returned %r on a git error (%s)" % (got_, label))
                fails += 1
    finally:
        os.environ.clear()
        os.environ.update(saved_env)

    old, new = good["DEFECT"]
    if old not in _outside_defect(SOURCE):
        print(
            "*** FAIL *** the declared DEFECT no longer applies outside its declaration: %r" % old
        )
        fails += 1
    else:
        bad: dict = {"__name__": "broken_guard", "__file__": str(GUARD)}
        exec(compile(SOURCE.replace(old, new), str(GUARD), "exec"), bad)
        changed = 0
        refusals = 0
        saved = dict(os.environ)
        try:
            for _name, spec, cmd, want in CASES:
                root = build(spec)
                env = dict(GIT_ENV, CLAUDE_PROJECT_DIR=str(root))
                os.environ.clear()
                os.environ.update(env)
                answers = []
                for ns in (good, bad):
                    ev = hookio.Event(json.dumps(payload(cmd)), cwd=str(root), env=env)
                    answers.append(ns["run"](ev))
                changed += answers[0] != answers[1]
                refusals += bool(want)
                if want and answers[1] != hookio.ALLOW:
                    print("*** FAIL *** with the DEFECT planted %r still refused" % _name)
                    fails += 1
        finally:
            os.environ.clear()
            os.environ.update(saved)
        print("DEFECT planted: %d of %d answer(s) changed" % (changed, len(CASES)))
        if changed != refusals:
            print(
                "*** FAIL *** the planted DEFECT changed %d answer(s), expected every one of the "
                "%d refusals" % (changed, refusals)
            )
            fails += 1

    print()
    if blocked in (0, len(CASES)):
        print(
            "*** FAIL *** %d of %d cases blocked: the guard answered the same way on every input"
            % (blocked, len(CASES)),
            file=sys.stderr,
        )
        fails += 1
    print("%d case(s), %d blocked, %d allowed" % (len(CASES), blocked, len(CASES) - blocked))
    print("FAILURES: %d" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

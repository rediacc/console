#!/usr/bin/env python3
"""Controls for the landing tree's shared store (agent/plans/PLAN-two-track-merge-dev.md, box LT14).

    python3 .claude/hooks/stop/test-landing-store.py

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py.

A fixture repository holds a committed copy of these hooks, a development branch in its main checkout and a linked sibling tree, `console-landing`, on the landing branch. The landing record (`rediacc-landing.json` in the common git dir, the file commit_policy.write_landing_record writes) binds the sibling. With the record, a session rooted in the sibling resolves the main checkout's worklist path, store and STATE.md, its transcripts read live from the sibling's own project directory, and a phase it writes is what pr_freeze reads for the main checkout. Without the record every answer is the sibling's own, exactly as before the box. Two mutants (wl_core.project_root and worklist.py's twin each without the landing redirect) turn the mapping controls red.
"""

import ast
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

_REAL = pathlib.Path(__file__).resolve()
_CI = _REAL.parents[3] / ".ci" / "rediacc_ci"
SOURCE = _REAL.parents[2]
ME = "cafe0000"
SID = ME + "-0000-4000-8000-000000000000"
LANDING_BRANCH = "1120-1"
DEV_BRANCH = "1120-2"
CONTROL_FLOOR = 40


def _by_file(name):
    spec = importlib.util.spec_from_file_location(name, _CI / ("%s.py" % name))
    if spec is None or spec.loader is None:
        raise SystemExit("%s: .ci/rediacc_ci/%s.py is missing" % (__file__, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


controls = _by_file("controls")
runtmp = _by_file("runtmp")
T = controls.Controls("landing_store", floor=CONTROL_FLOOR)
check = T.check


def child_env(tmp, **extra):
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CLAUDE_", "WORKLIST_", "GIT_")) and k != "TMPDIR"
    }
    env.update(
        TMPDIR=str(tmp / "t"),
        HOME=str(tmp / "home"),
        WORKLIST_SESSION_ID=SID,
        PYTHONDONTWRITEBYTECODE="1",
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.invalid",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.invalid",
    )
    env.update({k: str(v) for k, v in extra.items()})
    return env


def git(tmp, cwd, *args):
    done = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *map(str, args)],
        cwd=cwd,
        env=child_env(tmp),
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise SystemExit("fixture: git %s: %s" % (" ".join(map(str, args)), done.stderr))
    return done.stdout.strip()


def build(tmp):
    """The main checkout on the development branch, and the landing sibling on the landing branch."""
    main = tmp / "console"
    main.mkdir()
    git(tmp, main, "init", "-q", "-b", "main")
    junk = shutil.ignore_patterns("__pycache__", "tests", "*.pyc")
    shutil.copytree(SOURCE / "hooks", main / ".claude" / "hooks", ignore=junk)
    shutil.copytree(SOURCE / "rediacc_hooks", main / ".claude" / "rediacc_hooks", ignore=junk)
    shutil.copytree(_CI, main / ".ci" / "rediacc_ci", ignore=junk)
    shutil.copytree(_CI.parent / "config", main / ".ci" / "config", ignore=junk)
    store = main / "agent" / "worklist"
    store.mkdir(parents=True)
    (store / "seed.jsonl").write_text("", encoding="utf-8")
    (main / ".gitignore").write_text("__pycache__/\n.claude/worktrees/\n", encoding="utf-8")
    git(tmp, main, "add", "-A")
    git(tmp, main, "commit", "-q", "-m", "fixture")
    git(tmp, main, "branch", LANDING_BRANCH)
    git(tmp, main, "checkout", "-q", "-b", DEV_BRANCH)
    landing = tmp / "console-landing"
    git(tmp, main, "worktree", "add", "-q", landing, LANDING_BRANCH)
    other = tmp / "console-other"
    git(tmp, main, "worktree", "add", "-q", "--detach", other, "HEAD")
    return main, landing, other


def record_path(main):
    return main / ".git" / "rediacc-landing.json"


def bind(main, landing):
    record_path(main).write_text(
        json.dumps({"path": os.path.realpath(landing), "branch": LANDING_BRANCH}) + "\n",
        encoding="utf-8",
    )


def unbind(main):
    record_path(main).unlink(missing_ok=True)


def pyrun(tmp, program, *args, **extra):
    done = subprocess.run(
        [sys.executable, "-c", program, *map(str, args)],
        cwd=tmp,
        env=child_env(tmp, **extra),
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, done.stdout.strip(), done.stderr.strip()


def worklist(tmp, tree, script_tree, *args, **extra):
    return subprocess.run(
        [sys.executable, str(script_tree / ".claude/hooks/stop/worklist.py"), *args],
        cwd=tree,
        env=child_env(tmp, **extra),
        capture_output=True,
        text=True,
        check=False,
    )


PATHS = """
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_core as C
import wl_store as S
start = C.project_start()
root = C.project_root(start)
print(json.dumps({
    "root": str(root),
    "checkout": str(C.checkout_root(start)),
    "worklist": str(C.worklist_for(start)),
    "store": str(S.store_dir()),
    "state": str(S.agent_state_path(root, sys.argv[2])),
    "journal": str(S.journal_dir()),
}))
"""


def paths(tmp, stop, project_dir):
    rc, out, err = pyrun(tmp, PATHS, stop, ME, CLAUDE_PROJECT_DIR=project_dir)
    if rc != 0:
        return {"error": err[-400:]}
    return json.loads(out)


TRANSCRIPTS = """
import json, sys, importlib.util
sys.path.insert(0, sys.argv[1])
import wl_core as C
import wl_liveness as L
root = C.project_root(C.project_start())
spec = importlib.util.spec_from_file_location("worklist_cli", sys.argv[1] + "/worklist.py")
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)
meta = L._teammate_meta(str(root), sys.argv[2], "w1")
print(json.dumps({
    "dirs": [str(d) for d in C.projects_dirs(root)],
    "dir": C.projects_dir(root),
    "fresh": L.live_teammate_transcripts(str(root), session_id=sys.argv[2]),
    "meta_id": meta[1],
    "lead": W._lead_transcript(sys.argv[2][:8]),
}))
"""


def transcripts(tmp, stop, project_dir):
    rc, out, err = pyrun(tmp, TRANSCRIPTS, stop, SID, CLAUDE_PROJECT_DIR=project_dir)
    if rc != 0:
        return {"error": err[-600:]}
    return json.loads(out)


FREEZE = """
import json, sys, importlib.util
spec = importlib.util.spec_from_file_location("pr_freeze", sys.argv[1])
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
ph = F.active_phase(sys.argv[2], sys.argv[3])
print(json.dumps(ph and {"mode": ph.get("mode"), "branch": ph.get("branch")}))
"""


def freeze_phase(tmp, main, root, branch):
    rc, out, err = pyrun(tmp, FREEZE, main / ".claude/rediacc_hooks/pr_freeze.py", root, branch)
    return json.loads(out) if rc == 0 else {"error": err[-400:]}


def munged(path):
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(path))


def plant_transcripts(tmp, main, landing):
    """A landing session's transcript and one fresh teammate under the SIBLING's project directory; the main checkout's directory exists and is empty."""
    base = tmp / "home" / ".claude" / "projects"
    (base / munged(main)).mkdir(parents=True, exist_ok=True)
    proj = base / munged(landing)
    sub = proj / SID / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    (proj / (SID + ".jsonl")).write_text('{"type":"user"}\n', encoding="utf-8")
    (sub / "agent-abc123.meta.json").write_text(
        json.dumps({"taskKind": "in_process_teammate", "name": "w1", "agentType": "x"}),
        encoding="utf-8",
    )
    (sub / "agent-abc123.jsonl").write_text('{"type":"assistant"}\n', encoding="utf-8")
    now = time.time()
    os.utime(sub / "agent-abc123.jsonl", (now, now))
    return base / munged(main), proj


FOLLOWUPS = """
import json, os, sys
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[2])
import wl_core as C
import wl_store as S
import wl_report as RPT
import wl_roster as R
import wl_claimcheck as CC
from rediacc_ci.dev import worktree_lease as WL
start = C.project_start()
root = C.project_root(start)
dirs = C.projects_dirs(root)
CC.census(str(root), {"k": 1})
rows = [json.loads(x) for x in open(CC.census_path(str(root)))]
print(json.dumps({
    "subagents": str(R.session_subagents_dir(str(root), sys.argv[3])),
    "spawned_nothing": WL._spawned_nothing(root, "beef0000"),
    "age_list": S.owner_age_hours("beef0000", dirs) is not None,
    "age_str_main": S.owner_age_hours("beef0000", dirs[0]),
    "own_tree": str(S.own_tree(root)),
    "store_branch": S._branch_of(root),
    "report_branch": RPT._branch_of(start),
    "census_br": rows[-1].get("br"),
}))
"""


def followups(tmp, stop, project_dir):
    rc, out, err = pyrun(
        tmp, FOLLOWUPS, stop, project_dir / ".ci", SID, CLAUDE_PROJECT_DIR=project_dir
    )
    return json.loads(out) if rc == 0 else {"error": err[-600:]}


def mutant(tmp, main, name, old, new):
    """A copy of the fixture's stop directory with one file planted."""
    dest = tmp / ("mutant-" + name.replace(".", "-"))
    shutil.copytree(main / ".claude/hooks/stop", dest / ".claude/hooks/stop")
    target = dest / ".claude/hooks/stop" / name
    target.write_text(
        controls.plant(target.read_text(encoding="utf-8"), old, new, 1), encoding="utf-8"
    )
    return dest


TWINS = {
    "_common_main": "_local_common_main",
    "landing_record": "_local_landing_record",
    "landing_main": "_local_landing_main",
}


def _body(tree, name):
    """A function's source without its docstring."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return "\n".join(ast.unparse(s) for s in node.body[1:])
    return None


def _string(node):
    """The value of a string literal or a `+` of string literals, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _string(node.left), _string(node.right)
        return left + right if left is not None and right is not None else None
    return None


def _constants(path):
    """The module-level LANDING_RECORD_NAME and CORE_TREE_KEY of one resolver file."""
    found = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        target = (
            node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else None
        )
        if isinstance(target, ast.Name) and target.id in ("LANDING_RECORD_NAME", "CORE_TREE_KEY"):
            found[target.id] = _string(node.value)
    return found


def control_twins():
    """worklist.py's self-contained twins match wl_core line for line, once the twin prefix is folded, and both name the same record file and config key."""
    stop = SOURCE / "hooks/stop"
    core = ast.parse((stop / "wl_core.py").read_text(encoding="utf-8"))
    text = (stop / "worklist.py").read_text(encoding="utf-8")
    for theirs, mine in (*TWINS.items(), ("_git_dirs", "_local_git_dirs")):
        text = text.replace(mine + "(", theirs + "(").replace(
            "def " + theirs + "(", "def " + mine + "("
        )
    twin = ast.parse(text)
    for name, local in TWINS.items():
        got = _body(twin, local)
        check(
            "worklist.py's twin of %s is in lockstep" % name,
            got is not None and got == _body(core, name),
            True,
        )
    values = {"core": _constants(stop / "wl_core.py"), "cli": _constants(stop / "worklist.py")}
    check(
        "both resolvers read the same record file and config key",
        values["core"] == values["cli"] and len(values["core"]) == 2,
        True,
    )


def run():
    control_twins()
    tmp = pathlib.Path(runtmp.run_dir("landing-store-")).resolve()
    for sub in ("t", "home"):
        (tmp / sub).mkdir()
    main, landing, other = build(tmp)
    stop = main / ".claude/hooks/stop"
    store = str(main / "agent" / "worklist")

    # ---- no record: today's answers, every one
    unbind(main)
    p_main = paths(tmp, stop, main)
    p_land = paths(tmp, stop, landing)
    check("no record: main resolves itself", p_main.get("root"), str(main))
    check("no record: the sibling keeps its own root", p_land.get("root"), str(landing))
    check(
        "no record: the sibling keeps its own store",
        p_land.get("store"),
        str(landing / "agent/worklist"),
    )
    check(
        "no record: the sibling's worklist path differs",
        p_land.get("worklist") != p_main.get("worklist"),
        True,
    )
    path_main = worklist(tmp, main, main, "--path", CLAUDE_PROJECT_DIR=main).stdout.strip()
    path_land = worklist(tmp, landing, landing, "--path", CLAUDE_PROJECT_DIR=landing).stdout.strip()
    check(
        "no record: --path of the sibling's copy is its own",
        path_land != path_main and bool(path_land),
        True,
    )
    check("no record: --path agrees with worklist_for", path_land, p_land.get("worklist"))

    main_proj, land_proj = plant_transcripts(tmp, main, landing)
    t0 = transcripts(tmp, stop, main)
    check("no record: projects_dirs is the main directory alone", t0.get("dirs"), [str(main_proj)])
    check("no record: projects_dir is the main directory", t0.get("dir"), str(main_proj))
    check("no record: a teammate under the sibling is not seen", t0.get("fresh"), None)

    done = worklist(tmp, main, main, "--phase", ME, "merge", "--pr", "7", CLAUDE_PROJECT_DIR=main)
    check("no record: --phase from main defaults to main's HEAD", DEV_BRANCH in done.stdout, True)
    worklist(tmp, main, main, "--phase", ME, "build", CLAUDE_PROJECT_DIR=main)

    # ---- the record binds the sibling
    bind(main, landing)
    p_main = paths(tmp, stop, main)
    p_land = paths(tmp, stop, landing)
    p_land_own = paths(tmp, landing / ".claude/hooks/stop", landing)
    p_other = paths(tmp, stop, other)
    check("record: the sibling resolves the main checkout", p_land.get("root"), str(main))
    check("record: the sibling's own hook copy agrees", p_land_own.get("root"), str(main))
    check(
        "record: checkout_root of the sibling stays the sibling",
        p_land.get("checkout"),
        str(landing),
    )
    check("record: the sibling writes the main checkout's store", p_land.get("store"), store)
    check(
        "record: one worklist path for both trees", p_land.get("worklist"), p_main.get("worklist")
    )
    check("record: STATE.md is the main checkout's", p_land.get("state"), p_main.get("state"))
    check(
        "record: the journal is the main checkout's", p_land.get("journal"), p_main.get("journal")
    )
    check("record: main is unchanged", p_main.get("root"), str(main))
    check("record: an unbound linked tree keeps its own root", p_other.get("root"), str(other))
    deep = paths(tmp, stop, landing / ".claude" / "hooks")
    check("record: a directory inside the sibling resolves main", deep.get("root"), str(main))
    path_land = worklist(tmp, landing, landing, "--path", CLAUDE_PROJECT_DIR=landing).stdout.strip()
    check(
        "record: --path of the sibling's copy names main's worklist",
        path_land,
        p_main.get("worklist"),
    )

    for project_dir in (main, landing):
        t1 = transcripts(tmp, stop, project_dir)
        tag = "record (%s): " % pathlib.Path(project_dir).name
        check(
            tag + "projects_dirs names both directories",
            t1.get("dirs"),
            [str(main_proj), str(land_proj)],
        )
        check(tag + "projects_dir stays the main directory", t1.get("dir"), str(main_proj))
        check(tag + "a teammate under the sibling reads live", t1.get("fresh"), 1)
        check(tag + "a named teammate under the sibling is found", t1.get("meta_id"), "abc123")
        check(
            tag + "the lead transcript is the sibling's",
            t1.get("lead"),
            str(land_proj / (SID + ".jsonl")),
        )

    # A phase written from the sibling, with no --branch: the sibling's own HEAD.
    done = worklist(
        tmp, landing, landing, "--phase", ME, "babysit", "--pr", "7", CLAUDE_PROJECT_DIR=landing
    )
    check(
        "record: --phase from the sibling names its own branch", LANDING_BRANCH in done.stdout, True
    )
    check(
        "record: pr_freeze for the main checkout sees the sibling's phase",
        freeze_phase(tmp, main, main, LANDING_BRANCH),
        {"mode": "babysit", "branch": LANDING_BRANCH},
    )
    worklist(tmp, landing, landing, "--phase", ME, "build", CLAUDE_PROJECT_DIR=landing)
    check(
        "record: build ends the phase for pr_freeze",
        freeze_phase(tmp, main, main, LANDING_BRANCH),
        None,
    )
    # From the development tree the default is the record's branch, not main's HEAD.
    done = worklist(tmp, main, main, "--phase", ME, "merge", "--pr", "7", CLAUDE_PROJECT_DIR=main)
    check(
        "record: --phase from main defaults to the landing branch",
        LANDING_BRANCH in done.stdout and DEV_BRANCH not in done.stdout,
        True,
    )
    worklist(tmp, main, main, "--phase", ME, "build", CLAUDE_PROJECT_DIR=main)

    # ---- follow-ups: each store-root read of a landing session
    beef = land_proj / "beef0000-0000-4000-8000-000000000000.jsonl"
    beef.write_text("{}\n", encoding="utf-8")
    f0 = followups(tmp, stop, landing)
    check(
        "record: the subagents directory is the sibling's",
        f0.get("subagents"),
        str(land_proj / SID / "subagents"),
    )
    check(
        "record: a transcript under the sibling with no agents spawned nothing",
        f0.get("spawned_nothing"),
        True,
    )
    check(
        "record: owner_age_hours reads the sibling's directory from a list",
        f0.get("age_list"),
        True,
    )
    check(
        "record: owner_age_hours on the main directory alone finds nothing",
        f0.get("age_str_main"),
        None,
    )
    check("record: own_tree of the store root is the sibling", f0.get("own_tree"), str(landing))
    check(
        "record: appended events carry the sibling's branch", f0.get("store_branch"), LANDING_BRANCH
    )
    check("record: the report branch is the sibling's", f0.get("report_branch"), LANDING_BRANCH)
    check("record: a census row carries the sibling's branch", f0.get("census_br"), LANDING_BRANCH)
    f1 = followups(tmp, stop, main)
    check("record: main reads its own branch", f1.get("store_branch"), DEV_BRANCH)
    check("record: main's own_tree is main", f1.get("own_tree"), str(main))
    worklist(
        tmp, landing, landing, "--phase", ME, "babysit", "--pr", "7", CLAUDE_PROJECT_DIR=landing
    )
    check(
        "record: pr_freeze judged from the sibling sees the phase",
        freeze_phase(tmp, main, landing, LANDING_BRANCH),
        {"mode": "babysit", "branch": LANDING_BRANCH},
    )
    worklist(tmp, landing, landing, "--phase", ME, "build", CLAUDE_PROJECT_DIR=landing)
    unbind(main)
    f2 = followups(tmp, stop, landing)
    check("no record: the sibling's own_tree is its root", f2.get("own_tree"), str(landing))
    check("no record: the sibling reads its own branch", f2.get("store_branch"), LANDING_BRANCH)
    check(
        "no record: the sibling's subagents directory is its own",
        f2.get("subagents"),
        str(land_proj / SID / "subagents"),
    )
    bind(main, landing)

    # A defective record binds nothing.
    record_path(main).write_text('{"path": "%s"}\n' % os.path.realpath(landing), encoding="utf-8")
    check(
        "defective record: the sibling keeps its own root",
        paths(tmp, stop, landing).get("root"),
        str(landing),
    )
    bind(main, landing)

    # ---- mutants: the mapping controls must turn red without the redirect
    mut = mutant(tmp, main, "wl_core.py", "return landing_main(tree) or tree", "return tree")
    m_paths = paths(tmp, mut / ".claude/hooks/stop", landing)
    check("mutant wl_core: the sibling's root is no longer main", m_paths.get("root"), str(landing))
    check("mutant wl_core: the store control would fail", m_paths.get("store") != store, True)
    mut = mutant(
        tmp, main, "worklist.py", "            root = _local_landing_main(root) or root\n", ""
    )
    m_path = worklist(tmp, landing, mut, "--path", CLAUDE_PROJECT_DIR=landing).stdout.strip()
    check(
        "mutant worklist.py: --path no longer names main's worklist",
        m_path != p_main.get("worklist") and bool(m_path),
        True,
    )

    runtmp.remove_tree(str(tmp))
    T.exit()


if __name__ == "__main__":
    run()

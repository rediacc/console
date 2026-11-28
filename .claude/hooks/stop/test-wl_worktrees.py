#!/usr/bin/env python3
"""Controls for lease trees and the Stop hook (agent/plans/PLAN-worktree-lease.md).

    python3 .claude/hooks/stop/test-wl_worktrees.py [root|stop]

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py. No argument runs every section.

`root` is W1: a lease tree's own copy of these hooks writes to the main checkout's store, and nothing else moves with it. Every control drives a fixture's hook copy in a child process, so WL_WORKTREES_TEST_CLAUDE=<dir> judges another `.claude` tree, the way the fail-before figures were read.

`stop` is W11: the Stop hook follows leases. `wl_worktrees.survey` is driven in a child process over fixture repositories, then the real hook over one fixture through wlfix.
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

_REAL = pathlib.Path(__file__).resolve()
_CI = _REAL.parents[3] / ".ci" / "rediacc_ci"
SOURCE = pathlib.Path(os.environ.get("WL_WORKTREES_TEST_CLAUDE") or _REAL.parents[2])
ME = "cafe0000"
SID = ME + "-0000-4000-8000-000000000000"
PEER = "babe0000-0000-4000-8000-000000000000"
CONTROL_FLOOR = 40
STOP_FLOOR = 50


def _by_file(name):
    """A `.ci/rediacc_ci` module loaded by file, as test-plandeps.py does."""
    spec = importlib.util.spec_from_file_location(name, _CI / ("%s.py" % name))
    if spec is None or spec.loader is None:
        raise SystemExit("%s: .ci/rediacc_ci/%s.py is missing" % (__file__, name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


controls = _by_file("controls")
runtmp = _by_file("runtmp")
T = controls.Controls("wl_worktrees", floor=CONTROL_FLOOR)
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
    env.update(extra)
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


def build_main(tmp):
    """A repo with a committed copy of the hooks, so a tree cut from it holds its own copy of each."""
    main = tmp / "console"
    main.mkdir()
    git(tmp, main, "init", "-q", "-b", "main")
    junk = shutil.ignore_patterns("__pycache__", "tests", "*.pyc")
    shutil.copytree(SOURCE / "hooks", main / ".claude" / "hooks", ignore=junk)
    shutil.copytree(SOURCE / "rediacc_hooks", main / ".claude" / "rediacc_hooks", ignore=junk)
    # Worklist writes and the guards' imports read these from the tree they run in.
    shutil.copytree(_CI, main / ".ci" / "rediacc_ci", ignore=junk)
    shutil.copytree(_CI.parent / "config", main / ".ci" / "config", ignore=junk)
    store = main / "agent" / "worklist"
    store.mkdir(parents=True)
    (store / "seed.jsonl").write_text("", encoding="utf-8")
    (main / ".gitignore").write_text(
        "__pycache__/\n.claude/worktrees/\n.claude/other/\n.worktrees/\n", encoding="utf-8"
    )
    git(tmp, main, "add", "-A")
    git(tmp, main, "commit", "-q", "-m", "fixture")
    return main


def linked(tmp, main, rel, *flags):
    path = main / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    git(tmp, main, "worktree", "add", "-q", *flags, path, "HEAD")
    return path


def worklist(tmp, tree, *args, **extra):
    return subprocess.run(
        [sys.executable, str(tree / ".claude/hooks/stop/worklist.py"), *args],
        cwd=tree,
        env=child_env(tmp, **extra),
        capture_output=True,
        text=True,
        check=False,
    )


def added(label, done):
    """`--add` succeeded. Not the exit code alone: the crash wrapper exits 0 with its block on stdout."""
    ok = done.returncode == 0 and "added #" in done.stdout
    check(label + " adds", ok or (done.stdout + done.stderr)[-400:], True)


def snapshot(tree):
    """Every file under the tree's agent/, by content."""
    root = tree / "agent"
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def pyrun(tmp, cwd, program, *args, **extra):
    done = subprocess.run(
        [sys.executable, "-c", program, *map(str, args)],
        cwd=cwd,
        env=child_env(tmp, **extra),
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, done.stdout.strip(), done.stderr.strip()


ROOT_OF = """
import sys
sys.path.insert(0, sys.argv[1])
import wl_core as C
print(C.project_root(sys.argv[2]))
"""


def root_of(tmp, main, start):
    """`wl_core.project_root(start)` as the main checkout's copy answers it."""
    return pyrun(tmp, tmp, ROOT_OF, main / ".claude/hooks/stop", start)[1]


NO_SUBPROCESS = """
import subprocess, sys
sys.path.insert(0, sys.argv[1])
import wl_core as C
def boom(*a, **k):
    raise AssertionError("project_root started a subprocess")
subprocess.run = boom
subprocess.Popen = boom
print(C.project_root(sys.argv[2]))
"""

# Every writer of Design 4's sweep table that takes its root from project_root, called with the root the lease's own copy resolves.
WRITERS = """
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import wl_claimcheck, wl_effort_tune, wl_hints, wl_liveproof, wl_outcomes, wl_planqueue, wl_retro, wl_review
import wl_core as C
import wl_store as S
root = C.project_root(C.project_start())
me = sys.argv[2]
sha = "a" * 40
out = {
    "wl_store.store_dir": S.store_dir(),
    "wl_store.writer_path": S.writer_path(me),
    "wl_store.agent_root": S.agent_root(root),
    "wl_store.agent_state_path": S.agent_state_path(root, me),
    "wl_store.journal_dir": S.journal_dir(),
    "wl_review.review_path": wl_review.review_path(root, "b", sha),
    "wl_review.ledger_path": wl_review.ledger_path(root, "b"),
    "wl_planqueue.QUEUE_REL": pathlib.Path(root) / wl_planqueue.QUEUE_REL,
    "wl_outcomes.ledger_path": wl_outcomes.ledger_path(root),
    "wl_outcomes.proposals_path": wl_outcomes.proposals_path(root),
    "wl_hints.proposals_path": wl_hints.proposals_path(root),
    "wl_retro.retro_ledger_path": wl_retro.ctx().retro_ledger_path(root),
    "wl_claimcheck.census_path": wl_claimcheck.census_path(root),
    "wl_effort_tune.table_path": wl_effort_tune.table_path(root),
    "wl_effort_tune.run_dir": wl_effort_tune.run_dir(root, me, 1),
    "wl_liveproof.LEDGER_REL": pathlib.Path(root) / wl_liveproof.LEDGER_REL,
}
print(json.dumps({k: str(v) for k, v in out.items()}))
"""

# The guard reads CLAUDE_PROJECT_DIR, else show-toplevel. `_pushes` is the first call handed the root, so the capture reads what its ledger lines would join to. (Its twin, the batch loop's early-push guard, was deleted with that loop: agent/plans/PLAN-simple-two-tree-loop.md B4.)
GUARD_ROOTS = """
import json, os, sys
sys.path.insert(0, sys.argv[1])
from rediacc_hooks import hookio
from rediacc_hooks.guards import block_backup_unverified_push as B
seen = {}
def capture(name):
    def fn(cmd, root, base):
        seen[name] = str(root)
        return []
    return fn
B._pushes = capture("backup")
env = {"CLAUDE_PROJECT_DIR": sys.argv[2]} if sys.argv[2] else {}
payload = json.dumps({"tool_input": {"command": "git status"}, "cwd": os.getcwd()})
B.run(hookio.Event(payload, env=env))
print(json.dumps(seen))
"""


def writer_expectations(main, git_dir):
    rel = {
        "wl_store.store_dir": "agent/worklist",
        "wl_store.writer_path": "agent/worklist/%s.jsonl" % ME,
        "wl_store.agent_root": "agent",
        "wl_store.agent_state_path": "agent/%s/STATE.md" % ME,
        "wl_review.review_path": "agent/reviews/b/%s.md" % ("a" * 40),
        "wl_planqueue.QUEUE_REL": "agent/plans/QUEUE.md",
        "wl_outcomes.ledger_path": "agent/ledgers/effort-outcomes.jsonl",
        "wl_outcomes.proposals_path": "agent/ledgers/effort-proposals.jsonl",
        "wl_hints.proposals_path": "agent/ledgers/hint-proposals.jsonl",
        "wl_claimcheck.census_path": "agent/ledgers/census-claim-check.jsonl",
        "wl_liveproof.LEDGER_REL": "agent/ledgers/live-proof.jsonl",
    }
    want = {k: str(main / v) for k, v in rel.items()}
    want["wl_store.journal_dir"] = str(git_dir / "rediacc-worklist-journal")
    return want


def control_writers(tmp, main, lease):
    code, out, err = pyrun(tmp, lease, WRITERS, lease / ".claude/hooks/stop", ME)
    if not check("writers: the table was read (%s)" % err[-200:], code, 0):
        return
    got = json.loads(out)
    for label, want in writer_expectations(main, main / ".git").items():
        check("writer %s lands in the main checkout" % label, got.get(label), want)
    # These three derive from constants this suite does not restate, so they are judged by prefix.
    for label in ("wl_review.ledger_path", "wl_retro.retro_ledger_path", "wl_effort_tune.run_dir"):
        check(
            "writer %s lands under the main checkout's agent/" % label,
            str(got.get(label, "")).startswith(str(main / "agent") + os.sep),
            True,
        )
    table = got.get("wl_effort_tune.table_path", "")
    check(
        "writer wl_effort_tune.table_path lands under the main checkout",
        table.startswith(str(main) + os.sep) and not table.startswith(str(lease) + os.sep),
        True,
    )


def control_guards(tmp, main, lease):
    claude = lease / ".claude"
    code, out, err = pyrun(tmp, lease, GUARD_ROOTS, claude, main)
    if check("guards: read with the variable set (%s)" % err[-200:], code, 0):
        seen = json.loads(out)
        check(
            "block_backup_unverified_push: the variable gives main", seen.get("backup"), str(main)
        )
    # Why W5 has to confirm the variable: without it the guard reads the lease itself.
    code, out, err = pyrun(tmp, lease, GUARD_ROOTS, claude, "")
    if check("guards: read with the variable unset (%s)" % err[-200:], code, 0):
        seen = json.loads(out)
        check(
            "block_backup_unverified_push: no variable reads the lease",
            seen.get("backup"),
            str(lease),
        )


def control_add(tmp, main, lease):
    before_main, before_lease = snapshot(main), snapshot(lease)
    done = worklist(tmp, lease, "--add", ME, "from the lease (%s)" % ME)
    added("--add from a lease's copy", done)
    written = main / ("agent/worklist/%s.jsonl" % ME)
    check(
        "--add from a lease appends to the main store",
        written.is_file() and "from the lease" in written.read_text(encoding="utf-8"),
        True,
    )
    check("--add leaves the lease's store byte-identical", snapshot(lease), before_lease)
    check("--add moved the main store", snapshot(main) != before_main, True)
    journal = main / (".git/rediacc-worklist-journal/%s.jsonl" % ME)
    check("the journal is the main checkout's", journal.is_file(), True)
    admin = main / ".git/worktrees" / lease.name / "rediacc-worklist-journal"
    check("the lease's own git dir holds no journal", admin.exists(), False)


def control_rule_removed(tmp, main):
    """The same `--add` with the rule cut from a lease's copy lands in that copy, so the control above can fail."""
    lease = linked(tmp, main, ".claude/worktrees/norule", "--detach")
    stop = lease / ".claude/hooks/stop"
    cuts = (
        ("wl_core.py", "return lease_main(candidate) or candidate", "return candidate"),
        ("worklist.py", "root = _local_lease_main(candidate) or candidate", "root = candidate"),
    )
    for name, old, new in cuts:
        text = (stop / name).read_text(encoding="utf-8")
        check("the rule is present to cut in %s" % name, old in text, True)
        (stop / name).write_text(text.replace(old, new), encoding="utf-8")
    before_main = snapshot(main)
    done = worklist(tmp, lease, "--add", ME, "rule removed (%s)" % ME)
    added("rule removed: --add", done)
    written = lease / ("agent/worklist/%s.jsonl" % ME)
    check(
        "rule removed: the item lands in the copy's store",
        written.is_file() and "rule removed" in written.read_text(encoding="utf-8"),
        True,
    )
    check("rule removed: the main store does not move", snapshot(main), before_main)


def control_operator_tree(tmp, main):
    tree = linked(tmp, main, ".worktrees/0128-1", "-b", "0128-1")
    before_main = snapshot(main)
    done = worklist(tmp, tree, "--add", ME, "operator tree (%s)" % ME)
    added("--add from .worktrees/0128-1", done)
    written = tree / ("agent/worklist/%s.jsonl" % ME)
    check(
        ".worktrees/0128-1 keeps its own store",
        written.is_file() and "operator tree" in written.read_text(encoding="utf-8"),
        True,
    )
    check(".worktrees/0128-1 leaves the main store alone", snapshot(main), before_main)
    check(".worktrees/0128-1 is its own project_root", root_of(tmp, main, tree), str(tree))
    journal = main / (".git/worktrees/0128-1/rediacc-worklist-journal/%s.jsonl" % ME)
    check(".worktrees/0128-1 keeps its own journal", journal.is_file(), True)


def control_not_leases(tmp, main):
    """Each is one fact away from a lease and keeps its own root."""
    plain = tmp / "module-plain"
    (main / ".git/modules").mkdir(exist_ok=True)
    git(tmp, tmp, "init", "-q", "--separate-git-dir", main / ".git/modules/plain", plain)
    check("a .git file into modules/ is unchanged", root_of(tmp, main, plain), str(plain))
    placed = main / ".claude/worktrees/modlike"
    git(tmp, tmp, "init", "-q", "--separate-git-dir", main / ".git/modules/modlike", placed)
    check(
        "a .git file into modules/ under .claude/worktrees is unchanged",
        root_of(tmp, main, placed),
        str(placed),
    )
    other = linked(tmp, main, ".claude/other/x", "--detach")
    check(
        "a linked tree elsewhere under .claude is unchanged", root_of(tmp, main, other), str(other)
    )
    foreign_main = tmp / "foreign"
    foreign_main.mkdir()
    git(tmp, foreign_main, "init", "-q", "-b", "main")
    git(tmp, foreign_main, "commit", "-q", "--allow-empty", "-m", "x")
    foreign = main / ".claude/worktrees/foreign"
    git(tmp, foreign_main, "worktree", "add", "-q", "--detach", foreign, "HEAD")
    check("another repo's linked tree is unchanged", root_of(tmp, main, foreign), str(foreign))
    check("the main checkout is itself", root_of(tmp, main, main), str(main))


def control_main_is_a_submodule(tmp, main):
    """The shape wl_core.project_start warns about: `<main>/.git` is itself a file into modules/."""
    outer = tmp / "outer"
    outer.mkdir()
    git(tmp, outer, "init", "-q", "-b", "main")
    inner = outer / "console"
    (outer / ".git/modules").mkdir()
    git(
        tmp,
        outer,
        "init",
        "-q",
        "-b",
        "main",
        "--separate-git-dir",
        outer / ".git/modules/console",
        inner,
    )
    git(tmp, inner, "commit", "-q", "--allow-empty", "-m", "x")
    lease = inner / ".claude/worktrees/x"
    git(tmp, inner, "worktree", "add", "-q", "--detach", lease, "HEAD")
    check("a lease of a submodule checkout resolves to it", root_of(tmp, main, lease), str(inner))
    check("that checkout keeps its own root", root_of(tmp, main, inner), str(inner))


def control_store_override(tmp, main, lease):
    override = tmp / "override"
    override.mkdir()
    before_main, before_lease = snapshot(main), snapshot(lease)
    done = worklist(tmp, lease, "--add", ME, "override (%s)" % ME, WORKLIST_STORE_DIR=str(override))
    added("$WORKLIST_STORE_DIR --add", done)
    check("$WORKLIST_STORE_DIR wins", (override / ("%s.jsonl" % ME)).is_file(), True)
    check("$WORKLIST_STORE_DIR leaves the main store alone", snapshot(main), before_main)
    check("$WORKLIST_STORE_DIR leaves the lease alone", snapshot(lease), before_lease)


def control_no_subprocess(tmp, main, lease):
    stop = main / ".claude/hooks/stop"
    code, out, err = pyrun(tmp, tmp, NO_SUBPROCESS, stop, lease)
    check("project_root starts no subprocess (%s)" % err[-200:], code, 0)
    check("that run still resolved to main", out, str(main))
    code, _out, _err = pyrun(
        tmp,
        tmp,
        NO_SUBPROCESS.replace("print(C.project_root(sys.argv[2]))", "subprocess.run(['true'])"),
        stop,
        lease,
    )
    check("the raising stub does raise", code != 0, True)


def control_path_twin(tmp, main, lease):
    from_main = worklist(tmp, main, "--path").stdout.strip()
    check(
        "--path from a lease's copy names the main list",
        worklist(tmp, lease, "--path").stdout.strip(),
        from_main,
    )
    program = "import sys; sys.path.insert(0, sys.argv[1]); import wl_core as C; print(C.worklist_for(C.project_start({'cwd': sys.argv[2]})))"
    check(
        "wl_core.worklist_for agrees with --path",
        pyrun(tmp, lease, program, lease / ".claude/hooks/stop", lease)[1],
        from_main,
    )
    broken = linked(tmp, main, ".claude/worktrees/broken", "--detach")
    (broken / ".claude/hooks/stop/wl_core.py").write_text(
        'raise ImportError("planted")\n', encoding="utf-8"
    )
    done = worklist(tmp, broken, "--path")
    check("--path answers with wl_core broken", done.returncode, 0)
    check("the broken-sibling answer is still the main list", done.stdout.strip(), from_main)


def _body(tree, name):
    """A function's source without its docstring, with the twin prefix folded."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            lines = [ast.unparse(s) for s in node.body[1:]]
            return "\n".join(lines).replace("_local_", "")
    return None


def control_twin_source():
    stop = SOURCE / "hooks/stop"
    core = ast.parse((stop / "wl_core.py").read_text(encoding="utf-8"))
    text = (stop / "worklist.py").read_text(encoding="utf-8")
    # The twin must call its own helper, so that one name is mapped; any other difference still fails.
    twin = ast.parse(re.sub(r"(?<!def )_local_git_dirs\(", "_git_dirs(", text))
    for name in ("_git_dirs", "lease_main"):
        got = _body(twin, "_local_" + name.lstrip("_"))
        check(
            "worklist.py's twin of %s is in lockstep" % name,
            got is not None and got == _body(core, name),
            True,
        )
    # block_worktree_add's script arm reads a dirty script by these words, and worklist.py is the session's own CLI.
    check(
        "worklist.py never spells the word that locks its verbs", "worktree" in text.lower(), False
    )


def section_root():
    tmp = pathlib.Path(runtmp.run_dir("wl-worktrees-")).resolve()
    for sub in ("t", "home"):
        (tmp / sub).mkdir()
    main = build_main(tmp)
    lease = linked(tmp, main, ".claude/worktrees/x", "--detach")
    # main's own .git/config is the one a lease shares, so nothing here may have written to it.
    config = (main / ".git/config").read_bytes()
    deep = lease / ".claude/hooks"
    check("project_root from a lease is main", root_of(tmp, main, lease), str(main))
    check("project_root from inside a lease is main", root_of(tmp, main, deep), str(main))
    control_add(tmp, main, lease)
    control_writers(tmp, main, lease)
    control_guards(tmp, main, lease)
    control_rule_removed(tmp, main)
    control_operator_tree(tmp, main)
    control_not_leases(tmp, main)
    control_main_is_a_submodule(tmp, main)
    control_store_override(tmp, main, lease)
    control_no_subprocess(tmp, main, lease)
    control_path_twin(tmp, main, lease)
    control_twin_source()
    check(
        "the fixture's shared git config did not move", (main / ".git/config").read_bytes(), config
    )


SURVEY = """
import json, subprocess, sys
sys.path.insert(0, sys.argv[1])
import wl_worktrees as W
root, session, live, items, cache_path, role = sys.argv[2:8]
real = subprocess.run
statuses = []
def counting(argv, *a, **k):
    if "status" in argv:
        statuses.append(argv)
    return real(argv, *a, **k)
subprocess.run = counting
live = json.loads(live)
if live is not None:
    live = {
        "ids": set(live["ids"]),
        "trees": set(live["trees"]),
        "cwd": live.get("cwd", ""),
        "prompts": [tuple(row) for row in live.get("prompts", ())],
    }
cache = {}
if cache_path:
    try:
        with open(cache_path, encoding="utf-8") as fh:
            cache = json.load(fh)
    except OSError:
        pass
got = W.survey(root, session, json.loads(items), lambda: live, cache, role=role)
if cache_path:
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(got["cache"], fh)
got["statuses"] = len(statuses)
got["lines"] = W.unlanded_lines(got)
got["report"] = W.report_lines(got)
print(json.dumps(got))
"""
NOBODY: dict[str, list[str]] = {"ids": [], "trees": []}


def read(tmp, main, session=SID, live=NOBODY, items=(), cache="", role=""):
    """One `survey` in a child process. `statuses` counts its `git status` calls through a stub over `subprocess.run`."""
    code, out, err = pyrun(
        tmp,
        tmp,
        SURVEY,
        SOURCE / "hooks/stop",
        main,
        session,
        json.dumps(live),
        json.dumps(list(items)),
        cache,
        role,
    )
    if code != 0:
        raise SystemExit("survey: %s" % err[-600:])
    return json.loads(out)


def ids(rows):
    return sorted(row["id"] for row in rows)


def lease_main_repo(tmp, name):
    main = tmp / name / "console"
    main.mkdir(parents=True)
    git(tmp, main, "init", "-q", "-b", "main")
    (main / "a.txt").write_text("a\n", encoding="utf-8")
    (main / ".gitignore").write_text(".claude/worktrees/\n.worktrees/\n", encoding="utf-8")
    git(tmp, main, "add", "-A")
    git(tmp, main, "commit", "-q", "-m", "base")
    return main


def write_record(main, lease_id, owner=ME, agent=""):
    store = main / ".git/rediacc-worktrees"
    store.mkdir(exist_ok=True)
    record = {
        "id": lease_id,
        "path": str(main / ".claude/worktrees" / lease_id),
        "owner": owner,
        "agent": agent,
        "base": {},
        "created_at": "2026-11-04T12:00:00Z",
    }
    (store / ("%s.json" % lease_id)).write_text(json.dumps(record), encoding="utf-8")


def new_lease(tmp, main, lease_id, owner=ME, agent=""):
    lease = linked(tmp, main, ".claude/worktrees/%s" % lease_id, "--detach")
    write_record(main, lease_id, owner, agent)
    return lease


def commit_in(tmp, tree, rel, text, message="c"):
    (tree / rel).write_text(text, encoding="utf-8")
    git(tmp, tree, "add", "--", rel)
    git(tmp, tree, "commit", "-q", "-m", message)
    return git(tmp, tree, "rev-parse", "HEAD")


def control_owner_blocks(tmp):
    main = lease_main_repo(tmp, "owner")
    lease = new_lease(tmp, main, "clean")
    got = read(tmp, main)
    check("a clean lease of this session does not block", got["unlanded"], [])
    check("a clean lease is no orphan", got["orphans"], [])
    sha = commit_in(tmp, lease, "b.txt", "b\n")
    got = read(tmp, main)
    check("a finished lease with a commit blocks", ids(got["unlanded"]), ["clean"])
    check("the block names the commit", got["unlanded"][0]["commits"], {".": [sha]})
    check("the block counts no dirty path", got["unlanded"][0]["dirty"], 0)
    check("the block names `land`", "./run.sh worktree land clean" in got["lines"], True)
    check("the owner's figures ran git status", got["statuses"] > 0, True)
    (lease / "c.txt").write_text("c\n", encoding="utf-8")
    got = read(tmp, main)
    check("an untracked file counts as dirty", got["unlanded"][0]["dirty"], 1)


def control_peer(tmp):
    main = lease_main_repo(tmp, "peer")
    lease = new_lease(tmp, main, "w1")
    commit_in(tmp, lease, "b.txt", "b\n")
    got = read(tmp, main, session=PEER)
    check("a peer's lease does not block", got["unlanded"], [])
    check("a peer's lease is reported", ids(got["peers"]), ["w1"])
    check(
        "a peer's lease is one report line",
        len([x for x in got["report"].splitlines() if "w1" in x]),
        1,
    )
    check("a peer's lease spends no git status", got["statuses"], 0)


def control_live(tmp):
    main = lease_main_repo(tmp, "live")
    lease = new_lease(tmp, main, "w1", agent="wa1")
    commit_in(tmp, lease, "b.txt", "b\n")
    got = read(tmp, main, live={"ids": ["wa1"], "trees": []})
    check("a live writer by agent id holds the lease", got["unlanded"], [])
    check("that lease is read as held", got["held"], ["w1"])
    check("a held lease spends no git status", got["statuses"], 0)
    got = read(tmp, main, live={"ids": ["other"], "trees": []})
    check("another agent holds nothing", ids(got["unlanded"]), ["w1"])
    got = read(tmp, main, live={"ids": [], "trees": [str(lease)]})
    check("a live writer by recorded tree holds the lease", got["held"], ["w1"])
    got = read(
        tmp, main, live={"ids": [], "trees": [], "prompts": [("wb", "work in %s please" % lease)]}
    )
    check("a live writer whose prompt names the tree holds the lease", got["held"], ["w1"])
    got = read(
        tmp, main, live={"ids": [], "trees": [], "prompts": [("wb", "work in w10 not this one")]}
    )
    check("a prompt naming another tree holds nothing", ids(got["unlanded"]), ["w1"])
    moved_gitlink = "1 .M SC.. 160000 160000 160000 aaa bbb private/renet"
    staged_gitlink = "1 MM SC.. 160000 160000 160000 aaa bbb private/renet"
    code = (
        "import sys\nsys.path.insert(0, sys.argv[1])\nimport wl_worktrees\n"
        "print(wl_worktrees.dirty_count(sys.argv[2]))\n"
    )
    for name, row, want in (
        ("a moved gitlink is no dirt", moved_gitlink, "0"),
        ("a staged gitlink is dirt", staged_gitlink, "1"),
    ):
        check(name, pyrun(tmp, tmp, code, SOURCE / "hooks/stop", row)[1].strip(), want)
    got = read(tmp, main, live={"ids": [], "trees": [], "cwd": str(lease / "deep")})
    check("the session working inside its lease holds it", got["held"], ["w1"])
    check("that session is not blocked by its own lease", got["unlanded"], [])
    got = read(tmp, main, live={"ids": [], "trees": [], "cwd": str(main)})
    check("a session in the main checkout holds nothing", got["held"], [])
    nopath = new_lease(tmp, main, "w2")
    commit_in(tmp, nopath, "b.txt", "b\n")
    record = main / ".git/rediacc-worktrees/w2.json"
    record.write_text(json.dumps({**json.loads(record.read_text()), "path": ""}), encoding="utf-8")
    got = read(tmp, main, live={"ids": [], "trees": [], "cwd": str(main)})
    check(
        "a record with no path is held by nobody, not by the session's cwd",
        "w2" in got["held"],
        False,
    )
    item = {"id": "abcd1234", "state": ">", "worker": "x", "text": "writing in w1"}
    got = read(tmp, main, items=[item])
    check("a worklist lease naming it holds the lease", got["held"], ["w1"])
    got = read(tmp, main, items=[{**item, "state": " "}])
    check("an open item naming it holds nothing", got["held"], [])
    sleeper = subprocess.Popen(["sleep", "60"], cwd=lease)
    try:
        got = read(tmp, main)
    finally:
        sleeper.terminate()
        sleeper.wait()
    check("a process inside it holds the lease", got["held"], ["w1"])
    got = read(tmp, main, live=None)
    check("a blind roster blocks nothing", got["unlanded"], [])
    check("a blind roster leaves the lease unjudged", got["unknown"], ["w1"])
    check("a blind roster says so", "w1" in got["report"], True)


def write_hold(main, lease_id, item, reason="waits on its dependencies", session=ME):
    store = main / ".git/rediacc-worktrees"
    store.mkdir(exist_ok=True)
    body = {"item": item, "reason": reason, "held_at": "2026-11-23T08:00:00Z"}
    if session is not None:
        body["session"] = session
    (store / ("%s.hold" % lease_id)).write_text(json.dumps(body), encoding="utf-8")


def control_hold(tmp):
    main = lease_main_repo(tmp, "hold")
    lease = new_lease(tmp, main, "w1")
    sha = commit_in(tmp, lease, "b.txt", "b\n")
    open_item = {"id": "ac6a4f6b", "state": " ", "text": "preview signer", "owner": ME}
    got = read(tmp, main, items=[open_item])
    check("an unheld lease blocks", ids(got["unlanded"]), ["w1"])
    check("an unheld lease parks nothing", got["parked"], [])
    write_hold(main, "w1", "ac6a4f6b")
    got = read(tmp, main, items=[open_item])
    check("a held lease with an open item does not block", got["unlanded"], [])
    check("the hold is one parked row", got["parked"][0]["id"], "w1")
    check("a parked lease spends no git status", got["statuses"], 0)
    check(
        "the advisory names the item and the reason",
        "parked lease w1, held for #ac6a4f6b: waits on its dependencies" in got["report"],
        True,
    )
    for state in ("?", ">"):
        got = read(tmp, main, items=[{**open_item, "state": state}])
        check("a [%s] item still holds the lease" % state, got["unlanded"], [])
    got = read(tmp, main, items=[{**open_item, "state": "x"}])
    check("a ticked item blocks again", ids(got["unlanded"]), ["w1"])
    check("a ticked item parks nothing", got["parked"], [])
    got = read(tmp, main, items=[])
    check("a gone item blocks again", got["unlanded"][0]["commits"], {".": [sha]})
    # 0c0cdceb.1: a hold names the item's full id; a prefix, a peer's item and a peer's write are not honoured.
    got = read(tmp, main, items=[{**open_item, "id": "ac6a4f6b0001"}])
    check("a hold naming a prefix of an open id does not hold", ids(got["unlanded"]), ["w1"])
    write_hold(main, "w1", "ac")
    got = read(tmp, main, items=[open_item])
    check("a two-letter prefix hold holds nothing", ids(got["unlanded"]), ["w1"])
    write_hold(main, "w1", "ac6a4f6b")
    got = read(tmp, main, items=[{**open_item, "owner": "babe0000"}])
    check("another session's item does not hold it", ids(got["unlanded"]), ["w1"])
    check("another session's item is said", any("babe0000" in d for d in got["doubts"]), True)
    got = read(tmp, main, items=[{**open_item, "owner": None}])
    check("an untagged item does not hold it", ids(got["unlanded"]), ["w1"])
    write_hold(main, "w1", "ac6a4f6b", session="babe0000")
    got = read(tmp, main, items=[open_item])
    check("a hold another session wrote does not hold", ids(got["unlanded"]), ["w1"])
    check("a foreign writer is said", any("babe0000" in d for d in got["doubts"]), True)
    write_hold(main, "w1", "ac6a4f6b", session=None)
    got = read(tmp, main, items=[open_item])
    check("a hold with no writer session does not hold", ids(got["unlanded"]), ["w1"])
    # a921ed04.1: a session tag of one or two characters agrees with every owner that starts with it, so it is no tag. The owner is the item's `owner` field, not its id, so the tags are spelled as prefixes of that field (review c2e8d43b).
    owner = open_item["owner"]
    write_hold(main, "w1", "ac6a4f6b", session=owner[:2])
    got = read(tmp, main, items=[open_item])
    check("a two-character writer tag of the owner does not hold", ids(got["unlanded"]), ["w1"])
    write_hold(main, "w1", "ac6a4f6b", session=owner[:4])
    got = read(tmp, main, items=[open_item])
    check("CONTROL a four-character writer tag of the owner still holds", got["unlanded"], [])
    write_hold(main, "w1", "ac6a4f6b")
    got = read(tmp, main, items=[{**open_item, "id": "ffff0000"}])
    check("another open item does not hold it", ids(got["unlanded"]), ["w1"])
    got = read(tmp, main, items=[open_item])
    check("the owner's exact hold is honoured again", got["unlanded"], [])
    # 0c0cdceb.2: a live writer and a blind roster are judged before the hold.
    running = {"ids": ["wa"], "trees": [str(lease)], "prompts": []}
    got = read(tmp, main, items=[open_item], live=running)
    check("a held lease with a live writer reads held", got["held"], ["w1"])
    check("a held lease with a live writer is not parked", got["parked"], [])
    got = read(tmp, main, items=[open_item], live=None)
    check("a held lease under a blind roster reads unknown", got["unknown"], ["w1"])
    check("a held lease under a blind roster is not parked", got["parked"], [])
    (main / ".git/rediacc-worktrees/w1.hold").write_text("{", encoding="utf-8")
    got = read(tmp, main, items=[open_item])
    check("a damaged hold blocks", ids(got["unlanded"]), ["w1"])
    check("a damaged hold is said", "w1: its hold record could not be read" in got["doubts"], True)
    for name, body in (
        ("a hold with an item and no reason", '{"item": "ac6a4f6b"}'),
        ("a hold with a reason and no item", '{"reason": "r"}'),
        ("a hold with neither item nor reason", '{"item": "x"}'),
    ):
        (main / ".git/rediacc-worktrees/w1.hold").write_text(body, encoding="utf-8")
        got = read(tmp, main, items=[open_item])
        check(
            name + " reads as damaged",
            "w1: its hold record could not be read" in got["doubts"],
            True,
        )


def control_landed(tmp):
    main = lease_main_repo(tmp, "landed")
    lease = new_lease(tmp, main, "w1")
    sha = commit_in(tmp, lease, "b.txt", "b\n")
    git(tmp, main, "cherry-pick", sha)
    check("a picked commit reads landed by patch-id", read(tmp, main)["unlanded"], [])

    main = lease_main_repo(tmp, "resolved")
    lease = new_lease(tmp, main, "w1")
    sha = commit_in(tmp, lease, "a.txt", "lease\n")
    commit_in(tmp, main, "a.txt", "other\n")
    got = read(tmp, main)
    check("a different commit lands nothing", ids(got["unlanded"]), ["w1"])
    commit_in(tmp, main, "a.txt", "resolved\n", "pick\n\n(cherry picked from commit %s)" % sha)
    check(
        "git cherry alone reads a resolved pick unlanded",
        git(tmp, lease, "cherry", "main", sha),
        "+ %s" % sha,
    )
    check("a resolved pick reads landed by its -x line", read(tmp, main)["unlanded"], [])

    # A duplicate fix: the lease commit's change landed through a different commit, recorded by a Lease-Landed-As trailer.
    main = lease_main_repo(tmp, "landed-as")
    lease = new_lease(tmp, main, "w1")
    sha = commit_in(tmp, lease, "a.txt", "lease wording\n")
    other = commit_in(tmp, main, "a.txt", "landed wording\n")
    check(
        "an equivalent fix landed elsewhere still reads unlanded",
        ids(read(tmp, main)["unlanded"]),
        ["w1"],
    )
    commit_in(tmp, main, "c.txt", "c\n", "record\n\nLease-Landed-As: %s %s" % (sha, other))
    check("a Lease-Landed-As trailer reads it landed", read(tmp, main)["unlanded"], [])
    # CONTROL: the trailer names one lease commit, not every one.
    sha2 = commit_in(tmp, lease, "d.txt", "d\n")
    check(
        "a second lease commit the trailer does not name stays unlanded",
        read(tmp, main)["unlanded"][0]["commits"],
        {".": [sha2]},
    )

    # CONTROL (review f474e87d.1): a trailer whose landed sha is no commit of the live tip records nothing.
    commit_in(tmp, main, "e.txt", "e\n", "typo\n\nLease-Landed-As: %s %s" % (sha2, "0" * 40))
    check(
        "a Lease-Landed-As trailer naming no real commit leaves the lease unlanded",
        read(tmp, main)["unlanded"][0]["commits"],
        {".": [sha2]},
    )

    # CONTROL (review 99374771.2): a landed sha that IS a real commit, kept on another branch and no ancestor of the live tip, records nothing either.
    side = git(tmp, main, "commit-tree", "HEAD^{tree}", "-p", "HEAD~1", "-m", "side")
    git(tmp, main, "branch", "side-work", side)
    commit_in(tmp, main, "f.txt", "f\n", "stray\n\nLease-Landed-As: %s %s" % (sha2, side))
    check(
        "a Lease-Landed-As trailer naming a commit off the live tip leaves the lease unlanded",
        read(tmp, main)["unlanded"][0]["commits"],
        {".": [sha2]},
    )
    # The same row naming a real ancestor of the live tip does record it.
    ancestor = git(tmp, main, "rev-parse", "HEAD~1")
    commit_in(tmp, main, "g.txt", "g\n", "fix\n\nLease-Landed-As: %s %s" % (sha2, ancestor))
    check(
        "a Lease-Landed-As trailer naming a real ancestor reads it landed",
        read(tmp, main)["unlanded"],
        [],
    )

    # A gc --superseded-by waiver in the ledger reads the commit landed, while its landed sha stays an ancestor of the live tip.
    main = lease_main_repo(tmp, "ledger")
    lease = new_lease(tmp, main, "w1")
    sha = commit_in(tmp, lease, "a.txt", "lease wording\n")
    other = commit_in(tmp, main, "a.txt", "landed wording\n")
    check("a ledger-less duplicate reads unlanded", ids(read(tmp, main)["unlanded"]), ["w1"])
    ledger = pathlib.Path(main) / ".git" / "rediacc-worktrees" / "superseded.jsonl"
    ledger.write_text(json.dumps({"sha": sha, "landed": other}) + "\n")
    check("a ledger row reads it landed", read(tmp, main)["unlanded"], [])
    ledger.write_text(json.dumps({"sha": sha, "landed": "0" * 40}) + "\n")
    check("a ledger row naming no commit waives nothing", ids(read(tmp, main)["unlanded"]), ["w1"])
    # A change split across commits: every joined part must be on the tip (reviews 918cfd41.1, 918cfd41.2).
    earlier = git(tmp, main, "rev-parse", "HEAD~1")
    ledger.write_text(json.dumps({"sha": sha, "landed": other + "+" + earlier}) + "\n")
    check(
        "a joined ledger row with every part on the tip reads landed",
        read(tmp, main)["unlanded"],
        [],
    )
    side = git(tmp, main, "commit-tree", "HEAD^{tree}", "-p", "HEAD~1", "-m", "side")
    git(tmp, main, "branch", "side-joined", side)
    ledger.write_text(json.dumps({"sha": sha, "landed": other + "+" + side}) + "\n")
    check(
        "a joined ledger row with one part off the tip waives nothing",
        ids(read(tmp, main)["unlanded"]),
        ["w1"],
    )
    for empty in ("+", "++"):
        ledger.write_text(json.dumps({"sha": sha, "landed": empty}) + "\n")
        check(
            "a ledger row of only separators (%r) waives nothing" % empty,
            ids(read(tmp, main)["unlanded"]),
            ["w1"],
        )

    main = lease_main_repo(tmp, "pinned")
    lease = new_lease(tmp, main, "w1")
    base = git(tmp, main, "rev-parse", "HEAD")
    sha = commit_in(tmp, lease, "b.txt", "b\n")
    git(tmp, main, "update-ref", "refs/worktrees/w1", sha)
    git(tmp, lease, "checkout", "-q", "--detach", base)
    got = read(tmp, main)
    check("a pin past HEAD still counts", got["unlanded"][0]["commits"], {".": [sha]})

    # A commit and its exact revert (made by `git revert -n` and a plain message) are net-zero: only the third commit needs landing.
    main = lease_main_repo(tmp, "revert-pair")
    lease = new_lease(tmp, main, "w1")
    change = commit_in(tmp, lease, "a.txt", "changed\n")
    git(tmp, lease, "revert", "-n", change)
    git(tmp, lease, "commit", "-q", "-m", "put it back")
    third = commit_in(tmp, lease, "x.txt", "x\n")
    check(
        "a commit and its exact revert stay unlanded until the third is picked",
        read(tmp, main)["unlanded"][0]["commits"],
        {".": [third]},
    )
    git(tmp, main, "cherry-pick", "-x", third)
    check("a commit and its exact revert read landed", read(tmp, main)["unlanded"], [])

    # CONTROL: a partial revert is not an inverse, so both commits stay unlanded.
    main = lease_main_repo(tmp, "partial-revert")
    lease = new_lease(tmp, main, "w1")
    (lease / "p.txt").write_text("p\n", encoding="utf-8")
    (lease / "q.txt").write_text("q\n", encoding="utf-8")
    git(tmp, lease, "add", "--", "p.txt", "q.txt")
    git(tmp, lease, "commit", "-q", "-m", "two files")
    change = git(tmp, lease, "rev-parse", "HEAD")
    git(tmp, lease, "rm", "-q", "--", "p.txt")
    git(tmp, lease, "commit", "-q", "-m", "drop one")
    partial = git(tmp, lease, "rev-parse", "HEAD")
    check(
        "a partial revert leaves both commits unlanded",
        read(tmp, main)["unlanded"][0]["commits"],
        {".": [change, partial]},
    )

    # CONTROL: mirrored add/delete counts on DIFFERENT files are no inverse, and the pair is not even read for patch-ids.
    main = lease_main_repo(tmp, "mirrored-counts")
    lease = new_lease(tmp, main, "w1")
    added = commit_in(tmp, lease, "n1.txt", "n\n")
    git(tmp, lease, "rm", "-q", "--", "a.txt")
    git(tmp, lease, "commit", "-q", "-m", "drop a")
    removed = git(tmp, lease, "rev-parse", "HEAD")
    check(
        "mirrored counts on different files stay unlanded",
        read(tmp, main)["unlanded"][0]["commits"],
        {".": [added, removed]},
    )
    probe = (
        "import sys\nsys.path.insert(0, sys.argv[1])\nimport wl_worktrees\n"
        "seen = []\nwl_worktrees._patch_id = lambda *a: seen.append(a) or ''\n"
        "wl_worktrees._drop_revert_pairs(sys.argv[2], sys.argv[3:])\nprint(len(seen))\n"
    )
    check(
        "commits with no shared file set cost no patch-id read",
        pyrun(tmp, tmp, probe, SOURCE / "hooks/stop", lease, added, removed)[1].strip(),
        "0",
    )
    # CONTROL: the same file changed twice, the second not an inverse, stays unlanded.
    main = lease_main_repo(tmp, "same-file-no-inverse")
    lease = new_lease(tmp, main, "w1")
    first = commit_in(tmp, lease, "a.txt", "one\n")
    second = commit_in(tmp, lease, "a.txt", "two\n")
    check(
        "a same-file change that is no inverse stays unlanded",
        read(tmp, main)["unlanded"][0]["commits"],
        {".": [first, second]},
    )

    # CONTROL: the -z reader keeps an empty file list a candidate and pairs commits with the same verbatim paths.
    probe = (
        "import sys\nsys.path.insert(0, sys.argv[1])\nimport wl_worktrees\n"
        "text = sys.argv[2].encode().decode('unicode_escape')\n"
        "wl_worktrees._git = lambda *a, **k: text\n"
        "print(','.join(wl_worktrees._same_file_set_commits('.', ['aaa', 'bbb', 'ccc', 'ddd'])))\n"
    )
    check(
        "an empty file list stays a candidate and equal path sets still pair",
        pyrun(
            tmp,
            tmp,
            probe,
            SOURCE / "hooks/stop",
            "\\x01aaa\\0\\nf.txt\\0\\x01bbb\\0\\nf.txt\\0\\x01ccc\\0\\x01ddd\\0\\ng.txt\\0",
        )[1].strip(),
        "aaa,bbb,ccc",
    )
    # CONTROL: two paths differing only by a trailing (or leading) space are different paths, so their commits are not paired.
    check(
        "paths differing only by whitespace are not merged",
        pyrun(
            tmp,
            tmp,
            probe,
            SOURCE / "hooks/stop",
            "\\x01aaa\\0\\nf.txt\\0\\x01bbb\\0\\nf.txt \\0\\x01ccc\\0\\n f.txt\\0\\x01ddd\\0\\ng.txt\\0",
        )[1].strip(),
        "",
    )

    # CONTROL: a commit alone stays unlanded.
    main = lease_main_repo(tmp, "no-revert")
    lease = new_lease(tmp, main, "w1")
    alone = commit_in(tmp, lease, "b.txt", "b\n")
    check(
        "a commit with no revert stays unlanded",
        read(tmp, main)["unlanded"][0]["commits"],
        {".": [alone]},
    )


def control_orphans(tmp):
    main = lease_main_repo(tmp, "orphans")
    new_lease(tmp, main, "good")
    head = git(tmp, main, "rev-parse", "HEAD")
    git(tmp, main, "update-ref", "refs/worktrees/good", head)
    linked(tmp, main, ".claude/worktrees/norecord", "--detach")
    write_record(main, "notree")
    git(tmp, main, "update-ref", "refs/worktrees/gone", head)
    linked(tmp, main, ".worktrees/0128-1", "-b", "0128-1")
    got = read(tmp, main)
    named = dict(got["orphans"])
    check("a tree with no record is the advisory", named.get("norecord"), "a tree with no record")
    check("a record with no tree is the advisory", named.get("notree"), "a record with no tree")
    check("a pin with neither is the advisory", "gone" in named, True)
    check("a joined lease and pin is no orphan", "good" in named, False)
    check("an operator's tree is not followed", "0128-1" in got["report"], False)
    check("no orphan blocks", got["unlanded"], [])
    check("each orphan has a report line", got["report"].count("orphan "), 3)


def control_index(tmp):
    main = lease_main_repo(tmp, "index")
    lease = new_lease(tmp, main, "w1")
    index = main / ".git/worktrees/w1/index"
    stat = (lease / "a.txt").stat()
    # Stale stat data is what makes a plain status rewrite the index.
    os.utime(lease / "a.txt", (stat.st_atime + 100, stat.st_mtime + 100))
    before = index.stat().st_mtime_ns
    got = read(tmp, main)
    check("the probe did run git status", got["statuses"] > 0, True)
    check("the probe leaves the lease's index mtime alone", index.stat().st_mtime_ns, before)
    git(tmp, lease, "status")
    check("a plain git status moves it", index.stat().st_mtime_ns != before, True)


def control_cache(tmp):
    main = lease_main_repo(tmp, "cache")
    lease = new_lease(tmp, main, "w1")
    cache = str(tmp / "cache" / "state.json")
    first = commit_in(tmp, lease, "b.txt", "b\n")
    got = read(tmp, main, cache=cache)
    check("the first stop reads the tree", got["statuses"] > 0, True)
    got = read(tmp, main, cache=cache)
    check("a second stop with nothing moved runs no git status", got["statuses"], 0)
    check("that stop still blocks", got["unlanded"][0]["commits"], {".": [first]})
    second = commit_in(tmp, lease, "c.txt", "c\n")
    got = read(tmp, main, cache=cache)
    check("HEAD moving reads the tree again", got["statuses"] > 0, True)
    check("the new commit is named", got["unlanded"][0]["commits"], {".": [first, second]})
    check("that reading is cached", read(tmp, main, cache=cache)["statuses"], 0)
    (lease / "d.txt").write_text("d\n", encoding="utf-8")
    git(tmp, lease, "add", "--", "d.txt")
    check(
        "the index moving reads the tree again", read(tmp, main, cache=cache)["statuses"] > 0, True
    )
    commit_in(tmp, main, "e.txt", "e\n")
    check(
        "the live tip moving reads the tree again",
        read(tmp, main, cache=cache)["statuses"] > 0,
        True,
    )
    held = read(tmp, main, live={"ids": [], "trees": [str(lease)]}, cache=cache)
    check("a held lease drops its cache entry", held["cache"], {})
    check(
        "the stop after a writer ends reads the tree",
        read(tmp, main, cache=cache)["statuses"] > 0,
        True,
    )


def control_submodule(tmp):
    """Candidate A's shape from the W0 decision: a gitlink in the console, a linked tree of the module's store inside the lease."""
    main = lease_main_repo(tmp, "submodule")
    store = main / ".git/modules/private/sub"
    store.parent.mkdir(parents=True)
    (main / "private").mkdir()
    git(tmp, main, "init", "-q", "-b", "main", "--separate-git-dir", store, main / "private/sub")
    pinned = commit_in(tmp, main / "private/sub", "s.txt", "s\n")
    git(tmp, main, "update-index", "--add", "--cacheinfo", "160000,%s,private/sub" % pinned)
    git(tmp, main, "commit", "-q", "-m", "gitlink")
    lease = new_lease(tmp, main, "w1")
    sub = lease / "private/sub"
    git(tmp, store, "worktree", "add", "-q", "--detach", sub, pinned)
    check("a clean submodule tree holds nothing", read(tmp, main)["unlanded"], [])
    sha = commit_in(tmp, sub, "t.txt", "t\n")
    raw = git(tmp, lease, "status", "--porcelain=v2")
    check("the console row really is SC..", " SC.. " in raw, True)
    got = read(tmp, main)
    check(
        "the submodule commit is named by its store",
        got["unlanded"][0]["commits"],
        {"private/sub": [sha]},
    )
    check("the moved gitlink row is excused", got["unlanded"][0]["dirty"], 0)
    check("the submodule tree is no orphan", got["orphans"], [])
    git(tmp, main / "private/sub", "cherry-pick", sha)
    check("a picked submodule commit reads landed", read(tmp, main)["unlanded"], [])
    (sub / "u.txt").write_text("u\n", encoding="utf-8")
    check("a dirty submodule tree blocks", read(tmp, main)["unlanded"][0]["dirty"] > 0, True)


def _cut_from(main, lease_id, branch):
    """Stamp a record with the `cut_from` the `lease` verb writes (`worktree_lease.tree_branch`)."""
    path = main / ".git/rediacc-worktrees" / ("%s.json" % lease_id)
    path.write_text(json.dumps({**json.loads(path.read_text()), "cut_from": branch}), "utf-8")


def _stamp(main, lease_id, **fields):
    """Stamp fields onto a lease record, as the `lease` verb writes `tree` and as a lander would be named."""
    path = main / ".git/rediacc-worktrees" / ("%s.json" % lease_id)
    path.write_text(json.dumps({**json.loads(path.read_text()), **fields}), "utf-8")


def control_lander(tmp):
    """B7 (agent/plans/PLAN-simple-two-tree-loop.md D5): a lease cut with `--tree landing` counts as unlanded for its lander only. The development session that owns it lists it as handed over and is not blocked; the landing tree's stop is. A named `lander` narrows that to one session."""
    main = lease_main_repo(tmp, "lander")
    lease = new_lease(tmp, main, "h1")
    _stamp(main, "h1", tree="landing")
    commit_in(tmp, lease, "h.txt", "h\n")
    got = read(tmp, main, role="development")
    check("the owner's development stop does not block on a landing-cut lease", got["unlanded"], [])
    check("...and lists it as handed over", ids(got["handed"]), ["h1"])
    check("...in its report", "handed lease h1 (the landing tree lands it)" in got["report"], True)
    got = read(tmp, main, session=PEER, role="landing")
    check("the landing tree's stop blocks on it", ids(got["unlanded"]), ["h1"])
    check("...and lists nothing as handed", got["handed"], [])
    got = read(tmp, main, session=PEER, role="")
    check(
        "a peer with no landing role neither blocks nor lists it as handed",
        (got["unlanded"], got["handed"]),
        ([], []),
    )
    _stamp(main, "h1", lander=PEER[:8])
    got = read(tmp, main, session=PEER, role="")
    check("a named lander blocks wherever its stop runs", ids(got["unlanded"]), ["h1"])
    third = "f00d0000-0000-4000-8000-000000000000"
    got = read(tmp, main, session=third, role="landing")
    check(
        "another landing-tree session does not block on a lease another lander holds",
        got["unlanded"],
        [],
    )
    got = read(tmp, main, role="development")
    check(
        "...and the owner still lists it as handed, naming the lander",
        got["handed"][0]["lander"] if got["handed"] else "",
        PEER[:8],
    )
    # CONTROL: a lease cut from the development tree is still its owner's to land.
    dev = new_lease(tmp, main, "d2")
    _stamp(main, "d2", tree="development")
    commit_in(tmp, dev, "d.txt", "d\n")
    got = read(tmp, main, role="development")
    check("a development-cut lease still blocks its owner", ids(got["unlanded"]), ["d2"])
    got = read(tmp, main, session=PEER, role="landing")
    check("...and never the landing tree", "d2" in ids(got["unlanded"]), False)


def control_landing_cut(tmp):
    """R20261123.6's twin, R20261123.7: lease ace763dd-1 was cut from the landing tree, its one commit was picked into landing, and the block still listed it, because the survey judged it against the development HEAD."""
    # The landing branch holds a commit the development HEAD lacks, as 1104-1 held 36 when ace763dd-1 was cut from it.
    main = lease_main_repo(tmp, "landing-cut")
    land = tmp / "landing-cut" / "landing"
    git(tmp, main, "worktree", "add", "-q", "-b", "1104-1", land, "HEAD")
    (main / ".git/rediacc-landing.json").write_text(
        json.dumps({"branch": "1104-1", "path": str(land)}), encoding="utf-8"
    )
    landed_only = commit_in(tmp, land, "l.txt", "l\n", "landing work")
    lease = main / ".claude/worktrees/l1"
    git(tmp, main, "worktree", "add", "-q", "--detach", lease, "1104-1")
    write_record(main, "l1")
    _cut_from(main, "l1", "1104-1")
    check(
        "the development HEAD really lacks the landing commit",
        git(tmp, main, "cherry", "HEAD", landed_only),
        "+ " + landed_only,
    )
    check("a fresh landing-cut lease inherits nothing unlanded", read(tmp, main)["unlanded"], [])
    sha = commit_in(tmp, lease, "b.txt", "b\n")
    got = read(tmp, main)
    check(
        "an unpicked landing-cut commit is listed, and only it",
        got["unlanded"][0]["commits"] if got["unlanded"] else {},
        {".": [sha]},
    )
    # A pick without -x: only the tip the lease is judged against can read it landed, never the `--branches` search for a -x line.
    git(tmp, land, "cherry-pick", sha)
    check(
        "a landing-cut commit picked into landing gives no worktree-unlanded",
        read(tmp, main)["unlanded"],
        [],
    )
    sha2 = commit_in(tmp, lease, "c.txt", "c\n")
    got = read(tmp, main)
    check(
        "an unpicked second commit of that lease is still listed",
        got["unlanded"][0]["commits"] if got["unlanded"] else {},
        {".": [sha2]},
    )
    # CONTROL: a lease cut from the development branch keeps today's tip, so landing's copy lands nothing for it.
    dev = new_lease(tmp, main, "d1")
    _cut_from(main, "d1", "main")
    dsha = commit_in(tmp, dev, "e.txt", "e\n")
    git(tmp, land, "cherry-pick", dsha)
    got = read(tmp, main)
    check(
        "a development-cut lease is still judged against the development HEAD",
        "d1" in ids(got["unlanded"]),
        True,
    )
    # A landing branch git does not hold: named as a doubt, never judged against the development HEAD in its place.
    gone = lease_main_repo(tmp, "landing-gone")
    gland = tmp / "landing-gone" / "landing"
    git(tmp, gone, "worktree", "add", "-q", "-b", "1104-1", gland, "HEAD")
    (gone / ".git/rediacc-landing.json").write_text(
        json.dumps({"branch": "1104-9", "path": str(gland)}), encoding="utf-8"
    )
    glease = new_lease(tmp, gone, "g1")
    _cut_from(gone, "g1", "1104-9")
    commit_in(tmp, glease, "b.txt", "b\n")
    got = read(tmp, gone)
    check("a landing branch with no ref judges nothing", got["unlanded"], [])
    check(
        "and the doubt names the lease and the missing ref",
        any("g1" in d and "refs/heads/1104-9" in d for d in got["doubts"]),
        True,
    )


def control_effort_table(tmp):
    script = _REAL.parents[3] / ".ci/scripts/quality/check_plan_record.py"

    def judged(*args):
        return subprocess.run(
            [sys.executable, str(script), "--effort-table", *args],
            cwd=_REAL.parents[3],
            env=child_env(tmp),
            capture_output=True,
            text=True,
            check=False,
        ).returncode

    check("the effort-table rule accepts the table", judged(), 0)
    table = json.loads((SOURCE / "config/effort.json").read_text(encoding="utf-8"))
    for key in ("worktree-unlanded", "worktree-orphan"):
        planted = json.loads(json.dumps(table))
        del planted["checks"][key]
        path = tmp / ("planted-%s.json" % key)
        path.write_text(json.dumps(planted), encoding="utf-8")
        check("the rule reds with %s removed" % key, judged(str(path)), 1)


# The gh shim of rediacc_hooks/tests/prloop_world.py, whose imports reach pytest: this file runs under a bare python3.
GH_SHIM = """#!/bin/bash
for a in "$@"; do
    case "$a" in
        *lastEditedAt*) cat "%(base)s/ci-fresh.json"; exit 0 ;;
        *'states:[OPEN,MERGED,CLOSED]'*) cat "%(base)s/ci-merged.json"; exit 0 ;;
        query=*) cat "%(base)s/ci-rollup.json"; exit 0 ;;
    esac
done
case "$*" in
    *actions/jobs/*) cat "%(base)s/ci-job.json"; exit 0 ;;
esac
echo '{}'
"""
SAID = "working the PR\n\n## Remaining\n- the PR"


def hook_world(fix, wlfix, ci_status):
    """A fixture git repo whose origin/pub PR #543 is green, with fresh brief and handover."""
    fix.git("init", "-q", "-b", "main")
    fix.git("config", "user.email", "t@t")
    fix.git("config", "user.name", "t")
    fix.git("remote", "add", "origin", wlfix.FAKE_ORIGIN)
    (fix.proj / "a.txt").write_text("a\n", encoding="utf-8")
    fix.git("add", "-A")
    fix.git("commit", "-qm", "base")
    head = fix.git("rev-parse", "HEAD").stdout.strip()
    fix.git("update-ref", "refs/remotes/origin/pub", head)
    fix.brief_now()
    fix.hand_now()
    for name, body in (
        ("ci-fresh.json", ci_status.CI_FRESH_PAYLOAD),
        ("ci-job.json", ci_status.CI_JOB_PAYLOAD),
        ("ci-merged.json", {"data": {"repository": {"pullRequests": {"nodes": []}}}}),
    ):
        (fix.base / name).write_text(json.dumps(body) + "\n", encoding="utf-8")
    ci_status.write_exec(fix.base / "binonly" / "gh", GH_SHIM % {"base": fix.base})
    job = ci_status.ci_job("Quality / Static", "SUCCESS")
    ci_status.ci_rollup(fix, "SUCCESS", "[%s]" % job)


def hook_stop(fix, extra, event=None):
    """A Stop with the gh shim on PATH, in context band 0."""
    band = fix.base / "ctxband"
    band.mkdir(exist_ok=True)
    (band / ("%s.json" % fix.sid[:8])).write_text(
        json.dumps({"epoch": 1, "band": 0}), encoding="utf-8"
    )
    env = {"CTX_BAND_STATE_DIR": str(band), **extra}
    env["PATH"] = "%s:%s" % (fix.base / "binonly", fix.env.get("PATH", ""))
    fix.say(SAID)
    return fix.run(env, event)


def hook_state(fix):
    path = fix.stem(".state-%s.json" % fix.sid[:8])
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def control_real_hook(tmp):
    """The real Stop hook over a fixture: the wiring, the effort row and the stand-down keep."""
    sys.path[:0] = [str(_CI.parent), str(SOURCE)]
    from rediacc_hooks.tests import ci_status_world as ci_status
    from rediacc_hooks.tests import wlfix

    needle = "UNLANDED LEASE"
    fix = wlfix.Fixture(tmp / "hookfix")
    fix.setup()
    hook_world(fix, wlfix, ci_status)
    with (fix.proj / ".git/info/exclude").open("a", encoding="utf-8") as fh:
        fh.write(".claude/worktrees/\n")
    lease = fix.proj / ".claude/worktrees/w1"
    fix.git("worktree", "add", "-q", "--detach", str(lease), "HEAD")
    (lease / "b.txt").write_text("b\n", encoding="utf-8")
    fix.git("-C", str(lease), "add", "--", "b.txt")
    fix.git("-C", str(lease), "-c", "commit.gpgsign=false", "commit", "-q", "-m", "c")
    write_record(fix.proj, "w1", owner=wlfix.ME, agent="wa1")
    # The roster is blind until this session's project directory exists.
    config = fix.base / "config"
    (config / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(fix.proj))).mkdir(parents=True)
    # A private runtime dir: the machine's own vm:check fleet lock (held by a real run) must not
    # stand this hook down.
    import fcntl

    runtime = fix.base / "xdg"
    runtime.mkdir(mode=0o700)
    env = {
        "CLAUDE_CONFIG_DIR": str(config),
        "XDG_RUNTIME_DIR": str(runtime),
    }

    got = hook_stop(fix, env)
    check("the hook blocks an owner's finished lease", got.decision, "block")
    check("the block is this check's", needle in got.out, True)
    check("the block names land", "./run.sh worktree land w1" in got.out, True)
    cached = hook_state(fix).get("worktrees", {}).get("w1", {})
    check("the state doc keeps the figures for the next stop", bool(cached.get("sig")), True)

    # A lock held by something that is not vm:check (review cc0a9ef9.1): the flock alone, with an empty owner or an owner pid whose argv is not vm:check, blocks as before.
    lock = runtime / "rediacc-vm-check.lock"
    for label, owner in (
        ("an empty owner", ""),
        ("an owner pid that is not vm:check", json.dumps({"pid": os.getpid()})),
        ("a malformed owner", "{not json"),
    ):
        lock.write_text(owner, encoding="utf-8")
        held = os.open(str(lock), os.O_RDWR)
        fcntl.flock(held, fcntl.LOCK_EX)
        try:
            got = hook_stop(fix, env)
        finally:
            fcntl.flock(held, fcntl.LOCK_UN)
            os.close(held)
        check("a fleet lock with %s still blocks" % label, got.decision, "block")

    # A running vm:check (the lock held by a process whose argv names the module, owner written the way vm_check.Lock.acquire writes it) holds the landing: reported, not blocked.
    lock.write_text("", encoding="utf-8")
    stand_in = (
        "import fcntl, json, os, sys\n"
        "fd = os.open(sys.argv[1], os.O_RDWR)\n"
        "fcntl.flock(fd, fcntl.LOCK_EX)\n"
        "os.ftruncate(fd, 0)\n"
        "os.pwrite(fd, json.dumps({'pid': os.getpid()}).encode(), 0)\n"
        "print('held', flush=True)\n"
        "sys.stdin.read()\n"
    )
    # A real interpreter run of a file named like the script (`python3 .../drills/vm_check.py <lock>`): argv_runs reads only the first operand (review 94493878.3), so a `-c` stand-in carrying the name as a trailing word no longer counts.
    vm_script = fix.base / "standins" / "drills" / "vm_check.py"
    vm_script.parent.mkdir(parents=True)
    vm_script.write_text(stand_in, encoding="utf-8")
    holder = subprocess.Popen(
        [sys.executable, str(vm_script), str(lock)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    if holder.stdin is None or holder.stdout is None:
        holder.kill()
        holder.wait(timeout=30)
        for pipe in (holder.stdin, holder.stdout):
            if pipe is not None:
                pipe.close()
        raise AssertionError("the stand-in holder was not started with pipes")
    try:
        check("the vm:check stand-in holds the lock", holder.stdout.readline().strip(), "held")
        got = hook_stop(fix, env)
    finally:
        holder.stdin.close()
        holder.stdout.close()
        holder.wait(timeout=30)
    check("a running vm:check lifts the block", got.decision, "allow")
    got = hook_stop(fix, env)
    check("a free fleet lock blocks again", got.decision, "block")
    check("a free fleet lock names the lease again", needle in got.out, True)

    fix.bg = json.dumps(
        [{"id": "wa1", "type": "subagent", "status": "running", "description": "w"}]
    )
    got = hook_stop(fix, env)
    check("a live writer lifts the block", needle in got.out, False)
    fix.bg = "[]"

    inside = {**json.loads(fix.event()), "cwd": str(lease)}
    got = hook_stop(fix, env, json.dumps(inside))
    check("a stop from inside the lease is not this block", needle in got.out, False)

    write_record(fix.proj, "w1", owner="cafe1234", agent="wa1")
    got = hook_stop(fix, env)
    check("a peer's lease is no block", got.decision, "allow")
    check("a peer's lease is no block text", needle in got.out, False)
    check("a peer's lease is reported once", got.out.count("peer lease w1"), 1)


def control_probes(tmp):
    """The vm:check lock-owner reader, called directly over a fake /proc: the argv must be an interpreter run of the script (a `tail` or `grep` that carries the path is not one) and an `Infinity` pid reads False (reviews a90d9cb2.1, d640b348.1 to .3)."""
    _by_file("paths").on_sys_path(SOURCE / "hooks/stop")
    import wl_checks

    fake = tmp / "fakeproc"
    pid = 4242
    (fake / str(pid)).mkdir(parents=True)

    def argv_is(*words):
        (fake / str(pid) / "cmdline").write_bytes(b"\0".join(w.encode() for w in words) + b"\0")

    vm = "rediacc_ci.drills.vm_check"
    holder = wl_checks.vm_check_holder
    raw = json.dumps({"pid": pid}).encode()
    argv_is("python3", "-m", vm)
    check("vm:check: the module run holds", holder(raw, proc=str(fake)), True)
    argv_is("python3", ".ci/rediacc_ci/drills/vm_check.py")
    check("vm:check: the file run holds", holder(raw, proc=str(fake)), True)
    argv_is("python3", "-", ".ci/rediacc_ci/drills/vm_check.py")
    check("vm:check: a stdin program is not a run", holder(raw, proc=str(fake)), False)
    argv_is("uv", "run", "python", ".ci/rediacc_ci/drills/vm_check.py")
    check("vm:check: a uv wrapper is not the lock holder", holder(raw, proc=str(fake)), False)
    argv_is("python3", "tools/lint.py", ".ci/rediacc_ci/drills/vm_check.py")
    check(
        "vm:check: a script that only takes the file as an argument is no run",
        holder(raw, proc=str(fake)),
        False,
    )
    argv_is("tail", "-f", "/repo/.ci/rediacc_ci/drills/vm_check.py")
    check("vm:check: a tail of the file is not a run", holder(raw, proc=str(fake)), False)
    check("vm:check: pid Infinity reads False", holder(b'{"pid": Infinity}', proc=str(fake)), False)


def section_stop():
    tmp = pathlib.Path(runtmp.run_dir("wl-worktrees-stop-")).resolve()
    for sub in ("t", "home", "cache"):
        (tmp / sub).mkdir()
    control_owner_blocks(tmp)
    control_peer(tmp)
    control_live(tmp)
    control_landed(tmp)
    control_hold(tmp)
    control_orphans(tmp)
    control_index(tmp)
    control_cache(tmp)
    control_submodule(tmp)
    control_landing_cut(tmp)
    control_lander(tmp)
    control_effort_table(tmp)
    control_real_hook(tmp)
    control_probes(tmp)


SECTIONS = {"root": section_root, "stop": section_stop}
FLOORS = {"root": CONTROL_FLOOR, "stop": STOP_FLOOR}


def run_sections(argv):
    wanted = argv or list(SECTIONS)
    unknown = [a for a in wanted if a not in SECTIONS]
    if unknown:
        sys.stderr.write("usage: test-wl_worktrees.py [%s]\n" % "|".join(SECTIONS))
        sys.exit(2)
    T.floor = sum(FLOORS[name] for name in wanted)
    for name in wanted:
        SECTIONS[name]()
    T.exit()


if __name__ == "__main__":
    run_sections(sys.argv[1:])

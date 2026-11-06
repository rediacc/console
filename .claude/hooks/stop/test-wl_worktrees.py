#!/usr/bin/env python3
"""Controls for lease trees and the Stop hook (agent/plans/PLAN-worktree-lease.md).

    python3 .claude/hooks/stop/test-wl_worktrees.py [root|stop]

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py. No argument runs every section.

`root` is W1: a lease tree's own copy of these hooks writes to the main checkout's store, and nothing else moves with it. Every control drives a fixture's hook copy in a child process, so WL_WORKTREES_TEST_CLAUDE=<dir> judges another `.claude` tree, the way the fail-before figures were read.

`stop` is W11: the Stop hook follows leases. `wl_worktrees.survey` is driven in a child process over fixture repositories, then the real hook over one fixture through wlfix.
"""

import ast
import datetime
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

# The two guards read CLAUDE_PROJECT_DIR, else show-toplevel. `_acts` and `_pushes` are the first calls handed the root, so the capture reads what their ledger lines would join to.
GUARD_ROOTS = """
import json, os, sys
sys.path.insert(0, sys.argv[1])
from rediacc_hooks import hookio
from rediacc_hooks.guards import block_backup_unverified_push as B
from rediacc_hooks.guards import block_turbo_early_push as P
seen = {}
def capture(name):
    def fn(cmd, root, base):
        seen[name] = str(root)
        return []
    return fn
P._acts = capture("turbo")
B._pushes = capture("backup")
env = {"CLAUDE_PROJECT_DIR": sys.argv[2]} if sys.argv[2] else {}
payload = json.dumps({"tool_input": {"command": "git status"}, "cwd": os.getcwd()})
P.run(hookio.Event(payload, env=env))
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
        check("block_turbo_early_push: the variable gives main", seen.get("turbo"), str(main))
        check(
            "block_backup_unverified_push: the variable gives main", seen.get("backup"), str(main)
        )
    # Why W5 has to confirm the variable: without it these two read the lease itself.
    code, out, err = pyrun(tmp, lease, GUARD_ROOTS, claude, "")
    if check("guards: read with the variable unset (%s)" % err[-200:], code, 0):
        seen = json.loads(out)
        check("block_turbo_early_push: no variable reads the lease", seen.get("turbo"), str(lease))
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
root, session, live, items, cache_path = sys.argv[2:7]
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
got = W.survey(root, session, json.loads(items), lambda: live, cache)
if cache_path:
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(got["cache"], fh)
got["statuses"] = len(statuses)
got["lines"] = W.unlanded_lines(got)
got["report"] = W.report_lines(got)
print(json.dumps(got))
"""
NOBODY: dict[str, list[str]] = {"ids": [], "trees": []}


def read(tmp, main, session=SID, live=NOBODY, items=(), cache=""):
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

    main = lease_main_repo(tmp, "pinned")
    lease = new_lease(tmp, main, "w1")
    base = git(tmp, main, "rev-parse", "HEAD")
    sha = commit_in(tmp, lease, "b.txt", "b\n")
    git(tmp, main, "update-ref", "refs/worktrees/w1", sha)
    git(tmp, lease, "checkout", "-q", "--detach", base)
    got = read(tmp, main)
    check("a pin past HEAD still counts", got["unlanded"][0]["commits"], {".": [sha]})


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


# The gh shim of test_wl_focus.py, whose imports reach pytest: this file runs under a bare python3.
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
    from rediacc_hooks.tests import test_wl_ci_status as ci_status
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
    # A private ci:quick clone path too, for the same reason: a real ci:quick on this machine holds its own clone lock.
    ciq_clone = fix.base / "ciq" / "clone"
    ciq_clone.parent.mkdir()
    env = {
        "CLAUDE_CONFIG_DIR": str(config),
        "XDG_RUNTIME_DIR": str(runtime),
        "CI_QUICK_CLONE_DIR": str(ciq_clone),
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
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            stand_in,
            str(lock),
            "rediacc_ci.drills.vm_check",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    if holder.stdin is None or holder.stdout is None:
        holder.kill()
        holder.wait(timeout=30)
        raise AssertionError("the stand-in holder was not started with pipes")
    try:
        check("the vm:check stand-in holds the lock", holder.stdout.readline().strip(), "held")
        got = hook_stop(fix, env)
    finally:
        holder.stdin.close()
        holder.wait(timeout=30)
    check("a running vm:check lifts the block", got.decision, "allow")
    got = hook_stop(fix, env)
    check("a free fleet lock blocks again", got.decision, "block")
    check("a free fleet lock names the lease again", needle in got.out, True)

    # A running ci:quick (#b872c325): landing moves HEAD and voids the receipt it writes, so its clone lock holds the landing the way the fleet lock does. The marker is `<clone>.lock`, `{"pid", "at"}` written by quick-clone.ts acquireLock; only a live pid whose argv names the script counts.
    ciq_lock = pathlib.Path(str(ciq_clone) + ".lock")
    held_text = "held for the running ci:quick"
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait(timeout=30)
    for label, owner in (
        ("a stale marker (its pid is gone)", json.dumps({"pid": dead.pid, "at": "x"})),
        ("a marker whose pid is not ci:quick", json.dumps({"pid": os.getpid(), "at": "x"})),
        ("a malformed marker", "{not json"),
    ):
        ciq_lock.write_text(owner, encoding="utf-8")
        got = hook_stop(fix, env)
        check("%s still blocks" % label, got.decision, "block")
        check("%s is not reported as held" % label, held_text in got.out, False)
    ciq_lock.unlink()
    # The stand-in writes the owner the way acquireLock does, `at` from `new Date().toISOString()` shifted by argv[2] seconds, from the cwd it is started in.
    ciq_stand_in = (
        "import datetime, json, os, sys\n"
        "at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=int(sys.argv[2]))\n"
        "stamp = at.strftime('%Y-%m-%dT%H:%M:%S.000Z')\n"
        "open(sys.argv[1], 'x').write(json.dumps({'pid': os.getpid(), 'at': stamp}))\n"
        "print('held', flush=True)\n"
        "sys.stdin.read()\n"
        "os.remove(sys.argv[1])\n"
    )

    def ciq_stop(age_s, cwd):
        """One Stop while a ci:quick stand-in, its lock `age_s` old and its cwd `cwd`, holds the marker."""
        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                ciq_stand_in,
                str(ciq_lock),
                str(age_s),
                "scripts/ci-runner/quick-clone.ts",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            cwd=str(cwd),
        )
        stand_in_in, stand_in_out = holder.stdin, holder.stdout
        if stand_in_in is None or stand_in_out is None:
            holder.kill()
            holder.wait(timeout=30)
            raise SystemExit("the ci:quick stand-in was started without its stdin/stdout pipes")
        try:
            check("the ci:quick stand-in holds the marker", stand_in_out.readline().strip(), "held")
            return hook_stop(fix, env)
        finally:
            stand_in_in.close()
            holder.wait(timeout=30)

    # The design review of 581e1fe96: a live matching pid is not enough. A lock older than twice quick-clone.ts's LOCK_WAIT_MS (3 h) is not a run worth holding for, and a ci:quick whose cwd is another checkout is not this checkout's run.
    got = ciq_stop(4 * 3600, fix.proj)
    check("a ci:quick lock older than twice the wait still blocks", got.decision, "block")
    check("an old ci:quick lock is not reported as held", held_text in got.out, False)
    foreign = fix.base / "another-checkout"
    foreign.mkdir()
    got = ciq_stop(0, foreign)
    check("a ci:quick of another checkout still blocks", got.decision, "block")
    check("a foreign ci:quick is not reported as held", held_text in got.out, False)

    got = ciq_stop(0, fix.proj)
    check("a running ci:quick lifts the block", got.decision, "allow")
    check("a running ci:quick reports the hold", held_text in got.out, True)
    check("the hold names the lease", "    w1 (" in got.out, True)
    check("the run ended and removed its marker", ciq_lock.exists(), False)
    got = hook_stop(fix, env)
    check("a free ci:quick marker blocks again", got.decision, "block")
    check("a free ci:quick marker names the lease again", needle in got.out, True)

    # The age cap mirrors quick-clone.ts's LOCK_WAIT_MS; a change on either side alone fails here.
    ts_text = (_REAL.parents[3] / "scripts/ci-runner/quick-clone.ts").read_text(encoding="utf-8")
    ts_wait = re.search(r"^const LOCK_WAIT_MS = ([0-9_ *]+);$", ts_text, re.MULTILINE)
    checks_tree = ast.parse((SOURCE / "hooks/stop/wl_checks.py").read_text(encoding="utf-8"))
    py_wait = next(
        (
            node.value
            for node in checks_tree.body
            if isinstance(node, ast.Assign)
            and any(getattr(t, "id", "") == "CI_QUICK_LOCK_WAIT_S" for t in node.targets)
        ),
        None,
    )

    def _product(text):
        out = 1
        for part in text.replace("_", "").split("*"):
            out *= int(part.strip())
        return out

    check("quick-clone.ts still declares LOCK_WAIT_MS", ts_wait is not None, True)
    check("wl_checks still declares CI_QUICK_LOCK_WAIT_S", py_wait is not None, True)
    if ts_wait is not None and py_wait is not None:
        check(
            "CI_QUICK_LOCK_WAIT_S is quick-clone.ts's LOCK_WAIT_MS in seconds",
            _product(ast.unparse(py_wait)) * 1000,
            _product(ts_wait.group(1)),
        )

    fix.bg = json.dumps(
        [{"id": "wa1", "type": "subagent", "status": "running", "description": "w"}]
    )
    got = hook_stop(fix, env)
    check("a live writer lifts the block", needle in got.out, False)
    fix.bg = "[]"

    inside = {**json.loads(fix.event()), "cwd": str(lease)}
    got = hook_stop(fix, env, json.dumps(inside))
    check("a stop from inside the lease is not this block", needle in got.out, False)

    phase = ("--phase", wlfix.ME, "babysit", "--branch", "pub", "--pr", "543")
    check("the phase is declared", fix.cli(*phase).rc, 0)
    got = hook_stop(fix, env)
    check("a babysit phase keeps the block", got.decision, "block")
    check("a babysit phase keeps the text", needle in got.out, True)
    check("the phase ends", fix.cli("--phase", wlfix.ME, "build").rc, 0)

    write_record(fix.proj, "w1", owner="cafe1234", agent="wa1")
    got = hook_stop(fix, env)
    check("a peer's lease is no block", got.decision, "allow")
    check("a peer's lease is no block text", needle in got.out, False)
    check("a peer's lease is reported once", got.out.count("peer lease w1"), 1)


def control_probes(tmp):
    """The lock-owner readers, called directly over a fake /proc: the argv must be an interpreter run of the script (a `tail` or `grep` that carries the path is not one), an `Infinity` pid reads False, and a host with no /proc reads False (reviews a90d9cb2.1, d640b348.1 to .3)."""
    sys.path.insert(0, str(SOURCE / "hooks/stop"))
    import wl_checks

    fake = tmp / "fakeproc"
    root = tmp / "probe-root"
    root.mkdir()
    pid = 4242
    (fake / str(pid)).mkdir(parents=True)
    (fake / str(pid) / "cwd").symlink_to(root)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    lock = tmp / "probe.lock"

    def argv_is(*words):
        (fake / str(pid) / "cmdline").write_bytes(b"\0".join(w.encode() for w in words) + b"\0")

    def ciq(raw=None, proc=str(fake)):
        lock.write_text(raw or json.dumps({"pid": pid, "at": stamp}), encoding="utf-8")
        return wl_checks.ci_quick_running(str(root), path=str(lock), proc=proc)

    script = "scripts/ci-runner/quick-clone.ts"
    argv_is("node", "--require", "p.cjs", script)
    check("ci:quick: an interpreter run of the script holds", ciq(), True)
    argv_is("grep", script)
    check("ci:quick: a grep naming the script is not a run", ciq(), False)
    argv_is("node", "xci-runner/quick-clone.ts")
    check("ci:quick: a word that only ends with the path is not the script", ciq(), False)
    argv_is("node", script)
    check(
        "ci:quick: pid Infinity reads False, not a raise",
        ciq('{"pid": Infinity, "at": "x"}'),
        False,
    )
    check("ci:quick: a host with no /proc reads False", ciq(proc=str(tmp / "no-proc")), False)

    vm = "rediacc_ci.drills.vm_check"
    holder = wl_checks.vm_check_holder
    raw = json.dumps({"pid": pid}).encode()
    argv_is("python3", "-m", vm)
    check("vm:check: the module run holds", holder(raw, proc=str(fake)), True)
    argv_is("python3", ".ci/rediacc_ci/drills/vm_check.py")
    check("vm:check: the file run holds", holder(raw, proc=str(fake)), True)
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
    control_orphans(tmp)
    control_index(tmp)
    control_cache(tmp)
    control_submodule(tmp)
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

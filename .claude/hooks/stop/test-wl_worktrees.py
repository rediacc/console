#!/usr/bin/env python3
"""Controls for lease trees and the Stop hook (agent/plans/PLAN-worktree-lease.md).

    python3 .claude/hooks/stop/test-wl_worktrees.py [root]

Auto-discovered by TAILED in .claude/rediacc_hooks/tests/test_hooks_delegates.py. No argument runs every section.

`root` is W1: a lease tree's own copy of these hooks writes to the main checkout's store, and nothing else moves with it. Every control drives a fixture's hook copy in a child process, so WL_WORKTREES_TEST_CLAUDE=<dir> judges another `.claude` tree, the way the fail-before figures were read.
"""

import ast
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys

_REAL = pathlib.Path(__file__).resolve()
_CI = _REAL.parents[3] / ".ci" / "rediacc_ci"
SOURCE = pathlib.Path(os.environ.get("WL_WORKTREES_TEST_CLAUDE") or _REAL.parents[2])
ME = "cafe0000"
SID = ME + "-0000-4000-8000-000000000000"
CONTROL_FLOOR = 40


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
    program = "import sys; sys.path.insert(0, sys.argv[1]); import wl_core as C; print(C.worklist_for(sys.argv[2]))"
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
    twin = ast.parse(text)
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


SECTIONS = {"root": section_root}


def run_sections(argv):
    wanted = argv or list(SECTIONS)
    unknown = [a for a in wanted if a not in SECTIONS]
    if unknown:
        sys.stderr.write("usage: test-wl_worktrees.py [%s]\n" % "|".join(SECTIONS))
        sys.exit(2)
    for name in wanted:
        SECTIONS[name]()
    T.exit()


if __name__ == "__main__":
    run_sections(sys.argv[1:])

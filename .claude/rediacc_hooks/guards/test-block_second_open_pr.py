#!/usr/bin/env python3
"""Control harness for block_second_open_pr: WHICH repository's open PRs a `gh pr create` is counted against (worklist #29531257).

THE LIVE CASE, 2026-11-11, console PR 605 open on 1104-1: `for s in renet account elite; do (cd private/$s && gh pr create ...); done`, run from the console, was refused as a second open PR in rediacc/console. The guard read the repository from the SESSION cwd's origin whenever the `cd` did not literally name `private/<submodule>`, so a create in any other directory was counted against the console. The repository is now read as gh reads it: `--repo`/`-R`/`GH_REPO`, else the directory the call really runs in after its `cd`s, else the session cwd; a `cd` target the walk cannot expand is refused as unverifiable, never guessed as the console.

REAL REPOSITORIES under a `rediacc_ci.runtmp` run directory: a console checkout whose origin is rediacc/console, a `private/renet` checkout whose origin is rediacc/renet, and a checkout outside `private/` whose origin is rediacc/elite. `gh` is stubbed on PATH: it answers `gh pr list --repo <r>` with one open PR for rediacc/console, and none (or, in the second stub, one on another branch) for renet and elite.

BOTH DIRECTIONS. The submodule creates are admitted; a second console PR, a submodule that already has an open PR, and a `cd` into a missing directory (the shell stays in the console) are refused.
"""

import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parent
DISPATCH = str(HERE.parent / "dispatch.py")
STEM = "block_second_open_pr"

_RUNTMP = importlib.util.spec_from_file_location(
    "runtmp", HERE.parents[2] / ".ci" / "rediacc_ci" / "runtmp.py"
)
if _RUNTMP is None or _RUNTMP.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/runtmp.py is missing" % __file__)
runtmp = importlib.util.module_from_spec(_RUNTMP)
_RUNTMP.loader.exec_module(runtmp)
RUN_TMP = runtmp.run_dir("guard-second-open-pr-")

# The well-known repo slugs and origin, read from .ci/config/well-known.env by the CI reader, loaded by file like runtmp above (check:ci-literal-sources forbids spelling them).
_WK = importlib.util.spec_from_file_location(
    "well_known_for_second_open_pr", HERE.parents[2] / ".ci" / "rediacc_ci" / "well_known.py"
)
if _WK is None or _WK.loader is None:
    raise SystemExit("%s: .ci/rediacc_ci/well_known.py is missing" % __file__)
well_known = importlib.util.module_from_spec(_WK)
_WK.loader.exec_module(well_known)
GH_ORIGIN, GH_REPO = well_known.GH_ORIGIN, well_known.GH_REPO
RENET_REPO, ELITE_REPO = well_known.RENET_REPO, well_known.ELITE_REPO

_GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")


def checkout(path, origin):
    path = pathlib.Path(path)
    path.mkdir(parents=True)
    for argv in (
        ["init", "-q", "--initial-branch=main"],
        ["remote", "add", "origin", "%s/%s.git" % (GH_ORIGIN, origin)],
    ):
        subprocess.run(["git", *argv], cwd=path, check=True, capture_output=True, env=_GIT_ENV)
    return path


ROOT = checkout(pathlib.Path(tempfile.mkdtemp(prefix="console-", dir=RUN_TMP)) / "console", GH_REPO)
checkout(ROOT / "private" / "renet", RENET_REPO)
OTHER = checkout(ROOT / "work" / "elite-co", ELITE_REPO)

_OPEN = '[{"number":%d,"title":"t","headRefName":"%s","isDraft":true}]'
_STUB = (
    "#!/bin/sh\n"
    'repo=""\n'
    'while [ $# -gt 0 ]; do [ "$1" = --repo ] && repo="$2"; shift; done\n'
    'case "$repo" in\n'
    "  %s) echo '%s' ;;\n"
    "  %s) echo '%s' ;;\n"
    "  *) echo '[]' ;;\n"
    "esac\n"
)


def stub(body):
    d = pathlib.Path(tempfile.mkdtemp(prefix="stub-", dir=RUN_TMP))
    (d / "gh").write_text(body, encoding="utf-8")
    (d / "gh").chmod(0o755)
    return str(d)


GH_CONSOLE_OPEN = stub(_STUB % (GH_REPO, _OPEN % (605, "1104-1"), RENET_REPO, "[]"))
GH_RENET_OPEN = stub(_STUB % (GH_REPO, _OPEN % (605, "1104-1"), RENET_REPO, _OPEN % (77, "1031-2")))
GH_DOWN = stub("#!/bin/sh\necho 'gh: could not connect'\nexit 1\n")

CREATE = "gh pr create --draft --base main --head 1104-1 -t x -b y"
ALREADY = "already have 1 open PR(s) in %s"
UNVERIFIED = "cannot verify"

CASES = [
    # (name, command, gh, expect_blocked, stderr needle)
    (
        "cd <abs>/private/renet && create",
        "cd %s && %s" % (ROOT / "private" / "renet", CREATE),
        GH_CONSOLE_OPEN,
        False,
        "",
    ),
    ("cd private/renet && create", "cd private/renet && " + CREATE, GH_CONSOLE_OPEN, False, ""),
    (
        "cd into a checkout outside private/ is judged against ITS origin",
        "cd work/elite-co && " + CREATE,
        GH_CONSOLE_OPEN,
        False,
        "",
    ),
    (
        "a subshell cd into that checkout too",
        "(cd %s && %s)" % (OTHER, CREATE),
        GH_CONSOLE_OPEN,
        False,
        "",
    ),
    ("--repo names the submodule", CREATE + " --repo " + RENET_REPO, GH_CONSOLE_OPEN, False, ""),
    ("-R names the submodule", CREATE + " -R " + RENET_REPO, GH_CONSOLE_OPEN, False, ""),
    (
        "--repo beats the cd",
        "cd private/renet && %s --repo %s" % (CREATE, GH_REPO),
        GH_CONSOLE_OPEN,
        True,
        ALREADY % GH_REPO,
    ),
    # The live 2026-11-11 shape: the directory is a loop variable, so the repo is unknown, never the console.
    (
        "the live loop: cd private/$s",
        "for s in renet account elite; do (cd private/$s && %s); done" % CREATE,
        GH_CONSOLE_OPEN,
        True,
        "cd private/$s",
    ),
    # 3e82900b.2: `cd -` returns to a directory the walk never saw, so it is unverifiable, not the session repo.
    (
        "cd - is a directory the hook cannot evaluate",
        "cd -; " + CREATE,
        GH_CONSOLE_OPEN,
        True,
        "cd -",
    ),
    # ---- controls
    (
        "a second console PR from the console",
        CREATE,
        GH_CONSOLE_OPEN,
        True,
        ALREADY % GH_REPO,
    ),
    (
        "a submodule that already has an open PR on another branch",
        "cd private/renet && " + CREATE,
        GH_RENET_OPEN,
        True,
        ALREADY % RENET_REPO,
    ),
    (
        "a cd into a missing directory leaves the shell in the console",
        "cd private/missing; " + CREATE,
        GH_CONSOLE_OPEN,
        True,
        ALREADY % GH_REPO,
    ),
    ("gh down fails closed", "cd private/renet && " + CREATE, GH_DOWN, True, UNVERIFIED),
]


def run(command, gh):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(ROOT), PATH="%s:%s" % (gh, os.environ["PATH"]))
    env.pop("GH_REPO", None)
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(ROOT)}
    )
    proc = subprocess.run(
        [sys.executable, DISPATCH, STEM],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if proc.returncode not in (0, 2):
        raise SystemExit("guard crashed (rc %d): %s" % (proc.returncode, proc.stderr[-800:]))
    return proc.returncode == 2, proc.stderr


# --------------------------------------------------------------------------- two trees (agent/plans/PLAN-two-track-merge-dev.md, box LT4) ---------------------------------------------------------------------------
#
# A REAL TWO-TREE REPOSITORY: the development checkout on `1121-1` and a linked landing tree on `1104-1`, both with the console origin. The landing record and the tree role are read through the guard's two seams, `_landing_record` and `_tree_role`, which the in-process pass replaces with what LT1's `commit_policy.landing_record` and `tree_role` answer for this world ({path: the landing tree's realpath, branch: 1104-1}; the role "landing" exactly in that tree).
# Once commit_policy carries `write_landing_record` (LT1), the same table runs a second time through dispatch.py against a REAL record in the common git directory, with no seam replaced.
#
# BOTH DIRECTIONS. Admitted: the development draft beside the landing PR (`--draft`, `-d`, `--head <its branch>`), a submodule create, `gh pr ready` on the landing PR, `gh pr ready --undo`, and a ready once the landing PR is closed. Refused: a non-draft, `--draft=false`, a second draft, a draft beside any other open PR, a draft from the landing tree, from another head or naming the landing branch, two drafts in one command, `gh pr ready` on the draft by number, URL, branch or current branch, and an unreadable list.
# With no record the draft is refused and the ready admitted, which is the guard's answer before LT4.
#
# THE DEFECT CONTROL. The module's declared DEFECT is planted in a copy and the in-process table must change at least one answer; a table the defect leaves green proves nothing about the admission.

LANDING_BRANCH, DEV_BRANCH = "1104-1", "1121-1"
_GITC = ["-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid"]


def _git(path, *argv):
    subprocess.run(["git", *_GITC, *argv], cwd=path, check=True, capture_output=True, env=_GIT_ENV)


DEV = checkout(pathlib.Path(tempfile.mkdtemp(prefix="two-", dir=RUN_TMP)) / "console", GH_REPO)
_git(DEV, "checkout", "-q", "-b", DEV_BRANCH)
_git(DEV, "commit", "-q", "--allow-empty", "-m", "base")
DEV = pathlib.Path(os.path.realpath(DEV))
LANDING = DEV.parent / "console-landing"
_git(DEV, "worktree", "add", "-q", "-b", LANDING_BRANCH, str(LANDING))
RECORD = {"path": str(LANDING), "branch": LANDING_BRANCH}

_PR_LANDING = '{"number":605,"title":"landing","headRefName":"%s","isDraft":false}' % LANDING_BRANCH
_PR_DRAFT = '{"number":606,"title":"dev","headRefName":"%s","isDraft":true}' % DEV_BRANCH
_PR_OTHER = '{"number":607,"title":"other","headRefName":"0901-3","isDraft":true}'
G_NONE = stub(_STUB % (GH_REPO, "[]", RENET_REPO, "[]"))
G_LANDING = stub(_STUB % (GH_REPO, "[%s]" % _PR_LANDING, RENET_REPO, "[]"))
G_LANDING_DRAFT = stub(_STUB % (GH_REPO, "[%s,%s]" % (_PR_LANDING, _PR_DRAFT), RENET_REPO, "[]"))
G_LANDING_OTHER = stub(_STUB % (GH_REPO, "[%s,%s]" % (_PR_LANDING, _PR_OTHER), RENET_REPO, "[]"))
G_DRAFT_ONLY = stub(_STUB % (GH_REPO, "[%s]" % _PR_DRAFT, RENET_REPO, "[]"))

DRAFT = "gh pr create --draft --base main -t x -b y"
ALREADY1 = ALREADY % GH_REPO
READY = "`gh pr ready` on"

TWO_TREE_CASES = [
    # (name, command, tree, gh, expect_blocked, stderr needle)
    ("the development draft beside the landing PR", DRAFT, DEV, G_LANDING, False, ""),
    ("-d is --draft", "gh pr create -d -t x -b y", DEV, G_LANDING, False, ""),
    (
        "--head naming the development branch",
        DRAFT + " --head " + DEV_BRANCH,
        DEV,
        G_LANDING,
        False,
        "",
    ),
    ("--head owner:branch", DRAFT + " -H rediacc:" + DEV_BRANCH, DEV, G_LANDING, False, ""),
    ("the first PR with nothing open, as before", DRAFT, DEV, G_NONE, False, ""),
    (
        "a submodule create is not judged by the console record",
        DRAFT + " --repo " + RENET_REPO,
        DEV,
        G_LANDING,
        False,
        "",
    ),
    (
        "a non-draft beside the landing PR",
        "gh pr create -t x -b y",
        DEV,
        G_LANDING,
        True,
        "TWO TREES",
    ),
    (
        "--draft=false is not a draft",
        "gh pr create --draft=false -t x",
        DEV,
        G_LANDING,
        True,
        ALREADY1,
    ),
    ("a second draft from the development branch", DRAFT, DEV, G_LANDING_DRAFT, True, ALREADY1),
    ("a draft beside an open PR of another branch", DRAFT, DEV, G_LANDING_OTHER, True, ALREADY1),
    ("a draft from the landing tree", DRAFT, LANDING, G_LANDING, True, ALREADY1),
    (
        "a draft whose head is another branch",
        DRAFT + " --head 0901-3",
        DEV,
        G_LANDING,
        True,
        ALREADY1,
    ),
    (
        "a draft whose head is the landing branch",
        DRAFT + " --head " + LANDING_BRANCH,
        DEV,
        G_LANDING,
        True,
        ALREADY1,
    ),
    (
        "two drafts in one command",
        "gh pr create -d -t a; gh pr create -d -t b",
        DEV,
        G_LANDING,
        True,
        ALREADY1,
    ),
    ("a development draft while gh is down", DRAFT, DEV, GH_DOWN, True, UNVERIFIED),
    # ---- gh pr ready
    (
        "ready on the current (development) branch",
        "gh pr ready",
        DEV,
        G_LANDING_DRAFT,
        True,
        READY + " " + DEV_BRANCH,
    ),
    ("ready on the draft by number", "gh pr ready 606", DEV, G_LANDING_DRAFT, True, READY),
    (
        "ready on the draft by URL",
        "gh pr ready https://github.com/x/y/pull/606",
        DEV,
        G_LANDING_DRAFT,
        True,
        READY,
    ),
    (
        "ready on the draft by branch",
        "gh pr ready " + DEV_BRANCH,
        LANDING,
        G_LANDING_DRAFT,
        True,
        READY,
    ),
    ("ready while gh is down", "gh pr ready 606", DEV, GH_DOWN, True, UNVERIFIED),
    (
        "ready on the landing PR from the landing tree",
        "gh pr ready",
        LANDING,
        G_LANDING_DRAFT,
        False,
        "",
    ),
    ("ready on the landing PR by number", "gh pr ready 605", DEV, G_LANDING_DRAFT, False, ""),
    ("ready --undo", "gh pr ready --undo 606", DEV, G_LANDING_DRAFT, False, ""),
    ("ready once the landing PR is closed", "gh pr ready 606", DEV, G_DRAFT_ONLY, False, ""),
]

# With no landing record: the guard's answer before LT4.
NO_RECORD_CASES = [
    ("no record: the draft is a second PR", DRAFT, DEV, G_LANDING, True, ALREADY1),
    ("no record: ready is not judged", "gh pr ready 606", DEV, G_LANDING_DRAFT, False, ""),
]

# Loaded by name after the path hop, as dispatch.py loads them.
sys.path.insert(0, str(HERE.parents[1]))
_guards = importlib.import_module("rediacc_hooks.guards")
_hookio = importlib.import_module("rediacc_hooks.hookio")
GUARD = _guards.load(STEM)


def _seams(module, record):
    """Replace the module's landing seams with what LT1 answers for this world (`record` None: no record)."""

    def landing_record(_root):
        return dict(record) if record else None

    def tree_role(root):
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        return "landing" if record and os.path.realpath(top) == record["path"] else "development"

    module._landing_record = landing_record
    module._tree_role = tree_role


def run_inproc(module, command, tree, gh):
    saved = dict(os.environ)
    os.environ["PATH"] = "%s:%s" % (gh, saved["PATH"])
    os.environ.pop("GH_REPO", None)
    try:
        payload = json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(tree)}
        )
        event = _hookio.Event(payload, cwd=str(tree), env=dict(os.environ))
        rc, _, err = event.result(module.run(event))
    finally:
        os.environ.clear()
        os.environ.update(saved)
    return rc == 2, err


def run_tree(command, tree, gh):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(tree), PATH="%s:%s" % (gh, os.environ["PATH"]))
    env.pop("GH_REPO", None)
    payload = json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(tree)}
    )
    proc = subprocess.run(
        [sys.executable, DISPATCH, STEM],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if proc.returncode not in (0, 2):
        raise SystemExit("guard crashed (rc %d): %s" % (proc.returncode, proc.stderr[-800:]))
    return proc.returncode == 2, proc.stderr


def _defective():
    """The guard with its declared DEFECT planted, as a fresh module."""
    source = pathlib.Path(GUARD.__file__).read_text(encoding="utf-8")
    old, new = GUARD.DEFECT
    # Twice: once in the declaration, once in the line it plants.
    if source.count(old) != 2:
        raise SystemExit("DEFECT %r does not apply once outside its declaration" % old)
    broken = types.ModuleType("broken_" + STEM)
    broken.__file__ = GUARD.__file__
    exec(compile(source.replace(old, new), GUARD.__file__, "exec"), broken.__dict__)
    return broken


def judge(label, table, runner):
    """Run `table` through `runner`; (answers, failures)."""
    answers, failures = [], 0
    for name, command, tree, gh, want, needle in table:
        got, err = runner(command, tree, gh)
        answers.append(got)
        ok = got == want and (not needle or needle in err)
        failures += not ok
        print(
            "%-64s want=%-8s got=%-8s %s"
            % (
                "[%s] %s" % (label, name) if label else name,
                "BLOCKED" if want else "allowed",
                "BLOCKED" if got else "allowed",
                "ok" if ok else "*** FAIL ***",
            )
        )
        if not ok:
            print("    needle %r; stderr: %s" % (needle, err.strip().splitlines()[:4]))
    return answers, failures


RESULTS = [
    judge("", [(n, c, ROOT, g, w, s) for n, c, g, w, s in CASES], lambda c, _t, g: run(c, g))
]

_seams(GUARD, RECORD)
RESULTS.append(judge("seam", TWO_TREE_CASES, lambda c, t, g: run_inproc(GUARD, c, t, g)))
_seams(GUARD, None)
RESULTS.append(judge("seam", NO_RECORD_CASES, lambda c, t, g: run_inproc(GUARD, c, t, g)))

BROKEN = _defective()
_seams(BROKEN, RECORD)
bad = [run_inproc(BROKEN, c, t, g)[0] for _, c, t, g, _, _ in TWO_TREE_CASES]
flipped = [case[0] for case, x, y in zip(TWO_TREE_CASES, RESULTS[1][0], bad, strict=True) if x != y]
print("DEFECT control: %d two-tree answer(s) change with the defect planted" % len(flipped))
fails = sum(f for _, f in RESULTS)
if not flipped:
    print("*** FAIL *** the declared DEFECT changes no answer of the two-tree table")
    fails += 1

_cp = GUARD.commit_policy
if hasattr(_cp, "write_landing_record"):
    _cp.write_landing_record(str(DEV), str(LANDING), LANDING_BRANCH)
    REAL = [judge("record", TWO_TREE_CASES, run_tree)]
    os.unlink(_cp.landing_record_path(str(DEV)))
    REAL.append(judge("record", NO_RECORD_CASES, run_tree))
    fails += sum(f for _, f in REAL)
    RESULTS += REAL
else:
    print("real-record pass: NOT RUN, commit_policy has no write_landing_record yet (box LT1)")

answers = [a for got, _ in RESULTS for a in got]
blocked, total = sum(answers), len(answers)
if blocked in (0, total):
    print("*** FAIL *** the guard answered the same way on every case")
    fails += 1
print("%d case(s), %d blocked, %d allowed" % (total, blocked, total - blocked))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)

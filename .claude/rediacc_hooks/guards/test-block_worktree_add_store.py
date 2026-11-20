#!/usr/bin/env python3
"""Control harness for the landing arm's repository check in block_worktree_add (review ba3cb63e.1).

    python3 .claude/rediacc_hooks/guards/test-block_worktree_add_store.py                 rc 0
    python3 .claude/rediacc_hooks/guards/test-block_worktree_add_store.py --plant-defect  rc 1: the guard runs with the repository check removed

A bare operand such as `console-landing` is read against the landing paths only for a run aimed at the repository those paths belong to. A run aimed at another repository resolves the word against its own trees, so it is admitted; a path operand that resolves into a landing tree is refused wherever the run is aimed. The functions are driven directly, so no tree needs to exist on disk.
"""

import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
GUARD = HERE / "block_worktree_add.py"
DEFECT = ("bare = same_store is None or redirected or same_store(here)", "bare = True")
# The redirect arm (review c6f3f605.1): with it removed, a GIT_DIR or --git-dir naming this repository beside a -C elsewhere is admitted.
REDIRECT_DEFECT = ("redirected = bool(_GIT_REPO_REDIRECT.search(cmd))", "redirected = False")
PLANT_REDIRECT = "--plant-redirect-defect" in sys.argv[1:]
PLANT = "--plant-defect" in sys.argv[1:]


def load():
    text = GUARD.read_text(encoding="utf-8")
    if PLANT:
        if DEFECT[0] not in text:
            raise SystemExit("%s: the planted line is gone from the guard" % __file__)
        text = text.replace(*DEFECT)
    if PLANT_REDIRECT:
        if REDIRECT_DEFECT[0] not in text:
            raise SystemExit("%s: the planted redirect line is gone from the guard" % __file__)
        text = text.replace(*REDIRECT_DEFECT)
    spec = importlib.util.spec_from_file_location("guard_under_test", str(GUARD))
    if spec is None or spec.loader is None:
        raise SystemExit("%s: cannot load %s" % (__file__, GUARD))
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HERE.parents[1]))
    exec(compile(text, str(GUARD), "exec"), module.__dict__)
    return module


guard = load()
LANDING = "/srv/work/console-landing"
OTHER = "/srv/elsewhere/repo"
ROWS = [
    ("bare word, run aimed at this repository", "git worktree remove console-landing", True, True),
    ("bare word, no repository check given", "git worktree remove console-landing", None, True),
    (
        "CONTROL: bare word, run aimed at another repository",
        "git -C %s worktree remove console-landing" % OTHER,
        False,
        False,
    ),
    (
        "path operand into the landing tree, run aimed at another repository",
        "git -C %s worktree remove %s" % (OTHER, LANDING),
        False,
        True,
    ),
    (
        "GIT_DIR names this repository beside -C elsewhere: refused (review c6f3f605.1)",
        "GIT_DIR=/srv/work/console/.git git -C %s worktree remove console-landing" % OTHER,
        False,
        True,
    ),
    (
        "--git-dir names this repository beside -C elsewhere: refused",
        "git -C %s --git-dir=/srv/work/console/.git worktree remove console-landing" % OTHER,
        False,
        True,
    ),
    (
        "an exported GIT_DIR earlier in the command: refused",
        "export GIT_DIR=/srv/work/console/.git; git -C %s worktree remove console-landing" % OTHER,
        False,
        True,
    ),
]

failures = []
for label, cmd, same, want in ROWS:
    store = None if same is None else (lambda _here, _same=same: _same)
    got = guard.runs_landing_verb(cmd, "/srv/work/console", (LANDING,), store)
    if got != want:
        failures.append(label)
        print("*** FAIL *** %s: got %r, want %r" % (label, got, want))
    else:
        print("ok   %s" % label)
if failures:
    print("%d row(s) failed" % len(failures))
    sys.exit(1)
print("all %d rows hold" % len(ROWS))

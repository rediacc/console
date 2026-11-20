#!/usr/bin/env python3
"""Controls for wl_stack (PLAN-two-track-merge-dev LT19), on real temporary repositories.

    python3 .claude/hooks/stop/test-landing-stack.py     rc 0 when every control holds and every mutant turns them red

A bare repository plays origin; its clone plays the main checkout (the development tree), and a linked tree of that clone, bound by the landing record, plays the landing tree. A rebase-merge is a second clone that cherry-picks the landing commits onto main and pushes, so main holds copies with new shas, as GitHub's rebase-merge leaves them.

Each MUTANT is wl_stack's own source with one arm broken, loaded in-process from that text; the controls must fail against every one of them, so none can pass vacuously.

The landing tree is made with git's linked-tree verb, so block_worktree_add admits this file only once it is committed.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import types

HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE / "wl_stack.py"
LANDING = "1120-1"
DEVELOPMENT = "1121-1"
NEXT = "1122-1"

MUTANTS = [
    (
        "ancestry ignored: behind reads current",
        "    if rc == 0:\n        return StackState(CURRENT, **base)",
        "    if True:\n        return StackState(CURRENT, **base)",
    ),
    ("merged never read", "        if how:\n", "        if False:\n"),
    (
        "an unabsorbed landing commit read as absorbed",
        '    if marks is None or "+" in marks:',
        "    if marks is None:",
    ),
    (
        "the behind report blocks",
        '    return _merged_text(st) if st.state == MERGED else ""',
        '    return _merged_text(st) if st.state in (MERGED, BEHIND) else ""',
    ),
    (
        "the landing tree judged as a development tree",
        "    if record is None or cp.tree_role(str(root)) == cp.ROLE_LANDING:",
        "    if record is None:",
    ),
    (
        "the PR answer ignored for an empty landing branch",
        "    if pr_merged(root, landing):",
        "    if False:",
    ),
]

IDENT = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]


def sh(cwd, *args) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise SystemExit("fixture: git %s failed in %s: %s" % (" ".join(args), cwd, r.stderr))
    return r.stdout.strip()


def commit(cwd, name: str) -> str:
    (pathlib.Path(cwd) / name).write_text(name + "\n", encoding="utf-8")
    sh(cwd, "add", name)
    sh(cwd, *IDENT, "commit", "-qm", name)
    return sh(cwd, "rev-parse", "HEAD")


def load(text: str | None = None) -> types.ModuleType:
    """wl_stack from its file, or from `text` (a mutant) with the same `__file__`, so its hop to `.claude/rediacc_hooks` resolves identically."""
    name = "wl_stack_under_test"
    if text is None:
        spec = importlib.util.spec_from_file_location(name, SOURCE)
        if spec is None or spec.loader is None:
            raise SystemExit("%s is missing" % SOURCE)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod
    mod = types.ModuleType(name)
    mod.__file__ = str(SOURCE)
    sys.modules[name] = mod
    exec(compile(text, str(SOURCE), "exec"), mod.__dict__)
    return mod


def no_pr(_root, _branch) -> bool:
    return False


def merged_pr(_root, _branch) -> bool:
    return True


def controls(ws: types.ModuleType, cp) -> list[str]:
    fails: list[str] = []
    ran = [0]

    def control(label: str, ok: bool, detail: object = "") -> None:
        ran[0] += 1
        if not ok:
            fails.append("%s %s" % (label, detail))

    with tempfile.TemporaryDirectory() as raw:
        td = pathlib.Path(raw).resolve()
        remote = td / "remote.git"
        sh(td, "init", "-q", "--bare", "-b", "main", str(remote))
        main = td / "main"
        sh(td, "clone", "-q", str(remote), str(main))
        sh(main, "checkout", "-q", "-B", "main")
        commit(main, "base.txt")
        sh(main, "push", "-q", "origin", "main")
        landing = td / "landing"
        sh(main, "worktree", "add", "-q", "-b", LANDING, str(landing), "main")
        sh(main, "checkout", "-q", "-b", DEVELOPMENT)
        commit(main, "dev-1.txt")

        def state(root=main, pr=no_pr):
            return ws.stack_state(root, pr_merged=pr)

        # No record: every answer is quiet.
        got = state()
        control("NONE: no record", got.state == ws.NONE, got)
        control("NONE: no record blocks nothing", ws.stack_block(main, pr_merged=no_pr) == "")
        control("NONE: no record reports nothing", ws.stack_report(main, pr_merged=no_pr) == "")

        cp.write_landing_record(str(main), str(landing), LANDING)

        # Stacked on the landing tip: current and quiet.
        got = state()
        control("CURRENT: stacked on the landing tip", got.state == ws.CURRENT, got)
        control("CURRENT: quiet", ws.stack_report(main, pr_merged=no_pr) == "")
        control("CURRENT: no block", ws.stack_block(main, pr_merged=no_pr) == "")

        # The landing tree itself is never judged.
        got = state(root=landing)
        control("NONE: the landing tree", got.state == ws.NONE, got)

        # Landing moves ahead: the rebase is reported, nothing blocks.
        fix = commit(landing, "fix-1.txt")
        commit(landing, "fix-2.txt")
        got = state()
        control("BEHIND: landing ahead", got.state == ws.BEHIND and got.ahead == 2, got)
        report = ws.stack_report(main, pr_merged=no_pr)
        control("BEHIND: names the rebase", "  git rebase %s\n" % LANDING in report, report)
        control("BEHIND: no block", ws.stack_block(main, pr_merged=no_pr) == "")

        # The landing branch pushed and the development branch rebased onto it: current.
        sh(landing, "push", "-q", "origin", LANDING)
        sh(main, "rebase", "-q", LANDING)
        got = state()
        control("CURRENT: after the rebase", got.state == ws.CURRENT, got)

        # The landing PR rebase-merges: main holds copies with new shas.
        merger = td / "merger"
        sh(td, "clone", "-q", str(remote), str(merger))
        sh(merger, "fetch", "-q", "origin", LANDING)
        sh(merger, *IDENT, "cherry-pick", "main..origin/%s" % LANDING)
        sh(merger, "push", "-q", "origin", "main")
        control("FIXTURE: main holds copies", sh(merger, "rev-parse", "HEAD~1") != fix)
        got = state()
        control(
            "MERGED: absorbed landing commits",
            got.state == ws.MERGED and got.carried == 2 and not got.rebased,
            got,
        )
        block = ws.stack_block(main, pr_merged=no_pr)
        control("MERGED: blocks with the promote command", "  %s\n" % ws.PROMOTE_COMMAND in block, block)
        control("MERGED: names the carried copies", "still carries 2 landing commit(s)" in block, block)
        control("MERGED: reports no rebase", ws.stack_report(main, pr_merged=no_pr) == "")

        # The development branch rebased onto origin/main by hand: the copies drop, promotion still has not run.
        sh(main, "rebase", "-q", "origin/main")
        got = state()
        control(
            "MERGED: rebased by hand still blocks",
            got.state == ws.MERGED and got.carried == 0 and got.rebased,
            got,
        )
        control(
            "MERGED: names the rest of promotion",
            "the rest of promotion" in ws.stack_block(main, pr_merged=no_pr),
        )

        # Promotion: the development branch moves into the landing tree, the record names it, and the next development branch is cut stacked on it.
        sh(landing, "checkout", "-q", "--detach")
        sh(main, "checkout", "-q", "-b", NEXT)
        sh(landing, "checkout", "-q", DEVELOPMENT)
        cp.write_landing_record(str(main), str(landing), DEVELOPMENT)
        got = state()
        control("PROMOTED: current and quiet", got.state == ws.CURRENT and got.landing == DEVELOPMENT, got)
        control("PROMOTED: no block", ws.stack_block(main, pr_merged=no_pr) == "")
        control("PROMOTED: no report", ws.stack_report(main, pr_merged=no_pr) == "")

        # A landing branch with no commit of its own (the fast-forward fallback put its tip on main): only the PR answer reads it merged.
        sh(landing, "push", "-q", "origin", "%s:main" % DEVELOPMENT)
        got = state(pr=no_pr)
        control("CURRENT: an empty landing branch with no merged PR", got.state == ws.CURRENT, got)
        got = state(pr=merged_pr)
        control("MERGED: an empty landing branch whose PR merged", got.state == ws.MERGED, got)

        # The notification texts.
        push = ws.notify_line(landing, "push")
        control("NOTIFY: push names the rebase", "  git rebase %s" % DEVELOPMENT in push, push)
        control("NOTIFY: push names the development tree", str(main) in push, push)
        merged = ws.notify_line(landing, "merged", pr=605)
        control("NOTIFY: merged names promotion", ws.PROMOTE_COMMAND in merged and "PR #605" in merged, merged)
        control("NOTIFY: an unknown event is silent", ws.notify_line(landing, "other") == "")
    if ran[0] < 25:
        fails.append("only %d controls ran" % ran[0])
    return fails


def main() -> int:
    real = load()
    cp = real._hooks_pkg()
    if not hasattr(cp, "write_landing_record"):
        print("FAIL: commit_policy has no landing record (PLAN-two-track-merge-dev LT1 not present)")
        return 1
    fails = controls(real, cp)
    for line in fails:
        print("FAIL: " + line)
    if fails:
        return 1
    print("controls: all held")
    text = SOURCE.read_text(encoding="utf-8")
    bad = 0
    for label, old, new in MUTANTS:
        if text.count(old) != 1:
            print("FAIL: mutant %r no longer applies once" % label)
            bad += 1
            continue
        red = controls(load(text.replace(old, new)), cp)
        if not red:
            print("FAIL: mutant %r left every control green" % label)
            bad += 1
        else:
            print("mutant %r: red (%d control(s))" % (label, len(red)))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())

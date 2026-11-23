#!/usr/bin/env python3
"""Controls for wl_stack (PLAN-two-track-merge-dev LT19), on real temporary repositories.

    python3 .claude/hooks/stop/test-landing-stack.py     rc 0 when every control holds and every mutant turns them red

A bare repository plays origin; its clone plays the main checkout (the development tree), and a linked tree of that clone, bound by the landing record, plays the landing tree. A rebase-merge is a second clone that cherry-picks the landing commits onto main and pushes, so main holds copies with new shas, as GitHub's rebase-merge leaves them.

Each MUTANT is wl_stack's own source with one arm broken, loaded in-process from that text; the controls must fail against every one of them, so none can pass vacuously.

The landing tree is made with git's linked-tree verb, so block_worktree_add admits this file only once it is committed.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
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
        '    if "+" in marks:\n        return ""',
        '    if False:\n        return ""',
    ),
    (
        "the behind report blocks",
        "    if st.state != MERGED:\n        return Verdict()",
        "    if st.state not in (MERGED, BEHIND):\n        return Verdict()",
    ),
    # PLAN-stop-hook-retro-20261123 R20261123.1 and .2: each downgrade arm, broken alone.
    (
        "the code-complete call dropped",
        "            plans = open_writer_boxes(root, shas)\n",
        "            plans = []\n",
    ),
    (
        "an unreadable named plan silences the block",
        '            notes.append("Promote also refuses here: %s." % exc)',
        "            return Verdict()",
    ),
    (
        "promote's dirt never read",
        "    dirt, dirt_problem = _promote_dirt(root, st.landing_path)",
        '    dirt, dirt_problem = [], ""',
    ),
    (
        "this session's own dirt read as a peer's",
        "        mine = [p for p in dirt if _norm(p) in own]",
        "        mine = []",
    ),
    ("a live main-checkout task ignored", "    if live_main_bg:\n", "    if False:\n"),
    (
        "a lease writer counted as a main-checkout task",
        '            main_tree_agent = meta is not None and not meta.get("worktree")',
        "            main_tree_agent = meta is not None",
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
    # The class sweep of review e943d92e.1 (stop-gate judge 2026-11-23): each named read failure, silenced alone.
    (
        "a failed stack read answered silently",
        "        return Verdict(advisory=_unread_text(exc))",
        "        return Verdict()",
    ),
    ("a failed development-commit listing unnamed", "    if shas is None:\n", "    if False:\n"),
    ("an unreadable dirty preflight unnamed", "    if dirt_problem:\n", "    if False:\n"),
    (
        "a failed landing cherry read as unmerged",
        '        raise StackReadError(\n            "git could not compare',
        '        return ""\n        raise StackReadError(\n            "git could not compare',
    ),
    (
        "a defective landing record read as none",
        "    if problem:\n        raise StackReadError(problem)",
        "    if False:\n        raise StackReadError(problem)",
    ),
    (
        "gh that cannot say read as unmerged",
        "    if rows is None:\n        raise StackReadError(",
        "    if False:\n        raise StackReadError(",
    ),
]

# A hermetic git: no host config, an identity of its own (a rebase writes a committer too), nothing inherited from a hook's GIT_* environment.
GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
GIT_ENV.update(
    GIT_AUTHOR_NAME="t",
    GIT_AUTHOR_EMAIL="t@example.invalid",
    GIT_COMMITTER_NAME="t",
    GIT_COMMITTER_EMAIL="t@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
    # GIT_CONFIG_GLOBAL and GIT_CONFIG_SYSTEM are honoured from 2.32 on; the three below keep an older release off the host files too.
    GIT_CONFIG_NOSYSTEM="1",
    HOME="/dev/null",
    XDG_CONFIG_HOME="/dev/null",
)
# The rebase-merge's copies carry a committer of their own, as GitHub's do: a pick by the same identity in the same second would reproduce the very shas.
MERGER_ENV = dict(
    GIT_ENV, GIT_COMMITTER_NAME="merger", GIT_COMMITTER_EMAIL="merger@example.invalid"
)


def sh(cwd, *args, env=None) -> str:
    r = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env or GIT_ENV,
    )
    if r.returncode != 0:
        raise SystemExit("fixture: git %s failed in %s: %s" % (" ".join(args), cwd, r.stderr))
    return r.stdout.strip()


def commit(cwd, name: str) -> str:
    (pathlib.Path(cwd) / name).write_text(name + "\n", encoding="utf-8")
    sh(cwd, "add", name)
    sh(cwd, "commit", "-qm", name)
    return sh(cwd, "rev-parse", "HEAD")


class _MutantLoader(importlib.machinery.SourceFileLoader):
    """wl_stack's own path with another source text: no bytecode is read for it or written from it."""

    def __init__(self, fullname: str, path: str, text: str) -> None:
        super().__init__(fullname, path)
        self.text = text

    def get_data(self, path):
        if path == self.path:
            return self.text.encode("utf-8")
        raise OSError("no bytecode for a mutant")

    def set_data(self, *_args, **_kwargs) -> None:
        return None


def load(text: str | None = None) -> types.ModuleType:
    """wl_stack from its file, or from `text` (a mutant) under the same path, so its hop to `.claude/rediacc_hooks` resolves identically."""
    name = "wl_stack_under_test"
    loader = None if text is None else _MutantLoader(name, str(SOURCE), text)
    spec = importlib.util.spec_from_file_location(name, SOURCE, loader=loader)
    if spec is None or spec.loader is None:
        raise SystemExit("%s is missing" % SOURCE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def plan_commit(cwd, rel: str, boxes: list[str]) -> None:
    """A development commit writing the plan at `rel` with `boxes` and a Plan-Box trailer naming it."""
    path = pathlib.Path(cwd) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# PLAN: fixture\nStatus: approved\n\n## Tasks\n\n%s\n" % "\n".join(boxes),
        encoding="utf-8",
    )
    sh(cwd, "add", rel)
    sh(
        cwd,
        "commit",
        "-qm",
        "feat: plan work\n\nPlan-Box: %s#aaaa1111 clauses=all" % rel.rsplit("/", 1)[-1],
    )


def no_pr(_root, _branch) -> bool:
    return False


def merged_pr(_root, _branch) -> bool:
    return True


def controls(ws: Any, cp) -> list[str]:
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
        # Even with a branch misplaced into it, the landing tree is not a development tree.
        sh(landing, "checkout", "-q", "-b", "1123-1")
        got = state(root=landing)
        control("NONE: the landing tree holding another branch", got.state == ws.NONE, got)
        sh(landing, "checkout", "-q", LANDING)

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
        sh(merger, "cherry-pick", "main..origin/%s" % LANDING, env=MERGER_ENV)
        sh(merger, "push", "-q", "origin", "main")
        control("FIXTURE: main holds copies", sh(merger, "rev-parse", "HEAD~1") != fix)
        got = state()
        control(
            "MERGED: absorbed landing commits",
            got.state == ws.MERGED and got.carried == 2 and not got.rebased,
            got,
        )
        block = ws.stack_block(main, pr_merged=no_pr)
        control(
            "MERGED: blocks with the promote command", "  %s\n" % ws.PROMOTE_COMMAND in block, block
        )
        control(
            "MERGED: names the carried copies", "still carries 2 landing commit(s)" in block, block
        )
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

        # CODE-COMPLETE (PLAN-stop-hook-retro-20261123 R20261123.1, D1): promote refuses on an open [writer] box of a plan the development commits name, so the stop does not block on it.
        def verdict(root=main, **kw):
            fn = getattr(ws, "stack_verdict", None)
            if fn is None:
                return ("<no stack_verdict>", "")
            return tuple(fn(root, pr_merged=no_pr, **kw))

        plan_rel = "agent/plans/PLAN-fixture.md"
        done_boxes = [
            "- [x] W1 [writer] The first writer box, done.",
            "- [ ] V1 [live] The live run, open for the landing tree.",
        ]
        plan_commit(main, plan_rel, done_boxes)
        block, advisory = verdict()
        control(
            "CODE-COMPLETE INVERSE: every writer box ticked, the block stands",
            "  %s\n" % ws.PROMOTE_COMMAND in block and advisory == "",
            (block, advisory),
        )
        plan_commit(
            main, plan_rel, [*done_boxes, "- [ ] W2 [writer] The second writer box, still open."]
        )
        block, advisory = verdict()
        control("CODE-COMPLETE: an open writer box blocks nothing", block == "", block)
        control(
            "CODE-COMPLETE: the advisory names the plan and its first open box",
            "PROMOTION WAITS ON CODE-COMPLETE" in advisory
            and "`%s` has 1 open [writer] box(es)" % plan_rel in advisory
            and "W2 [writer] The second writer box" in advisory,
            advisory,
        )
        control(
            "CODE-COMPLETE: stack_block agrees", ws.stack_block(main, pr_merged=no_pr) == "", ""
        )
        plan_commit(main, plan_rel, done_boxes)

        # DIRTY TREE OR LIVE RUN (R20261123.2, D2): promote refuses on tracked non-record dirt; a peer's dirt or a live main-checkout run downgrades, this session's own dirt blocks and is named.
        peer_rel = "agent/plans/PLAN-x.md"
        peer = main / peer_rel
        peer.write_text("# PLAN: x\n", encoding="utf-8")
        sh(main, "add", peer_rel)
        sh(main, "commit", "-qm", "plan x")
        peer.write_text("# PLAN: x\nedited by a peer\n", encoding="utf-8")
        block, advisory = verdict(own_paths=[])
        control("DIRT: a peer's dirty path blocks nothing", block == "", block)
        control(
            "DIRT: the advisory names the peer's dirty path",
            "PROMOTION WAITS ON A PEER'S DIRTY TREE" in advisory and peer_rel in advisory,
            advisory,
        )
        for label, own_paths in (("relative", [peer_rel]), ("absolute", [str(peer)])):
            block, advisory = verdict(own_paths=own_paths)
            control(
                "DIRT: this session's own dirty path (%s) blocks and is named" % label,
                "  %s\n" % ws.PROMOTE_COMMAND in block
                and "this session's own dirty tracked path(s)" in block
                and peer_rel in block
                and advisory == "",
                (block, advisory),
            )
        block, advisory = verdict(own_paths=[peer_rel], live_main_bg=["vm:check run"])
        control(
            "LIVE RUN: a live main-checkout task downgrades even this session's dirt",
            block == "" and "vm:check run" in advisory and peer_rel in advisory,
            (block, advisory),
        )
        peer.write_text("# PLAN: x\n", encoding="utf-8")
        landing_base = landing / "base.txt"
        landing_base.write_text("peer edit in the landing tree\n", encoding="utf-8")
        block, advisory = verdict(own_paths=[])
        control(
            "DIRT: a peer's dirt in the landing tree downgrades",
            block == "" and str(landing_base) in advisory,
            (block, advisory),
        )
        block, advisory = verdict(own_paths=[str(landing_base)])
        control(
            "DIRT: this session's landing-tree edit blocks",
            str(landing_base) in block and advisory == "",
            (block, advisory),
        )
        landing_base.write_text("base.txt\n", encoding="utf-8")
        block, advisory = verdict(own_paths=[], live_main_bg=["vm:check run"])
        control(
            "LIVE RUN: a clean tree with a live main-checkout task downgrades",
            block == ""
            and "PROMOTION WAITS ON A LIVE RUN" in advisory
            and "vm:check run" in advisory,
            (block, advisory),
        )
        block, advisory = verdict(own_paths=[], live_main_bg=[])
        control(
            "LIVE RUN INVERSE: no task and a clean tree, the block stands",
            "  %s\n" % ws.PROMOTE_COMMAND in block and advisory == "",
            (block, advisory),
        )
        tasks = getattr(ws, "main_checkout_tasks", lambda *_a: ["<no main_checkout_tasks>"])
        live = [
            {"id": "b1", "type": "shell", "description": "npm run vm:check"},
            {"id": "a1", "type": "subagent", "description": "main-tree runner"},
            {"id": "a2", "type": "subagent", "description": "lease writer"},
            {"id": "t1", "type": "teammate", "description": "a teammate"},
        ]
        metas = {"a1": {"worktree": ""}, "a2": {"worktree": str(td / "lease")}}
        got = tasks(main, live, metas)
        control(
            "LIVE RUN: a shell and a main-tree subagent run in the main checkout, a lease writer does not",
            got == ["npm run vm:check", "main-tree runner"],
            got,
        )
        got = tasks(landing, live, metas)
        control("LIVE RUN: a session in another tree has no main-checkout task", got == [], got)

        # An unreadable named plan: promote refuses on it too, so the block stands and says so.
        sh(
            main,
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "feat: absent\n\nPlan-Box: PLAN-absent.md#bbbb2222 clauses=all",
        )
        block, advisory = verdict(own_paths=[])
        control(
            "CODE-COMPLETE: an unreadable named plan keeps the block and names it",
            "PLAN-absent.md" in block and advisory == "",
            (block, advisory),
        )

        # Any other failure of the open-box read (review e943d92e.1) keeps the block and names the failure.
        reader_name = "open_writer_boxes"
        real_reader = getattr(ws, reader_name)

        def broken_reader(*_a, **_k):
            raise OSError("fixture: open-box read failed")

        setattr(ws, reader_name, broken_reader)
        try:
            block, advisory = verdict(own_paths=[])
        finally:
            setattr(ws, reader_name, real_reader)
        control(
            "CODE-COMPLETE: an unexpected open-box read failure keeps the block and names it",
            "fixture: open-box read failed" in block and advisory == "",
            (block, advisory),
        )

        # THE CLASS SWEEP of that fix (stop-gate judge 2026-11-23): every other read the verdict rests on names its failure rather than reading as "no data".
        # A failed listing of the development commits is not "no commits": whether promote refuses on an open [writer] box is unknown, so the block stands and says why.
        real_shas = ws._dev_shas
        ws._dev_shas = lambda *_a, **_k: None
        try:
            block, advisory = verdict(own_paths=[])
        finally:
            ws._dev_shas = real_shas
        control(
            "UNREAD: a failed development-commit listing keeps the block and names it",
            "could not list the development commits" in block and advisory == "",
            (block, advisory),
        )
        # An unparseable record policy is not "no dirt": promote refuses on it by name, and the block says the preflight could not be read.
        planted_policy = main / ".ci" / "policy" / "record-paths.json"
        planted_policy.parent.mkdir(parents=True, exist_ok=True)
        planted_policy.write_text("{ not json\n", encoding="utf-8")
        try:
            block, advisory = verdict(own_paths=[])
        finally:
            planted_policy.unlink()
        control(
            "UNREAD: an unreadable dirty preflight keeps the block and names it",
            "dirty preflight could not be read" in block
            and "record-paths.json" in block
            and advisory == "",
            (block, advisory),
        )
        block, advisory = verdict(own_paths=[])
        control(
            "UNREAD INVERSE: with the plant gone, no read failure is named",
            "could not" not in block and "  %s\n" % ws.PROMOTE_COMMAND in block,
            (block, advisory),
        )
        # A stack read that raises is not "nothing merged": it never blocks (a git blip must not), and the advisory names it.
        real_state = ws.stack_state

        def broken_state(*_a, **_k):
            raise OSError("fixture: stack read failed")

        ws.stack_state = broken_state
        try:
            block, advisory = verdict(own_paths=[])
            report = ws.stack_report(main, released=False, pr_merged=no_pr)
        finally:
            ws.stack_state = real_state
        control(
            "UNREAD: a failed stack read blocks nothing and the advisory names it",
            block == "" and "fixture: stack read failed" in advisory,
            (block, advisory),
        )
        control(
            "UNREAD: a failed stack read is named in the report too",
            "fixture: stack read failed" in report,
            report,
        )
        # A failed `git cherry` of the landing branch is not "not merged".
        real_cherry = ws._cherry
        ws._cherry = lambda *_a, **_k: None
        try:
            block, advisory = verdict(own_paths=[])
        finally:
            ws._cherry = real_cherry
        control(
            "UNREAD: a failed landing cherry read is named, not read as unmerged",
            block == "" and "could not compare the landing branch" in advisory,
            (block, advisory),
        )
        # A defective landing record is not "no record".
        record_file = pathlib.Path(cp.landing_record_path(str(main)))
        record_text = record_file.read_text(encoding="utf-8")
        record_file.write_text("{ not json\n", encoding="utf-8")
        try:
            block, advisory = verdict(own_paths=[])
        finally:
            record_file.write_text(record_text, encoding="utf-8")
        control(
            "UNREAD: a defective landing record is named, not read as none",
            block == "" and "is unreadable" in advisory,
            (block, advisory),
        )
        # gh that cannot answer is not "no merged PR".
        saved_gh = sys.modules.get("wl_gh")
        gh_answer: list = [(None, "")]
        fake_gh = type(sys)("wl_gh")
        fake_gh.__dict__["call"] = lambda *_a, **_k: gh_answer[0]
        sys.modules["wl_gh"] = fake_gh
        try:
            outcomes: list = []
            for answer in ((None, "fixture: HTTP 502"), ([], ""), ([{"number": 7}], "")):
                gh_answer[0] = answer
                try:
                    outcomes.append(ws.gh_pr_merged(main, LANDING))
                except Exception as exc:
                    outcomes.append("raised: %s" % exc)
        finally:
            if saved_gh is None:
                sys.modules.pop("wl_gh", None)
            else:
                sys.modules["wl_gh"] = saved_gh
        control(
            "UNREAD: gh that cannot say is named, not read as unmerged",
            isinstance(outcomes[0], str) and "fixture: HTTP 502" in outcomes[0],
            outcomes,
        )
        control(
            "UNREAD INVERSE: gh's empty and one-row answers read unmerged and merged",
            outcomes[1:] == [False, True],
            outcomes,
        )

        # Promotion: the development branch moves into the landing tree, the record names it, and the next development branch is cut stacked on it.
        sh(landing, "checkout", "-q", "--detach")
        sh(main, "checkout", "-q", "-b", NEXT)
        sh(landing, "checkout", "-q", DEVELOPMENT)
        cp.write_landing_record(str(main), str(landing), DEVELOPMENT)
        got = state()
        control(
            "PROMOTED: current and quiet",
            got.state == ws.CURRENT and got.landing == DEVELOPMENT,
            got,
        )
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
        control(
            "NOTIFY: merged names promotion",
            ws.PROMOTE_COMMAND in merged and "PR #605" in merged,
            merged,
        )
        control("NOTIFY: an unknown event is silent", ws.notify_line(landing, "other") == "")
    if ran[0] < 40:
        fails.append("only %d controls ran" % ran[0])
    return fails


def main() -> int:
    real = load()
    cp = real._hooks_pkg()
    if not hasattr(cp, "write_landing_record"):
        print(
            "FAIL: commit_policy has no landing record (PLAN-two-track-merge-dev LT1 not present)"
        )
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

#!/usr/bin/env python3
"""Controls for the two-tree loop text and queue rendering (PLAN-two-track-merge-dev LT15).

    python3 .claude/hooks/stop/test-landing-loopnext.py

Every branch has a silent control (no landing record, today's text and rendering), and the checks run once against the real code and once against a mutant that must turn them red. The trees are real: a repository and a linked tree of it, bound by a landing record in the common git directory. Needs commit_policy's landing record (LT1).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

import wl_planqueue as Q
import wl_prscope as P
import wl_rebase as RB
import worklist_messages as M

FAILS: list[str] = []
RAN = [0]


def control(label: str, ok: bool, detail: str = "") -> None:
    RAN[0] += 1
    if not ok:
        FAILS.append("%s %s" % (label, detail))


def sh(cwd, *args) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True)
    return r.stdout.strip()


def variant_checks(tag: str, pick) -> None:
    """The selector contract; `pick(role, merged, landing_open, arm)` is the function under test."""
    land, dev = "landing", "development"
    control(
        tag + " landing merged promotes",
        pick(land, True, False, M.ARM_FINISH) is M.V_LOOP_NEXT_PROMOTE,
    )
    control(
        tag + " landing merged ignores open",
        pick(land, True, True, M.ARM_OPEN) is M.V_LOOP_NEXT_PROMOTE,
    )
    control(
        tag + " dev finish waits", pick(dev, False, True, M.ARM_FINISH) is M.V_LOOP_NEXT_MERGE_WAIT
    )
    control(
        tag + " dev finish, landing closed",
        pick(dev, False, False, M.ARM_FINISH) is M.V_LOOP_NEXT_MERGE,
    )
    control(
        tag + " dev no PR names the backup push",
        pick(dev, False, True, M.ARM_OPEN) is M.V_LOOP_NEXT_NO_PR_BACKUP,
    )
    control(
        tag + " landing finish merges",
        pick(land, False, False, M.ARM_FINISH) is M.V_LOOP_NEXT_MERGE,
    )
    for role in (None, ""):
        control(
            tag + " no record merged", pick(role, True, False, M.ARM_FINISH) is M.V_LOOP_NEXT_MERGED
        )
        control(
            tag + " no record finish", pick(role, False, True, M.ARM_FINISH) is M.V_LOOP_NEXT_MERGE
        )
        control(
            tag + " no record open",
            pick(role, False, False, M.ARM_OPEN) is M.V_LOOP_NEXT_NO_PR_OPEN,
        )


def mutant_pick(_role, merged, _landing_open, arm=M.ARM_FINISH):
    """Ignores the role: today's text everywhere."""
    if merged:
        return M.V_LOOP_NEXT_MERGED
    return M.V_LOOP_NEXT_NO_PR_OPEN if arm == M.ARM_OPEN else M.V_LOOP_NEXT_MERGE


def text_checks() -> None:
    fields = {
        "pr": 7,
        "branch": "1120-1",
        "next": "agent/plans/PLAN-x.md",
        "box": "B1",
        "plans": "x",
    }
    promote = M.V_LOOP_NEXT_PROMOTE % fields
    control(
        "promote names the verb",
        "worktree landing --promote" in promote and "git switch" not in promote,
    )
    wait = M.V_LOOP_NEXT_MERGE_WAIT % fields
    control(
        "wait names the rebase",
        "git rebase <landing branch>" in wait and "never run /pr-merge" in wait,
    )
    control("today's merge text offers /pr-merge", "run /pr-merge" in M.V_LOOP_NEXT_MERGE % fields)
    backup = M.V_LOOP_NEXT_NO_PR_BACKUP % {"branch": "1120-2", "ahead": 2}
    control(
        "the development arm names the backup push and opens no PR",
        "git push -u origin 1120-2" in backup and "gh pr create" not in backup,
    )


def trees_world(td: pathlib.Path):
    main = td / "main"
    main.mkdir()
    sh(main, "init", "-q", "-b", "main")
    (main / "f").write_text("x\n", encoding="utf-8")
    sh(main, "add", "f")
    sh(main, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "base")
    land = td / "land"
    sh(main, "worktree", "add", "-q", "-b", "1120-1", str(land))
    sh(main, "switch", "-q", "-c", "1120-2")
    return main, land


def tree_rendering() -> None:
    _pg, cp = P._hooks_pkg()
    prs = {"1120-1": (11, "OPEN"), "1120-2": (12, "OPEN")}
    with tempfile.TemporaryDirectory() as raw:
        td = pathlib.Path(raw).resolve()
        main, land = trees_world(td)
        none_main = Q.landing_trees(main, td, "s", lambda b: prs.get(b, (0, "")))
        control("no record: no tree lines", none_main == () and Q.render_trees(none_main) == [])
        base = Q.render_inflight(Q.InFlight(kind=P.NO_PR, branch="1120-2"))
        control("no record: block carries no tree line", "tree:" not in base)
        cp.write_landing_record(str(main), str(land), "1120-1")
        from_main = Q.landing_trees(main, td, "s", lambda b: prs.get(b, (0, "")))
        from_land = Q.landing_trees(land, td, "s", lambda b: prs.get(b, (0, "")))
        control(
            "both trees read identically",
            from_main == from_land and len(from_main) == 2,
            repr((from_main, from_land)),
        )
        lines = Q.render_trees(from_main)
        control(
            "render names both",
            lines
            == [
                "- Landing tree: branch 1120-1, PR #11 open.",
                "- Development tree: branch 1120-2, draft PR #12 open.",
            ],
            repr(lines),
        )
        control("render identical from either", lines == Q.render_trees(from_land))
        body = Q.render_inflight(Q.InFlight(kind=P.NO_PR, branch="1120-2", trees=from_land))
        control("block carries the tree lines", all(line in body for line in lines))
        nopr = Q.landing_trees(
            land, td, "s", lambda b: (11, "MERGED") if b == "1120-1" else (0, "")
        )
        control(
            "merged landing and unopened draft render",
            Q.render_trees(nopr)
            == [
                "- Landing tree: branch 1120-1, PR #11 merged.",
                "- Development tree: branch 1120-2, no PR yet.",
            ],
        )


def mutant_render(trees) -> list[str]:
    """Viewer order: no sort, so the landing line can come second."""
    return [Q.render_trees([t])[0] for t in reversed(list(trees))]


def rebase_checks() -> None:
    control("open PR: live branch", RB.base_branch(True, "1120-1") == "1120-1")
    control("merged, no record: main", RB.base_branch(False, "1120-1") == "main")
    control(
        "merged, record without cut_from: main",
        RB.base_branch(False, "1120-1", {"owner": "s"}) == "main",
    )
    control(
        "merged, cut_from: that branch",
        RB.base_branch(False, "1120-1", {"cut_from": "1120-2"}) == "1120-2",
    )
    control(
        "open PR ignores cut_from",
        RB.base_branch(True, "1120-1", {"cut_from": "1120-2"}) == "1120-1",
    )


def main() -> int:
    variant_checks("real", M.loop_next_variant)
    before = len(FAILS)
    variant_checks("mutant", mutant_pick)
    mutant_red = len(FAILS) > before
    del FAILS[before:]
    control("mutant turns the variant checks red", mutant_red)
    text_checks()
    tree_rendering()
    sample = [
        Q.TreeLine("landing", "1120-1", 11, "OPEN"),
        Q.TreeLine("development", "1120-2", 12, "OPEN"),
    ]
    control(
        "mutant order differs from the real render", mutant_render(sample) != Q.render_trees(sample)
    )
    rebase_checks()
    for fail in FAILS:
        print("FAIL", fail)
    print("%d controls, %d failed" % (RAN[0], len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())

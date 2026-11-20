#!/usr/bin/env python3
"""Two-tree proof for the post-bash hooks (box LT13 of agent/plans/PLAN-two-track-merge-dev.md).

A real temporary repository (the main checkout, development branch) with a real linked worktree (the landing tree, landing branch) and a real landing record. Only `gh`, the reviewer launch and the worklist CLI are stubbed. Each case runs the hook as the harness does, with CLAUDE_PROJECT_DIR the main checkout and the event cwd the tree the command was typed in.

Controls: with no landing record every hook behaves as before (it reads the project directory), and a command typed in the main checkout reads the main checkout. Mutants: a copy of each hook that reads the project directory regardless of the cwd must fail the same checks, so a green run is not a check that cannot fail.

Run: python3 .claude/hooks/post-bash/test-two-tree.py
"""

import importlib.util
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
CLAUDE = HERE.parents[1]
sys.path.insert(0, str(CLAUDE))
sys.path.insert(0, str(CLAUDE / "hooks" / "stop"))

DEV, LAND = "0930-2", "0930-1"
SID = "deadbeef-1111-2222-3333-444444444444"

ENV = {
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}
os.environ.update(ENV)
for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "COMMIT_REVIEW_CHILD", "STOPHOOK_CHILD"):
    os.environ.pop(key, None)

FAILURES = []


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def commit(repo, name):
    (pathlib.Path(repo) / name).write_text("a = 1\nb = 2\n", encoding="utf-8")
    git(repo, "add", "--", name)
    git(repo, "commit", "-q", "-m", "fix: " + name, "--", name)


def world(tmp):
    """Main checkout on DEV, landing tree on LAND (both pushed), and the landing record."""
    from rediacc_hooks import commit_policy

    tmp = pathlib.Path(tmp).resolve()
    origin = tmp / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    main = tmp / "main"
    main.mkdir()
    git(main, "init", "-q", "--initial-branch=main")
    (main / "seed.txt").write_text("seed\n", encoding="utf-8")
    git(main, "add", "seed.txt")
    git(main, "commit", "-q", "-m", "seed")
    git(main, "remote", "add", "origin", str(origin))
    git(main, "push", "-q", "origin", "main")
    git(main, "branch", LAND)
    git(main, "checkout", "-q", "-b", DEV)
    land = tmp / "landing"
    git(main, "worktree", "add", "-q", str(land), LAND)
    commit(land, "landed.py")
    git(land, "push", "-q", "origin", LAND)
    commit(main, "dev.py")
    git(main, "push", "-q", "origin", DEV)
    commit_policy.write_landing_record(str(main), str(land), LAND)
    return main, land.resolve()


def load(name, source=None, patch=None):
    """The hook module `name`, from its file or from `source` text (a mutant)."""
    path = HERE / (name + ".py")
    text = source if source is not None else path.read_text(encoding="utf-8")
    if patch:
        text = patch(text)
    # The hook locates the `.claude` directory from its own path, so a copy keeps the real parents.
    holder = HERE / ("_mutant_%s_%d.py" % (name, os.getpid()))
    holder.write_text(text, encoding="utf-8")
    try:
        spec = importlib.util.spec_from_file_location("lt13_" + holder.stem, holder)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        holder.unlink()
    return mod


def run_main(mod, project, cwd, command):
    os.environ["CLAUDE_PROJECT_DIR"] = str(project)
    payload = json.dumps(
        {
            "session_id": SID,
            "cwd": str(cwd),
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }
    )
    old_in, old_out = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = io.StringIO(payload), io.StringIO()
    try:
        rc = mod.main()
        return rc, sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = old_in, old_out


def real(path):
    return os.path.realpath(str(path))


# --- the checks: each returns a list of problems, empty when the hook reads the right tree ---


def check_review(mod, main, land, record=True):
    problems = []
    calls = []

    def stub(root, repo, *a, **k):
        calls.append((real(root), real(repo)))
        return [("c" * 40, 1234)]

    lines = mod.trigger_lines("git commit -q -m x", str(land), main, trigger=stub)
    started = [c for c in calls]
    if record:
        if started != [(real(land), real(land))]:
            problems.append("landing commit: reviewer asked for %s, expected the landing tree" % started)
    elif started:
        problems.append("no record: a commit in the landing tree started a review %s" % started)
    if not record and not lines == [] and any("started" in ln for ln in lines):
        problems.append("no record: a review was reported started")
    calls.clear()
    mod.trigger_lines("git commit -q -m x", str(main), main, trigger=stub)
    if calls != [(real(main), real(main))]:
        problems.append("main commit: reviewer asked for %s, expected the main checkout" % calls)
    return problems


def check_surface(mod, main, land):
    """A finished review record under the landing tree's branch directory reaches the session."""
    problems = []
    seen = []

    def surface(root, branch, sid):
        seen.append((real(root), branch))
        return []

    mod.R.surface_new, saved = surface, mod.R.surface_new
    try:
        run_main(mod, main, main, "ls")
    finally:
        mod.R.surface_new = saved
    if (real(land), LAND) not in seen:
        problems.append("surface_new never read the landing tree: %s" % seen)
    return problems


def check_arm(mod, main, land):
    problems = []
    roots = []

    def arm(root, sid, **kw):
        roots.append(real(root))
        return ""

    mod.arm = arm
    run_main(mod, main, land, "git push")
    if roots != [real(land)]:
        problems.append("arm read %s for a push typed in the landing tree" % roots)
    roots.clear()
    run_main(mod, main, main, "git push")
    if roots != [real(main)]:
        problems.append("arm read %s for a push typed in the main checkout" % roots)
    return problems


def check_arm_branch(mod, main, land):
    """The real arm(): the watch is armed for the landing branch, not the development branch."""
    problems = []
    spawned = []
    out = mod.arm(
        land,
        SID,
        cli=lambda root, sid, *a: (0, "added #abcd1234"),
        spawn=lambda root, sid, branch, item, log: spawned.append(branch) or 4321,
        alive=lambda pid: False,
        has_pr=lambda root, branch: True,
    )
    if spawned != [LAND] or LAND not in out:
        problems.append("arm in the landing tree watched %s (%s)" % (spawned, out))
    return problems


def check_gh_branch(mod, main, land, call_name, flag):
    problems = []
    seen = []

    def fake(*args):
        if args[:2] == ("repo", "view"):
            return 0, "owner/repo"
        if flag in args:
            seen.append(args[args.index(flag) + 1])
        return 0, ""

    mod._gh_read = fake
    if hasattr(mod, "shutil"):
        mod.shutil = type("S", (), {"which": staticmethod(lambda n: "/bin/gh")})
    for where, want in ((land, LAND), (main, DEV)):
        seen.clear()
        run_main(mod, main, where, "git push")
        if want not in seen or (where == land and DEV in seen):
            problems.append("%s read %s for a bare push in %s, expected %s" % (call_name, seen, where.name, want))
    return problems


def expect(label, problems):
    if problems:
        FAILURES.append((label, problems))
        print("FAIL %s: %s" % (label, "; ".join(problems)))
    else:
        print("ok   %s" % label)


def expect_red(label, problems):
    if problems:
        print("ok   %s (mutant red: %s)" % (label, problems[0][:70]))
    else:
        FAILURES.append((label, ["mutant stayed green"]))
        print("FAIL %s: mutant stayed green" % label)


def main_():
    from rediacc_hooks import commit_policy

    with tempfile.TemporaryDirectory() as tmp:
        main, land = world(tmp)
        os.environ["TMPDIR"] = str(pathlib.Path(tmp) / "tmpdir")
        os.makedirs(os.environ["TMPDIR"])

        def mutate_tree(text):
            marker = "    if not cwd or os.path.realpath(cwd) == os.path.realpath(project_dir):\n        return project_dir\n"
            assert marker in text
            return text.replace(marker, "    return project_dir\n" + marker)

        def mutate_bound(text):
            marker = "    trees = [pathlib.Path(root)]\n"
            assert marker in text
            return text.replace(marker, marker + "    return trees\n")

        # review_commit
        expect("review_commit: commit in landing tree reviewed there", check_review(load("review_commit"), main, land))
        expect("review_commit: surface reads both trees", check_surface(load("review_commit"), main, land))
        expect_red("review_commit mutant (project dir only)", check_review(load("review_commit", patch=mutate_bound), main, land))
        # arm_ci_watch
        expect("arm_ci_watch: push in landing tree reads landing", check_arm(load("arm_ci_watch"), main, land))
        expect("arm_ci_watch: armed branch is the landing branch", check_arm_branch(load("arm_ci_watch"), main, land))
        expect_red("arm_ci_watch mutant", check_arm(load("arm_ci_watch", patch=mutate_tree), main, land))
        # refresh_pr_body and cancel_old_ci
        expect("refresh_pr_body: bare push branch", check_gh_branch(load("refresh_pr_body"), main, land, "refresh_pr_body", "--head"))
        expect_red("refresh_pr_body mutant", check_gh_branch(load("refresh_pr_body", patch=mutate_tree), main, land, "refresh_pr_body", "--head"))
        expect("cancel_old_ci: bare push branch", check_gh_branch(load("cancel_old_ci"), main, land, "cancel_old_ci", "--branch"))
        expect_red("cancel_old_ci mutant", check_gh_branch(load("cancel_old_ci", patch=mutate_tree), main, land, "cancel_old_ci", "--branch"))

        # controls: no record, behaviour as today
        record = pathlib.Path(commit_policy.landing_record_path(str(main)))
        record.unlink()
        expect("review_commit control: no record", check_review(load("review_commit"), main, land, record=False))
        for name, flag in (("refresh_pr_body", "--head"), ("cancel_old_ci", "--branch")):
            mod = load(name)
            seen = []

            def fake(*args, seen=seen, flag=flag):
                if args[:2] == ("repo", "view"):
                    return 0, "owner/repo"
                if flag in args:
                    seen.append(args[args.index(flag) + 1])
                return 0, ""

            mod._gh_read = fake
            if hasattr(mod, "shutil"):
                mod.shutil = type("S", (), {"which": staticmethod(lambda n: "/bin/gh")})
            run_main(mod, main, land, "git push")
            expect("%s control: no record reads the project dir" % name, [] if seen and set(seen) == {DEV} else ["read %s, expected only %s" % (seen, DEV)])
        mod = load("arm_ci_watch")
        roots = []
        mod.arm = lambda root, sid, **kw: roots.append(real(root)) or ""
        run_main(mod, main, land, "git push")
        expect("arm_ci_watch control: no record reads the project dir", [] if roots == [real(main)] else ["read %s" % roots])
    return 0


if __name__ == "__main__":
    main_()
    if FAILURES:
        print("%d check(s) failed" % len(FAILURES))
        sys.exit(1)
    print("all checks passed")

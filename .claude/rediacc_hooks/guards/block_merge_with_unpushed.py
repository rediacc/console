"""Refuse `gh pr merge` while the branch still has commits that are only local.

WHY, and it is a near-miss from 2026-09-01 rather than a hypothetical. A land pass had pushed head `a3701d631` and was one step from `gh pr merge`. A later commit -- `23e734384`, a gate fix -- was still local. All five repos here set `delete_branch_on_merge: true`, so the merge would have deleted `0831-1` out from under it. The commit would not have been "lost" (it sits in the
local reflog) but it would have been orphaned: not on `main`, not on any branch, not in any PR, and invisible to every later `git log` a session runs. It was caught by reasoning about branch deletion, which is exactly the kind of catch that works until the once it does not.

WHY A HOOK AND NOT A CI GATE. A gate runs in CI, against the tree that was PUSHED. Local unpushed commits are invisible to it by construction -- the gate's own view is the evidence that they are missing. The only place this is checkable is the machine holding the commits, at the moment the merge is typed. That is here.

NOT COVERED BY warn-remote-drift.sh, which is the nearest thing and looks similar: that guard fires only on `git push`, and it checks the OPPOSITE direction (remote moved ahead of local, so a push would be stale). Local-ahead-of-remote at merge time is a different question with a different answer.

FAIL OPEN on every environmental error -- detached HEAD, no such remote branch, no network, a merge typed for some other repo's PR. A guard against orphaning work must never become an outage that stops work landing.

PORT NOTE ON THE FAIL-OPEN CHAIN. The bash spells it as eight consecutive `|| exit 0` / `[ -n ... ] || exit 0` lines, and every one of them is load-bearing
prose above. In Python the same chain is `run_out(..., want_rc=True)` returning
None, which is why `git_out` is called with `want_rc` set rather than with the default: the default turns a git FAILURE into an empty string, and an empty string here would fall through to the next test instead of allowing the merge. Confusing those two is how a fail-open guard becomes a fail-closed one.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-merge-with-unpushed.sh"
ORDER = 27

# On `main` there is no feature branch to strand, and /pr-merge deliberately ends there; without this arm the guard refuses the last step of the sanctioned landing sequence.
DEFECT = ('if branch == "main":', "if False:")

# THE THREE GIT WORLDS THIS GUARD DISTINGUISHES, and it distinguishes none of them inside a feature worktree. Run against this checkout it fails open on every input, because no `origin/<branch>` ref exists here -- so the whole corpus would have compared two constants. `test_every_guard_discriminates` said so on the first run, which is what these are an answer to.
ENVS = [
    ("ahead", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
    ("synced", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-synced}"}, {}),
    ("main", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
    # A FROZEN clone of this checkout, never the checkout itself: a real branch with real history and a real remote-tracking ref, and immune to the commit a concurrent session lands between the differential's bash pass and its Python side. See `_snapshot_this_worktree` in test_guards_differential.py for the measured divergence (66 unpushed commits from bash, 67 from the port) that
    # retired the live spelling on 2026-09-22.
    ("this-worktree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:this-worktree-snapshot}"}, {}),
]

EDGE_CASES = [
    ("the verb at a command position", "gh pr merge 42"),
    # `gh pr view`, `gh pr list`, and a merge typed inside a heredoc that documents this hook are all none of its business.
    ("a different pr subcommand", "gh pr view 42"),
    ("a merge for another repository", "gh pr merge 42 --repo rediacc/renet"),
    ("a merge for this repository, named", "gh pr merge 42 --repo rediacc/console"),
    ("--repo with an equals sign", "gh pr merge 42 --repo=rediacc/renet"),
    ("the verb inside quoted prose", "echo 'run gh pr merge when green'"),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    # Bypass-resistant command scanning (unwraps sh -c/eval payloads, strips heredocs+prose), same as block_admin_merge.py: worklist evidence prose MENTIONING "gh pr merge" must not trip this guard, only a real invocation.
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if not shellscan.gh_pr_at_command_pos(scan, "merge"):
        return hookio.ALLOW

    # `cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0`. Reproduced as the
    # cwd every git call below is given, rather than by changing this process's directory: a chained dispatcher runs several guards in one interpreter (see `dispatch.run_chain`), and a guard that chdir'd would move the ones after it.
    root = ev.project_dir

    branch = hookio.git_out(["symbolic-ref", "--short", "-q", "HEAD"], cwd=root, want_rc=True)
    if branch is None or branch == "":
        return hookio.ALLOW
    # On `main` there is no feature branch to strand, and /pr-merge deliberately ends there.
    if branch == "main":
        return hookio.ALLOW

    # `--repo <other>` means the merge targets a DIFFERENT repository, so this checkout's unpushed state is irrelevant to it. Only judge a merge that could delete THIS branch.
    repo_arg = ""
    matches = hookio.grep_o(r"--repo[= ]+[^ ]+", cmd)
    if matches:
        repo_arg = hookio.sed_sub(r".*[= ]", "", matches[0]).rstrip("\n")
    if not (repo_arg == "" or hookio.case_glob(repo_arg, "*/console")):
        return hookio.ALLOW

    remote = hookio.git_out(
        ["rev-parse", "-q", "--verify", "refs/remotes/origin/%s" % branch],
        cwd=root,
        want_rc=True,
    )
    if remote is None or remote == "":
        return hookio.ALLOW

    ahead = hookio.git_out(
        ["rev-list", "--count", "origin/%s..HEAD" % branch], cwd=root, want_rc=True
    )
    if ahead is None or ahead in {"", "0"}:
        return hookio.ALLOW

    log = hookio.git_out(["log", "--oneline", "origin/%s..HEAD" % branch], cwd=root)
    # `| sed 's/^/ /' | head -10`. sed indents every line INCLUDING an empty trailing one, which is why the substitution runs over records rather than over the joined text.
    indented = hookio.sed_sub(r"^", "    ", log)
    lines = indented.split("\n")[:10]
    body = "\n".join(lines)

    ev.warn_raw(
        "BLOCKED: %s commit(s) on '%s' are not pushed, and merging deletes the branch.\n"
        "\n"
        "%s\n"
        "\n"
        "`delete_branch_on_merge` is true on all five repos here, so the merge removes\n"
        "'%s' as soon as it lands. These commits are not on main, not on any other\n"
        "branch, and not in any PR. They survive only in this machine's reflog, where no\n"
        "later `git log` will find them.\n"
        "\n"
        "This is not the same thing as an unclean tree, and it is not the drift that\n"
        "warn-remote-drift.sh checks: that one fires on `git push` when the REMOTE has\n"
        "moved ahead. This is local work the remote has never seen.\n"
        "\n"
        "Pick one:\n"
        "  1. Push them, let CI run, then merge:  git push origin %s\n"
        "  2. If they genuinely do not belong in this PR, move them to their own branch\n"
        "     FIRST (`git branch <name>`), so the merge cannot take them with it.\n"
        % (ahead, branch, body, branch, branch)
    )
    return hookio.DENY

"""Refuse a commit on `main` unless it is a well-formed `[hotfix]`, and refuse `[hotfix]` anywhere else.

WHY. Operator ruling, 2026-09-25: "if we really need to fix some bugs on main then okay but otherwise we must follow the branch naming rules to open new branches if we're working on main." Work lands on the one `MMDD-N` branch in small reviewed commits; `main` takes a commit only for the main-only failure class of pr-merge step 5 (a job that failed on `main` never ran, or ran differently, on the PR's own run) or when the operator called it a hotfix in this task.

WHAT A HOTFIX CARRIES (the commit-policy plan in agent/plans, section 4.1, checked by `commit_policy.hotfix_ok`):

  * `[hotfix]` at the end of the subject;
  * a `Hotfix-Evidence:` trailer naming the red main run (id or actions/runs URL) or `ASKED:<ISO minute>`;
  * at most `hotfix_max_files` paths (5, decision 4), counted from the pathspec or, without one, from the index.

It needs no `PR-TASK:` trailer (`block_untagged_commit` stops asking on `main`), it is always reviewed (Z, operator ruling 1), and it is PUSHED only by the operator with `!`: `block_push_to_protected_branch` is unconditional and stays that way.

OFF `main` THE TAG IS REFUSED, so the audit stays clean: a `[hotfix]` on a feature branch would read as a reviewed-on-main commit to anyone scanning the log for them.

WHAT IS JUDGED. Every `git commit` bash would run in the command (a `sh -c` payload and an `eval` included), each against the branch of the repository it acts on: this checkout, or a submodule inside it through `cd`/`-C` (`git -C private/account commit` on account's `main` is refused like the console's). A repository outside this checkout (a `/tmp` fixture) is not this policy's business. The message is read in the three shapes `block_untagged_commit` established; one this guard cannot read on `main` is refused, because a hotfix it cannot see is not one it can admit.

THE GIT-LEVEL TWIN. `.claude/rediacc_hooks/git/commit-msg` enforces the same rule on every commit in a checkout whose `core.hooksPath` points there, including the operator's own terminal; that layer honours `COMMIT_POLICY_OK=1`, this one never does.
"""

from rediacc_hooks import commit_policy, hookio

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 45

# The `main` arm is the guard. With it gone every commit on `main` passes, which is the drift the ruling exists to stop.
DEFECT = ('if branch == "main":', "if False:")

ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("main-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
    ("feature-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
]

HOTFIX = 'git commit -m "fix(ci): x [hotfix]\n\nHotfix-Evidence: 12345678" -- a.ts'

EDGE_CASES = [
    ("a plain commit", 'git commit -m "feat(x): y" -- a.ts'),
    ("a valid hotfix", HOTFIX),
    (
        "a hotfix above the file limit",
        'git commit -m "fix: x [hotfix]\n\nHotfix-Evidence: 12345678" -- a b c d e f',
    ),
    ("a hotfix with no evidence", 'git commit -m "fix: x [hotfix]" -- a.ts'),
    (
        "a hotfix whose evidence has no known shape",
        'git commit -m "fix: x [hotfix]\n\nHotfix-Evidence: trust me" -- a.ts',
    ),
    (
        "the ASKED evidence form",
        'git commit -m "fix: x [hotfix]\n\nHotfix-Evidence: ASKED:2026-09-25T10:00Z" -- a.ts',
    ),
    ("a wrapper payload is still judged", "sh -c 'git commit -m \"feat: y\" -- a.ts'"),
    ("a commit in a scratch repo", 'git -C /tmp commit -m "x" -- a'),
    ("prose about committing", "echo 'git commit on main'"),
    ("git log is not a commit", "git log -n 5"),
]


def _message(branch, main_hint):
    if branch == "main":
        return (
            "BLOCKED: this commits to `main`, and it is not a `[hotfix]`.\n"
            "\n"
            "Operator ruling, 2026-09-25: work lands on the one MMDD-N branch in small\n"
            "reviewed commits; `main` takes a commit only for a genuine hotfix (a job that\n"
            "failed on `main` and never ran, or ran differently, on the PR's own run; or the\n"
            "operator called it a hotfix in this task).\n"
            "\n"
            "Move to the branch first; the uncommitted work comes along:\n"
            "\n"
            "  %s\n"
            "\n"
            "A genuine hotfix ends its subject with `[hotfix]` and carries a trailer:\n"
            "\n"
            "  fix(ci): what broke on main [hotfix]\n"
            "\n"
            "  Hotfix-Evidence: <red main run id or URL>   (or ASKED:<YYYY-MM-DDTHH:MMZ>)\n"
            "\n"
            "at most 5 files, no PR-TASK trailer. The operator pushes it with `!`.\n" % main_hint
        )
    return (
        "BLOCKED: `[hotfix]` is for commits on `main`, and this branch is `%s`.\n"
        "\n"
        "A hotfix tag on a feature branch reads as a reviewed-on-main commit to anyone\n"
        "scanning the log for them. Drop the tag; the commit rides the branch's PR.\n" % branch
    )


def _switch_hint(repo_root, main_hint_cache):
    if repo_root in main_hint_cache:
        return main_hint_cache[repo_root]
    live = commit_policy.live_branches(repo_root, gh=False)
    if live:
        hint = "git switch %s" % live[0]
    else:
        hint = "git switch -c <today's MMDD-N: MAX+1 over `gh pr list --state all` heads>"
    main_hint_cache[repo_root] = hint
    return hint


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null"):
        return hookio.ALLOW
    commits = commit_policy.git_runs(cmd, "commit")
    if not commits:
        return hookio.ALLOW

    root = ev.env("CLAUDE_PROJECT_DIR") or hookio.git_out(["rev-parse", "--show-toplevel"])
    base = ev.field("cwd") or root
    cfg = commit_policy.load_config(root)
    hints: dict[str, str] = {}
    for commit in commits:
        # A directory that resolves to no repository is one git itself will refuse; one outside this checkout is not this policy's business.
        repo = commit_policy.run_repo(commit, base)
        if not repo or not commit_policy.is_inside(repo, root):
            continue
        branch = commit_policy.current_branch(repo)
        msg = commit_policy.commit_message_text(cmd, base, run=commit)
        is_hotfix = "hotfix" in commit_policy.tags(msg)
        if branch == "main":
            if not is_hotfix:
                ev.warn_raw(_message("main", _switch_hint(repo, hints)))
                return hookio.DENY
            paths = commit_policy.judged_paths(commit, cmd, repo, base)
            ok, reason = commit_policy.hotfix_ok(msg, paths, cfg)
            if not ok:
                ev.warn_raw(
                    "BLOCKED: this `[hotfix]` on `main` is not well-formed: %s.\n"
                    "\n"
                    "A hotfix ends its subject with `[hotfix]`, carries a\n"
                    "`Hotfix-Evidence: <red main run id or URL | ASKED:<YYYY-MM-DDTHH:MMZ>>`\n"
                    "trailer, and touches at most %d files. Anything larger belongs on the\n"
                    "branch and its reviewed PR.\n" % (reason, int(cfg["hotfix_max_files"]))
                )
                return hookio.DENY
        elif is_hotfix:
            ev.warn_raw(_message(branch or "(detached)", ""))
            return hookio.DENY
    return hookio.ALLOW

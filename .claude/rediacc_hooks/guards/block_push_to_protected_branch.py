"""Refuse `git push` when its destination resolves to `main`, in any spelling.

THE INCIDENT THIS CLOSES, 2026-09-22. A background sub-agent ran `.ci/scripts/release/update-homebrew-tap.sh --push` as a W7P5-a real-run rehearsal. That script's `update_submodule_pointer()` does, from the REAL working checkout (not an isolated clone):

    git -c user.name=... -c user.email=... commit -m "chore(release): update homebrew-tap ..."
    git push origin HEAD:main

Nobody typed `git push origin HEAD:main` that day. A shell script three process-levels down the Bash tool call did, and NOTHING in the pre-bash chain inspected it, because every guard in this package (including `block_git_force_push.py`, the nearest thing) reads the literal command TEXT the Bash tool was invoked with -- `.ci/scripts/release/update-homebrew-tap.sh --push` -- which
never contains the string "git push" at all. The dangerous command lived inside a file on disk, not on the command line, and a text scanner cannot see into a file it was never asked to read. That gap is NOT closed by this guard either: it is recorded here so it is not mistaken for closed, and the real, durable fix is the class of fix CLAUDE.md's worklist owns (the script itself
must never push from `$REPO_ROOT` -- it is out of this guard's reach, `.ci/scripts/release/**` is explicitly off limits to it).

What this guard DOES close is the other half: an agent's own Bash tool typing `git push` straight at `main`, or a wrapper (`eval`, `sh -c`) doing the same. GitHub's own ruleset let the push through as an ADMIN BYPASS (`gh api repos/rediacc/console/rulesets/12344707`: `bypass_actors` grants `RepositoryRole` id 5 "always" bypass of both the pull-request rule and the
required-status-checks rule; the push output's own text, "Bypassed rule violations... 2 of 2 required status checks are expected", is that bypass firing) -- so GitHub-side protection was never going to stop a credential that already has bypass rights, and a hook that only fires from THIS tool's own Bash calls is the one lever that does not depend on GitHub's configuration at all.
The open PR for the branch then auto-flipped to MERGED, even though `ci.yml`'s last several runs on that branch were red: GitHub does that whenever a PR branch's commits land on the base branch by ANY means, push included, which is a second reason "check CI before push" is the wrong shape of fix here -- CI's colour was never consulted by GitHub either, once the commits were on
`main`.

WHY THIS IS UNCONDITIONAL, and why "block only when CI is red" was rejected. A pre-bash hook sees the command about to run, not GitHub's live state, so it cannot cheaply ask "is CI red" on every git command -- but it does not need to. No direct push to `main` should ever succeed from this tool, in any CI state, because normal landings go through a reviewed PR (`gh pr merge --rebase
--auto`, `.claude/commands/pr-merge.md`). A guard conditioned on CI colour would have let this exact incident through anyway: nothing here ever asked GitHub what colour CI was, the push simply ran. Blocking every direct push to `main` is strictly STRONGER than gating on CI colour and costs nothing legitimate: see the next paragraph for the one sanctioned exception, which is not for
this tool at all.

THE ONE DOCUMENTED DIRECT PUSH TO MAIN, named here because this guard now sits in its path. `.claude/commands/pr-merge.md`'s pure-fast-forward fallback (step 3, when `gh pr merge --rebase` fails with "This branch can't be rebased" on an oversized PR) reads `git push origin origin/<branch>:main` -- and until this guard existed that line ran from whichever session was driving
`/pr-merge`. It still can, exactly like `git worktree add` (`block_worktree_add.py`) and a force-push rewrite (`block_git_force_push.py`): the operator runs it directly with the `!` prefix, which bypasses PreToolUse hooks entirely. That is not a new restriction invented for this guard -- CLAUDE.md's own rule already reads "Never push to `main`... without explicit user
authorization" -- it is this guard making the existing rule apply to the one place in this repo's own docs where an agent might otherwise have typed `git push` at `main` on its own.

WHAT COUNTS AS "main", explicit or not:
  git push origin main                     bare destination name
  git push origin HEAD:main                the incident's own shape
  git push origin refs/heads/main          the long form
  git push origin <anything>:main          any source, explicit destination
  git push origin :main                    the empty-source delete form
  git push origin --delete main            the flagged delete form
  git push --all origin                    every branch, main included
  git push                                 no refspec at all -- git's own
  git push origin                          fallback (push.default) is the
  git push origin HEAD                     CURRENT branch, or its remote-
                                            side alias HEAD; this checkout's
                                            actual branch decides these three

A bare `--tags` push moves no branch ref at all and is let through even while sitting on `main`; `--follow-tags` is NOT exempted, because unlike `--tags` it also pushes the current branch.

FAILS OPEN on the branch lookup for the three implicit forms (`git symbolic-ref` itself failing, a detached HEAD, no such repo): the same command would fail at the real `git` layer too, so refusing here buys nothing and an outage over a broken lookup is the wrong direction for a guard whose whole job is to stay out of the way of everything except main.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = None
# AHEAD OF block_unverified_push (its old position, now 40), deliberately: "this branch may not be pushed to at all" is the more fundamental refusal, and telling a session to go run `npm run ci:quick` for a push it was never going to be allowed to make, regardless of that run's colour, is the wrong message to lead with. Every guard from here on was re-keyed by one to make room.
ORDER = 39

# `run` reaching the branch check is the whole reason this guard exists for the IMPLICIT forms; the header records why the check itself must fire on "main" rather than skip it.
DEFECT = ('if branch == "main":', "if False:")

# THE THREE GIT WORLDS THE IMPLICIT FORMS DISTINGUISH, same reasoning as block_merge_with_unpushed.py's own ENVS: run against THIS checkout (whatever feature branch a session happens to be on) a bare `git push` always takes the "not main" branch of the fallback logic, so the corpus alone proves nothing about the branch check -- and the defect above would pass
# silently planted, exactly as it did before this was added (test_the_differential_can_fail caught it live on 2026-09-22).
ENVS = [
    ("main-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
    ("feature-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
    # A FROZEN clone of this checkout rather than the live one, for the reason block_merge_with_unpushed.py:31 records: a shared tree's branch moves under a running differential. Same snapshot, built once per session.
    ("this-worktree", {"CLAUDE_PROJECT_DIR": "{FIXTURE:this-worktree-snapshot}"}, {}),
]

GIT_AT_CMD = hookio.rx(r"(^|[;&|(]|\$\(|`)[{S}]*git([{S}]+-[A-Za-z-]+([{S}]+[^ ;&|]+)?)*[{S}]+")
GIT_PUSH_AT_CMD = GIT_AT_CMD + hookio.rx(r"push([{S}]|$)")

# A dry run publishes nothing and buys no protection to police.
DRY_RUN = r"git push[^|;&]*--dry-run"

# Explicit destination "main": a colon-qualified refspec (`<src>:main`, `<src>:refs/heads/main`, the empty-source delete form `:main`) or a BARE token naming it directly (`git push origin main`, `git push origin refs/heads/main`). Left boundary is a run's start, whitespace, or the refspec colon; right boundary is whitespace, a closing paren, or the end of the statement. `[^;&|)]*`
# bounds the match to THIS invocation, the same convention `block_git_force_push.py` and `block_unverified_push.py` already use for "the rest of this command, not the rest of the line".
DEST_MAIN = hookio.rx(r"git push[^;&|)]*[{S}:](refs/heads/)?main([{S})]|$)")

# `--all` pushes every branch, main included.
ALL_BRANCHES = hookio.rx(r"git push[^;&|)]*[{S}]--all([{S})]|$)")

# `--tags` pushes only tag refs -- no branch ref moves, so this is not this guard's business even while sitting on main. `--follow-tags` is deliberately NOT matched here: unlike `--tags` it also pushes the current branch, so it falls through to BARE_PUSH below instead.
TAGS_ONLY = hookio.rx(r"git push[^;&|)]*[{S}]--tags([{S})]|$)")

# No destination named at all: `git push`, or `git push <remote>` with only recognised flags and at most one bare word (the remote). Git's own fallback (push.default, "simple" since Git 2.0) is to push the CURRENT branch to its upstream, so whether that lands on `main` depends on what branch this checkout is on -- read below rather than guessed here.
BARE_PUSH = hookio.rx(
    r"git push([{S}]+(--[A-Za-z-]+(=[^{S};&|)]*)?|-[A-Za-z]+))*([{S}]+[A-Za-z0-9_.-]+)?[{S}]*([;&|)]|$)"
)

# `git push <remote> HEAD` (no colon) is git's documented alias for "the remote branch of the SAME NAME as the branch checked out here" -- the colon-less twin of the incident's own `HEAD:main`, just as blind to which branch that resolves to without reading this checkout.
BARE_HEAD = hookio.rx(r"git push[^;&|)]*[{S}]HEAD([{S})]|$)")

MESSAGE = (
    "BLOCKED: this pushes straight to a PROTECTED branch (main). Direct pushes bypass code review and required status checks -- which is exactly what happened on 2026-09-22, when a script run through this tool's own Bash access (update-homebrew-tap.sh's update_submodule_pointer()) ran `git push origin HEAD:main` from the real working checkout. GitHub's own ruleset let it through as an admin bypass ('Bypassed rule violations... 2 of 2 required status checks are expected'), and the branch's open PR auto-flipped to MERGED with red CI on its last several runs. Nobody typed that push; a script three levels down did, and nothing inspected it before it ran.\n"
    "\n"
    "The fix is not 'check CI first' -- a hook sees the command, not GitHub's live state, and GitHub itself never consulted CI colour before flipping the PR either. The fix is that NO direct push to main should ever succeed from this tool, in any spelling: explicit (`git push origin main`, `git push origin HEAD:main`, `git push origin refs/heads/main`, `git push origin :main`, `--delete main`, `--all`) or implicit (a bare `git push` / `git push origin` / `git push origin HEAD` while this checkout is ON main).\n"
    "\n"
    "Land through a reviewed PR instead (`gh pr merge --rebase --auto`, see .claude/commands/pr-merge.md). The one documented direct push to main -- that same file's pure-fast-forward fallback, `git push origin origin/<branch>:main` -- is the operator's call, not an agent's: run it directly with the `!` prefix, which bypasses this hook entirely. Do not ask through chat and then run it here."
)

EDGE_CASES = [
    ("the incident's own shape", "git push origin HEAD:main"),
    ("a bare destination name", "git push origin main"),
    ("an explicit source, destination main", "git push origin 0914-1:main"),
    ("the refs-qualified long form", "git push origin refs/heads/main"),
    ("the empty-source delete form", "git push origin :main"),
    ("the flagged delete form", "git push origin --delete main"),
    ("--all pushes every branch, main included", "git push --all origin"),
    ("a bare push with no refspec at all", "git push"),
    ("a remote with no refspec", "git push origin"),
    ("HEAD with no colon aliases the current branch's own name", "git push origin HEAD"),
    ("a wrapper payload is still scanned", 'eval "git push origin main"'),
    # Controls: none of these are this guard's business.
    ("an ordinary push to a feature branch", "git push origin 0914-1"),
    ("a branch merely prefixed with main", "git push origin main-2"),
    ("a branch merely suffixed onto main", "git push origin not-main"),
    ("an explicit non-main destination overrides ambiguity", "git push origin feature-x"),
    ("a dry run publishes nothing", "git push --dry-run origin main"),
    ("tags only, no branch ref moves", "git push --tags origin"),
    ("prose about pushing is not a push", "echo 'never push straight to main'"),
    ("git pull is not git push", "git pull --rebase"),
    (
        "cd into a submodule pushing its own feature branch",
        "cd private/renet && git push origin 0914-1",
    ),
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd in ("", "null"):
        return hookio.ALLOW

    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if not hookio.grep_q(GIT_PUSH_AT_CMD, scan):
        return hookio.ALLOW

    if hookio.grep_q(DRY_RUN, cmd):
        return hookio.ALLOW

    if hookio.grep_q(DEST_MAIN, scan) or hookio.grep_q(ALL_BRANCHES, scan):
        ev.warn(MESSAGE)
        return hookio.DENY

    if hookio.grep_q(TAGS_ONLY, scan):
        return hookio.ALLOW

    if not (hookio.grep_q(BARE_PUSH, scan) or hookio.grep_q(BARE_HEAD, scan)):
        return hookio.ALLOW

    # `cd "${CLAUDE_PROJECT_DIR:-.}"`, same convention as block_merge_with_unpushed.py, then
    # resolve any `-C <dir>` / `cd <dir>` hint the command itself carries (a chained dispatcher runs several guards in one interpreter, so this reads cwd rather than changing it).
    root = ev.project_dir
    target = shellscan.target_root(scan, root)
    git_root = target if target != "" else root

    branch = hookio.git_out(["symbolic-ref", "--short", "-q", "HEAD"], cwd=git_root, want_rc=True)
    if branch is None or branch == "":
        return hookio.ALLOW
    if branch == "main":
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW

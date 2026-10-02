"""Block force-push (--force / -f / --mirror / +refspec), and --force-with-lease to anything but the one live MMDD-N branch.

THE LEASE EXCEPTION, box M3 of PLAN-plan-per-pr-loop (operator ruling 2026-10-02: "The live MMDD-N branch may be force-pushed with --force-with-lease only"). A rebase of the live branch has to be republished, and the lease is the form that refuses to overwrite a remote tip nobody has seen. It is admitted only when EVERY one of these holds, read from the parsed command (`commit_policy.git_runs`, the shared lexer) and from the target repository's own refs:

  * no other forcing form anywhere in the command: no --force, -f, --mirror, and no `+refspec`;
  * every lease push the text shows is one the lexer placed (a count mismatch is a push this guard cannot judge, and is refused);
  * the repository is inside this checkout, and its checked-out branch is an `MMDD-N` name that is its ONE live branch (`commit_policy.live_branches`, local facts only); in a submodule that name is also the console's;
  * the push names only that branch: no refspec (git pushes the current branch), `<branch>`, `HEAD`, `HEAD:<branch>` or `<branch>:<branch>`, `refs/heads/` spellings included, to `origin`;
  * a lease value, when given, names that same branch (`--force-with-lease=<branch>[:<expected sha>]`).

Everything else stays refused, `main` above all: `main` is never an `MMDD-N` name, so no lease reaches it.

THE ORIGINAL RULE, unchanged for every other form:

The first three flags are the obvious spelling. The other two were a HOLE, found 2026-08-23 while an agent was carrying out an operator-approved history rewrite: this guard refused the rewrite push, and the agent noticed that dropping the word --force would have slipped the identical non-fast-forward push straight past the regex. A --mirror git push forces every ref and deletes
remote refs absent locally; a leading + on a refspec forces that ref. Both rewrite published history, which is exactly what this guard reserves for the operator, and neither was matched.

THE + REFSPEC MATCH IS DELIBERATELY UNQUALIFIED, and the first attempt at this fix was not. It matched only `+refs/...`, which is the long form. A refspec does NOT need to be refs-qualified to force: `+main:main` and `+HEAD:main` are the common shorthand and force the remote ref exactly the same way. Both slipped straight past the widened guard that this file's own commit message
said had closed the hole. Caught in review on PR #571, and reproduced before fixing: rc 0 for `+main:main` and `+HEAD:main`, rc 2 for `+refs/heads/main`.

The pattern requires WHITESPACE before the plus, so a plus INSIDE a token is untouched: `HEAD:refs/heads/feature+x` is a legal branch name and stays allowed. That arm is pinned by a control in test-hooks.sh, because a guard widened without one is how the next false positive gets shipped.

Nothing in this repo pushes with --mirror or a + refspec (verified by grep over *.sh, *.yml, *.md, *.ts), so widening the pattern costs no legitimate caller. The mirror git push for a history rewrite is run by the operator directly, with the ! prefix, which is the intended path.
"""

import os
import re

from rediacc_hooks import commit_policy, hookio, shellscan

CHAIN = "pre-bash"
ORDER = 18

# THE TWO GIT WORLDS THE LEASE ARM DISTINGUISHES. `default` keeps its label and points at a checkout on `main`, where no lease is admitted, so every record the cross-corpus froze before M3 answers as it did. `live-branch` is a checkout on `0831-1`, the one live branch, where a lease naming it is admitted. Without the second world no case could reach the allow arm, and without the first the corpus would read the live checkout's branch.
ENVS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    ("default", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-main}"}, {}),
    ("live-branch", {"CLAUDE_PROJECT_DIR": "{FIXTURE:git-ahead}"}, {}),
]

# Re-qualifying the plus arm to `+refs/` is precisely the first attempt the header records: `+main:main` and `+HEAD:main` go back to being allowed while the long form is still refused, which is what made the hole look closed.
DEFECT = (r"]\+[^", r"]\+refs/[^")

# ANCHORED TO COMMAND POSITION 2026-08-28, after check:ci-guard-mention-anchoring found this guard refusing an ordinary sentence. Matching the phrase ANYWHERE means a doc line, a worklist note or an `echo` explaining the rule is refused as if it were the rule being broken. This NARROWS PROSE ONLY: every control below still blocks the real command, at line start and after a
# separator. NOT AN ALLOW-LIST, which this guard's own text forbids: the set of refused FLAGS is untouched. Only the position of `git push` is constrained, so a sentence about force-pushing stops being treated as one.
#
# ROUTED THROUGH lib/command-scan.sh 2026-08-30 (review finding on PR #579). Every sibling guard touched in this same PR (block-cli-bundle.sh, block-protected-files.sh, block-unverified-push.sh, block-untagged-commit.sh) scans hook_scan_target's output specifically because it unwraps eval/sh -c payloads; this guard matched $CMD directly, so `eval "git push --force ..."` or `sh -c
# 'git push --force ...'` left the push text preceded by a quote character instead of a line start or accepted separator, and the anchor added above never fired -- the exact bypass class command-scan.sh's own header exists to close, on the one guard this file calls "the whole security story".
FORCE_PUSH = hookio.rx(
    r"(^|[;&|(])[{S}]*git push[^|;&]*(--force-with-lease|--force([{S}]|=|$)|[{S}]-f([{S}]|$)|--mirror([{S}]|=|$)|[{S}]\+[^{S}])"
)

# The same forms WITHOUT the lease arm: any match here is a force the lease exception never covers.
FORCE_NOT_LEASE = hookio.rx(
    r"(^|[;&|(])[{S}]*git push[^|;&]*(--force([{S}]|=|$)|[{S}]-f([{S}]|$)|--mirror([{S}]|=|$)|[{S}]\+[^{S}])"
)

# One match per `git push` statement carrying a lease, to compare against what the lexer placed.
LEASE_PUSH = hookio.rx(r"(^|[;&|(])[{S}]*git push[^|;&]*--force-with-lease")

LEASE_FLAG = "--force-with-lease"
# Flags that ride a lease push without forcing anything else. `--force-if-includes` only narrows the lease.
LEASE_COMPANIONS = frozenset(("-q", "--quiet", "-v", "--verbose", "--force-if-includes"))
SHA = re.compile(r"^[0-9a-f]{7,40}$")

MESSAGE = (
    "BLOCKED: this force-push is not admitted (--force / -f / --mirror / +refspec are never "
    "admitted; --force-with-lease only to the one live MMDD-N branch). Force-push overwrites "
    "remote history and erases the trace of individual PR changes, which is exactly what "
    "broke traceability before. Use a plain git push so each CI fix lands as its own "
    "reviewable commit.\n"
    "\n"
    "THE ADMITTED FORM (operator ruling 2026-10-02): after a rebase of the live branch, "
    "`git push --force-with-lease origin <live MMDD-N branch>` from that branch's checkout, "
    "optionally `--force-with-lease=<branch>:<expected sha>`. Never main, never another "
    "branch, never --force, -f, --mirror or a +refspec.\n"
    "\n"
    "When the branch AND its submodules have to be republished together, there is a "
    "mediated verb for exactly that:\n"
    "\n"
    "    .claude/hooks/stop/worklist.py --git force-push <branch>            # prints the plan\n"
    "    .claude/hooks/stop/worklist.py --git force-push <branch> --execute  # performs it\n"
    "\n"
    "It refuses main, refuses every forcing flag except the leased one, pushes SUBMODULES "
    "BEFORE THE CONSOLE so a console head can never name an unpublished submodule commit, "
    "prints the pre-push remote tips as an UNDO block, and halts on the first failure. Dry "
    "run by default: run it without --execute and read the plan first.\n"
    "\n"
    "The lease rule is exact and stays exact: no wider allow-list. Use the admitted form or "
    "the verb."
)

EDGE_CASES = [
    ("the obvious flag", "git push --force origin main"),
    ("the short flag", "git push -f origin main"),
    ("the leased flag", "git push --force-with-lease"),
    # The 2026-08-23 hole, both halves.
    ("a mirror push forces every ref", "git push --mirror origin"),
    ("a shorthand plus refspec forces one", "git push origin +main:main"),
    ("the refs-qualified long form", "git push origin +refs/heads/main"),
    # The control that keeps the widening honest.
    ("a plus INSIDE a token is a legal branch name", "git push origin HEAD:refs/heads/feature+x"),
    ("a plain push", "git push origin main"),
    # The 2026-08-30 routing exists for these two.
    ("prose about force-pushing is not one", "echo 'never git push --force'"),
    ("a wrapper payload is still scanned", 'eval "git push --force origin main"'),
    # RULE T (PLAN-retire-bash-oracles A4): A0's fail-open list, measured rc 0 on 2026-09-24 and refused since `shellscan.lifted_commands`. Every shape below is a push bash RUNS; the prose, data and print-only twins after them stay allowed.
    ("L1 an assignment's substitution runs", "x=$(git push --force origin main)"),
    ("L1 an assignment's backticks run", "x=`git push --force origin main`"),
    ("L2 a substitution inside double quotes runs", 'echo "$(git push --force origin main)"'),
    (
        "L3 an unquoted heredoc body expands",
        "cat > R.md <<EOF\n$(git push --force origin main)\nEOF",
    ),
    ("L4 a shell reading a heredoc runs it", "bash <<'EOF'\ngit push --force origin main\nEOF"),
    ("L4 a shell reading a here-string runs it", "bash <<< 'git push --force origin main'"),
    ("L5 a here-string swallows no later line", "cat <<<x\ngit push --force origin main"),
    (
        "L6 an apostrophe inside double quotes pairs with nothing",
        "echo \"it's\"; git push --force origin main; echo 'y'",
    ),
    ("L7 a quoted command word is still git", '"git" push --force origin main'),
    ("L7 an escaped command word is still git", "\\git push --force origin main"),
    ("L8 a backslash-newline joins the command", "git push \\\n--force origin main"),
    ("L9 a brace group", "{ git push --force origin main; }"),
    ("L9 a leading redirect", ">/dev/null git push --force origin main"),
    (
        "L9 sudo and time run the next word",
        "sudo git push -f origin main; time git push --mirror origin",
    ),
    ("L10 c inside a short-flag bundle", "bash -ce 'git push --force origin main'"),
    ("L11 the second wrapper on a line", "sh -c true; sh -c 'git push --force origin main'"),
    (
        "control: a quoted heredoc body is data",
        "cat > R.md <<'EOF'\n$(git push --force origin main)\nEOF",
    ),
    (
        "control: double-quoted prose is not a push",
        'git commit -m "never git push --force origin main"',
    ),
    ("control: command -v only prints", "command -v git push --force"),
    # M3 (PLAN-plan-per-pr-loop, operator ruling 2026-10-02). `0831-1` is the live branch of the `live-branch` world and absent from the `default` (main) world, so each admitted case is refused there: the two worlds are the two directions.
    ("M3 lease to the live branch", "git push --force-with-lease origin 0831-1"),
    (
        "M3 lease with an expected sha",
        "git push --force-with-lease=0831-1:0123456789abcdef0123456789abcdef01234567 origin 0831-1",
    ),
    ("M3 lease of HEAD to the live branch", "git push --force-with-lease origin HEAD:0831-1"),
    ("M3 lease in a wrapper payload", "sh -c 'git push --force-with-lease origin 0831-1'"),
    ("M3 lease to main", "git push --force-with-lease origin main"),
    ("M3 lease of HEAD to main", "git push --force-with-lease origin HEAD:main"),
    ("M3 lease to another branch", "git push --force-with-lease origin 0831-2"),
    ("M3 lease beside a plus refspec", "git push --force-with-lease origin +0831-1"),
    ("M3 lease beside --force", "git push --force --force-with-lease origin 0831-1"),
    ("M3 lease naming another ref", "git push --force-with-lease=main origin 0831-1"),
    ("M3 lease to two refspecs", "git push --force-with-lease origin 0831-1 0831-2"),
    ("M3 lease to another remote", "git push --force-with-lease upstream 0831-1"),
    ("M3 lease in a repository outside", "git -C /tmp push --force-with-lease origin 0831-1"),
    ("M3 lease with --all", "git push --force-with-lease --all origin"),
    ("M3 lease through -C to the live branch", "git -C . push --force-with-lease origin 0831-1"),
    # A global option between `git` and `push` matched nothing until 2026-10-02 (both measured rc 0 then).
    ("a -C global option before push", "git -C . push --force origin main"),
    ("a -c global option before push", "git -c a=b push -f origin x"),
]


def _count(pattern, text):
    compiled = re.compile(pattern)
    records, _ = hookio._records(text)
    return sum(len(list(compiled.finditer(record))) for record in records)


def _names(branch):
    return (branch, "refs/heads/" + branch)


def _lease_run_refusal(run, root, base):
    """ "" when this lease push is the admitted form, else why not."""
    _, _, args = commit_policy.git_split(run.argv)
    flags = [a for a in args if a.startswith("-")]
    positionals = [a for a in args if not a.startswith("-")]
    repo = commit_policy.run_repo(run, base)
    if not repo or not commit_policy.is_inside(repo, root):
        return "the repository it pushes is not inside this checkout"
    live = commit_policy.current_branch(repo)
    if not commit_policy.BRANCH_SHAPE.match(live):
        return "the checkout is on `%s`, not an MMDD-N branch" % (live or "(detached)")
    if commit_policy.live_branches(repo, gh=False) != [live]:
        return "`%s` is not the ONE live branch here" % live
    top = commit_policy.toplevel(root)
    if os.path.realpath(repo) != os.path.realpath(top):
        console = commit_policy.current_branch(top, foreign=True) if top else ""
        if live != console:
            return "a submodule's live branch carries the console's name (`%s`)" % console
    for flag in flags:
        if flag == LEASE_FLAG or flag in LEASE_COMPANIONS:
            continue
        if flag.startswith(LEASE_FLAG + "="):
            ref = flag[len(LEASE_FLAG) + 1 :]
            name, _, expect = ref.partition(":")
            if name not in _names(live) or (expect and not SHA.match(expect)):
                return "the lease names `%s`, not the live branch `%s`" % (ref, live)
            continue
        return "`%s` is not part of the admitted lease form" % flag
    if len(positionals) > 2:
        return "it pushes more than one refspec"
    if positionals and positionals[0] != "origin":
        return "the remote is `%s`, not origin" % positionals[0]
    if len(positionals) == 2:
        src, colon, dst = positionals[1].partition(":")
        if not colon:
            dst = src
        if src not in (*_names(live), "HEAD") or dst not in (*_names(live), "HEAD"):
            return "the refspec `%s` is not the live branch `%s`" % (positionals[1], live)
    return ""


def lease_refusal(ev, cmd, scan, text_scan):
    """ "" when every force in `cmd` is an admitted lease to the one live branch, else why not.

    `scan` carries the lexer's canonical push lines; `text_scan` is the command text alone, whose lease count the lexer has to reach (a lease the text shows and the lexer did not place is one this guard cannot judge).
    """
    if hookio.grep_q(FORCE_NOT_LEASE, scan):
        return "a forcing form other than --force-with-lease"
    leases = [
        r
        for r in commit_policy.git_runs(cmd, "push")
        if any(a == LEASE_FLAG or a.startswith(LEASE_FLAG + "=") for a in r.argv)
    ]
    if not leases or len(leases) < _count(LEASE_PUSH, text_scan):
        return "a lease push this guard cannot place"
    root = ev.project_dir
    base = ev.field("cwd") or root
    for run in leases:
        reason = _lease_run_refusal(run, root, base)
        if reason:
            return reason
    return ""


def run(ev):
    cmd = ev.raw("tool_input", "command")
    text_scan = scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    # `git -C <dir> push --force` put a word between `git` and `push` and matched nothing here until 2026-10-02; the lexer's canonical spelling of each push closes that (commit_policy.push_texts).
    canon = commit_policy.push_texts(cmd)
    if canon:
        scan = scan + "\n" + canon

    if hookio.grep_q(FORCE_PUSH, scan):
        reason = lease_refusal(ev, cmd, scan, text_scan)
        if reason == "":
            return hookio.ALLOW
        ev.warn(MESSAGE + "\n\nNot admitted here because: " + reason + ".")
        return hookio.DENY
    return hookio.ALLOW

"""Block force-push (--force / -f / --force-with-lease / --mirror / +refspec).

The first three flags are the obvious spelling. The other two were a HOLE, found 2026-08-23 while an agent was carrying out an operator-approved history rewrite: this guard refused the rewrite push, and the agent noticed that dropping the word --force would have slipped the identical non-fast-forward push straight past the regex. A --mirror git push forces every ref and deletes
remote refs absent locally; a leading + on a refspec forces that ref. Both
rewrite published history, which is exactly what this guard reserves for the operator, and neither was matched.

THE + REFSPEC MATCH IS DELIBERATELY UNQUALIFIED, and the first attempt at this fix was not. It matched only `+refs/...`, which is the long form. A refspec does NOT need to be refs-qualified to force: `+main:main` and `+HEAD:main` are the common shorthand and force the remote ref exactly the same way. Both slipped straight past the widened guard that this file's own commit message
said had closed the hole. Caught in review on PR #571, and reproduced before fixing: rc 0 for `+main:main` and `+HEAD:main`, rc 2 for `+refs/heads/main`.

The pattern requires WHITESPACE before the plus, so a plus INSIDE a token is untouched: `HEAD:refs/heads/feature+x` is a legal branch name and stays allowed. That arm is pinned by a control in test-hooks.sh, because a guard widened without one is how the next false positive gets shipped.

Nothing in this repo pushes with --mirror or a + refspec (verified by grep over *.sh, *.yml, *.md, *.ts), so widening the pattern costs no legitimate caller. The mirror git push for a history rewrite is run by the operator directly, with the ! prefix, which is the intended path.
"""

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
TWIN = "pre-bash/block-git-force-push.sh"
ORDER = 19

# Re-qualifying the plus arm to `+refs/` is precisely the first attempt the header records: `+main:main` and `+HEAD:main` go back to being allowed while the long form is still refused, which is what made the hole look closed.
DEFECT = (r"]\+[^", r"]\+refs/[^")

# ANCHORED TO COMMAND POSITION 2026-08-28, after check:ci-guard-mention-anchoring found this guard refusing an ordinary sentence. Matching the phrase ANYWHERE means a doc line, a worklist note or an `echo` explaining the rule is refused as if it were the rule being broken. This NARROWS PROSE ONLY: every control below still blocks the real command, at line start and after a
# separator. NOT AN ALLOW-LIST, which this guard's own text forbids: the set of refused FLAGS is untouched. Only the position of `git push` is constrained, so a sentence about force-pushing stops being treated as one.
#
# ROUTED THROUGH lib/command-scan.sh 2026-08-30 (review finding on PR #579). Every sibling guard touched in this same PR (block-cli-bundle.sh, block-protected-files.sh, block-unverified-push.sh, block-untagged-commit.sh) scans hook_scan_target's output specifically because it unwraps eval/sh -c
# payloads; this guard matched $CMD directly, so `eval "git push --force ..."`
# or `sh -c 'git push --force ...'` left the push text preceded by a quote character instead of a line start or accepted separator, and the anchor added above never fired -- the exact bypass class command-scan.sh's own header exists to close, on the one guard this file calls "the whole security story".
FORCE_PUSH = hookio.rx(
    r"(^|[;&|(])[{S}]*git push[^|;&]*(--force-with-lease|--force([{S}]|=|$)|[{S}]-f([{S}]|$)|--mirror([{S}]|=|$)|[{S}]\+[^{S}])"
)

MESSAGE = (
    "BLOCKED: Do not force-push (--force / -f / --force-with-lease / --mirror / +refspec). "
    "Force-push overwrites remote history and erases the trace of individual PR changes, "
    "which is exactly what broke traceability before. Use a plain git push so each CI fix "
    "lands as its own reviewable commit. Rewriting already-pushed history is the user's "
    "decision, not an agent's: the operator runs it directly with the ! prefix.\n"
    "\n"
    "THE ONE SANCTIONED EXCEPTION, named here because this guard is the last thing you read "
    "before changing course and it used to send you away empty-handed. After a REBASE the "
    "branch and its submodules have to be republished together, and there is a mediated "
    "verb for exactly that:\n"
    "\n"
    "    .claude/hooks/stop/worklist.py --git force-push <branch>            # prints the plan\n"
    "    .claude/hooks/stop/worklist.py --git force-push <branch> --execute  # performs it\n"
    "\n"
    "It refuses main, refuses every forcing flag except the leased one, pushes SUBMODULES "
    "BEFORE THE CONSOLE so a console head can never name an unpublished submodule commit, "
    "prints the pre-push remote tips as an UNDO block, and halts on the first failure. Dry "
    "run by default: run it without --execute and read the plan first.\n"
    "\n"
    "This guard staying strict is the whole security story, so do not add an allow-list to "
    "it. Use the verb."
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
]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    if hookio.grep_q(FORCE_PUSH, scan):
        ev.warn(MESSAGE)
        return hookio.DENY
    return hookio.ALLOW

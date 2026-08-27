#!/usr/bin/env bash
# Block force-push (--force / -f / --force-with-lease / --mirror / +refspec).
#
# The first three flags are the obvious spelling. The other two were a HOLE,
# found 2026-08-23 while an agent was carrying out an operator-approved history
# rewrite: this guard refused the rewrite push, and the agent noticed that
# dropping the word --force would have slipped the identical non-fast-forward
# push straight past the regex. A --mirror git push forces every ref and deletes
# remote refs absent locally; a leading + on a refspec forces that ref. Both
# rewrite published history, which is exactly what this guard reserves for the
# operator, and neither was matched.
#
# THE + REFSPEC MATCH IS DELIBERATELY UNQUALIFIED, and the first attempt at this
# fix was not. It matched only `+refs/...`, which is the long form. A refspec does
# NOT need to be refs-qualified to force: `+main:main` and `+HEAD:main` are the
# common shorthand and force the remote ref exactly the same way. Both slipped
# straight past the widened guard that this file's own commit message said had
# closed the hole. Caught in review on PR #571, and reproduced before fixing:
# rc 0 for `+main:main` and `+HEAD:main`, rc 2 for `+refs/heads/main`.
#
# The pattern requires WHITESPACE before the plus, so a plus INSIDE a token is
# untouched: `HEAD:refs/heads/feature+x` is a legal branch name and stays allowed.
# That arm is pinned by a control in test-hooks.sh, because a guard widened
# without one is how the next false positive gets shipped.
#
# Nothing in this repo pushes with --mirror or a + refspec (verified by grep
# over *.sh, *.yml, *.md, *.ts), so widening the pattern costs no legitimate
# caller. The mirror git push for a history rewrite is run by the operator
# directly, with the ! prefix, which is the intended path.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'git push[^|;&]*(--force-with-lease|--force([[:space:]]|=|$)|[[:space:]]-f([[:space:]]|$)|--mirror([[:space:]]|=|$)|[[:space:]]\+[^[:space:]])'; then
    echo "BLOCKED: Do not force-push (--force / -f / --force-with-lease / --mirror / +refspec). Force-push overwrites remote history and erases the trace of individual PR changes, which is exactly what broke traceability before. Use a plain git push so each CI fix lands as its own reviewable commit. Rewriting already-pushed history is the user's decision, not an agent's: the operator runs it directly with the ! prefix.

THE ONE SANCTIONED EXCEPTION, named here because this guard is the last thing you read before changing course and it used to send you away empty-handed. After a REBASE the branch and its submodules have to be republished together, and there is a mediated verb for exactly that:

    .claude/hooks/stop/worklist.py --git force-push <branch>            # prints the plan
    .claude/hooks/stop/worklist.py --git force-push <branch> --execute  # performs it

It refuses main, refuses every forcing flag except the leased one, pushes SUBMODULES BEFORE THE CONSOLE so a console head can never name an unpublished submodule commit, prints the pre-push remote tips as an UNDO block, and halts on the first failure. Dry run by default: run it without --execute and read the plan first.

This guard staying strict is the whole security story, so do not add an allow-list to it. Use the verb." >&2
    exit 2
fi
exit 0

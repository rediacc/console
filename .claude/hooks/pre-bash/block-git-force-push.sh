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
# Nothing in this repo pushes with --mirror or a + refspec (verified by grep
# over *.sh, *.yml, *.md, *.ts), so widening the pattern costs no legitimate
# caller. The mirror git push for a history rewrite is run by the operator
# directly, with the ! prefix, which is the intended path.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
if echo "$CMD" | grep -qE 'git push[^|;&]*(--force-with-lease|--force([[:space:]]|=|$)|[[:space:]]-f([[:space:]]|$)|--mirror([[:space:]]|=|$)|[[:space:]]\+refs/)'; then
    echo "BLOCKED: Do not force-push (--force / -f / --force-with-lease / --mirror / +refspec). Force-push overwrites remote history and erases the trace of individual PR changes, which is exactly what broke traceability before. Use a plain git push so each CI fix lands as its own reviewable commit. Rewriting already-pushed history is the user's decision, not an agent's: the operator runs it directly with the ! prefix." >&2
    exit 2
fi
exit 0

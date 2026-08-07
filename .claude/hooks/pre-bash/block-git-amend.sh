#!/usr/bin/env bash
# Block `git commit --amend` for PR babysitting.
#
# WHY THE HEREDOC STRIPPING. The first version grepped the raw command text, so
# it fired on any command that merely CONTAINED the phrase -- including
# `cat > RULES.md <<'EOF'` writing documentation that explains this very rule.
# A guard that blocks you from documenting it is a false positive, and false
# positives are how guards get disabled.
#
# The strip is deliberately narrow: only heredocs introduced by `cat` or `tee`,
# which write bytes and cannot execute them. A heredoc fed to an INTERPRETER
# (`bash <<EOF ... EOF`) really can run the command, so those bodies are left
# in place and still match. Widening this to all heredocs would open exactly
# that hole.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)

# Drop the bodies of cat/tee heredocs before matching.
SCAN=$(printf '%s' "$CMD" | awk '
    # inside a strippable heredoc: emit nothing until the delimiter line
    inside {
        if ($0 == delim) { inside = 0 }
        next
    }
    {
        line = $0
        # only consider a heredoc whose writer is cat or tee
        if (line ~ /(^|[|;&[:space:]])(cat|tee)([[:space:]]|$)/ &&
            match(line, /<<-?[[:space:]]*['"'"'"]?[A-Za-z_][A-Za-z0-9_]*['"'"'"]?/)) {
            d = substr(line, RSTART, RLENGTH)
            gsub(/^<<-?[[:space:]]*/, "", d)
            gsub(/['"'"'"]/, "", d)
            delim = d
            inside = 1
        }
        print line
    }
')

if echo "$SCAN" | grep -qE 'git commit[^|;&]*--amend|git commit[^|;&]*[[:space:]]-[a-zA-Z]*amend'; then
    echo "❌ BLOCKED: Do not use 'git commit --amend' for PR babysitting. Amending rewrites the existing PR commit in place, which collapses every CI fix into one commit and destroys the per-change history (this PR's single commit was already amended 16 times and the individual changes became impossible to trace). Make EACH fix a NEW commit: git commit -m 'fix(scope): ...' then a plain 'git push'. The reviewer needs a readable per-commit trail. If commits genuinely need squashing, that is the user's call at merge time, not yours." >&2
    exit 2
fi
exit 0

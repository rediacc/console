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
    #
    # `<<-` STRIPS LEADING TABS FROM THE TERMINATOR, and comparing $0 raw missed that:
    # bash closes the heredoc at a tab-indented delimiter, so everything after it is
    # ordinary shell again -- but this scanner stayed `inside` to EOF and swallowed it,
    # taking any amend on those lines with it. Fail-OPEN, and the whole point of the
    # scanner is to see past heredocs, so it undid the guard rather than degrading it.
    inside {
        term = $0
        if (dash) { sub(/^\t+/, "", term) }
        if (term == delim) { inside = 0 }
        next
    }
    {
        line = $0
        # only consider a heredoc whose writer is cat or tee
        if (line ~ /(^|[|;&[:space:]])(cat|tee)([[:space:]]|$)/ &&
            match(line, /<<-?[[:space:]]*['"'"'"]?[A-Za-z_][A-Za-z0-9_]*['"'"'"]?/)) {
            d = substr(line, RSTART, RLENGTH)
            dash = (d ~ /^<<-/)   # remember the tab-stripping form for the terminator match
            gsub(/^<<-?[[:space:]]*/, "", d)
            gsub(/['"'"'"]/, "", d)
            delim = d
            inside = 1
        }
        print line
    }
')

# QUOTED SPANS GO TOO, on top of the heredoc stripping above. The awk pass
# handles a documented heredoc; it does nothing for `echo 'git commit --amend'`
# or a commit message quoting the rule, both of which were refused as if they
# were amends.
#
# BUT STRIPPING QUOTES ALONE OPENS AN EVASION, and the first draft of this
# shipped it: `sh -c "git commit --amend"` has the whole command inside a quoted
# span, so removing quotes removed the amend and the guard returned 0. The
# comment written alongside that draft claimed the dedicated test file pinned
# the `sh -c` case. It does not -- the file has no such case, and the claim was
# never checked. One probe found both the false comment and the hole.
#
# So the wrapper payload is extracted and appended, exactly as
# hook_scan_target does for the guards that use it wholesale. This one cannot
# use it wholesale: hook_scan_target drops heredoc BODIES, and the awk pass
# above exists to keep a `cat <<EOF` body as docs while still reading a body
# that would execute. Two different heredoc rules, so only the wrapper half is
# borrowed.
source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN_WRAPPED=$(printf '%s' "$SCAN" | tr '\n' ' ' | _hook_wrapper_payload | sed -e "s/['\"]/ /g")
SCAN=$(printf '%s' "$SCAN" | tr '\n' '\001' | sed -e "s/'[^']*'//g" -e 's/"[^"]*"//g' | tr '\001' '\n')
SCAN="$SCAN
$SCAN_WRAPPED"

if echo "$SCAN" | grep -qE 'git commit[^|;&]*--amend|git commit[^|;&]*[[:space:]]-[a-zA-Z]*amend'; then
    echo "❌ BLOCKED: Do not use 'git commit --amend' for PR babysitting. Amending rewrites the existing PR commit in place, which collapses every CI fix into one commit and destroys the per-change history (this PR's single commit was already amended 16 times and the individual changes became impossible to trace). Make EACH fix a NEW commit: git commit -m 'fix(scope): ...' then a plain 'git push'. The reviewer needs a readable per-commit trail. If commits genuinely need squashing, that is the user's call at merge time, not yours." >&2
    exit 2
fi
exit 0

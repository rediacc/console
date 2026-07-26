#!/usr/bin/env bash
# Gate `gh pr ready` on green CI: a console PR may leave draft state ONLY when
# the single required check, "CI Complete", is SUCCESS on its current head.
# Flipping ready is what triggers the automated Claude review, and the review
# invariant is "non-draft AND green" -- this hook enforces the green half.
#
# `gh pr ready --undo` (back to draft) is always allowed: it can never expose
# an unreviewed/red PR. Network paths here are NOT covered by test-hooks.sh
# (only the pattern paths are); verification failures fail CLOSED.
INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
# Two-stage false-positive defense, both learned from live firings:
# 1. Strip quoted strings (multi-line aware: newlines are folded so a quoted
#    commit message spanning lines is one strippable blob) -- v2 fired on a
#    `git commit -m` body whose prose said "; gh pr ready is hook-gated".
# 2. Command-position anchor on what remains (line start or after ; & | $( )
#    -- v1 fired on a heredoc mentioning the command in prose.
# Bypass-resistant scanning so `sh -c 'gh pr ready'` cannot skip the green
# gate. SCAN carries both the prose-stripped command and any unwrapped
# wrapper payload, and every field below is parsed from it -- one view, no
# drift between two regexes. See lib/command-scan.sh.
source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")
hook_gh_pr_at_command_pos "$SCAN" ready || exit 0

# Every field below is read from the SEGMENT that carries `gh pr ready`, never
# from the whole bash line. Line-wide parsing let a sibling command donate its
# fields to this one: `gh pr ready --undo 1; gh pr ready 531` looked like an
# always-allowed undo, and `gh pr view 1 --repo rediacc/renet; gh pr ready 531`
# looked like a non-console flip -- both would have skipped the green gate
# entirely. See hook_gh_pr_segment.
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
while IFS= read -r SEG; do
    [[ -z "$SEG" ]] && continue
    # --undo (always safe: it can only push a PR back to draft) must belong to
    # THIS invocation, not to a sibling one earlier on the line.
    printf '%s\n' "$SEG" | grep -qE -- '--undo' && continue

    # Only console has draft PRs (free plan, public repo). A --repo pointing
    # elsewhere is a no-op flip; let gh handle it.
    REPO=$(hook_target_repo "$SEG" "$SCAN" "$CWD")
    [[ "$REPO" != "rediacc/console" ]] && continue

    # PR selector: first bare number/URL/branch token after `ready`, else the
    # session cwd's current branch (matching gh's own default resolution).
    SEL=$(hook_pr_selector "$SEG" ready)
    [[ -z "$SEL" ]] && SEL=$(git -C "${CWD:-.}" branch --show-current 2>/dev/null)

    CONCLUSION=$(timeout 20 gh pr view "$SEL" --repo rediacc/console \
        --json statusCheckRollup \
        --jq '[.statusCheckRollup[] | select(.name == "CI Complete")] | first | .conclusion // "ABSENT"' 2>/dev/null)
    if [[ "$CONCLUSION" != "SUCCESS" ]]; then
        echo "❌ BLOCKED: 'gh pr ready' requires CI Complete = SUCCESS on the PR's current head (got: ${CONCLUSION:-verification failed}). A draft flips to ready only when CI is green -- that flip triggers the automated Claude review, whose invariant is non-draft AND green. Wait out the running CI (armed terminal-state watch), fix the red, or if this was a gh/network hiccup, re-run the exact same command." >&2
        exit 2
    fi
done <<<"$(hook_gh_pr_segment "$SCAN" ready)"
exit 0

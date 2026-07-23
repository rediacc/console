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
STRIPPED=$(printf '%s' "$CMD" | tr '\n' '\001' | sed -e "s/'[^']*'//g" -e 's/"[^"]*"//g' | tr '\001' '\n')
echo "$STRIPPED" | grep -qE '(^|[;&|]|\$\()[[:space:]]*gh pr ready' || exit 0
echo "$STRIPPED" | grep -qE -- '--undo' && exit 0

# Only console has draft PRs (free plan, public repo). A --repo pointing
# elsewhere is a no-op flip; let gh handle it.
REPO=$(printf '%s\n' "$STRIPPED" | grep -oE -- '(--repo[= ]|-R )[A-Za-z0-9_./-]+' | head -1 | sed -E 's/^(--repo[= ]|-R )//')
[[ -n "$REPO" && "$REPO" != "rediacc/console" ]] && exit 0

# PR selector: first bare number/URL/branch token after `ready`, else the
# session cwd's current branch (matching gh's own default resolution).
SEL=$(printf '%s\n' "$STRIPPED" | sed -n 's/.*gh pr ready[[:space:]]*//p' | awk '{for (i=1; i<=NF; i++) if ($i !~ /^-/) { print $i; exit }}')
if [[ -z "$SEL" ]]; then
    CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
    SEL=$(git -C "${CWD:-.}" branch --show-current 2>/dev/null)
fi

CONCLUSION=$(timeout 20 gh pr view "$SEL" --repo rediacc/console \
    --json statusCheckRollup \
    --jq '[.statusCheckRollup[] | select(.name == "CI Complete")] | first | .conclusion // "ABSENT"' 2>/dev/null)
if [[ "$CONCLUSION" != "SUCCESS" ]]; then
    echo "❌ BLOCKED: 'gh pr ready' requires CI Complete = SUCCESS on the PR's current head (got: ${CONCLUSION:-verification failed}). A draft flips to ready only when CI is green -- that flip triggers the automated Claude review, whose invariant is non-draft AND green. Wait out the running CI (armed terminal-state watch), fix the red, or if this was a gh/network hiccup, re-run the exact same command." >&2
    exit 2
fi
exit 0

#!/usr/bin/env bash
# WARNING ONLY. Always exits 0. Never blocks.
#
# The hooks are the enforcement layer, and until 2026-08-25 nothing at all
# guarded changing them: block-protected-files.sh covers only settings.json and
# pre-commit-check.sh, and only against restore/checkout/rm. One session changed
# 5 hook files across 6 commits with no friction. A session that finds a guard
# inconvenient can weaken it AND delete its controls in the same commit.
#
# The operator chose WARN over BLOCK here (2026-08-25): a hard block would have
# fired six times that day on legitimate hook work. The teeth are in CI instead
# -- check:ci-hook-integrity holds a shrink-only inventory and requires every
# guard to keep controls in BOTH directions. This is the reminder at the moment
# of the act; the gate is what actually refuses.
INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command' 2>/dev/null) || exit 0
case "$CMD" in
    *"git commit"*) ;;
    *) exit 0 ;;
esac

STAGED=$(git diff --cached --name-only 2>/dev/null | grep '^\.claude/hooks/' || true)
[ -n "$STAGED" ] || exit 0

{
    echo "NOTE: this commit changes the enforcement layer itself:"
    printf '%s\n' "$STAGED" | while IFS= read -r f; do printf '  %s\n' "$f"; done
    echo "  A guard weakened is a rule deleted. If any of these relaxes a check,"
    echo "  say so in the commit message and keep its controls in BOTH directions"
    echo "  (one case asserting it blocks, one asserting it allows) -- a guard with"
    echo "  only block-cases cannot detect over-blocking, which is how a guard ends"
    echo "  up removed. check:ci-hook-integrity enforces this in CI."
} >&2
exit 0

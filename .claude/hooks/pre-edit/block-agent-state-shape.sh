#!/usr/bin/env bash
# Shape-guard for .agent/<branch>/STATE.md on the Edit/Write tool path.
#
# WHY THIS EXISTS. The old compact-recovery handover lived at a TMPDIR path
# nobody would ever open with Write, so a CLI-side refusal was a complete gate.
# STATE.md lives at a normal repo path, and any agent reaches for Write first:
# a CLI-only refusal is bypassed by the most natural tool in the box, and the
# session bypassing it would not know it had. This guard is the half that
# actually closes the hole (operator decision 2026-07-30: it ships WITH the
# migration, not after).
#
# Two rules, and the second is one the CLI could never enforce:
#   1. Edit/MultiEdit/NotebookEdit on STATE.md -> DENY outright. STATE.md is
#      REWRITTEN, never appended to or patched (.agent/README.md); partial
#      edits are how a narrative document accretes stale layers.
#   2. Write on STATE.md -> the same shape rule the Stop check reads with:
#      250-4000 chars and a '## Next action' section. Kept in lockstep with
#      wl_store.agent_state_shape; if the constants move there, move them here.
#
# RULES.md and TRAPS.md are deliberately untouched: RULES.md is sharpened by
# normal edits, TRAPS.md is appended by hand, and neither has a shape gate.
IN=$(cat)
TOOL=$(jq -r '.tool_name // empty' <<<"$IN" 2>/dev/null)
FILE=$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' <<<"$IN" 2>/dev/null)

case "$FILE" in
    */.agent/*/STATE.md) ;;
    *) exit 0 ;;
esac

if [[ "$TOOL" != "Write" ]]; then
    echo "❌ BLOCKED: STATE.md is REWRITTEN, never appended to or patched (see .agent/README.md). Use Write with the full document, or worklist.py --state <me> with the body on stdin, which also records the freshness signature." >&2
    exit 2
fi

CONTENT=$(jq -r '.tool_input.content // empty' <<<"$IN" 2>/dev/null)
LEN=$(printf '%s' "$CONTENT" | awk '{gsub(/^[ \t]+|[ \t]+$/,"")} {n+=length($0)+1} END {print n+0}')
if ((LEN < 250)); then
    echo "❌ BLOCKED: this STATE.md is thin (${LEN} chars, minimum 250). A stub is not a recovery document; the next session inherits ONLY what is written here." >&2
    exit 2
fi
# The cap SCALES with the number of `## SESSION` blocks, matching
# wl_store.agent_state_max_chars. The document is per BRANCH but the budget is
# per SESSION, and a flat cap left the second session ~1850 usable chars --
# whose cheapest remedy is deleting the other session's block, the exact loss
# this document warns about. Kept in lockstep with wl_store deliberately: this
# guard fires on a direct Write, that one on `--state`, and a guard stricter
# than the tool would block a body the tool accepts.
BLOCKS=$(grep -ciE '^[ \t]*##[ \t]+SESSION\b' <<<"$CONTENT" || true)
((BLOCKS < 1)) && BLOCKS=1
MAXLEN=$((4000 * BLOCKS))
if ((LEN > MAXLEN)); then
    echo "❌ BLOCKED: this STATE.md is bloated (${LEN} chars, maximum ${MAXLEN} = ${BLOCKS} session block(s) x 4000). Standing rules belong in RULES.md and hard-won lessons in ../TRAPS.md; STATE.md carries only what is volatile." >&2
    exit 2
fi
if ! grep -qiE '^[ \t]*#{1,6}[ \t]*next action\b' <<<"$CONTENT"; then
    echo "❌ BLOCKED: this STATE.md has no '## Next action' section, which is the one thing it exists to answer. Length is a proxy for value; the next action IS the value." >&2
    exit 2
fi
exit 0

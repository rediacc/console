#!/usr/bin/env bash
# Deny EVERY direct tool write to .agent/<branch>/STATE.md.
#
# WHY THIS EXISTS. The old compact-recovery handover lived at a TMPDIR path
# nobody would ever open with Write, so a CLI-side refusal was a complete gate.
# STATE.md lives at a normal repo path, and any agent reaches for Write first:
# a CLI-only refusal is bypassed by the most natural tool in the box, and the
# session bypassing it would not know it had.
#
# WHY THE SHAPE CHECK LEFT THIS FILE (2026-08-09). This guard used to DENY Edit
# and merely shape-check Write: 250-4000 chars and a '## Next action' section,
# the same rule the Stop check reads with. That was the right gate for a
# document whose contract was "rewrite the whole thing every time". The
# contract is now one OWNED SECTION PER SESSION, merged in place, because
# rewrite-every-time met three live sessions in one checkout and a session
# obeying a staleness nag destroyed a peer's entire state document.
#
# A shape-only shell guard cannot enforce merge semantics. A whole-file Write
# can be perfectly shaped and still delete every peer's section -- exactly as
# thoroughly as the old CLI did -- so a guard that measured its LENGTH was
# waving through the only defect that matters. Only the CLI can merge, so the
# CLI is the only writer.
#
# The escape hatches that matter survive: restoring a backup is `cp` in Bash,
# and worklist.py is a script anyone can run. The residual is a Bash heredoc
# straight onto the path, which no PreToolUse hook can see; that is handled by
# the unowned-section rule in wl_store.agent_state_parse and the timestamp
# fallback in agent_state_state, rather than pretended away.
#
# RULES.md and TRAPS.md are deliberately untouched: RULES.md is sharpened by
# normal edits, TRAPS.md is appended by hand, and neither has a shape gate.
IN=$(cat)
FILE=$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' <<<"$IN" 2>/dev/null)

case "$FILE" in
    */.agent/*/STATE.md) ;;
    *) exit 0 ;;
esac

echo "❌ BLOCKED: STATE.md is not written by tools. It holds ONE OWNED SECTION PER SESSION, and only worklist.py can merge yours in without destroying a peer's. A whole-file Write deletes every other session's section, which is how a live campaign's state document was lost on 2026-08-09. Send YOUR SECTION'S BODY ALONE (250-4000 chars, with a '## Next action' section, no '## SESSION' heading -- the tool writes that) on stdin:  .claude/hooks/stop/worklist.py --state <your-prefix> <<'EOF' ... EOF   See .agent/README.md if present (that tree is gitignored, so a fresh clone will not have it; this message is the contract)." >&2
exit 2

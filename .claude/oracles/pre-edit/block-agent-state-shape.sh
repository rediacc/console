#!/usr/bin/env bash
# Deny EVERY direct tool write to agent/<session>/STATE.md.
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
#
# WHY A REGEX AND NOT A `case` GLOB (2026-08-14, when the tree moved from
# .agent/<branch>/ to a per-session directory). `case` globs are not
# path-segment aware -- `*` happily eats `/` -- so `*/agent/*/STATE.md` does
# match the deeper path, and would ALSO match anything anywhere whose path
# merely contains a directory called `agent`. That breadth mattered little
# while the leading dot made `.agent/` unmistakable; without it, `agent` is an
# ordinary word this repo uses in `docs/agent/`, `.claude/agents/` and agent
# source trees. This hook FAILS OPEN by design (the `exit 0` below), so an
# over-broad pattern is not a loud mistake, it is a guard that blocks writes
# nobody was making while looking exactly as green as a correct one.
#
# The regex is segment-aware: `agent` (or the legacy `.agent`) must start a
# path component, and STATE.md must sit exactly one or two components below it.
# ONE component is the live shape as of 2026-08-18: agent/<session>/STATE.md,
# with no branch in the path. TWO is kept deliberately, because both retired
# shapes had one -- agent/<branch>/<session>/STATE.md before the branch left,
# and .agent/<branch>/STATE.md before the split -- and a session running stale
# instructions writes the old path, not a nonexistent one. Blocking a dead
# shape costs one message; waving it through writes a document nothing reads.
# The docs trees are excluded outright:
# standing prose lives in docs/agent-reference/ and docs/agent/ is what it was
# called before, and neither is this hook's business.
#
# NAMED RESIDUAL: an unrelated `<something>/agent/<x>/<y>/STATE.md` in some
# other tree is denied too, because the payload carries a path and no repo
# root, and anchoring on CLAUDE_PROJECT_DIR would silently stop guarding every
# SUBMODULE's own agent/ tree. Denying a write nobody makes costs one message;
# missing one costs a document.
IN=$(cat)
FILE=$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' <<<"$IN" 2>/dev/null)

case "$FILE" in
    docs/agent/* | */docs/agent/* | docs/agent-reference/* | */docs/agent-reference/*) exit 0 ;;
esac
[[ "$FILE" =~ (^|/)\.?agent/[^/]+/([^/]+/)?STATE\.md$ ]] || exit 0

echo "❌ BLOCKED: STATE.md is not written by tools. It lives at agent/<your-prefix>/STATE.md (no branch in the path) and only worklist.py writes it -- with the heading, the stamp and the lock that make it recoverable. A tool write puts an unstamped document at a path a peer may not even be the owner of, which is how a live campaign's state document was lost on 2026-08-09. Send YOUR BODY ALONE (250-4000 chars, with a '## Next action' section, no '## SESSION' heading -- the tool writes that) on stdin:  .claude/hooks/stop/worklist.py --state <your-prefix> <<'EOF' ... EOF   See agent/README.md (that tree is tracked, so it is in every clone; this message is the contract)." >&2
exit 2

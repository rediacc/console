#!/usr/bin/env bash
# Deny a tool edit that would rewrite the SPINE of a compacted plan record.
#
# WHY THIS EXISTS. `agent/PLAN-*.md` files can be COMPACTED (W12,
# .claude/hooks/stop/wl_planrec.py): the file keeps its path, so the 2,539
# citations of those paths still resolve, and its full text moves into a git
# BLOB. The header then carries the only pointer back to that text:
#
#     Status: compacted
#     Full-Text: <sha9> <path>
#     Full-Text-Blob: <40 hex>
#     Record-Sig: <8 hex>
#
# Rewrite that header by hand and the pointer is gone. Nothing errors. The file
# still looks like a document, `git show` on the old blob still works for
# whoever remembers the id, and nobody does -- so the plan's full text becomes
# unreachable in practice while the record goes on advertising a recovery
# command that returns nothing. That is strictly worse than the deletion this
# whole mechanism exists to avoid: a deleted plan announces its own absence.
#
# WHY A GUARD AND NOT A GATE ALONE. check:ci-plan-record already catches a
# broken pointer, and catching it in CI is a round trip AFTER the plan text is
# only in an object nobody can name any more. The blob is still reachable at
# that point -- `git log --find-object` will find it if you know to look -- but
# the session that made the edit has moved on, and the next reader inherits a
# file whose header is self-consistent and wrong. The cheap moment to refuse is
# the edit.
#
# WHY IT DENIES THE SPINE AND NOT THE WHOLE FILE, which was the first design and
# was wrong. A record is meant to be SHARPENED: `Record-Sig` deliberately
# canonicalises status, pointer and the box table and NOT the prose, exactly so
# `## Why`, `## Outcome` and `## Lessons` stay editable in place -- that is the
# "sharpen; edit in place when wrong" lifetime agent/README.md:57 assigns to a
# durable design. A guard that refused every edit would make the record the one
# document in this tree nobody may correct, and an uncorrectable document is one
# people route around. So:
#
#   DENIED   a Write (whole-file replacement always carries the spine), and any
#            Edit/MultiEdit/NotebookEdit whose old or new text contains a header
#            field, a checkbox line, or a `(record)` annotation line.
#   ALLOWED  a prose edit, silently. That is the common case and it must stay
#            frictionless.
#
# THE TWO LEGITIMATE WAYS TO CHANGE A SPINE both go through Python and neither
# touches the Edit tool, so neither is affected by this guard:
#
#     worklist.py --plan-revive  <me> <path> --write   full text back from the blob
#     worklist.py --plan-compact <me> <path> --write   re-derive the record
#
# FAILS OPEN, on purpose and in every direction: no jq, no file, an unreadable
# payload, a path that is not a plan, a plan that is not a record. This guard
# can only ever turn an allowed edit into a refused one, so every uncertainty
# resolves to `exit 0`. The gate is the backstop.
#
# RESIDUAL, named rather than implied: a session can still `cat > file` from
# Bash, which this chain never sees. That is not a hole worth a second guard --
# check:ci-plan-record fails on the result, and the pre-bash chain already
# refuses the shapes worth refusing. What this closes is the ACCIDENT, which is
# the one that actually happens: an Edit aimed at prose that swallows the header
# because the old_string was anchored one line too high.

set -uo pipefail

command -v jq >/dev/null 2>&1 || exit 0

INPUT=$(cat)

FILE=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null)
[ -n "$FILE" ] || exit 0

case "$FILE" in
    */agent/PLAN-*.md | agent/PLAN-*.md) ;;
    */agent/plans/PLAN-*.md | agent/plans/PLAN-*.md) ;;
    */agent/plans/_done/PLAN-*.md | agent/plans/_done/PLAN-*.md) ;;
    */agent/plans/_removed/PLAN-*.md | agent/plans/_removed/PLAN-*.md) ;;
    *) exit 0 ;;
esac

[ -f "$FILE" ] || exit 0

# IS IT A RECORD? Read the same 10-line header window every status regex in this
# repo reads (wl_checks.PLAN_HEADER_LINES). Both halves are required: a plan may
# legitimately say `parked` in prose, and a `Full-Text-Blob:` with no record
# status is not a record either.
HEAD10=$(head -10 "$FILE" 2>/dev/null) || exit 0
printf '%s' "$HEAD10" | grep -qE '^Status:[[:space:]]*(compacted|parked)[[:space:]]*$' || exit 0
BLOB=$(printf '%s' "$HEAD10" | sed -n 's/^Full-Text-Blob:[[:space:]]*\([0-9a-f]\{40\}\).*/\1/p' | head -1)
[ -n "$BLOB" ] || exit 0
SIG=$(printf '%s' "$HEAD10" | sed -n 's/^Record-Sig:[[:space:]]*\([0-9a-f]\{8\}\).*/\1/p' | head -1)

TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)

# The four-tool payload union: `content` is Write, `new_string`/`old_string` are
# Edit, `new_source` is NotebookEdit, `edits[]` is MultiEdit. old_string is in
# here deliberately -- an Edit that DELETES the header names it only there.
FRAGMENTS=$(printf '%s' "$INPUT" | jq -r '
    [ .tool_input.content,
      .tool_input.new_string,
      .tool_input.old_string,
      .tool_input.new_source,
      (.tool_input.edits[]?.new_string),
      (.tool_input.edits[]?.old_string) ]
    | map(select(. != null)) | join("\n")' 2>/dev/null)
[ -n "$FRAGMENTS" ] || exit 0

# TWO KINDS OF TEST, and the first version had only the first kind, which missed
# the exact accident this guard is named for. Line-anchored patterns catch an
# edit that quotes a WHOLE line. But the Edit tool asks for a MINIMAL UNIQUE
# old_string, and the most unique string in a record is the 40-hex blob -- so
# the natural way to break the pointer is `old_string: "c129f44d...0168"`, with
# no line prefix at all. Reproduced 2026-09-06 against this hook with real
# payloads: four of five spine-destroying edits passed, including that one.
#
# So the VALUES are tested too, by substring: the blob, the signature, any
# `done=` attestation, and the text of any box line already in the file. Those
# are read out of the FILE rather than pattern-matched out of the payload, which
# is what makes them exact.
SPINE=""
if [ "$TOOL" = "Write" ]; then
    SPINE="the whole file -- a Write replaces the header, the boxes and the signature at once"
elif printf '%s' "$FRAGMENTS" | grep -qE '^(Status|Owner|Full-Text|Full-Text-Blob|Record-Sig):'; then
    SPINE="the header block (Status / Full-Text / Full-Text-Blob / Record-Sig)"
elif printf '%s' "$FRAGMENTS" | grep -qF "$BLOB"; then
    SPINE="the Full-Text-Blob VALUE, which is the only pointer to the plan's text"
elif [ -n "$SIG" ] && printf '%s' "$FRAGMENTS" | grep -qF "$SIG"; then
    SPINE="the Record-Sig VALUE, which check:ci-plan-record recomputes and compares"
elif printf '%s' "$FRAGMENTS" | grep -qE 'done=([0-9a-f]{9}|open|abandoned)'; then
    SPINE="a done= attestation, which is proved against the committed box ledger"
elif printf '%s' "$FRAGMENTS" | grep -qE '^[[:space:]]*[-*+][[:space:]]+\[[ xX]\][[:space:]]'; then
    SPINE="a checkbox line under ## Boxes"
elif printf '%s' "$FRAGMENTS" | grep -qE '^[[:space:]]{4}\(record\)[[:space:]]'; then
    SPINE="a (record) attestation line"
fi

# THE BOX BODIES, by substring, for the same reason as the blob above: rewriting
# a box's TEXT moves its ledger signature, and check_plan_boxes.py's A1 reports a
# moved signature as a box that VANISHED. The 12-character floor keeps a short
# body from matching ordinary prose.
if [ -z "$SPINE" ]; then
    # BOTH DIRECTIONS, because an Edit quotes a MINIMAL unique substring and a
    # one-direction test misses half the cases. `old_string` may be the whole box
    # body (body inside the fragment) or the shortest distinguishing part of it
    # (fragment inside the body). Bash pattern containment rather than grep: the
    # needle is quoted inside the pattern so it stays literal, and this runs with
    # no subprocess at all on a path every Edit in the repo pays for.
    while IFS= read -r _bl; do
        _body="${_bl#*] }"
        [ "${#_body}" -ge 12 ] || continue
        while IFS= read -r _fr; do
            [ "${#_fr}" -ge 12 ] || continue
            if [[ $_fr == *"$_body"* || $_body == *"$_fr"* ]]; then
                SPINE="the TEXT of a box line, which moves its ledger signature"
                break 2
            fi
        done <<<"$FRAGMENTS"
    done < <(grep -E '^[[:space:]]*[-*+][[:space:]]+\[[ xX]\][[:space:]]' "$FILE" 2>/dev/null)
fi

[ -n "$SPINE" ] || exit 0

cat >&2 <<MSG
❌ BLOCKED: $FILE is a COMPACTED PLAN RECORD, and this edit rewrites $SPINE.

The plan's full text is not in this file any more. It is in a git blob, and the
header you are editing is the only pointer to it:

    git show $BLOB
    git log --find-object=$BLOB --all

Rewrite that header by hand and nothing errors -- the file still reads as a
document, and the text simply becomes unreachable to everyone who does not
already know the blob id. A record that advertises a recovery command returning
nothing is worse than the deleted plan it replaced.

WHAT TO DO INSTEAD.

  Working on the plan again? Restore the full text first, then edit it as an
  ordinary plan. This puts it back on the housekeeping clock, which is correct:

      .claude/hooks/stop/worklist.py --plan-revive <you> $FILE --write

  Re-deriving the record (the boxes moved, the ledger caught up)? Revive it,
  make the change in the real plan, COMMIT, then compact again. The commit is
  not optional -- --plan-compact refuses a dirty path, because the record's
  pointer is the hash of the bytes on disk and the record then overwrites them.
  The compact verb recomputes the blob, the box attestations and the signature
  together, which is the only way they stay consistent:

      .claude/hooks/stop/worklist.py --plan-revive  <you> $FILE --write
      # ... edit the plan, then commit it ...
      .claude/hooks/stop/worklist.py --plan-compact <you> $FILE --why auto
      .claude/hooks/stop/worklist.py --plan-compact <you> $FILE --write

  Only sharpening the prose? That is ALLOWED and this guard does not fire on it.
  Edit ## Why, ## Outcome or ## Lessons and leave the header, the boxes and the
  (record) lines alone -- Record-Sig deliberately does not cover the prose, so
  correcting it costs nothing and needs no re-derivation.
MSG
exit 2

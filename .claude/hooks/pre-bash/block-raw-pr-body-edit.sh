#!/usr/bin/env bash
# Refuse a hand-written PR body edit; route it through the tool that rebuilds it.
#
# WHY. The console PR description is not free text any more: it carries a
# delimited worklist-epics block generated from agent/pr/<branch>.md, and CI
# gates on that block matching the published snapshot. A raw
# `gh pr edit --body`/`--body-file` writes the WHOLE body, so it silently drops
# the block, and the next thing anyone learns is a red gate several minutes
# later with no hint of what removed it.
#
# THE SAME CLASS ALREADY BIT THIS REPO ONCE, one level down:
# .ci/scripts/autopilot/submodule-prs.sh's header warns that its block must not
# share markers with refresh-pr-body.sh, "because that hook rewrites the WHOLE
# body on every push and anything inside its markers is destroyed on the next
# one." A whole-body writer is the hazard; this guard is that lesson applied to
# the model's own hands.
#
# NOT BLOCKED, deliberately:
#   - the sanctioned tool itself, .ci/scripts/pr/sync-epic-block.sh, which
#     strips and rebuilds only its own markers;
#   - `gh pr create` whose body ALREADY carries the block, and `gh pr create`
#     with no body flag at all -- create is the one call with no block to
#     destroy, so it is judged on what it produces, not on being a whole-body
#     write;
#   - `gh api .../pulls/<n> -X PATCH` that carries no body field (a title or
#     state change), for the same reason;
#   - `gh pr edit` for anything that is not the body: --title, --add-label,
#     --add-reviewer, --milestone. The guard keys on the body flags alone,
#     because a guard whose usual outcome is a false positive teaches people to
#     route around it;
#   - the PostToolUse hook refresh-pr-body.sh and the autopilot scripts, which
#     are not model Bash calls and never reach this chain.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)

# ANCHORED AT COMMAND POSITION, not matched anywhere on the line.
#
# The first version grepped the raw string and blocked `echo "never use gh pr
# edit --body by hand"`, which is prose ABOUT the rule, not a violation of it.
# block-commit-meta.sh's header names that failure exactly: "a guard whose only
# failure mode is refusing CORRECT input teaches people to reword honest
# messages until it stops complaining." lib/command-scan.sh already solves this,
# and block-second-open-pr.sh uses the same two calls for `gh pr create`.
source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")

# The sanctioned tool is allowed to do exactly what it exists to do.
if printf '%s' "$CMD" | grep -qF 'sync-epic-block.sh'; then
    exit 0
fi

# ORDER MATTERS: the edit arm runs FIRST. One command can do both, and the
# create arm below exits 0 on a body that already carries the block -- so with
# create checked first, `gh pr create --fill && gh pr edit N --body-file b.md`
# would take that exit and never reach the edit refusal, which applies whether
# or not the block is there.
# THE FLAG BELONGS TO ITS OWN INVOCATION, and reading it line-wide is the same
# scope bug hook_gh_pr_segment was written for. `gh pr create --body "<a body
# that carries the block>" && gh pr edit N --add-label x` is entirely legal, and
# a line-wide `--body` test refuses it -- the edit verb is present, the flag is
# present, and they belong to different commands. Scope both arms to segments.
EDIT_SEG=$(hook_gh_pr_at_command_pos "$SCAN" edit && hook_gh_pr_segment "$SCAN" edit)
CREATE_SEG=$(hook_gh_pr_at_command_pos "$SCAN" create && hook_gh_pr_segment "$SCAN" create)

BEGIN_MARKER='<!-- worklist-epics:begin -->'
# Every machine-written section of a PR body in this repo. An edit must carry them
# ALL, because `gh pr edit --body` writes the whole body and anything absent is gone.
# Measured on PR #585, 2026-09-03: the body carries worklist-epics AND pushed-head.
GENERATED_MARKERS='worklist-epics pushed-head'

refuse_whole_body_edit() {
    cat >&2 <<'MSG'
BLOCKED: do not write a PR body by hand.

The description carries generated `<!-- worklist-epics:begin -->` and
`<!-- pushed-head:begin -->` blocks, and a whole-body write (`gh pr edit --body`,
or `gh api .../pulls/<n> -X PATCH -F body=...`) replaces the WHOLE body, so any
block absent from what you send is gone. CI then fails on a missing block,
minutes later, naming nothing that would point back here.

Use the tool, which strips and rebuilds only its own markers and leaves your
prose alone:

  worklist.py --publish <me> <branch>          # refresh the snapshot
  .ci/scripts/pr/sync-epic-block.sh <pr> <branch>   # sync it into the PR

To change the narrative part of the description, keep EVERY marker in the body
you write -- a body that already carries them all is not refused, because it
cannot be the thing that drops them. Read the current body, change your prose,
leave the marker sections alone, and send it with the PATCH form (`gh pr edit
--body` is refused by block-adhoc-sanctioned.sh: it exits 1 on a deprecated
GraphQL field and leaves the body unchanged). Give the file by its LITERAL path;
a path behind a shell variable is unreadable here and is refused, not trusted:

  gh pr view <pr> --json body -q .body > /abs/path/body.md   # keeps the blocks
  # edit the prose in body.md, leave the worklist-epics and pushed-head sections untouched
  gh api repos/<owner>/<repo>/pulls/<pr> -X PATCH -F body=@/abs/path/body.md

`gh pr edit --title`, `--add-label` and friends are not affected by this guard.
MSG
    exit 2
}

# Read whatever body text this command makes visible: --body is in the command,
# --body-file is on disk. Shared by both arms, because both ask the same
# question -- does the body this call writes carry the block?
hook_visible_body() {
    local seg="$1" body="" f cand
    hook_flag_present "$seg" body && body="$CMD"
    local root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        [ "$f" = "-" ] && continue
        for cand in "$f" "$root/$f"; do
            if [ -f "$cand" ]; then
                body="$body
$(cat "$cand" 2>/dev/null)"
                HOOK_SAW_BODY_FILE=1
                break
            fi
        done
    done < <(printf '%s' "$CMD" | grep -oE -- '--body-file([[:space:]]+|=)[^[:space:];|&]+' |
        sed -E 's/^--body-file([[:space:]]+|=)//')
    printf '%s' "$body"
}

# THE EDIT ARM CHECKS EVERY GENERATED MARKER, NOT JUST THE EPIC ONE. Corrected
# 2026-09-03, same day, after the narrowing below was written and its own test
# refused it. The narrowing said an edit carrying `worklist-epics` "cannot drop the
# block" and is therefore as safe as a create. That was half the picture: `gh pr edit
# --body` replaces the WHOLE body, and this repo's PR bodies carry a SECOND generated
# section, `<!-- pushed-head:begin -->`. A body carrying only the epic block passes
# the narrowed check and silently destroys the pushed-head section -- which is exactly
# the class of loss this guard exists to prevent, arriving through the door the
# narrowing opened.
#
# So the test that failed was right and the narrowing was wrong. The rule is now: an
# edit is permitted only when its body carries EVERY marker this repo generates. That
# keeps the real case the narrowing was written for (fix the prose, leave the machine
# sections alone) and refuses the case it accidentally allowed. That refusal is the failure
# mode this file's own header names, quoting block-commit-meta.sh: "a guard whose
# only failure mode is refusing CORRECT input teaches people to route around it."
# It bit for real: a PR body had to lose a footer that check-claude-attribution.sh
# refuses, the corrected body kept the block, and the only routes left were the
# GitHub UI (unavailable to an agent) or closing and reopening the PR.
#
# The asymmetry with create that REMAINS is deliberate and is the whole safety
# argument: create may write an UNREADABLE body (a heredoc, a file a later step
# writes) because there is no block yet to destroy. Edit may not -- an unreadable
# edit body is refused, because it can silently replace one that exists.
HOOK_SAW_BODY_FILE=0
if [ -n "$EDIT_SEG" ] &&
    { hook_flag_present "$EDIT_SEG" body || hook_flag_present "$EDIT_SEG" body-file; }; then
    EDIT_BODY=$(hook_visible_body "$EDIT_SEG")
    EDIT_OK=1
    for _m in $GENERATED_MARKERS; do
        printf '%s' "$EDIT_BODY" | grep -qF -- "<!-- ${_m}:begin -->" || EDIT_OK=0
    done
    if [ "$EDIT_OK" = 1 ]; then
        exit 0
    fi
    refuse_whole_body_edit
fi

# ---- the SANCTIONED body write is a whole-body write too -------------------
# block-adhoc-sanctioned.sh refuses `gh pr edit --body` (it exits 1 on the
# deprecated projectCards GraphQL field with the body UNCHANGED) and prescribes
# `gh api repos/<o>/<r>/pulls/<n> -X PATCH -F body=@<file>` instead. That form
# replaces the whole body exactly as `gh pr edit --body` does, and until
# 2026-09-04 it walked past this guard unread: this file's own message pointed
# at `gh pr edit --body-file`, the sanctioned guard refused that, and the door
# it pointed to instead had no marker check at all. Same rule as the edit arm:
# every generated marker must be visible in the body this call writes, and an
# unreadable body is refused, because it can silently replace one that exists.
API_SEGS=$(printf '%s' "$SCAN" | sed -e 's/[;&|()`]/\n/g' |
    grep -E '^[[:space:]]*gh[[:space:]]+api([[:space:]]|$)' |
    grep -E 'pulls/[0-9]+' | grep -E '(^|[[:space:]])(-X|--method)[[:space:]]+PATCH([[:space:]]|$)')
if [ -n "$API_SEGS" ] && printf '%s' "$API_SEGS" |
    grep -qE -- '(^|[[:space:]])(-F|-f|--field|--raw-field)[[:space:]]+body=|(^|[[:space:]])--input([[:space:]]|=)'; then
    PATCH_BODY="$CMD"
    ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
    SAW=0
    NEED=0
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        NEED=1
        for cand in "$f" "$ROOT/$f"; do
            if [ -f "$cand" ]; then
                SAW=1
                PATCH_BODY="$PATCH_BODY
$(cat "$cand" 2>/dev/null)"
                break
            fi
        done
    done < <(printf '%s' "$API_SEGS" |
        grep -oE -- '((-F|--field)[[:space:]]+body=@|--input([[:space:]]+|=))[^[:space:];|&]+' |
        sed -E 's/^((-F|--field)[[:space:]]+body=@|--input([[:space:]]+|=))//')
    PATCH_OK=1
    if [ "$NEED" = 1 ] && [ "$SAW" = 0 ]; then
        PATCH_OK=0
    else
        for _m in $GENERATED_MARKERS; do
            printf '%s' "$PATCH_BODY" | grep -qF -- "<!-- ${_m}:begin -->" || PATCH_OK=0
        done
    fi
    [ "$PATCH_OK" = 1 ] && exit 0
    refuse_whole_body_edit
fi

# ---- `gh pr create` was the hole, and it is the one that bit -------------
# Measured 2026-08-27: this guard returned rc=0 for every `gh pr create --body`
# shape and rc=2 for the matching `edit` ones. The operator's symptom -- "why
# don't I see the epics in the PR description?" -- came in through create, not
# edit, and the guard was looking only at the door nobody used.
#
# create is NOT refused outright, because it is the one call that legitimately
# writes a whole body: there is no block yet to destroy. It is refused only when
# the body it writes does NOT already carry the block, which is precisely the
# state CI fails on minutes later. A body that carries it passes untouched, so
# the sanctioned flow (build the body from the snapshot, create with it) is not
# in this guard's way at all.
if [ -n "$CREATE_SEG" ]; then
    hook_flag_present "$CREATE_SEG" body || hook_flag_present "$CREATE_SEG" body-file || exit 0

    # What body text can we actually see? --body is in the command; --body-file
    # is on disk. Same readability rule as block-untagged-commit.sh: judge what
    # can be read, ALLOW what cannot, rather than refusing blind.
    # Content, unlike flags, is read from the RAW command: a quoted body may
    # itself contain a separator, and a segment would truncate it.
    BODY=""
    hook_flag_present "$CREATE_SEG" body && BODY="$CMD"
    ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
    SAW_FILE=0
    while IFS= read -r f; do
        [ -n "$f" ] || continue
        [ "$f" = "-" ] && continue
        for cand in "$f" "$ROOT/$f"; do
            if [ -f "$cand" ]; then
                SAW_FILE=1
                BODY="$BODY
$(cat "$cand" 2>/dev/null)"
                break
            fi
        done
    done < <(printf '%s' "$CMD" | grep -oE -- '--body-file([[:space:]]+|=)[^[:space:];|&]+' |
        sed -E 's/^--body-file([[:space:]]+|=)//')

    # A --body-file naming a path that does not exist yet (written by a later
    # step of the same command, or by a heredoc this scan stripped) is genuinely
    # unreadable. Allow it; CI still gates the result.
    if hook_flag_present "$CREATE_SEG" body-file && [ "$SAW_FILE" = 0 ] &&
        ! hook_flag_present "$CREATE_SEG" body; then
        exit 0
    fi

    printf '%s' "$BODY" | grep -qF -- "$BEGIN_MARKER" && exit 0

    cat >&2 <<MSG
BLOCKED: this \`gh pr create\` body carries no worklist-epics block.

The description is generated content: CI's check:ci-pr-epic-block diffs the
\`$BEGIN_MARKER\` block against agent/pr/<branch>.md. Creating the PR with a
hand-written body means the block is absent from the moment the PR exists, and
the first anyone hears of it is a red gate several minutes later.

Create it, then sync the block in the same breath:

  .claude/hooks/stop/worklist.py --publish <me> <branch>   # refresh the snapshot
  gh pr create --draft --title "..." --body "..."          # your prose
  .ci/scripts/pr/sync-epic-block.sh <pr> <branch>          # add the block

A body that already contains the block is NOT refused, so building the body
from the snapshot first works too.
MSG
    exit 2
fi

exit 0

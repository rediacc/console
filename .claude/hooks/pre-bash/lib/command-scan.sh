#!/usr/bin/env bash
# Shared command scanning for the gh-pr guardrail hooks (block-admin-merge,
# block-nondraft-pr-create, block-premature-ready).
#
# The old inline approach — strip every quoted span, then anchor `gh pr <verb>`
# at a command position — had a review-found bypass class: stripping ALL quotes
# also erases a command hidden inside a shell-execution wrapper, so
# `sh -c 'gh pr merge --admin'`, `bash -c "..."`, `eval "..."`, variable
# indirection (`X=--admin; gh pr merge $X`), and `--admin=true` all sailed past
# the bans. The stripping exists to avoid PROSE false positives
# (`git commit -m "...gh pr merge --admin..."`), so it cannot simply be
# removed. This lib keeps the prose defense AND scans wrapper payloads.
#
# hook_scan_target builds the string the anchor runs against, from three parts:
#   1. Heredoc bodies removed. A `<<MARKER ... MARKER` body is DATA, never
#      executed, so dropping it is safe and kills the heredoc false positive
#      (a worklist note mentioning the command used to fire the hook).
#   2. Prose-stripped: quoted spans removed (multi-line aware) so quoted prose
#      cannot trip the anchor.
#   3. Wrapper payloads: the argument of a shell-execution wrapper
#      (sh/bash/dash/zsh/ash/ksh -c, or eval) with its quotes turned to spaces,
#      so the inner command lands at a command position and IS scanned.
#
# hook_flag_present matches a long flag in every form a shell accepts —
# `--flag`, `--flag=value`, `--flag;`, and inside a quoted/assignment token —
# so `--admin=true` and `X="--admin"` are caught. Combined with a
# command-position verb match, over-blocking a command that both names the flag
# and runs the verb is the safe direction.

# Drop heredoc bodies: from a line introducing `<< [-] ['"]?MARKER['"]?` up to
# the line that is exactly MARKER (optionally tab-indented for <<-). Keeps the
# introducing line (which may itself hold the real command) and the rest.
_hook_strip_heredocs() {
    awk '
    {
        if (skip) { if ($0 ~ ("^[ \t]*" marker "[ \t]*$")) { skip=0 }; next }
        line=$0
        if (match(line, /<<-?[ \t]*['"'"'"]?[A-Za-z_][A-Za-z0-9_]*['"'"'"]?/)) {
            m=substr(line, RSTART, RLENGTH)
            gsub(/<<-?[ \t]*['"'"'"]?/, "", m); gsub(/['"'"'"]?$/, "", m)
            marker=m; skip=1
        }
        print line
    }' 2>/dev/null
}

hook_scan_target() {
    local cmd="$1" nohd stripped wrapped
    nohd=$(printf '%s' "$cmd" | _hook_strip_heredocs)
    stripped=$(printf '%s' "$nohd" | tr '\n' '\001' | sed -e "s/'[^']*'//g" -e 's/"[^"]*"//g' | tr '\001' '\n')
    # Extract shell-wrapper payloads and STRIP the wrapper prefix + quotes so
    # the inner command sits at line start (a command position for the anchor):
    # `sh -c 'gh pr merge --admin'` -> `gh pr merge --admin `.
    # WRAPPER_RE tolerates intervening flags before the final `-c`-ending
    # token, bundled (`bash -lc`) or separate (`bash -eux -c`, `sh -eu -c`) --
    # review finding (round 39): the old `[[:space:]]+-c[[:space:]]` required
    # the shell name and -c to be IMMEDIATELY adjacent, so `bash -lc '...'`
    # matched neither this extraction NOR the prose-strip (which erases the
    # quoted payload unconditionally), leaving zero trace of the wrapped
    # command in either half of the scan target -- a total bypass.
    local WRAPPER_RE='(sh|bash|dash|zsh|ash|ksh)([[:space:]]+-[[:alnum:]]+)*[[:space:]]-[[:alnum:]]*c[[:space:]].*|eval[[:space:]].*'
    wrapped=$(printf '%s' "$nohd" | tr '\n' ' ' |
        grep -oE "$WRAPPER_RE" |
        sed -E -e 's/^(sh|bash|dash|zsh|ash|ksh)([[:space:]]+-[[:alnum:]]+)*[[:space:]]-[[:alnum:]]*c[[:space:]]+//; s/^eval[[:space:]]+//' -e "s/['\"]/ /g")
    printf '%s\n%s' "$stripped" "$wrapped"
}

# hook_gh_pr_at_command_pos <scan-target> <verb>
# Command position = line start (covers wrapper-payload lines, now
# prefix-stripped), or after ; & | ( $( or a backtick.
hook_gh_pr_at_command_pos() {
    local scan="$1" verb="$2"
    printf '%s' "$scan" | grep -qE "(^|[;&|(]|\\\$\\(|\`)[[:space:]]*gh[[:space:]]+pr[[:space:]]+${verb}([[:space:]]|\$)"
}

# hook_flag_present <raw-cmd> <flag-without-dashes>
hook_flag_present() {
    local cmd="$1" flag="$2"
    printf '%s' "$cmd" | grep -qE -- "--${flag}([[:space:]=;&|)\"'\`]|\$)"
}

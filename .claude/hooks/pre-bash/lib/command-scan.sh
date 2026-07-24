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

# Extract the payload of a shell-wrapper invocation (`<shell> [...anything...]
# -c <payload>` or `eval <payload>`) by SCANNING TOKENS for the token that
# actually selects -c mode, instead of enumerating flag shapes in a regex.
# Review findings (rounds 39-40) showed that a single regex chasing flag
# shapes is a losing game: bare `-c`, then bundled (`-lc`) and separate
# (`-eux -c`) short flags, then GNU long options (`--posix`, `--norc`) and
# value-taking short options (`-o pipefail`) each broke it in turn, and there
# will always be another shape. Token-scanning treats ANY intervening token as
# skippable and asks only "is THIS token the -c selector" -- a closed,
# enumerable question (`-c` exactly, or a single-dash bundle ending in `c`) --
# so no flag syntax needs to be recognized at all. This also drops the old
# design's second failure mode: the extraction regex and a separate
# prefix-strip regex had to independently agree on the exact same shape, and
# small drift between the two was itself a bug source; this emits the payload
# directly, so there is nothing left to keep in sync.
_hook_wrapper_payload() {
    awk '
    {
        n = split($0, tok, /[ \t]+/)
        for (i = 1; i <= n; i++) {
            if (tok[i] == "eval") {
                out = ""
                for (j = i + 1; j <= n; j++) out = out tok[j] (j < n ? " " : "")
                print out
                exit
            }
            if (tok[i] ~ /^(sh|bash|dash|zsh|ash|ksh)$/) {
                for (j = i + 1; j <= n; j++) {
                    t = tok[j]
                    if (t == "-c" || t ~ /^-[^-].*c$/) {
                        out = ""
                        for (m = j + 1; m <= n; m++) out = out tok[m] (m < n ? " " : "")
                        print out
                        exit
                    }
                }
            }
        }
    }' 2>/dev/null
}

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
    # Extract the wrapper payload (see _hook_wrapper_payload above), then turn
    # its quotes to spaces so the inner command lands at a command position:
    # `sh -c 'gh pr merge --admin'` -> `gh pr merge --admin `.
    wrapped=$(printf '%s' "$nohd" | tr '\n' ' ' | _hook_wrapper_payload | sed -e "s/['\"]/ /g")
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

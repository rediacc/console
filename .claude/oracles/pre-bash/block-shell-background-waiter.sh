#!/usr/bin/env bash
# Block launching a long-lived waiter/watcher with a shell `&` instead of the
# harness's run_in_background.
#
# WHY. On 2026-08-08 a session launched wl_wait.py with a trailing `&`. A
# shell-backgrounded process is untracked: the harness cannot notify on its
# exit, so the waiter fires into the void and the session stops hearing
# cross-session mail without any visible failure. The same session then spent
# three rounds chasing "respawning" waiters that were its own pgrep wrappers
# self-matching. Every instruction file already says run_in_background: true;
# instructions demonstrably did not hold under load, so this hook does.
#
# SCOPE IS DELIBERATELY NARROW: only the known long-lived instruments
# (wl_wait.py today) followed by a backgrounding `&`. A general `&` ban would
# be wrong -- `cmd1 & cmd2 & wait` fan-outs and `disown` teardowns are
# legitimate. `&&` never matches (the regex requires a NON-& character or
# end-of-line after the single `&`).
CMD=$(jq -r '.tool_input.command' 2>/dev/null)

# Strip quoted strings so an `&` inside a commit message or echo cannot
# false-positive, and strip fd-redirect forms (2>&1, >&2, 3>&-) whose `&` is
# not backgrounding -- caught as a live false positive during the hook's own
# proving run; then look for <waiter> ... & at a command boundary.
# ORDER MATTERS, and getting it wrong reopened the very false positive the heredoc
# stripper below was added to close. Quote-stripping runs `s/'[^']*'//g`, which turns a
# QUOTED heredoc delimiter `<<'EOF'` into a bare `<<` -- so the awk stripper then finds no
# delimiter name, never enters the body, and scans the document as command text. It worked
# for `<<EOF` and failed for `<<'EOF'`, which is the form this repo's own guidance uses.
#
# Measured 2026-09-01: a session writing its recovery document with
# `worklist.py --state <<'EOF'` was blocked because the DOCUMENT contained the sentence
# "never with a shell `&`" -- the hook forbidding its own documentation, a second time.
#
# So heredoc bodies come off the RAW command first; quotes and redirects after.
STRIPPED="$CMD"

# Also strip HEREDOC BODIES, which are data rather than commands. Caught as a
# live false positive: a session writing its recovery document with
# `worklist.py --state <<EOF ... EOF` was blocked because the DOCUMENT explained
# this very rule, so the hook forbade documenting itself. Quoted-delimiter
# heredocs are never expanded or executed.
#
# NOT stripped when the heredoc feeds a shell (`| bash`, `| sh`, `bash <<`),
# because there the body IS the command and stripping it would open a bypass.
if ! printf '%s' "$CMD" | grep -qE '\|[[:space:]]*(bash|sh|zsh)\b|\b(bash|sh|zsh)[[:space:]]+<<'; then
    STRIPPED=$(printf '%s' "$STRIPPED" | awk '
        /<<-?'"'"'?[A-Za-z_][A-Za-z0-9_]*'"'"'?/ && !indoc {
            match($0, /<<-?'"'"'?[A-Za-z_][A-Za-z0-9_]*'"'"'?/)
            d = substr($0, RSTART, RLENGTH)
            gsub(/^<<-?'"'"'?|'"'"'$/, "", d)
            delim = d; indoc = 1; print; next
        }
        indoc && $0 == delim { indoc = 0; next }
        indoc { next }
        { print }
    ')
fi

# NOW the quotes and redirects, on whatever survived the heredoc strip.
STRIPPED=$(printf '%s' "$STRIPPED" | sed -e "s/'[^']*'//g" -e 's/"[^"]*"//g' -e 's/[0-9]*>&[0-9-]*//g')

if printf '%s' "$STRIPPED" | grep -qE 'wl_wait\.py[^&|;]*&([^&]|$)'; then
    echo '❌ BLOCKED: wl_wait.py must NOT be launched with a shell `&`. A shell-backgrounded process is untracked -- the harness can never notify you when it fires, so you stop hearing cross-session mail silently. Launch it as a harness background task instead: run the plain command `python3 .claude/hooks/stop/wl_wait.py <session-prefix> --timeout 60` with run_in_background: true on the Bash tool call. (Also: to check whether one is already running, match the PYTHON process, not your own wrapper: ps -eo pid,args | grep "[p]ython3.*wl_wait" -- a bare pgrep -f self-matches the Bash tool wrapper containing your pattern text.)' >&2
    exit 2
fi
exit 0

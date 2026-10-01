#!/usr/bin/env bash
# Runs the pre-placed bitwarden/sm-action binary directly, retrying a transient Bitwarden failure, and classifies a final failure as either an outage or a credential problem.
#
# Usage: fetch.sh <path-to-sm-action-binary>
# Environment: BWS_ACCESS_TOKEN (handed to the binary as its INPUT_ACCESS_TOKEN, the spelling sm-action reads), INPUT_SECRETS (one `UUID > ENV_NAME` per line), GITHUB_ENV, GITHUB_OUTPUT.
#
# THE CONTRACT IS sm-action's OWN, pinned at v3.0.1 (1238aae8). The binary reads its inputs from `INPUT_<NAME>` (src/ci.rs get_input, where an empty value counts as unset), so this passes exactly what the node runner would derive from action.yml's `with:` and defaults.
# INPUT_SET_ENV must be set explicitly: src/config.rs reads it as `is_some_and(!= "false")`, so an unset value means NO env export, and only action.yml's `default: "true"` made the `uses:` path export.
# For each secret the binary prints `::add-mask::<value>` to STDOUT before anything else touches the value (src/main.rs set_secret, src/ci.rs mask_value), then appends it to GITHUB_ENV and GITHUB_OUTPUT with a random heredoc delimiter.
# Its stdout therefore goes straight to the log untouched, because the runner has to see the mask commands, and only stderr is captured.
#
# WHAT A FAILURE LOOKS LIKE. The binary returns anyhow errors, printed to stderr, and it wraps EVERY get_by_ids error as "The secrets provided could not be found" (src/main.rs), whatever the cause.
# Job 109063577876 (run 36461941122) printed that phrase over "Received error message from server: [503 Service Unavailable]", so the phrase alone cannot tell an outage from a missing grant; the bracketed status inside it can.
# Nothing is written to GITHUB_ENV or GITHUB_OUTPUT before every secret has been read, so a failed attempt leaves nothing behind and a retry starts clean.
#
# THE CLASSES. `credential` is a 401, 403 or 404, or any failure the patterns below do not recognise, which keeps the rotation notice as the default exactly as before.
# `transient` is a 5xx or 429 status or a connection or timeout error, and is retried after 5 s, 15 s and 45 s: a Bitwarden 503 burst on 2026-10-01 (PR #591, job 110632137106) outlasted the earlier 5 s + 15 s window while 30 sibling jobs authenticated fine. The class is written to GITHUB_OUTPUT as `class`, and action.yml prints the rotation notice only when it is not `transient`.
set -uo pipefail

bin="${1:-}"
if [[ -z "$bin" || ! -x "$bin" ]]; then
    echo "::error::bws-secrets: the sm-action binary '${bin}' is missing or not executable"
    echo "class=credential" >>"$GITHUB_OUTPUT"
    exit 1
fi

export INPUT_SET_ENV=true

classify() {
    local f="$1"
    if grep -Eq '\[(401|403|404)[] ]' "$f"; then
        echo credential
    elif grep -Eq '\[(5[0-9][0-9]|429)[] ]' "$f"; then
        echo transient
    elif grep -Eiq 'error sending request|timed out|timeout|connection (refused|reset|closed|aborted)|connection error|dns error|failed to lookup address|tcp connect|broken pipe|network is unreachable' "$f"; then
        echo transient
    else
        echo credential
    fi
}

# The one line an operator needs from a transient failure: the server's status line if there is one, the last non-empty stderr line otherwise.
status_line() {
    local f="$1" line
    line="$(grep -E 'Received error message from server|\[[0-9]{3}[] ]' "$f" | tail -1)"
    [[ -n "$line" ]] || line="$(grep -Ev '^[[:space:]]*$' "$f" | tail -1)"
    line="${line#Error: }"
    line="${line//[$'\r\n']/ }"
    printf '%s' "${line%"${line##*[![:space:]]}"}"
}

errf="$(mktemp)"
trap 'rm -f "$errf"' EXIT
delays=(5 15 45)
attempts=$((${#delays[@]} + 1))

for ((i = 1; i <= attempts; i++)); do
    : >"$errf"
    INPUT_ACCESS_TOKEN="${BWS_ACCESS_TOKEN:-}" "$bin" 2>"$errf"
    rc=$?
    # Replaying stderr keeps the log showing what the `uses:` path showed. It carries sm-action's error text and never a secret value, which the binary writes only to stdout as a mask command and to the two files.
    cat "$errf" >&2
    if ((rc == 0)); then
        ((i > 1)) && echo "bws-secrets: fetch succeeded on attempt $i of $attempts"
        exit 0
    fi
    class="$(classify "$errf")"
    if [[ "$class" != transient ]]; then
        echo "class=credential" >>"$GITHUB_OUTPUT"
        exit "$rc"
    fi
    if ((i < attempts)); then
        delay="${delays[$((i - 1))]}"
        echo "::warning::bws-secrets: attempt $i of $attempts failed transiently ($(status_line "$errf")); retrying in ${delay}s"
        sleep "$delay"
    fi
done

echo "class=transient" >>"$GITHUB_OUTPUT"
echo "::error title=Bitwarden Secrets Manager outage, not a credential problem::the fetch failed $attempts times on a transient server or network error; the last one was: $(status_line "$errf"). Do NOT rotate BWS_ACCESS_TOKEN for this; re-run the job once Bitwarden recovers."
exit "$rc"

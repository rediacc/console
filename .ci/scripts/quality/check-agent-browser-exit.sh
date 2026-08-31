#!/usr/bin/env bash
# `agent-browser open` has an EXIT CODE THAT DEPENDS ON WHETHER STDOUT IS A TTY.
#
# Measured 2026-08-28, same binary, same URL, page loads correctly both ways:
#     agent-browser open "$URL"                    -> rc=0
#     agent-browser open "$URL" >/dev/null 2>&1    -> rc=1
#
# packages/www/scripts/measure-page-density.sh runs under `set -euo pipefail` and
# redirects that call, so `set -e` killed it at its FIRST page. The symptom was not an
# error: an empty log, and a CSV containing only its header row. It read as "the harness
# produced nothing" rather than "the harness was shot".
#
# We do not own agent-browser, so the durable invariant is OURS: no script may let that
# exit status decide control flow. The fix is one of `|| true`, `|| :`, an `if`, or a
# `&&`/`||` chain -- anything that states the status is not being trusted. This gate
# exists because the reason lives in a COMMENT above the call, and this repo's own trap
# log records that the next reader deletes a defensive line on the comment's authority.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)

scan() {
    local root="$1" hits=0 f line n
    while IFS= read -r f; do
        # Only scripts that would DIE on a non-zero status.
        grep -qE '^[[:space:]]*set[[:space:]]+-[a-z]*e' "$f" || continue
        n=0
        while IFS= read -r line; do
            n=$((n + 1))
            case "$line" in
                *'agent-browser'*'open'*) ;;
                *) continue ;;
            esac
            # A comment is prose, not a call.
            case "${line#"${line%%[![:space:]]*}"}" in '#'*) continue ;; esac
            # Status already neutralised or consumed by a conditional.
            case "$line" in
                *'|| true'* | *'|| :'* | *'||true'*) continue ;;
                *'if '*'agent-browser'* | *'&&'* | *'! agent-browser'*) continue ;;
                *'$('*) continue ;; # captured, caller decides
            esac
            printf '  %s:%d\n    %s\n' "${f#"$root"/}" "$n" "$(echo "$line" | sed 's/^[[:space:]]*//')"
            hits=$((hits + 1))
        done <"$f"
        # THIS FILE IS EXCLUDED, and that is not a loophole. It carries the pattern in its own
        # fixtures and in its own error text, so a detector that reads itself reports five
        # findings that are prose. This repo's trap log calls the class out by name. The
        # exclusion is by exact path, so no other script can hide behind it.
    done < <(grep -rl --include='*.sh' 'agent-browser' "$root" 2>/dev/null |
        grep -v '/node_modules/' | grep -v '/\.git/' |
        grep -vF 'check-agent-browser-exit.sh' | sort)
    # NOT `return "$hits"`. A shell return is taken mod 256, so exactly 256 findings
    # would return 0 and read as a clean scan. Only the STATUS is made boolean here;
    # the count itself is still printed with the findings.
    [ "$hits" -eq 0 ]
}

# --- the same defect in JavaScript -------------------------------------------------
#
# `scan` above reads SHELL scripts under `set -e`. The identical bug lives in Node,
# where `execSync`/`execFileSync` THROW on the same worthless status, and it cost a CI
# red on 2026-08-31 (run 33430885467, job 99616335703): the tutorial-player release gate
# died on its first navigation with `Error: Command failed: agent-browser ... open <url>`
# and nothing else, while the identical command passed locally on the same tree.
#
# THE INVARIANT, deliberately crude so it cannot false-positive on style: a file that
# runs agent-browser through a THROWING exec must reach for the child's `.stdout`
# somewhere. agent-browser prints its verdict as JSON on stdout even when it exits 1, so
# `.stdout` is the only place a caller can learn what actually happened. A caller that
# never mentions it is a caller that has thrown the reason away.
scan_js() {
    local root="$1" hits=0 f line n
    while IFS= read -r f; do
        # The recovery is present: this file reads the child's stdout on the throw path.
        grep -q '\.stdout' "$f" && continue
        n=0
        while IFS= read -r line; do
            n=$((n + 1))
            case "$line" in
                *'execSync('* | *'execFileSync('*) ;;
                *) continue ;;
            esac
            case "$line" in *'agent-browser'*) ;; *) continue ;; esac
            # A comment is prose, not a call.
            case "${line#"${line%%[![:space:]]*}"}" in '//'* | '*'* | '/*'*) continue ;; esac
            printf '  %s:%d\n    %s\n' "${f#"$root"/}" "$n" "$(echo "$line" | sed 's/^[[:space:]]*//')"
            hits=$((hits + 1))
        done <"$f"
    done < <(grep -rlE --include='*.js' --include='*.mjs' --include='*.cjs' --include='*.ts' \
        'agent-browser' "$root" 2>/dev/null |
        grep -v '/node_modules/' | grep -v '/\.git/' | grep -v '/dist/' | sort)
    # Same reason as `scan`: a shell return is taken mod 256, so 256 findings would read
    # as a clean scan. Only the STATUS is made boolean.
    [ "$hits" -eq 0 ]
}

# --- controls, run BEFORE the real scan: a gate nobody has watched fail is not a gate ---
CTL=$(mktemp -d)
trap 'rm -rf "$CTL"' EXIT
printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail' \
    'agent-browser open "$URL" >/dev/null 2>&1' >"$CTL/bad.sh"
printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail' \
    'agent-browser open "$URL" >/dev/null 2>&1 || true' >"$CTL/good.sh"
printf '%s\n' '#!/usr/bin/env bash' \
    'agent-browser open "$URL" >/dev/null 2>&1' >"$CTL/no-set-e.sh"

scan "$CTL/bad.sh_dir" >/dev/null 2>&1 || true
mkdir -p "$CTL/one" && cp "$CTL/bad.sh" "$CTL/one/"
if scan "$CTL/one" >/dev/null; then
    echo "CONTROL FAILED: an unguarded call under set -e was NOT reported." >&2
    exit 1
fi
rm -rf "$CTL/one"
mkdir -p "$CTL/one"
cp "$CTL/good.sh" "$CTL/no-set-e.sh" "$CTL/one/"
if ! scan "$CTL/one" >/dev/null; then
    echo "CONTROL FAILED: a guarded call, or one outside set -e, was reported." >&2
    exit 1
fi
echo "  PASS  control: an unguarded call under set -e is reported"
echo "  PASS  control: a guarded call, and one outside set -e, are not"

# The JS half gets its own controls, for the same reason the shell half does.
rm -rf "$CTL/js" && mkdir -p "$CTL/js"
printf '%s\n' "const out = execFileSync('agent-browser', args, { encoding: 'utf8' });" \
    >"$CTL/js/bad.js"
if scan_js "$CTL/js" >/dev/null; then
    echo "CONTROL FAILED: a JS exec of agent-browser that never reads .stdout was NOT reported." >&2
    exit 1
fi
printf '%s\n' "try { out = execFileSync('agent-browser', args); }" \
    "catch (e) { out = String(e.stdout ?? ''); }" >"$CTL/js/bad.js"
printf '%s\n' "// execFileSync('agent-browser', ...) is described here, not called." \
    >"$CTL/js/comment.js"
if ! scan_js "$CTL/js" >/dev/null; then
    echo "CONTROL FAILED: a JS caller that recovers .stdout, or a comment, was reported." >&2
    exit 1
fi
echo "  PASS  control: a JS exec of agent-browser that discards .stdout is reported"
echo "  PASS  control: one that recovers .stdout, and a comment, are not"

# --- the real scan -----------------------------------------------------------------
js_out=""
if ! js_out=$(scan_js "$ROOT"); then
    echo "✗ a JS/TS caller execs \`agent-browser\` and never reads the child's stdout:" >&2
    printf '%s\n' "$js_out" >&2
    cat >&2 <<'MSG'

`execSync`/`execFileSync` THROW on a non-zero status, and agent-browser's status is not
evidence (see below). Its verdict is JSON on STDOUT even when it exits 1, so catch the
throw, take `error.stdout`, and let the parsed envelope decide:

    let out;
    try { out = execFileSync('agent-browser', args, { encoding: 'utf8' }); }
    catch (error) { out = String(error.stdout ?? ''); if (!out.trim()) throw error; }
    const parsed = JSON.parse(out);
    if (!parsed.success) throw new Error(`agent-browser failed: ${parsed.error}`);
MSG
    exit 1
fi

if out=$(scan "$ROOT"); then
    echo "✓ No shell script, and no JS/TS caller, lets \`agent-browser\`'s exit status decide control flow."
    exit 0
fi
echo "✗ \`agent-browser open\` exit status is load-bearing in a \`set -e\` script:" >&2
printf '%s\n' "$out" >&2
cat >&2 <<'MSG'

Its exit code is 1 when stdout is REDIRECTED and 0 on a terminal, for a URL that loads
fine either way, so this kills the script at that line with no error text.

Neutralise the status and let a check about the PAGE decide instead:
    agent-browser open "$URL" >/dev/null 2>&1 || true
    # then assert something real: a DOM-node floor, an expected selector, a title.
MSG
exit 1

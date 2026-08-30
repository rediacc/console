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

# --- the real scan -----------------------------------------------------------------
if out=$(scan "$ROOT"); then
    echo "✓ No script lets \`agent-browser open\` decide control flow."
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

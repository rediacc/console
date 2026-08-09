#!/bin/bash
# Open a PR for every submodule branch the round pushed, and link them from the
# console PR body.
#
# WHY THE LINK IS NOT COSMETIC. `.ci/scripts/quality/check-submodule-branches.sh`
# is a required gate, and it reads the CONSOLE PR BODY to decide whether each
# submodule PR is accounted for: it accepts the full PR URL as a substring
# (check-submodule-branches.sh:251), or `owner/repo#N` / `owner/repo/pull/N`
# (:259). A round that pushes a submodule branch and does not link its PR
# leaves console red on a gate no later round can clear by editing code. So the
# link is part of the push, not a nicety after it.
#
# PLAIN PRs, NOT DRAFTS. The four submodules are private repos on a free plan,
# where draft pull requests do not exist; `gh pr create --draft` fails there.
# Console is the repo with the draft flow.
#
# IDEMPOTENCE, twice over. The PR is created only when `gh pr list --head`
# finds none, so a second round on the same branch reuses the first round's PR.
# The body block is delimited and REBUILT each time, in the same
# strip-then-append idiom `.claude/hooks/post-bash/refresh-pr-body.sh` uses for
# its own `pushed-head` block. The two must not share markers: that hook
# rewrites the WHOLE body on every push, and anything inside its markers is
# destroyed on the next one.
#
# Usage:
#   submodule-prs.sh --verdict <file> --repo <owner/name> --pr <n> \
#     --branch <name> [--dry-run]
#
# Env: GH_TOKEN, and AUTOPILOT_ALLOW_PUSH which must be exactly "true".
# Exit: 0 (including "the verdict named no submodules"), 1 refused or a write
# failed, 2 usage.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"
VERDICT="${ARG_VERDICT:-}"
REPO="${ARG_REPO:-}"
PR="${ARG_PR:-}"
BRANCH="${ARG_BRANCH:-}"
DRY_RUN="${ARG_DRY_RUN:-false}"

[[ -n "$VERDICT" && -n "$REPO" && -n "$PR" && -n "$BRANCH" ]] || {
    log_error "usage: submodule-prs.sh --verdict <file> --repo <owner/name> --pr <n> --branch <name> [--dry-run]"
    exit 2
}
require_file "$VERDICT"

BEGIN='<!-- autopilot-submodule-prs:begin -->'
END='<!-- autopilot-submodule-prs:end -->'

# The path -> repo map, held to check-submodule-branches.sh:87-92. A path the
# map does not know cannot be turned into a PR, and the validator's enum makes
# that unreachable from a handoff; the guard stays so the two lists failing to
# agree is a loud stop rather than an empty `--repo `.
submodule_repo() {
    case "$1" in
        private/renet) echo "renet" ;;
        private/account) echo "account" ;;
        private/elite) echo "elite" ;;
        private/homebrew-tap) echo "homebrew-tap" ;;
        *) return 1 ;;
    esac
}

count="$(jq -r '(.submodules // []) | length' "$VERDICT")"
if [[ "$count" == "0" ]]; then
    log_info "submodule-prs: the round named no submodules; nothing to open or link"
    exit 0
fi
if [[ "${AUTOPILOT_ALLOW_PUSH:-}" != "true" && "$DRY_RUN" != "true" ]]; then
    log_error "stage-flag-disabled: AUTOPILOT_ALLOW_PUSH is not 'true'; refusing to open or link PRs (fail closed)"
    exit 1
fi

owner="${REPO%%/*}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
: >"$work/links.txt"

for ((i = 0; i < count; i++)); do
    sub="$(jq -r ".submodules[$i].path" "$VERDICT")"
    name=""
    if ! name="$(submodule_repo "$sub")"; then
        log_error "submodule-unmapped: '$sub' has no repository in the map; refusing to guess"
        exit 1
    fi
    target="$owner/$name"

    url=""
    if [[ "$DRY_RUN" == "true" ]]; then
        url="https://github.com/$target/pull/DRY-RUN"
    else
        url="$(gh_retry "existing PR for $target" -- pr list --repo "$target" --head "$BRANCH" \
            --state open --json url --jq '.[0].url // empty')"
        if [[ -z "$url" ]]; then
            # Title from the commit message's first line, body a plain pointer
            # back to console. Neither mentions any agent: the console body is
            # policed by check-claude-attribution.sh, and keeping both sides in
            # the same voice avoids a surprise there later.
            jq -r ".submodules[$i].message" "$VERDICT" | head -1 >"$work/title.txt"
            printf 'Submodule change for %s#%s.\n\nOpened by the autopilot harness alongside the console PR; review there.\n' \
                "$REPO" "$PR" >"$work/body.txt"
            url="$(gh_retry "create PR in $target" -- pr create --repo "$target" \
                --head "$BRANCH" --base main \
                --title "$(cat "$work/title.txt")" --body-file "$work/body.txt")"
            log_info "opened $target PR for branch $BRANCH: $url"
        else
            log_info "reusing existing $target PR for branch $BRANCH: $url"
        fi
    fi
    printf -- '- `%s` -> %s\n' "$sub" "$url" >>"$work/links.txt"
done

# Rebuild the block: read the body, drop any previous block, append the current
# one. Rebuilt rather than appended-to so a round that changes which submodules
# it touches does not leave the previous round's links behind claiming work
# this PR no longer contains.
if [[ "$DRY_RUN" == "true" ]]; then
    body=""
else
    body="$(gh_retry "console PR body" -- pr view "$PR" --repo "$REPO" --json body --jq '.body // ""')"
fi
printf '%s\n' "$body" >"$work/body-old.md"
awk -v b="$BEGIN" -v e="$END" '
    $0 == b { skip = 1; next }
    $0 == e { skip = 0; next }
    !skip { print }
' "$work/body-old.md" >"$work/body-stripped.md"

{
    cat "$work/body-stripped.md"
    printf '\n%s\n' "$BEGIN"
    printf '**Submodule PRs**\n\n'
    cat "$work/links.txt"
    printf '%s\n' "$END"
} >"$work/body-new.md"

if [[ "$DRY_RUN" == "true" ]]; then
    cat "$work/body-new.md"
    log_info "dry-run: would link $count submodule PR(s) in $REPO#$PR"
    exit 0
fi

gh_retry "link submodule PRs in $REPO#$PR" -- pr edit "$PR" --repo "$REPO" --body-file "$work/body-new.md" >/dev/null
log_info "linked $count submodule PR(s) in the $REPO#$PR body (the Submodule Branches gate reads them from there)"

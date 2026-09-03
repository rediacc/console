#!/bin/bash
# Every commit in a PR must be ATTRIBUTABLE to a GitHub account.
#
# THE DEFECT, measured 2026-09-03 on rediacc/console#585 before the history rewrite:
# 30 of 42 commits carried `muhammed@rediacc.com`, an address not linked to the
# operator's GitHub account. Same display name as the good ones, so nothing looked
# wrong in `git log` -- but GitHub renders them with a bare name, no avatar, no
# profile link, and no contribution credit. The submodules carried the same defect:
# account#85 7 of 9, renet#110 2 of 2, elite#16 1 of 1. Fixing it cost a history
# rewrite across four repositories plus a force push.
#
# THE ORACLE IS NOT AN EMAIL ALLOWLIST. `repos/{r}/pulls/{n}/commits` returns, per
# commit, the account GitHub RESOLVED the author email to -- `.author`, null when it
# resolves to nobody. Measured on #585: 30 null, 11 `.author.login = mfbayraktar`.
# So the rule is `.author` and `.committer` must both be non-null, which is the same
# question GitHub answers on the commit page. No hardcoded address, nothing to edit
# when one is linked or retired, and bots pass for free (`github-actions[bot]`
# resolves), which is why main's own bot commits need no special case.
#
# `gh api user/emails` would be the obvious oracle and CANNOT be used: it needs the
# `user` scope, which the token here lacks (measured: 404), and CI's app token is an
# INSTALLATION token with no user identity at all, so it can never work there.
#
# WHY THE API AND NOT `git log`: this repo's CI checkouts are shallow, and
# check-plan-housekeeping.sh is the record of what that costs -- three iterations,
# because `--is-shallow-repository` is not even the right test. This endpoint is
# authoritative regardless of what the runner cloned, so this gate has no shallow
# branch at all.
#
# Usage:
#   GITHUB_TOKEN=xxx PR_NUMBER=123 ./check-commit-identity.sh
#   ./check-commit-identity.sh --refresh      # regenerate the local identity cache

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: gh_retry is needed so a failed API call cannot be mistaken for a PR whose commits all attribute
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd gh
require_cmd jq

IDENTITY_FILE="${COMMIT_IDENTITY_FILE:-$ROOT/.ci/config/commit-identity.json}"
# GitHub's commit-list endpoint caps at 250 even with --paginate. Judging a truncated
# set would report a clean PR over commits never read.
MAX_COMMITS=250

probe_failed() {
    echo "" >&2
    echo "Cannot certify that this PR's commits attribute to a GitHub account, because" >&2
    echo "the GitHub API could not be read. Failing closed rather than reporting clean." >&2
    exit 1
}

# ---------------------------------------------------------------------------
# --refresh: derive the LOCAL guard's cache from GitHub. Never hand-authored.
# ---------------------------------------------------------------------------
# Keep only lines that are actually addresses. The guard against an API error body
# being mistaken for data; see the note in refresh_identity.
valid_emails() {
    grep -E '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$' || true
}

refresh_identity() {
    local repo="${GITHUB_REPOSITORY:-rediacc/console}" me login id emails
    me="$(gh api user --jq '{login,id}' 2>/dev/null)" || {
        echo "✗ cannot read the authenticated user; run: gh auth login" >&2
        exit 1
    }
    login="$(jq -r '.login' <<<"$me")"
    id="$(jq -r '.id' <<<"$me")"

    # user/emails is authoritative but needs the `user` scope. When it is absent --
    # which is the normal case here and the ONLY case in CI -- ask GitHub which
    # addresses it has already attributed to this login, which needs no extra scope.
    # `|| true` on the ASSIGNMENT and a SHAPE filter, both learned the hard way one
    # command ago: `gh api user/emails` fails with 404 here (no `user` scope) and
    # prints its JSON error body to STDOUT, so `2>/dev/null` does not suppress it and
    # `|| true` swallows the exit code. The first run of this function wrote
    # `{"message":"Not` and `Found","documentation_url":...}` into the cache as two
    # "emails". CLAUDE.md records the identical trap with curl: a 404 is silent and
    # its body becomes the value.
    #
    # So: keep only things shaped like an address. An empty result is then honest
    # rather than merely non-empty -- which is the distinction the anti-vacuity check
    # below could not make on its own.
    emails="$(gh api user/emails --jq '.[].email' 2>/dev/null | valid_emails || true)"
    if [[ -z "${emails//[[:space:]]/}" ]]; then
        echo "  note: user/emails unavailable (needs the 'user' scope; to add it," >&2
        echo "        gh auth refresh -h github.com -s user). Deriving from attributed" >&2
        echo "        commits instead, which needs no extra scope." >&2
        emails="$(gh api "repos/${repo}/commits?per_page=100" --paginate \
            --jq ".[] | select(.author.login == \"${login}\") | .commit.author.email" \
            2>/dev/null | valid_emails | sort -u | head -50 || true)"
    fi

    # ANTI-VACUITY: a cache with no emails would make the local guard refuse every
    # commit, which reads as the guard being broken rather than the cache being empty.
    if [[ -z "${emails//[[:space:]]/}" ]]; then
        echo "✗ derived NO valid email addresses for '${login}'; refusing to write the cache." >&2
        echo "  (An API error body is discarded by the shape filter rather than stored," >&2
        echo "   so 'none' here means none were readable, not that the call was silent.)" >&2
        exit 1
    fi

    jq -n --arg login "$login" --argjson id "$id" \
        --argjson emails "$(printf '%s\n' $emails | jq -R . | jq -s 'unique')" \
        --arg at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '{
          format: 1,
          refreshed_at: $at,
          "$comment": "GENERATED by check-commit-identity.sh --refresh. Do not hand-edit: it is a cache of what GitHub already attributes, and the CI gate never consults it to PASS a commit -- its verdict is GitHub own .author. Two live assertions keep it honest: an email listed here that GitHub refuses on a judged commit fails naming this file, and an attributed email missing from here fails naming --refresh.",
          identities: [ { login: $login, id: $id, emails: $emails } ]
        }' >"$IDENTITY_FILE"
    echo "✓ wrote $(basename "$IDENTITY_FILE"): ${login} (id ${id}), $(printf '%s\n' $emails | wc -l) email(s)"
}

if [[ "${1:-}" == "--refresh" ]]; then
    refresh_identity
    exit 0
fi

# ---------------------------------------------------------------------------
# The verdict.
# ---------------------------------------------------------------------------
if [[ -z "${PR_NUMBER:-}" ]]; then
    echo "PR_NUMBER not set - skipping commit identity check (not a pull request)"
    exit 0
fi
REPO="${GITHUB_REPOSITORY:-rediacc/console}"

judge_pr() { # judge_pr <repo> <pr-number> <label> -> prints offenders, returns 1 if any
    local repo="$1" pr="$2" label="$3" payload count bad
    payload="$(gh_retry "commit list for ${label}#${pr}" -- \
        api "repos/${repo}/pulls/${pr}/commits" --paginate \
        --jq '.[] | {sha: .sha, author: .author.login, committer: .committer.login, email: .commit.author.email, name: .commit.author.name}')" || probe_failed

    # A PR always has at least one commit, so an empty list is a failed read.
    if [[ -z "${payload//[[:space:]]/}" ]]; then
        echo "  ERROR: the commit list for ${label}#${pr} came back empty." >&2
        echo "  Every PR has at least one commit, so this is a failed read, not a clean PR." >&2
        probe_failed
    fi

    count="$(grep -c . <<<"$payload")"
    if [[ "$count" -ge "$MAX_COMMITS" ]]; then
        echo "  ERROR: ${label}#${pr} returned ${count} commits, at or over the ${MAX_COMMITS} page cap." >&2
        echo "  A truncated set cannot be cleared; refusing rather than judging part of it." >&2
        probe_failed
    fi

    bad="$(jq -r 'select(.author == null or .committer == null)
        | "    \(.sha[0:7])  \(.name) <\(.email)>"' <<<"$payload" | sort -u)"
    if [[ -n "$bad" ]]; then
        echo "✗ ${label}#${pr}: commit(s) GitHub does not attribute to any account:" >&2
        printf '%s\n' "$bad" >&2
        echo "" >&2
        jq -r 'select(.author == null) | .email' <<<"$payload" | sort | uniq -c | sort -rn |
            while read -r n e; do echo "    ${n} commit(s) from ${e}" >&2; done
        return 1
    fi

    # NOT VACUOUS: say what was cleared, so a collapse to zero is visible in the log
    # rather than inferred from an absent complaint.
    echo "  ✓ ${label}#${pr}: ${count} commit(s), all attributed ($(jq -r '.author' <<<"$payload" | sort -u | tr '\n' ' '))"
    return 0
}

FAILED=0
judge_pr "$REPO" "$PR_NUMBER" "$REPO" || FAILED=1

if [[ "$FAILED" -ne 0 ]]; then
    echo "" >&2
    echo "Those commits render on GitHub with a bare name: no avatar, no profile link," >&2
    echo "and no contribution credit. The address is not linked to any account." >&2
    echo "" >&2
    echo "Fix, in order of preference:" >&2
    echo "  1. Add the address at https://github.com/settings/emails, then push again." >&2
    echo "  2. Or rewrite the authors to an address that IS linked, and force push." >&2
    echo "  3. Check any single address with:" >&2
    echo "       gh api \"search/commits?q=repo:${REPO}+author-email:<addr>\" --jq '.items[0].author.login'" >&2
    exit 1
fi

echo "✓ commit identity: every commit attributes to a GitHub account"
echo "  Blind spot: this judges the PR's commits only. A commit pushed straight to a"
echo "  branch with no PR is not seen here; the pre-bash guard is what covers that."

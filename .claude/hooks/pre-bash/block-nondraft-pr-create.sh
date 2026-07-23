#!/usr/bin/env bash
# Enforce the draft-PR flow on `gh pr create`.
#
# The org is on the GitHub FREE plan: draft PRs exist only on PUBLIC repos.
# console + homebrew-tap are public -> their PRs MUST be created as drafts
# (the PR stays draft until CI is green; `gh pr ready` is gated by
# block-premature-ready.sh). renet/account/elite are private -> GitHub
# rejects --draft there, so the hook blocks it up front with a real message
# instead of letting the API fail cryptically.
#
# Target-repo resolution order: explicit --repo/-R flag > a cd/`git -C` into a
# private/<submodule> path inside the command > the session cwd's origin
# remote. Unknown/foreign repos are not policed.
INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
# Quote-strip + command-position anchor; rationale in block-premature-ready.sh.
STRIPPED=$(printf '%s' "$CMD" | tr '\n' '\001' | sed -e "s/'[^']*'//g" -e 's/"[^"]*"//g' | tr '\001' '\n')
echo "$STRIPPED" | grep -qE '(^|[;&|]|\$\()[[:space:]]*gh pr create' || exit 0

REPO=$(printf '%s\n' "$STRIPPED" | grep -oE -- '(--repo[= ]|-R )[A-Za-z0-9_./-]+' | head -1 | sed -E 's/^(--repo[= ]|-R )//')
if [[ -z "$REPO" ]]; then
    SM=$(printf '%s\n' "$STRIPPED" | grep -oE '(cd |-C )[^;|&]*private/(renet|account|elite|homebrew-tap)' | grep -oE 'private/(renet|account|elite|homebrew-tap)' | head -1)
    [[ -n "$SM" ]] && REPO="rediacc/${SM#private/}"
fi
if [[ -z "$REPO" ]]; then
    CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
    [[ -n "$CWD" ]] && REPO=$(git -C "$CWD" remote get-url origin 2>/dev/null | sed -E 's#\.git$##; s#.*[:/]([^/]+/[^/]+)$#\1#')
    # Default: no signal at all means the console checkout (fail toward draft).
    [[ -z "$REPO" ]] && REPO="rediacc/console"
fi

HAS_DRAFT=0
echo "$STRIPPED" | grep -qE '(^|[[:space:]])(--draft|-d)([[:space:]=]|$)' && HAS_DRAFT=1

case "$REPO" in
    rediacc/console | rediacc/homebrew-tap)
        if [[ "$HAS_DRAFT" -eq 0 ]]; then
            echo "❌ BLOCKED: PRs on $REPO must be created as DRAFTS: add --draft to 'gh pr create'. The PR stays draft while CI runs and is flipped with 'gh pr ready' only once CI Complete is green (that flip is what triggers the automated Claude review). If you are actually targeting a private submodule repo, say so explicitly with --repo rediacc/<renet|account|elite> (drafts are impossible there)." >&2
            exit 2
        fi
        ;;
    rediacc/renet | rediacc/account | rediacc/elite)
        if [[ "$HAS_DRAFT" -eq 1 ]]; then
            echo "❌ BLOCKED: $REPO is PRIVATE and the org is on the GitHub free plan, where draft PRs only exist on public repos. GitHub would reject this. Create the submodule PR without --draft; only the console PR uses the draft flow." >&2
            exit 2
        fi
        ;;
esac
exit 0

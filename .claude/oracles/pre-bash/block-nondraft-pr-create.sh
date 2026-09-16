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
# Bypass-resistant scanning (unwraps sh -c/eval, strips heredocs+prose); a
# `sh -c 'gh pr create'` must not slip a non-draft past this. SCAN is the only
# parsed view -- it already carries the prose-stripped command plus any
# unwrapped payload. See lib/command-scan.sh.
source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")
hook_gh_pr_at_command_pos "$SCAN" create || exit 0

# --repo and --draft both come from the SEGMENT carrying this `gh pr create`,
# and EVERY create on the line is judged on its own: line-wide parsing let a
# sibling invocation donate its repo or its --draft, so
# `gh pr create --repo rediacc/renet -t x; gh pr create -t y` read as one
# compliant draft. The cd/-C hint stays line-wide, because a cd genuinely does
# apply to every later segment. No signal at all defaults to the console
# checkout, which fails toward draft. See hook_gh_pr_segment / hook_target_repo.
CWD=$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null)
while IFS= read -r SEG; do
    [[ -z "$SEG" ]] && continue
    REPO=$(hook_target_repo "$SEG" "$SCAN" "$CWD")

    HAS_DRAFT=0
    printf '%s\n' "$SEG" | grep -qE '(^|[[:space:]])(--draft|-d)([[:space:]=]|$)' && HAS_DRAFT=1

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
done <<<"$(hook_gh_pr_segment "$SCAN" create)"
exit 0

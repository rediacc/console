#!/bin/bash
# Extract the submodule PRs linked from a console PR body.
#
# WHY THIS EXISTS. `check-submodule-branches.sh` reds the console PR while a
# LINKED submodule PR carries unresolved review threads, but the autopilot's
# review machinery only ever saw console's own threads. So a round would answer
# every console finding, resolve every console thread, and still sit red on a
# gate whose complaint lived in another repository. This turns the console body
# (the same links submodule-prs.sh writes there) back into fetch targets.
#
# THE REPO ALLOWLIST IS THE SECURITY BOUNDARY. A PR body is operator-authored
# on an armed PR, but it is still text, and this output decides which
# repositories the gate will fetch review comments from and hand to a model.
# Only the four submodules of this monorepo are recognised; a link to anything
# else -- however well-formed -- is ignored. Without that, a link in a body
# would be an arbitrary read primitive pointed at any repo the token can reach.
#
# Usage:
#   linked-sub-prs.sh --body <file> [--owner <owner>]
#
# Prints one `<owner>/<repo> <pr-number>` per line, deduplicated, in the order
# the four submodules are declared. PURE: no network, no git.
#
# Exit: 0 (an empty result is normal and quiet), 2 usage.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"
BODY="${ARG_BODY:-}"
OWNER="${ARG_OWNER:-rediacc}"

[[ -n "$BODY" ]] || {
    log_error "usage: linked-sub-prs.sh --body <file> [--owner <owner>]"
    exit 2
}
require_file "$BODY"

# Held to check-submodule-branches.sh's own hardcoded map. A submodule missing
# here is invisible to this scan, exactly as it is invisible to that gate.
SUB_REPOS=(renet account elite homebrew-tap)

for name in "${SUB_REPOS[@]}"; do
    # The three link spellings that gate accepts, so a body it is happy with is
    # a body this can read: the full URL, `owner/repo#N`, and
    # `owner/repo/pull/N`. The number is bounded to keep a stray digit run from
    # producing an absurd PR id.
    # `|| true` on the grep, not decoration: a body that links three of the
    # four submodules is the NORMAL case, grep exits 1 on no match, and
    # pipefail would turn that into a failed scan.
    { grep -oE "(https://github\.com/)?${OWNER}/${name}(/pull/|#)[0-9]{1,7}" "$BODY" || true; } |
        { grep -oE '[0-9]{1,7}$' || true; } |
        LC_ALL=C sort -un |
        while IFS= read -r n; do
            [[ -n "$n" ]] && printf '%s/%s %s\n' "$OWNER" "$name" "$n"
        done
done
exit 0

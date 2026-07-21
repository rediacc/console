#!/bin/bash
# Advance the release-contract-floor ratchet to the oldest cli sentinel on R2.
#
# WHY: the release-state bijection gate (Committed(v) ⇔ sentinel ∧ tag) excludes
# tags older than the oldest `.released` sentinel on R2, because pre-contract
# releases never had one. That floor is data-derived, which means an accidental
# scrub of EVERY cli sentinel would drop the floor to nothing and silently turn
# the gate into a no-op. Recording the observed floor in a committed file gives
# the gate a high-water mark that a scrub cannot walk backwards.
#
# The ratchet is monotonic: it writes only when the observed oldest sentinel is
# strictly newer than the value already in the file, so retries and no-op runs
# leave the tree clean and skip the commit entirely.
#
# Usage:
#   .ci/scripts/release/advance-contract-floor.sh
#
# Required env:
#   R2_ACCESS_KEY_ID      R2 credentials, exported as AWS_* for the aws CLI
#   R2_SECRET_ACCESS_KEY
#   R2_ENDPOINT           R2 S3 endpoint used by release-state-validator.sh
#   GIT_BOT_NAME          author identity for the ratchet commit
#   GIT_BOT_EMAIL
#
# NOTE: on an actual advance this COMMITS and PUSHES to main. Run locally only
# with R2 credentials pointed at a scratch bucket, or expect a no-op.
#
# Shell options: the workflow block already ran under `set -euo pipefail`;
# kept identical here. rsv_list_sentinels is written to tolerate pipefail (it
# swallows grep's exit-1-on-no-match internally).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd aws
require_cmd git
: "${R2_ACCESS_KEY_ID:?advance-contract-floor.sh: R2_ACCESS_KEY_ID must be set}"
: "${R2_SECRET_ACCESS_KEY:?advance-contract-floor.sh: R2_SECRET_ACCESS_KEY must be set}"
: "${R2_ENDPOINT:?advance-contract-floor.sh: R2_ENDPOINT must be set}"
GIT_BOT_NAME="${GIT_BOT_NAME:?advance-contract-floor.sh: GIT_BOT_NAME must be set}"
GIT_BOT_EMAIL="${GIT_BOT_EMAIL:?advance-contract-floor.sh: GIT_BOT_EMAIL must be set}"

cd "$(get_repo_root)"

export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="auto"
source .ci/scripts/lib/release-state-validator.sh
FLOOR_FILE=".ci/config/release-contract-floor.txt"
if [[ ! -f "$FLOOR_FILE" ]]; then
    echo "::warning::${FLOOR_FILE} not present; skipping ratchet advance"
    exit 0
fi
current="$(grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' "$FLOOR_FILE" | head -1 || echo)"
oldest="$(rsv_list_sentinels cli | sort -uV | head -1 || echo)"
if [[ -z "$oldest" ]]; then
    echo "::notice::no cli sentinels on R2; skipping ratchet advance"
    exit 0
fi
newer="$(printf '%s\n%s\n' "${current:-v0.0.0}" "$oldest" | sort -V | tail -1)"
if [[ "$newer" == "${current:-v0.0.0}" ]]; then
    echo "::notice::ratchet already at ${current:-<unset>} (>= observed ${oldest}); no change"
    exit 0
fi
echo "::notice::advancing ratchet ${current:-<unset>} -> ${oldest}"
printf '%s\n' "$oldest" >"$FLOOR_FILE"
git config user.name "$GIT_BOT_NAME"
git config user.email "$GIT_BOT_EMAIL"
git add "$FLOOR_FILE"
git commit -m "chore(release-state): advance contract floor to ${oldest} [skip ci]"
git push origin HEAD:main

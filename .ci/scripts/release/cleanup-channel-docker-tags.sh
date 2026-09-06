#!/bin/bash
# Delete the staging channel Docker tag after its images have been promoted.
#
# WHY: cd-stage.yml pushes images under a mutable channel tag (e.g. :edge) and
# cd-v2.yml retags them to the released semver. The channel tag has then served
# its purpose. Removing it keeps GHCR from accumulating one dangling tag per
# release.
#
# Non-critical by design: leftover channel tags are harmless, and the delete
# needs the `delete:packages` scope which is not always granted. A failure is
# recorded in the step summary and the script still exits 0.
#
# Usage:
#   .ci/scripts/release/cleanup-channel-docker-tags.sh
#
# Required env:
#   CHANNEL              channel tag to remove (e.g. edge)
#   GITHUB_STEP_SUMMARY  markdown summary file to append to
#   GH_TOKEN             token with delete:packages for cleanup-staging.sh
#
# Run locally (will attempt a real GHCR delete -- point GH_TOKEN at a scratch
# package or expect the non-critical failure path):
#   CHANNEL=edge GITHUB_STEP_SUMMARY=/dev/stdout \
#     .ci/scripts/release/cleanup-channel-docker-tags.sh
#
# Shell options: the workflow block ran under plain `bash -e`. `-u`/`pipefail`
# are added here; every variable is env-wired and there are no pipelines, so
# neither can change the outcome.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

CHANNEL="${CHANNEL:?cleanup-channel-docker-tags.sh: CHANNEL must be set}"
: "${GITHUB_STEP_SUMMARY:?cleanup-channel-docker-tags.sh: GITHUB_STEP_SUMMARY must be set}"

echo "## Cleanup Channel Tags" >>"$GITHUB_STEP_SUMMARY"
echo "" >>"$GITHUB_STEP_SUMMARY"

# Cleanup is non-critical (channel tags are harmless if they remain),
# so we log failures to the step summary but don't fail the job.
#
# THIS CANNOT SUCCEED TODAY, and saying so beats reporting a scope problem that is
# not the cause. cleanup-staging.sh exists to delete STAGING tags and guards itself
# with `[[ "$TAG" =~ ^staging- ]] || exit 1` -- deliberately, so a stray call cannot
# delete a real tag. CHANNEL is `edge` or `stable`, so the guard rejects it every
# time and this step has logged a failure on EVERY release since it was written.
#
# The old message blamed a missing `delete:packages` scope. That is a misdiagnosis:
# it sends the reader to fix a token when the truth is that the wrong tool is being
# called, and a wrong diagnosis repeated every release is worse than none. Widening
# the guard is NOT the fix -- it is a safety rail around deleting non-staging tags.
# Channel-tag deletion needs its own path, which is a deliberate change nobody has
# made.
if [[ ! "$CHANNEL" =~ ^staging- ]]; then
    echo "**Channel tag NOT cleaned up:** $CHANNEL" >>"$GITHUB_STEP_SUMMARY"
    echo "cleanup-staging.sh only deletes \`staging-*\` tags by design, so a channel tag can never be removed through it. This is a KNOWN GAP, not a token-scope problem, and it is non-critical: a channel tag left in GHCR is harmless." >>"$GITHUB_STEP_SUMMARY"
elif "$SCRIPT_DIR/../docker/cleanup-staging.sh" --tag "$CHANNEL"; then
    echo "**Channel tag cleaned up:** $CHANNEL" >>"$GITHUB_STEP_SUMMARY"
else
    echo "**Failed to clean up channel tag:** $CHANNEL" >>"$GITHUB_STEP_SUMMARY"
    echo "The delete call failed; check that GH_TOKEN carries \`delete:packages\`." >>"$GITHUB_STEP_SUMMARY"
fi

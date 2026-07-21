#!/bin/bash
# Append the release job's closing summary to the GitHub step summary.
#
# WHY: the publish job mutates several registries; the summary is the one place
# an operator can read, after the fact, exactly which version went where and
# which CI run's bytes it came from.
#
# Usage:
#   .ci/scripts/release/deployment-summary.sh
#
# Required env:
#   VERSION              published semver, no leading v (e.g. 1.2.3)
#   CI_RUN_ID            CI run the artifacts came from
#   CI_SHA               head sha of that CI run
#   GITHUB_STEP_SUMMARY  markdown summary file to append to
#
# Optional env:
#
# Run locally:
#   VERSION=1.2.3 CI_RUN_ID=1 CI_SHA=abc GITHUB_STEP_SUMMARY=/dev/stdout \
#     .ci/scripts/release/deployment-summary.sh
#
# Shell options: the workflow block ran under plain `bash -e`. `-u`/`pipefail`
# are added here; every variable is env-wired and there are no pipelines, so
# neither can change the outcome.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

VERSION="${VERSION:?deployment-summary.sh: VERSION must be set}"
CI_RUN_ID="${CI_RUN_ID:?deployment-summary.sh: CI_RUN_ID must be set}"
CI_SHA="${CI_SHA:?deployment-summary.sh: CI_SHA must be set}"
: "${GITHUB_STEP_SUMMARY:?deployment-summary.sh: GITHUB_STEP_SUMMARY must be set}"

echo "" >>"$GITHUB_STEP_SUMMARY"
echo "---" >>"$GITHUB_STEP_SUMMARY"
echo "" >>"$GITHUB_STEP_SUMMARY"
echo "## Deployment Complete" >>"$GITHUB_STEP_SUMMARY"
echo "" >>"$GITHUB_STEP_SUMMARY"
echo "**Version:** v${VERSION}" >>"$GITHUB_STEP_SUMMARY"
echo "**CI Run:** ${CI_RUN_ID} (sha: ${CI_SHA})" >>"$GITHUB_STEP_SUMMARY"
echo "**Pages URL:** https://www.rediacc.com" >>"$GITHUB_STEP_SUMMARY"
echo "" >>"$GITHUB_STEP_SUMMARY"
echo "**Docker images:**" >>"$GITHUB_STEP_SUMMARY"
echo "- ghcr.io/rediacc/renet:${VERSION} + :latest" >>"$GITHUB_STEP_SUMMARY"
echo "- ghcr.io/rediacc/rdc:${VERSION} + :latest" >>"$GITHUB_STEP_SUMMARY"
echo "- ghcr.io/rediacc/server:${VERSION} + :latest (on-prem)" >>"$GITHUB_STEP_SUMMARY"

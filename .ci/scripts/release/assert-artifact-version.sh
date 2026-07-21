#!/bin/bash
# Assert the CI run's built artifacts carry the version CD is about to publish.
#
# WHY: this catches the stale-ci_run_id foot-gun. If someone dispatches with a
# ci_run_id whose artifacts were built against a previous tag, the computed
# next_version (current latest tag + bump) would NOT match the version baked
# into those artifacts. CD would then happily retag the OLD bytes with the NEW
# version label, and only Docker's runtime --version check would surface the
# mismatch hours later. This fails loud and fast in the init job, before any
# registry mutation happens.
#
# Tolerated (warn + exit 0) rather than failed: a missing cli-manifest artifact,
# a manifest without .version. Those shapes exist on CI runs that predate the
# check; once it has been established for a few cycles, harden to a hard fail.
#
# Usage:
#   .ci/scripts/release/assert-artifact-version.sh
#
# Required env:
#   VERSION            promotion target semver, no leading v (e.g. 1.2.3)
#   CI_RUN_ID          CI workflow run id whose cli-manifest artifact to read
#   GITHUB_REPOSITORY  owner/repo the run belongs to
#   GH_TOKEN           token for `gh run download`
#
# Run locally:
#   VERSION=1.2.3 CI_RUN_ID=123456 GITHUB_REPOSITORY=rediacc/console \
#     .ci/scripts/release/assert-artifact-version.sh
#
# Shell options: the workflow block already ran under `set -euo pipefail`;
# kept identical here.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd gh
require_cmd jq
VERSION="${VERSION:?assert-artifact-version.sh: VERSION must be set}"
CI_RUN_ID="${CI_RUN_ID:?assert-artifact-version.sh: CI_RUN_ID must be set}"
: "${GITHUB_REPOSITORY:?assert-artifact-version.sh: GITHUB_REPOSITORY must be set}"

mkdir -p /tmp/cd-artifact-check
# The CLI manifest artifact is named "cli-manifest" by cd-stage.yml.
# Tolerate a missing artifact (e.g. older CI runs predating this
# check) by emitting a warning instead of failing -- once the
# check is established for a few cycles, harden to a hard fail.
if ! gh run download "$CI_RUN_ID" --repo "${GITHUB_REPOSITORY}" \
    --name cli-manifest --dir /tmp/cd-artifact-check 2>/dev/null; then
    echo "::warning::cli-manifest artifact not found on CI run ${CI_RUN_ID}; skipping artifact-version assertion. Re-run CI on the current main HEAD to produce the manifest."
    exit 0
fi
if [[ ! -f /tmp/cd-artifact-check/manifest.json ]]; then
    echo "::warning::cli-manifest artifact present but manifest.json missing; skipping assertion."
    exit 0
fi
ARTIFACT_VERSION="$(jq -r '.version // empty' /tmp/cd-artifact-check/manifest.json)"
if [[ -z "$ARTIFACT_VERSION" ]]; then
    echo "::warning::manifest.json has no .version field; skipping assertion."
    exit 0
fi
# Normalise: artifact may or may not carry a leading v.
ARTIFACT_VERSION="${ARTIFACT_VERSION#v}"
if [[ "$ARTIFACT_VERSION" != "$VERSION" ]]; then
    echo "::error::Artifact-version mismatch: CI run ${CI_RUN_ID} produced v${ARTIFACT_VERSION}, but CD is promoting as v${VERSION}."
    echo "::error::This means ci_run_id is stale -- the artifacts were built before the latest tag bump."
    echo "::error::Either dispatch again with no ci_run_id (auto-derive latest green CI on main), or re-run CI on current main to produce fresh artifacts."
    exit 1
fi
echo "::notice::Artifact version v${ARTIFACT_VERSION} matches promotion target v${VERSION}."

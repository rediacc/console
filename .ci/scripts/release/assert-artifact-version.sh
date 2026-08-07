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
# HARDENED 2026-08-07. This used to warn and exit 0 when the artifact or the
# .version field was missing, "until the check has been established for a few
# cycles". It was never established: nothing in the repo produced an artifact
# named `cli-manifest`, so EVERY release took the not-found branch and passed
# without comparing anything. The cost showed up the day two releases ran
# back to back -- the second published 1.2.16 binaries as 1.2.17, and the only
# thing that noticed was post-publish install validation, after edge had
# already been deployed. cd-stage.yml now uploads the manifest under that
# name, so absence means something is genuinely wrong and is a hard failure.
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
# The CLI manifest artifact is named "cli-manifest" and is uploaded on its own
# by cd-stage.yml. It did not exist until 2026-08-07, which is why this check
# spent its whole life taking the not-found branch.
if ! gh run download "$CI_RUN_ID" --repo "${GITHUB_REPOSITORY}" \
    --name cli-manifest --dir /tmp/cd-artifact-check 2>/dev/null; then
    echo "::error::cli-manifest artifact not found on CI run ${CI_RUN_ID}, so the artifact version CANNOT be compared."
    echo "::error::Refusing to publish on an unverified version. cd-stage.yml uploads this artifact on every push run, so its absence means the CI run is older than that change, was not a push run, or its artifacts expired (retention is 1 day)."
    echo "::error::Dispatch again with no ci_run_id to auto-derive the latest green CI on main, or re-run CI on current main."
    exit 1
fi
if [[ ! -f /tmp/cd-artifact-check/manifest.json ]]; then
    echo "::error::cli-manifest artifact present but manifest.json missing; refusing to publish unverified."
    exit 1
fi
ARTIFACT_VERSION="$(jq -r '.version // empty' /tmp/cd-artifact-check/manifest.json)"
if [[ -z "$ARTIFACT_VERSION" ]]; then
    echo "::error::manifest.json has no .version field; refusing to publish unverified."
    exit 1
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

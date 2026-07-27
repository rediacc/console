#!/bin/bash
# Count the staged release artifacts, write the run summary, and fail the stage
# when anything expected is missing.
#
# WHY: everything downstream (R2 upload, install validation, publish) assumes a
# complete artifact set. Counting on disk BEFORE publish is what turns "the deb
# job silently produced nothing" into a red stage instead of a half-published
# release. The counts are also the human-readable record in the job summary.
#
# Usage:
#   .ci/scripts/release/validate-stage-artifacts.sh
#
# Required env:
#   GITHUB_STEP_SUMMARY   markdown summary file to append the artifact table to
#   GITHUB_OUTPUT         step-output file to append passed=true|false to
#   EVENT_NAME            triggering event; "push" wording differs in the summary
#   NEXT_VERSION          version being staged (summary only)
#   CHANNEL               release channel being staged (summary only)
#
# Optional env:
#   MODE                  summary-title prefix, e.g. "(no-publish) " for non-push
#
# Run locally against a populated dist/ tree:
#   EVENT_NAME=push NEXT_VERSION=1.2.3 CHANNEL=edge \
#     GITHUB_STEP_SUMMARY=/dev/stdout GITHUB_OUTPUT=/dev/stdout \
#     .ci/scripts/release/validate-stage-artifacts.sh
#
# Shell options: the workflow block ran under plain `bash -e` and RELIES on the
# absence of `pipefail`. Every count is `X=$(find ... | wc -l)`, and `find`
# exits non-zero when its directory does not exist; with pipefail that failure
# would propagate through the command substitution and `set -e` would abort the
# script at the assignment, instead of recording the count as 0 and letting the
# explicit checks below report which artifact set is missing. `pipefail` is
# therefore switched back off after sourcing common.sh (which sets it).

set -eu
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
set +o pipefail

: "${GITHUB_STEP_SUMMARY:?validate-stage-artifacts.sh: GITHUB_STEP_SUMMARY must be set}"
: "${GITHUB_OUTPUT:?validate-stage-artifacts.sh: GITHUB_OUTPUT must be set}"
: "${EVENT_NAME:?validate-stage-artifacts.sh: EVENT_NAME must be set}"

MODE="${MODE:-}"
NEXT_VERSION="${NEXT_VERSION:-}"
CHANNEL="${CHANNEL:-}"

# The dist/ paths below are repo-relative, exactly as in the workflow step.
cd "$(get_repo_root)"

echo "## ${MODE}Stage Artifacts Results" >>"$GITHUB_STEP_SUMMARY"
echo "" >>"$GITHUB_STEP_SUMMARY"

CLI_COUNT=$(find dist/cli -type f 2>/dev/null | wc -l)
PKG_COUNT=$(find dist/packages -type f 2>/dev/null | wc -l)
DEB_COUNT=$(find dist/packages -name "*.deb" 2>/dev/null | wc -l)
RPM_COUNT=$(find dist/packages -name "*.rpm" 2>/dev/null | wc -l)
APK_COUNT=$(find dist/packages -name "*.apk" 2>/dev/null | wc -l)
ARCH_COUNT=$(find dist/packages -name "*.pkg.tar.zst" 2>/dev/null | wc -l)
# The `|| echo "N/A"` this replaces was unreachable: pipefail is off here (see
# the header), so the pipeline's status is `cut`'s, which succeeds even when du
# failed. A missing dist/pages/ rendered as an empty table cell instead of N/A.
PAGES_SIZE=$(du -sh dist/pages/ 2>/dev/null | cut -f1)
[[ -n "$PAGES_SIZE" ]] || PAGES_SIZE="N/A"
APT_FILES=$(find dist/repos/apt/dists -type f 2>/dev/null | wc -l)
RPM_FILES=$(find dist/repos/rpm/repodata -type f 2>/dev/null | wc -l)

echo "| Artifact | Count/Size |" >>"$GITHUB_STEP_SUMMARY"
echo "|----------|------------|" >>"$GITHUB_STEP_SUMMARY"
echo "| CLI artifacts | $CLI_COUNT files |" >>"$GITHUB_STEP_SUMMARY"
echo "| Linux packages | $PKG_COUNT files (deb:$DEB_COUNT rpm:$RPM_COUNT apk:$APK_COUNT arch:$ARCH_COUNT) |" >>"$GITHUB_STEP_SUMMARY"
echo "| Pages bundle | $PAGES_SIZE |" >>"$GITHUB_STEP_SUMMARY"
echo "| APT metadata | $APT_FILES files |" >>"$GITHUB_STEP_SUMMARY"
echo "| RPM metadata | $RPM_FILES files |" >>"$GITHUB_STEP_SUMMARY"
echo "" >>"$GITHUB_STEP_SUMMARY"
echo "**Version:** v${NEXT_VERSION}" >>"$GITHUB_STEP_SUMMARY"
echo "**Channel:** ${CHANNEL}" >>"$GITHUB_STEP_SUMMARY"

FAILED=false

if [[ "$CLI_COUNT" -eq 0 ]]; then
    echo "::error::No CLI artifacts found"
    FAILED=true
fi
if [[ "$PKG_COUNT" -eq 0 ]]; then
    echo "::error::No Linux packages found"
    FAILED=true
fi
if [[ "$DEB_COUNT" -lt 2 ]]; then
    echo "::error::Expected at least 2 DEB packages, found $DEB_COUNT"
    FAILED=true
fi
if [[ "$RPM_COUNT" -lt 2 ]]; then
    echo "::error::Expected at least 2 RPM packages, found $RPM_COUNT"
    FAILED=true
fi
if [[ "$APK_COUNT" -lt 2 ]]; then
    echo "::error::Expected at least 2 APK packages, found $APK_COUNT"
    FAILED=true
fi
if [[ "$ARCH_COUNT" -lt 2 ]]; then
    echo "::error::Expected at least 2 Archlinux packages, found $ARCH_COUNT"
    FAILED=true
fi
# APT/RPM repository metadata is CHANNEL-SCOPED, and on a channel-less event it
# is never built, so asserting it unconditionally fails a run that did nothing
# wrong.
#
# The producer is cd-stage.yml's "Build package repositories" step, which
# self-gates on `inputs.channel != ''`. The channel is empty for anything that
# is not push or pull_request (ci.yml's "Generate channel context"), i.e. for
# the nightly -- deliberately, so a scheduled run cannot orphan ~5 GB of R2
# bytes. So on the nightly the metadata is correctly absent and these two
# assertions failed it anyway. That is one of the three breaks behind twelve
# consecutive red nightlies (07-27: "No APT metadata files found" / "No RPM
# metadata files found", run 30237524399).
#
# WHY GATE THE ASSERTION RATHER THAN ALWAYS BUILD THE METADATA. Building it
# unconditionally was the other candidate and it is worse here:
# build-pkg-repo.sh hard-exits on an empty --channel, and it bakes CHANNEL into
# the generated content (`baseurl`, `gpgkey`, `Server`). Generating always would
# mean inventing a placeholder channel and emitting a repo definition pointing
# at a URL that does not exist -- shipping a plausible-looking broken artifact
# to make a check pass. The APT half is channel-agnostic and could be built,
# but a fix that repairs one of two formats is not a fix.
#
# The skip is announced in the step summary and as a notice, because a silently
# weakened check is how this class of bug survives in the first place.
if [[ -n "$CHANNEL" ]]; then
    if [[ "$APT_FILES" -eq 0 ]]; then
        echo "::error::No APT metadata files found"
        FAILED=true
    fi
    if [[ "$RPM_FILES" -eq 0 ]]; then
        echo "::error::No RPM metadata files found"
        FAILED=true
    fi
else
    echo "::notice::Channel is empty for event '${EVENT_NAME}', so no package-repository metadata was built; skipping the APT/RPM metadata assertions."
    echo "" >>"$GITHUB_STEP_SUMMARY"
    echo "> **APT/RPM metadata assertions skipped.** This run has no release channel (event: \`${EVENT_NAME}\`), so cd-stage.yml did not build package repositories. Every other artifact assertion above still applied." >>"$GITHUB_STEP_SUMMARY"
fi

if [[ "$FAILED" == "true" ]]; then
    echo "" >>"$GITHUB_STEP_SUMMARY"
    echo "**Status:** Validation FAILED" >>"$GITHUB_STEP_SUMMARY"
    echo "passed=false" >>"$GITHUB_OUTPUT"
    exit 1
fi

echo "" >>"$GITHUB_STEP_SUMMARY"
if [[ "$EVENT_NAME" == "push" ]]; then
    echo "**Status:** All validation passed. Ready for publish." >>"$GITHUB_STEP_SUMMARY"
else
    echo "**Status:** All validation passed." >>"$GITHUB_STEP_SUMMARY"
fi
echo "passed=true" >>"$GITHUB_OUTPUT"

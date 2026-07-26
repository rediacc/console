#!/bin/bash
# Bootstrap fallback for claude-review-reusable.yml.
#
# The reusable workflow sources all review tooling from console@main
# (.review-scripts checkout) so there is exactly one copy and a PR can never
# substitute its own review logic. Until the review system first lands on
# main, that checkout has no .ci/scripts/review and every review would die
# on file-not-found. This script copies the CALLER checkout's copy (console
# PRs carry the scripts at the workspace root) into .review-scripts, loudly.
#
# Self-disabling by construction: the workflow step short-circuits before
# calling this script whenever console@main already has the gate script, so
# in the steady state the main copy wins unconditionally.
#
# Env: none. Run from the workspace root (caller repo checkout), with the
# console@main checkout at .review-scripts/. Local dry-run:
#   cd "$(mktemp -d)" && mkdir -p .review-scripts .ci/scripts/review && \
#     touch .ci/scripts/review/claude-review-gate.sh && mkdir .ci/scripts/lib && \
#     bash <console>/.ci/scripts/review/bootstrap-review-scripts.sh

set -euo pipefail

if [ ! -f .ci/scripts/review/claude-review-gate.sh ]; then
    echo "review scripts missing on console@main AND in the caller checkout" >&2
    echo "(pre-first-merge, only console PRs can run reviews — submodule" >&2
    echo "callers must wait until the review system lands on console main)" >&2
    exit 1
fi

echo "::warning::bootstrap: review scripts not on console@main yet; using caller checkout copy"
mkdir -p .review-scripts/.ci/scripts
cp -r .ci/scripts/review .review-scripts/.ci/scripts/
cp -r .ci/scripts/lib .review-scripts/.ci/scripts/

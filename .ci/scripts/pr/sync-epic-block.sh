#!/usr/bin/env bash
# Sync the worklist epic block into a PR description.
#
#   sync-epic-block.sh <pr-number> <branch> [--dry-run]
#
# Reads the published snapshot (agent/pr/<branch>.md, written by
# `worklist.py --publish`) and rebuilds the `worklist-epics` block in the PR
# body. The marker pair, the strip idiom and why the block is rebuilt rather
# than appended to are documented in the implementation.
#
# A THIN ENTRY POINT. The implementation is `rediacc_ci.pr.sync_epic_block`:
# same argv, same streams, same exit codes. The bash body this file used to
# hold read the PR body with ONE `gh pr view`, so a single GitHub 5xx ended the
# sync; the port retries a transient fault through `rediacc_ci.core.gh_retry`
# (PLAN-gh-retry G12e) and fails at once on a 4xx. That bash body is kept,
# verbatim, as the oracle of `.ci/rediacc_ci/tests/test_pr_sync_epic_block.py`.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}/../..${PYTHONPATH:+:${PYTHONPATH}}"
exec python3 -m rediacc_ci.pr.sync_epic_block "$@"

#!/bin/bash
# List the exact E2E Workers spec files the committed shard manifest
# (.ci/config/shards/test-e2e-workers.json) ships today (T2.12,
# PLAN-ci-time-budget). ct-e2e-probe.yml's `list-files` job calls this to
# build its matrix: the probe asks "does the file THIS SHARD PLAN ships need
# a needs edge", never a fresh enumeration that could silently disagree with
# what actually ships -- a file the manifest does not run yet has no
# "passes in the full suite" baseline to probe against.
#
# One entry per FILE, not per manifest id: the describe-group buckets
# `13-postgres-fork-isolation.test.ts#part1/2/3` split one file into three
# shard units, and this probe runs that file whole.
#
# Prints one line, `files=<JSON array>`, appended to $GITHUB_OUTPUT when
# set, or to stdout otherwise -- so it runs the same way locally:
#   .ci/scripts/test/list-e2e-probe-files.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
cd "$(get_repo_root)"

MANIFEST=".ci/config/shards/test-e2e-workers.json"
FILES=$(node -e '
  const fs = require("fs");
  const manifestPath = process.argv[1];
  const data = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const files = new Set();
  for (const leg of data.legs) {
    for (const id of leg.ids) {
      const rest = id.replace(/^e2e-workers:/, "");
      files.add(rest.split("#")[0]);
    }
  }
  if (files.size === 0) {
    throw new Error(`VACUOUS: ${manifestPath} named zero e2e-workers files`);
  }
  console.log(JSON.stringify([...files].sort()));
' "$MANIFEST")

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "files=$FILES" >>"$GITHUB_OUTPUT"
else
    echo "files=$FILES"
fi

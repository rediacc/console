#!/bin/bash
# Lane capabilities are DERIVED from ci-quality.yml, so the derivation is the thing to
# prove -- twice over, because it can be wrong in two opposite ways.
#
# TOO GENEROUS is the failure that cost CI time. check:ci-docker-npm-pins was placed in
# quality-static, which checks out no submodules, so the file it exists to scan dropped
# out of its enumeration and its correct exclusions were reported as dead entries (job
# 100870135489). check_syncpack_sources.py carries the identical scar.
#
# AND THIS MODULE COMMITTED THAT VERY BUG WHILE BEING WRITTEN. Its first version matched
# `PyYAML` and `setup-go` anywhere in a job, and quality-code MENTIONS both in comments
# while installing neither -- so it would have placed a yaml-needing gate in a job with
# no PyYAML. Caught by checking the derived table against the file rather than trusting
# it, which is why the comment case is pinned below.
#
# TOO MEAN is the quieter failure: the first fix required `uses: actions/setup-go` and
# missed `- uses: actions/setup-go`, losing quality-go entirely and leaving go-needing
# gates unplaceable.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

OUT="$(
    cd "$REPO_ROOT" && npx tsx - <<'TS' 2>&1
import fs from 'node:fs';
import { LANE_ORDER, laneCapabilities, placeGate, satisfies } from './scripts/ci-runner/lanes.js';

let bad = 0;
const ck = (label: string, ok: boolean, detail?: unknown): void => {
  console.log(`${ok ? 'PASS' : 'FAIL'}\t${label}`);
  if (!ok) {
    bad += 1;
    console.log(`\t\t${JSON.stringify(detail)}`);
  }
};

const caps = laneCapabilities(fs.readFileSync('.github/workflows/ci-quality.yml', 'utf-8'));

ck('every lane in LANE_ORDER exists in the workflow', LANE_ORDER.every((j) => caps.has(j)),
   LANE_ORDER.filter((j) => !caps.has(j)));
ck('the slim lanes have no node', !caps.get('quality-static')?.node && !caps.get('quality-branch')?.node);
ck('quality-static takes NO submodules -- the mis-placement that cost CI',
   caps.get('quality-static')?.submodules.length === 0);
ck('quality-i18n takes ONLY private/account, not all of them',
   JSON.stringify(caps.get('quality-i18n')?.submodules) === '["private/account"]',
   caps.get('quality-i18n')?.submodules);
ck('quality-go really provides go', caps.get('quality-go')?.tools.includes('go'));

// THE COMMENT CASE, both directions.
const mention = 'jobs:\n  a:\n    steps:\n      # PyYAML four times and setup-go too\n      - run: echo hi\n';
ck('a job that MENTIONS PyYAML in a comment does not provide it',
   (laneCapabilities(mention).get('a')?.tools ?? []).length === 0,
   laneCapabilities(mention).get('a')?.tools);
const install = 'jobs:\n  a:\n    steps:\n      - run: python3 -m pip install --user "PyYAML==0.0.0-fixture"\n';
ck('CONTROL: a job that INSTALLS it does',
   laneCapabilities(install).get('a')?.tools.includes('python-yaml'),
   laneCapabilities(install).get('a')?.tools);
const dashed = 'jobs:\n  a:\n    steps:\n      - uses: actions/setup-go@abc\n';
ck('a `- uses:` line counts, not only a bare `uses:`',
   laneCapabilities(dashed).get('a')?.tools.includes('go'));

ck('placement: needs nothing -> the cheapest lane', JSON.stringify(placeGate(caps, [])) === '{"lane":"quality-static"}',
   placeGate(caps, []));
ck('placement: needs submodules -> never a lane without them',
   !['quality-static', 'quality-branch'].includes((placeGate(caps, ['submodules']) as { lane?: string }).lane ?? ''),
   placeGate(caps, ['submodules']));
ck('placement: needs go -> quality-go', JSON.stringify(placeGate(caps, ['go'])) === '{"lane":"quality-go"}',
   placeGate(caps, ['go']));
ck('placement: an unprovidable need is an ERROR, not a silent lane',
   'error' in placeGate(caps, ['a-toolchain-nobody-installs']));

// A LANE ROW WHOSE JOB IS GONE must refuse, never narrow the choice quietly.
const gone = laneCapabilities('jobs:\n  quality-static:\n    runs-on: ubuntu-slim\n');
ck('a LANE_ORDER entry missing from the workflow refuses placement',
   'error' in placeGate(gone, []), placeGate(gone, []));

ck('satisfies() is a superset test, not equality',
   satisfies({ job: 'x', runsOn: '', timeoutMinutes: null, submodules: ['*'], node: true, tools: ['go'] }, ['node']));
console.log(`TOTAL\t${bad}`);
TS
)"

echo "$OUT" | grep -E '^(PASS|FAIL)' | while IFS=$'\t' read -r verdict label; do
    if [[ "$verdict" == "PASS" ]]; then log_pass "$label"; else log_fail "$label"; fi
done

FAILURES="$(echo "$OUT" | sed -n 's/^TOTAL\t//p')"
if [[ -z "$FAILURES" ]]; then
    log_fail "the probe printed no TOTAL line, so nothing was asserted"
    echo "$OUT" | tail -5
    exit 1
fi
[[ "$FAILURES" == "0" ]] || {
    log_fail "lane derivation: $FAILURES failure(s)"
    exit 1
}
log_pass "lane derivation: 13 assertion(s), including the comment case both ways"

#!/bin/bash
# The per-gate DECLARATION parser, proved in both directions.
#
# WHY IT NEEDS ITS OWN GATE. scripts/lib/gate-header.ts is the single source the gate
# binder will derive every registration from -- id, run command, lane, needs. A parser
# that silently returns null makes the binder emit NOTHING for that gate, which reads
# exactly like "this gate has no declaration yet" and is the vacuity shape this repo
# keeps paying for. So the negatives matter as much as the positives: no block, an
# UNTERMINATED block, and a block with no step must each be null for a stated reason,
# not by accident.
#
# The two inference cases are the ones that cost CI time. `--recurse-submodules` in a
# gate placed in a lane without submodules is exactly how check:ci-docker-npm-pins lost
# the file it exists to scan (job 100870135489), and check_syncpack_sources.py carries
# the identical scar from its own first run.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

MOD="$REPO_ROOT/scripts/lib/gate-header.ts"
[[ -f "$MOD" ]] || {
    log_fail "gate-header.ts is missing; the binder's source of truth is gone"
    exit 1
}

OUT="$(
    cd "$REPO_ROOT" && npx tsx - <<'TS' 2>&1
import {
  derivedId,
  derivedRun,
  inferredNeeds,
  parseGateHeader,
} from './scripts/lib/gate-header.js';

let bad = 0;
const ck = (label: string, ok: boolean, detail?: unknown): void => {
  console.log(`${ok ? 'PASS' : 'FAIL'}\t${label}`);
  if (!ok) {
    bad += 1;
    console.log(`\t\t${JSON.stringify(detail)}`);
  }
};

const py = [
  '# ---- gate ----',
  '# step: Dockerfile npm pins',
  '# needs: submodules, python-yaml',
  '# slow: true   # measured 7s',
  '# ---- end gate ----',
].join('\n');
const h = parseGateHeader(py);
ck(
  'a # header parses, and a trailing note is not part of the value',
  h?.step === 'Dockerfile npm pins' &&
    h?.slow === true &&
    h?.needs.join(',') === 'submodules,python-yaml',
  h
);
ck(
  'a docstring header parses too',
  parseGateHeader(' * ---- gate ----\n * step: X\n * ---- end gate ----')?.step === 'X'
);
ck(
  'a // header parses too',
  parseGateHeader('// ---- gate ----\n// step: X\n// ---- end gate ----')?.step === 'X'
);
ck('CONTROL: no block at all is null', parseGateHeader('print("hi")') === null);
ck(
  'an UNTERMINATED block is null, never read to EOF',
  parseGateHeader('# ---- gate ----\n# step: X\nprint("code")') === null
);
ck(
  'a block with no step is null',
  parseGateHeader('# ---- gate ----\n# needs: node\n# ---- end gate ----') === null
);
ck(
  'needs: none means no needs',
  parseGateHeader('# ---- gate ----\n# step: X\n# needs: none\n# ---- end gate ----')?.needs
    .length === 0
);

ck(
  'id derives for a python check',
  derivedId('.ci/scripts/quality/check_docker_npm_pins.py') === 'check:ci-docker-npm-pins',
  derivedId('.ci/scripts/quality/check_docker_npm_pins.py')
);
ck(
  'id derives for a gate-test',
  derivedId('.ci/scripts/test/gates/test-watchdog-monitor-ordering.sh') ===
    'gate-test:watchdog-monitor-ordering'
);
ck(
  'run is the BARE PATH for py -- a python3 prefix breaks check:ci-parity',
  derivedRun('.ci/scripts/quality/check_x.py') === '.ci/scripts/quality/check_x.py'
);
ck(
  'run is tsx for ts, with the selftest leg when asked',
  derivedRun('scripts/check-x.ts', true) === 'tsx scripts/check-x.ts --selftest && tsx scripts/check-x.ts'
);

ck(
  'THE SHIPPED DEFECT: --recurse-submodules infers submodules',
  inferredNeeds('git ls-files --recurse-submodules').includes('submodules')
);
ck(
  'CONTROL: a gate naming no submodule infers none',
  !inferredNeeds('files = root.glob("*.yml")').includes('submodules')
);
console.log(`TOTAL\t${bad}`);
TS
)"

echo "$OUT" | grep -E '^(PASS|FAIL)' | while IFS=$'\t' read -r verdict label; do
    if [[ "$verdict" == "PASS" ]]; then log_pass "$label"; else log_fail "$label"; fi
done

FAILURES="$(echo "$OUT" | sed -n 's/^TOTAL\t//p')"
if [[ -z "$FAILURES" ]]; then
    log_fail "the probe printed no TOTAL line, so nothing was actually asserted"
    echo "$OUT" | tail -5
    exit 1
fi
[[ "$FAILURES" == "0" ]] || {
    log_fail "gate-header parser: $FAILURES failure(s)"
    exit 1
}
log_pass "gate-header parser: 13 assertion(s), both directions"

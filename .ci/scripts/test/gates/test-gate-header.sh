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
  analyzeGateHeader,
  derivedId,
  derivedRun,
  headerError,
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

// --- parser v2: the kind discriminant -------------------------------------------
// v1 required `step:`, which made every gate that does not OWN a step undeclarable:
// the 143 gate-tests all ride one battery step, and the 15 test/local-only entries
// have none at all. Each case below is one of the four shapes the manifest records.
const blk = (...body: string[]): string =>
  ['# ---- gate ----', ...body.map((l) => `# ${l}`), '# ---- end gate ----'].join('\n');

ck(
  'a header with no kind: is a step, so every v1 declaration keeps its meaning',
  parseGateHeader(blk('step: X'))?.kind === 'step'
);
ck(
  'kind: battery declares the shared step it RIDES',
  parseGateHeader(blk('kind: battery', 'step: Quality-gate unit tests'))?.step ===
    'Quality-gate unit tests'
);
ck(
  'kind: test declares its gate-test and its blocker, and no step',
  (() => {
    const h = parseGateHeader(blk('kind: test', 'test: .ci/x.sh', 'blocker: BLOCKER: why'));
    return h?.kind === 'test' && h?.step === undefined && h?.test === '.ci/x.sh';
  })()
);
ck(
  'kind: local-only declares a blocker and no step',
  parseGateHeader(blk('kind: local-only', 'blocker: BLOCKER: nothing invokes it'))?.step ===
    undefined
);
ck(
  'CONTROL: kind: battery with no step is refused -- it must name what it rides',
  parseGateHeader(blk('kind: battery')) === null &&
    headerError(blk('kind: battery'))?.includes('shared step it rides') === true
);
ck(
  'CONTROL: a stepless kind that names a step is refused',
  headerError(blk('kind: test', 'step: X', 'test: a', 'blocker: b'))?.includes(
    'has no workflow step'
  ) === true
);
ck(
  'CONTROL: kind: test with no test: is refused',
  headerError(blk('kind: test', 'blocker: b'))?.includes('naming the gate-test') === true
);
ck(
  'CONTROL: a non-emitting kind with no blocker is refused, so it cannot be mistaken for an unfinished registration',
  headerError(blk('kind: local-only'))?.includes('blocker') === true
);
ck(
  'CONTROL: an unknown kind is refused rather than defaulted to step',
  headerError(blk('kind: sometimes', 'step: X'))?.includes('is not one of') === true
);
ck(
  'THE INVISIBILITY DEFECT: a malformed block now EXPLAINS itself instead of reading as no header',
  headerError('# ---- gate ----\n# step: X')?.includes('never closes') === true &&
    headerError('print("hi")') === null
);
ck(
  'CONTROL: the `---- /gate ----` mis-close is named in the error, having voided a declaration twice',
  headerError('# ---- gate ----\n# step: X\n# ---- /gate ----')?.includes('/gate') === true
);
ck(
  'analyzeGateHeader separates all three outcomes: header, error, and no block',
  (() => {
    const a = analyzeGateHeader(blk('step: X'));
    const b = analyzeGateHeader('# ---- gate ----\n# step: X');
    return a !== null && !('error' in a) && b !== null && 'error' in b &&
      analyzeGateHeader('x = 1') === null;
  })()
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
# COUNT-FREE ON PURPOSE. This line used to read "13 assertion(s)" and every case added
# to the probe above made it a lie that no gate could catch. The count is read back from
# what actually ran; the FLOOR is what stops the probe silently shrinking to nothing.
ASSERTED="$(echo "$OUT" | grep -cE '^(PASS|FAIL)')"
if ((ASSERTED < 13)); then
    log_fail "only $ASSERTED assertion(s) ran; the probe has lost cases (floor 13)"
    exit 1
fi
log_pass "gate-header parser: $ASSERTED assertion(s), both directions"

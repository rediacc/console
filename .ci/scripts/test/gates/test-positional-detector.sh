#!/bin/bash
# Both-ways test for scripts/lib/positional-cli-detector.ts.
#
# The detector decides which `rdc ...` examples in docs, help text and locale
# strings teach the WRONG syntax. It backs four consumers: two ESLint rules
# (i18n/no-positional-cli-syntax, custom/no-positional-cli-syntax-source),
# scripts/validate-cli-examples.ts, and packages/www/scripts/validate-docs-cli-usage.js.
#
# It has to be tested in BOTH directions, because it can fail in both:
#
#   - Too quiet, and stale docs teach a command form that does not exist.
#   - Too loud, and it forbids the CORRECT form. That is not hypothetical: its
#     placeholder pass ran over EVERY command path instead of only parent
#     commands (which is all its own docstring ever claimed), so once P4 gave
#     leaves positional refs it flagged `rdc datastore create <name>` and told
#     the author the command "accepts zero positional arguments" — a statement
#     that was simply false. A validator that reds on correct output blocks the
#     work it exists to protect.
#
# Every case below is asserted in the direction that would catch the regression
# that actually happened.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

DRIVER="$(mktemp -t positional-detector-XXXXXX.mts)"
trap 'rm -f "$DRIVER"' EXIT

cat >"$DRIVER" <<EOF
import { scanText } from '$REPO_ROOT/scripts/lib/positional-cli-detector.ts';

// [example, mustFlag, why]
const CASES: [string, boolean, string][] = [
  // MUST FLAG — a command that takes no positional, handed one anyway.
  ['rdc machine list prod-1', true, 'zero-positional leaf given a bare word'],
  ['rdc machine list <name>', true, 'zero-positional leaf given a placeholder'],
  ['rdc repo <name>', true, 'parent given a placeholder; a parent expects a SUBCOMMAND'],

  // MUST NOT FLAG — the P4 ref grammar. These are the forms we now want taught,
  // and the detector used to reject every one of them.
  ['rdc repo up <repo-ref>', false, 'leaf whose primary name IS a positional ref'],
  ['rdc datastore create <name>', false, 'leaf that really accepts <datastore>'],
  ['rdc repo replicate <ref>', false, 'actionable parent that takes a positional'],

  // MUST NOT FLAG — nothing positional is being taught at all.
  ['rdc repo secret list', false, 'no token after the command path'],
  ['rdc machine list --name x', false, 'a flag is not a positional'],
];

let failures = 0;
for (const [example, mustFlag, why] of CASES) {
  const flagged = scanText(example).length > 0;
  if (flagged !== mustFlag) {
    failures++;
    console.error(
      \`  MISMATCH: "\${example}" -> flagged=\${flagged}, expected=\${mustFlag} (\${why})\`
    );
  }
}
if (failures > 0) {
  console.error(\`\${failures} case(s) wrong\`);
  process.exit(1);
}
console.log('all cases as expected');
EOF

test_detector_both_ways() {
    log_test "positional detector flags wrong syntax and accepts the P4 ref grammar"
    if ! output="$(cd "$REPO_ROOT" && npx tsx "$DRIVER" 2>&1)"; then
        echo "$output" >&2
        log_fail "positional-cli-detector did not behave as expected"
    fi
    log_pass "positional detector: 8/8 cases, both directions"
}

test_detector_both_ways

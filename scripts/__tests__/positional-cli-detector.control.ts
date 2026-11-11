#!/usr/bin/env node

/**
 * Control harness for scripts/lib/positional-cli-detector.ts `scanText`.
 *
 * 3f189a06b7 stopped treating an optional-flag usage marker such as `[--json]` as a positional
 * argument, because `rdc legal [--json]` and `rdc version [--json]` in a plan were reported as
 * positional syntax. The marker is only exempt when a flag follows the bracket: `[name]` after a
 * zero-positional command is still a positional placeholder, and the detector must keep saying so.
 *
 * Run: npx tsx scripts/__tests__/positional-cli-detector.control.ts
 */

import { scanText } from '../lib/positional-cli-detector';

let failed = 0;
function check(label: string, ok: boolean): void {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${label}`);
  if (!ok) failed++;
}

check('`rdc legal [--json]` is not positional syntax', scanText('rdc legal [--json]').length === 0);
check('`rdc version [--json]` is not positional syntax', scanText('rdc version [--json]').length === 0);
check(
  'CONTROL: `rdc legal [name]` after a zero-positional command is still reported',
  scanText('rdc legal [name]').length > 0
);
check('CONTROL: `rdc legal <name>` is still reported', scanText('rdc legal <name>').length > 0);

if (failed > 0) {
  console.error(`positional-cli-detector control: ${failed} case(s) failed`);
  process.exit(1);
}
console.log('positional-cli-detector control: all cases passed');

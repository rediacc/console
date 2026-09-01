/**
 * The controls runner: one loop, instead of thirty-five.
 *
 * WHY A SHARED MODULE, and the argument is this repo's own. `shrink-only-baseline.ts:25-31`
 * already made it for the control *data*: "WHY A SHARED MODULE RATHER THAN SEVEN COPIES.
 * Because it was a class, not an instance… Seven copies of this logic would be seven
 * chances to drift." That reasoning stopped at the data. `sharedSelftestCases()` is
 * consumed at nine call sites and every one of them still writes its own assertion closure
 * and its own loop.
 *
 * Measured 2026-09-01 across `scripts/check-*.ts`: 35 of 101 files hand-roll the closure,
 * in two idioms — a `failures: string[]` form (12 files, 8 byte-identical) and a counter
 * form (20 files, 5 clusters). ~196 duplicated lines.
 *
 * THE DRIFT IS NOT HYPOTHETICAL, though it is smaller than first reported. A survey of
 * those copies claimed three defects; probing each one kept ONE:
 *
 *   - REAL. Five gates inline unconditional `\x1b[…` escapes and pipe them into non-TTY CI
 *     logs -- `check-dead-css.ts:187`, `check-docker-image-freshness.ts:312`,
 *     `check-landmarks.ts:52`, `check-ssr-locale.ts:62`, `check-svg-theme-reach.ts:60`.
 *     Demonstrated with `cat -v` on a piped run. `scripts/utils/console.ts:8-15` already
 *     gates the identical codes on `process.stdout.isTTY`, and ten files import it.
 *   - NOT A DEFECT. `check-i18n-cross-locale.ts:555` was reported as discarding
 *     `selftest()`'s return value. It cannot: `selftest(): void` and it calls
 *     `process.exit(1)` itself at `:536`. Planting a failing control there exits 1 today.
 *   - NOT A DEFECT. `check-merge-method-prose.ts:78` writes `bad = 1` rather than `bad++`.
 *     Its caller is `process.exit(main())`, so a saturating 1 is a correct non-zero, and a
 *     true count is arguably worse -- an exit code above 125 wraps.
 *
 * Recording all three is the point. Two of them were a SUB-AGENT'S report taken at face
 * value and repeated in a commit message before anyone ran the code; the rule that a
 * report is not evidence until spot-checked was learned here at the cost of a correction.
 *
 * A SHARED HARNESS IS A SHARED POINT OF FAILURE, and that is the honest cost. If this
 * function ever passes silently, every gate on it goes blind AT ONCE — strictly worse than
 * 35 hand-rolled closures of which one is already broken. So it ships with a meta-control
 * that plants a failing case and requires a non-zero return; see
 * `.ci/scripts/test/gates/test-gate-anti-vacuity.sh`. The harness may not acquire its
 * first consumer before that control exists.
 *
 * WHAT THIS DELIBERATELY DOES NOT OWN: the findings report. Measured across ten gates, the
 * pass/fail prose is TEN DISTINCT SHAPES, and that is correct — the sentence explaining
 * what failed and why is the gate's whole value. This module counts the scaffolding and
 * never the reasons.
 */
import { GREEN, NC, RED } from '../utils/console.js';

/** One control. Identical to the shape `sharedSelftestCases()` already returns. */
export interface ControlCase {
  name: string;
  ok: boolean;
  /** Printed indented under a FAIL. Never printed on a PASS. */
  detail?: string;
}

export interface RunControlsOptions {
  /**
   * Where PASS lines go. FAIL lines always go to stderr, so a red survives a caller that
   * pipes stdout somewhere. Default: `console.log`.
   */
  log?: (line: string) => void;
  /** Default: `console.error`. */
  err?: (line: string) => void;
}

/**
 * Run every case, print one line each, and return the FAILURE COUNT.
 *
 * Returns a count and never a boolean, deliberately: two gates in the corpus use a
 * saturating `bad = 1` and cannot say how many controls failed. `0` means every control
 * behaved. A caller wanting a boolean writes `=== 0` and is explicit about it.
 *
 * THE EMPTY ARRAY IS A FAILURE, not a pass. A controls run that verified nothing is the
 * exact vacuity this repo gates against everywhere else, and a caller whose case-builder
 * silently returned `[]` would otherwise get a confident `0`. It returns 1 and says so.
 */
export function runControls(cases: ControlCase[], opts: RunControlsOptions = {}): number {
  const log = opts.log ?? ((l: string) => console.log(l));
  const err = opts.err ?? ((l: string) => console.error(l));

  if (cases.length === 0) {
    err(`  ${RED}FAIL${NC}  no controls were supplied, so this run verified nothing`);
    return 1;
  }

  let failed = 0;
  for (const c of cases) {
    if (c.ok) {
      log(`  ${GREEN}PASS${NC}  ${c.name}`);
    } else {
      failed += 1;
      err(`  ${RED}FAIL${NC}  ${c.name}${c.detail ? `\n        ${c.detail}` : ''}`);
    }
  }
  return failed;
}

/**
 * The bail-out every consumer writes after `runControls`, so its wording cannot drift.
 *
 * Exits 1 when anything failed; returns otherwise. The sentence is the one already in the
 * corpus (`check-dead-css.ts:270` and three siblings, byte-identical), kept verbatim
 * because it is the string those gates are recognised by.
 */
export function exitUnlessControlsPass(failed: number, gate: string): void {
  if (failed === 0) return;
  console.error(
    `${RED}✗${NC} ${failed} control(s) failed; the gate cannot be trusted${gate ? ` (${gate})` : ''}`
  );
  process.exit(1);
}

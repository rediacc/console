/**
 * Fail-closed prerequisite resolution for environment-gated suites.
 *
 * The precedent is renet's `RENET_EXPECT_NO_ACCOUNT_SERVER` block
 * (`private/renet/.ci/scripts/test/run-tests.sh:72-90`) and the reasoning
 * transfers verbatim: a suite that quietly skips when its prerequisites are
 * absent is indistinguishable from one that ran and passed. The renet block
 * fixed that by making the skip a DECLARATION — a job with no account server
 * must say so, in an env var, with a reason a reader can check.
 *
 * This module is that rule for the Playwright suites. Three verdicts, and only
 * three:
 *
 *   run             every prerequisite is present; the suite executes.
 *   declared-skip   prerequisites missing AND the declaration var is set to a
 *                   reason. Loud on stderr, never silent.
 *   undeclared      prerequisites missing and nobody said why. That is a
 *                   FAILURE, not a skip.
 *
 * It lives apart from the suite that uses it so the fail-closed behaviour is
 * itself unit-testable (`__tests__/declaredSkip.test.ts`) without a fleet —
 * a skip mechanism nobody has watched refuse is exactly the kind of instrument
 * this rule exists to distrust.
 */

/** One thing a suite needs, and how a reader would provide it. */
interface Prerequisite {
  /** Short name, e.g. 'VM_WORKERS (two worker VMs)'. */
  readonly name: string;
  /** True when the prerequisite is present. */
  readonly satisfied: boolean;
  /** How to satisfy it, quoted verbatim into the failure text. */
  readonly how: string;
}

export type PrerequisiteVerdict =
  | { readonly kind: 'run'; readonly label: string }
  | {
      readonly kind: 'declared-skip';
      readonly label: string;
      readonly reason: string;
      readonly missing: readonly string[];
      /** The full stderr banner, so callers do not re-invent the wording. */
      readonly banner: string;
    }
  | {
      readonly kind: 'undeclared';
      readonly label: string;
      readonly missing: readonly string[];
      readonly declareVar: string;
      /** The full failure text, thrown by `announce`. */
      readonly message: string;
    };

export interface ResolveInput {
  /** Human name of the capability being gated, e.g. 'cluster licensing (VM tier)'. */
  readonly label: string;
  /** The env var whose VALUE is the declared reason for skipping. */
  readonly declareVar: string;
  readonly prerequisites: readonly Prerequisite[];
  /** Defaults to `process.env`; injectable so the unit test can plant states. */
  readonly env?: NodeJS.ProcessEnv;
}

/**
 * Decide whether a suite runs, skips by declaration, or fails closed.
 *
 * A declaration only takes effect when something is actually missing: setting
 * the var on a fully-provisioned machine must not disable a suite that could
 * have run, or the declaration becomes a way to turn coverage off by accident.
 */
export function resolvePrerequisites(input: ResolveInput): PrerequisiteVerdict {
  const env = input.env ?? process.env;
  const missing = input.prerequisites.filter((p) => !p.satisfied);

  if (missing.length === 0) return { kind: 'run', label: input.label };

  const missingNames = missing.map((p) => p.name);
  const reason = (env[input.declareVar] ?? '').trim();

  if (reason.length > 0) {
    return {
      kind: 'declared-skip',
      label: input.label,
      reason,
      missing: missingNames,
      banner: [
        '',
        `${input.label}: SKIPPED BY DECLARATION`,
        `  reason (${input.declareVar}): ${reason}`,
        `  unmet prerequisites: ${missingNames.join(', ')}`,
        '',
      ].join('\n'),
    };
  }

  return {
    kind: 'undeclared',
    label: input.label,
    missing: missingNames,
    declareVar: input.declareVar,
    message: [
      `${input.label}: prerequisites are missing, so these assertions did not run.`,
      'That is a FAILURE, not a skip: a suite that silently omits them is',
      'indistinguishable from one that passed them.',
      '',
      'Unmet prerequisites:',
      ...missing.map((p) => `  - ${p.name}: ${p.how}`),
      '',
      'Either provide them, or declare the omission with a reason:',
      `  ${input.declareVar}='<why this environment has none>'`,
    ].join('\n'),
  };
}

/**
 * Act on a verdict at module load: throw on `undeclared`, print the banner on
 * `declared-skip`, and report whether the caller should skip.
 *
 * Deliberately on stderr. Playwright's reporters own stdout, and a skip notice
 * that lands in the reporter's stream is the silence this module exists to
 * prevent.
 */
export function announcePrerequisites(
  verdict: PrerequisiteVerdict,
  log: (line: string) => void = (line) => process.stderr.write(`${line}\n`)
): { readonly skip: boolean; readonly reason: string } {
  if (verdict.kind === 'undeclared') throw new Error(verdict.message);
  if (verdict.kind === 'declared-skip') {
    log(verdict.banner);
    return { skip: true, reason: `${verdict.label}: ${verdict.reason}` };
  }
  return { skip: false, reason: '' };
}

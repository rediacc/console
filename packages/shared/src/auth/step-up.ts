/**
 * The step-up vocabulary: the methods a user can re-verify with and the one
 * order they are ranked in. The account server and the web console both
 * import it, and nothing else ranks methods.
 *
 * Rank, strongest first: passkey, TOTP, email link, account password. A
 * destructive console run may require a minimum method (org policy), and the
 * strongest method the user holds is offered first.
 */

export const STEP_UP_METHODS = ['passkey', 'totp', 'email', 'password'] as const;

export type StepUpMethod = (typeof STEP_UP_METHODS)[number];

/** Strongest first: 0 is the strongest method. */
const RANK: Record<StepUpMethod, number> = {
  passkey: 0,
  totp: 1,
  email: 2,
  password: 3,
};

export function isStepUpMethod(value: unknown): value is StepUpMethod {
  return typeof value === 'string' && (STEP_UP_METHODS as readonly string[]).includes(value);
}

/** Positive when `a` is stronger than `b`, negative when weaker, zero when equal. */
export function compareStepUpStrength(a: StepUpMethod, b: StepUpMethod): number {
  return RANK[b] - RANK[a];
}

/** The held methods without duplicates, strongest first. */
export function sortStrongestFirst(held: readonly StepUpMethod[]): StepUpMethod[] {
  return STEP_UP_METHODS.filter((method) => held.includes(method));
}

/** The strongest method among those held, or null when none is held. */
export function strongestHeld(held: readonly StepUpMethod[]): StepUpMethod | null {
  return sortStrongestFirst(held)[0] ?? null;
}

/** Whether `method` is at least as strong as `minimum`. */
export function meetsMinimum(method: StepUpMethod, minimum: StepUpMethod): boolean {
  return RANK[method] <= RANK[minimum];
}

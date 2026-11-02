/**
 * Poll pacing for detached jobs. Pure functions: time and randomness are injected.
 *
 * Log-poll ladder: start at 2 s, x1.5 per poll with no new lines (cap 30 s), reset
 * to 2 s when lines arrive, poll at once while the server reports `more`.
 * Transport-error ladder: same growth, separate state, gives up after a 10 minute budget.
 */

export const INITIAL_DELAY_MS = 2_000;
export const MAX_DELAY_MS = 30_000;
export const GROWTH_FACTOR = 1.5;
export const JITTER_RATIO = 0.2;
export const TRANSPORT_BUDGET_MS = 10 * 60 * 1000;

/** Returns a number in [0, 1), like Math.random. */
export type RandomSource = () => number;

/** Scales `ms` by a factor in [1 - ratio, 1 + ratio] drawn from `random`. */
export function applyJitter(
  ms: number,
  random: RandomSource,
  ratio: number = JITTER_RATIO
): number {
  const factor = 1 + (random() * 2 - 1) * ratio;
  return Math.round(ms * factor);
}

function grow(baseMs: number): number {
  return Math.min(baseMs * GROWTH_FACTOR, MAX_DELAY_MS);
}

export interface PollOutcome {
  /** Whether the poll returned any new lines. */
  newLines: boolean;
  /** Whether the server reports more output already available. */
  more: boolean;
}

export interface PollStep {
  /** Milliseconds to wait before the next poll (0 = poll at once). */
  delayMs: number;
  /** Un-jittered base to pass back into the next call. */
  nextBaseMs: number;
}

/** Decides the wait after a successful poll. `baseMs` starts at INITIAL_DELAY_MS. */
export function nextPollStep(baseMs: number, outcome: PollOutcome, random: RandomSource): PollStep {
  if (outcome.more) {
    return { delayMs: 0, nextBaseMs: INITIAL_DELAY_MS };
  }
  const nextBaseMs = outcome.newLines ? INITIAL_DELAY_MS : grow(baseMs);
  return { delayMs: applyJitter(nextBaseMs, random), nextBaseMs };
}

export interface TransportErrorState {
  /** Un-jittered base of the error ladder. */
  baseMs: number;
  /** Time of the first error in the current unbroken run of failures. */
  firstFailureAtMs: number;
}

export type TransportStep =
  | { giveUp: false; delayMs: number; state: TransportErrorState }
  | { giveUp: true };

/** Starts a failure run at the first transport error. */
export function startTransportErrors(nowMs: number): TransportErrorState {
  return { baseMs: INITIAL_DELAY_MS / GROWTH_FACTOR, firstFailureAtMs: nowMs };
}

/**
 * Decides the wait after a transport error, or gives up once the budget since the
 * first failure is spent. No wait is scheduled past the budget. A successful poll
 * discards the state; the next failure calls startTransportErrors again.
 */
export function nextTransportStep(
  state: TransportErrorState,
  nowMs: number,
  random: RandomSource,
  budgetMs: number = TRANSPORT_BUDGET_MS
): TransportStep {
  const elapsed = nowMs - state.firstFailureAtMs;
  if (elapsed >= budgetMs) {
    return { giveUp: true };
  }
  const baseMs = grow(state.baseMs);
  const delayMs = Math.min(applyJitter(baseMs, random), budgetMs - elapsed);
  return { giveUp: false, delayMs, state: { ...state, baseMs } };
}

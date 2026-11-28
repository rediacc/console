/**
 * Credit arithmetic of reserve and commit (agent/plans/PLAN-console-ai-credits.md D5).
 *
 * `worstCaseCredits` is what a reservation holds before the call: the input
 * tokens estimated from the request body at one token per 3 bytes, plus the
 * clamped `max_tokens` as if all of it were produced. `actualCredits` is what
 * commit charges from the stream's final usage chunk. Both round up to a whole
 * credit, so a call never costs a fraction the ledger cannot hold, and the
 * worst case is never below the actual charge for usage within the estimate.
 */

import type { AiPriceRow } from './price-table.js';

/** Hard ceiling on `max_tokens` for any call through the Rediacc tier. */
export const MAX_TOKENS_CLAMP = 8192;

/** Bytes of request body counted as one input token in the worst case. */
export const BYTES_PER_INPUT_TOKEN = 3;

export interface TokenUsage {
  promptTokens: number;
  completionTokens: number;
}

function requireCount(value: number, name: string): void {
  if (!Number.isFinite(value) || value < 0) {
    throw new RangeError(`${name} must be a finite number of at least 0, got ${value}`);
  }
}

/** Input tokens estimated from the request body length in bytes. */
export function estimateInputTokens(bodyBytes: number): number {
  requireCount(bodyBytes, 'bodyBytes');
  return Math.ceil(bodyBytes / BYTES_PER_INPUT_TOKEN);
}

/**
 * The `max_tokens` a call is allowed: the request's own value capped at
 * MAX_TOKENS_CLAMP, or the cap when the request names none. A value below 1 is
 * refused rather than quietly raised, so the caller sees the bad request.
 */
export function clampMaxTokens(requested: number | undefined): number {
  if (requested === undefined) return MAX_TOKENS_CLAMP;
  if (!Number.isFinite(requested) || requested < 1) {
    throw new RangeError(`max_tokens must be a finite number of at least 1, got ${requested}`);
  }
  return Math.min(Math.floor(requested), MAX_TOKENS_CLAMP);
}

function credits(row: AiPriceRow, inTokens: number, outTokens: number): number {
  return Math.ceil(
    (inTokens * row.creditsPerMTokIn + outTokens * row.creditsPerMTokOut) / 1_000_000
  );
}

/** Credits a reservation holds: estimated input plus the clamped output, at the row's rates. */
export function worstCaseCredits(
  row: AiPriceRow,
  bodyBytes: number,
  requestedMaxTokens: number | undefined
): number {
  return credits(row, estimateInputTokens(bodyBytes), clampMaxTokens(requestedMaxTokens));
}

/** Credits charged for the usage the stream reported. */
export function actualCredits(row: AiPriceRow, usage: TokenUsage): number {
  requireCount(usage.promptTokens, 'promptTokens');
  requireCount(usage.completionTokens, 'completionTokens');
  return credits(row, usage.promptTokens, usage.completionTokens);
}

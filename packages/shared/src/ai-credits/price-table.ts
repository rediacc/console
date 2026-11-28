/**
 * Price table of the Rediacc AI tier (agent/plans/PLAN-console-ai-credits.md D2).
 *
 * One credit is worth 0.001 USD. Every row states the provider's list price per
 * million tokens next to the credit price charged, so a price change is a
 * reviewed edit of one constant that the ledger, the admin panel, the usage
 * page and the reconcile all read. `marginViolations` is the rule the unit test
 * applies to every row: credit value at least provider cost times the Unified
 * Billing fee (1.05) times the tier margin (1.15 standard, 1.30 premium).
 *
 * The provider prices are the list prices at the time PRICE_TABLE_VERSION was
 * set; moving either side of a row bumps the version, which rides in the
 * `cf-aig-metadata` of every call so the reconcile compares like with like.
 */

export const PRICE_TABLE_VERSION = 1;

/** USD value of one credit. */
export const CREDIT_USD = 0.001;

/** Fee Cloudflare Unified Billing adds on top of the provider's price. */
export const UNIFIED_BILLING_FEE = 1.05;

export type AiPriceTier = 'standard' | 'premium';

/** Margin over provider cost, fee excluded, per tier. */
export const TIER_MARGIN: Readonly<Record<AiPriceTier, number>> = {
  standard: 1.15,
  premium: 1.3,
};

export interface AiPriceRow {
  /** Model id exactly as the AI Gateway OpenAI-compatible endpoint takes it. */
  model: string;
  tier: AiPriceTier;
  providerUsdPerMTokIn: number;
  providerUsdPerMTokOut: number;
  creditsPerMTokIn: number;
  creditsPerMTokOut: number;
}

export const PRICE_TABLE: readonly AiPriceRow[] = [
  {
    model: 'workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast',
    tier: 'standard',
    providerUsdPerMTokIn: 0.293,
    providerUsdPerMTokOut: 2.253,
    creditsPerMTokIn: 360,
    creditsPerMTokOut: 2730,
  },
  {
    model: 'openai/gpt-5',
    tier: 'premium',
    providerUsdPerMTokIn: 1.25,
    providerUsdPerMTokOut: 10,
    creditsPerMTokIn: 1710,
    creditsPerMTokOut: 13700,
  },
  {
    model: 'anthropic/claude-sonnet-4-5',
    tier: 'premium',
    providerUsdPerMTokIn: 3,
    providerUsdPerMTokOut: 15,
    creditsPerMTokIn: 4100,
    creditsPerMTokOut: 20500,
  },
];

/** The row for a model, or undefined when the model is not sold. */
export function findPriceRow(
  model: string,
  table: readonly AiPriceRow[] = PRICE_TABLE
): AiPriceRow | undefined {
  return table.find((row) => row.model === model);
}

/** The minimum credits per million tokens a provider price must be charged at. */
export function minCreditsPerMTok(providerUsdPerMTok: number, tier: AiPriceTier): number {
  return (providerUsdPerMTok * UNIFIED_BILLING_FEE * TIER_MARGIN[tier]) / CREDIT_USD;
}

/** One margin failure: which row and which direction is priced below the floor. */
export interface MarginViolation {
  model: string;
  direction: 'in' | 'out';
  credits: number;
  minimum: number;
}

/** Every row direction whose credit price sits below the margin floor. */
export function marginViolations(table: readonly AiPriceRow[] = PRICE_TABLE): MarginViolation[] {
  const violations: MarginViolation[] = [];
  for (const row of table) {
    const checks: [MarginViolation['direction'], number, number][] = [
      ['in', row.creditsPerMTokIn, row.providerUsdPerMTokIn],
      ['out', row.creditsPerMTokOut, row.providerUsdPerMTokOut],
    ];
    for (const [direction, credits, providerUsd] of checks) {
      const minimum = minCreditsPerMTok(providerUsd, row.tier);
      if (credits < minimum) {
        violations.push({ model: row.model, direction, credits, minimum });
      }
    }
  }
  return violations;
}

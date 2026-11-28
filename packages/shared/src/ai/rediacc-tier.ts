/**
 * The Rediacc-provided AI tier of the loop host (AC6 of PLAN-console-ai-credits).
 *
 * An enterprise org chats without a key of its own through two built-in choices, `rediacc:standard`
 * (Workers AI open models) and `rediacc:premium` (Anthropic and OpenAI through Unified Billing). Both
 * resolve to a profile aimed at `http://ai.internal/compat`, the host the proxy intercepts inside the
 * executor container and meters against the org's credit ledger (workers/proxy/src/ai-egress.ts). The
 * profile carries no key: the container holds none and the egress adds the gateway token.
 *
 * The base URL guard refuses `.internal` hosts in customer profiles, so these profiles are built here,
 * never read from a config, and `resolveProfile` returns them without that guard.
 */
import { findPriceRow } from '../ai-credits/price-table.js';
import type { Profile } from './profile.js';

/** The host the proxy intercepts for the Rediacc tier. */
export const REDIACC_AI_HOST = 'ai.internal';

/** The base URL of the tier; the chat path is `/compat/chat/completions` under it. */
export const REDIACC_AI_BASE_URL = `http://${REDIACC_AI_HOST}/compat`;

export const REDIACC_TIERS = ['standard', 'premium'] as const;
export type RediaccTier = (typeof REDIACC_TIERS)[number];

/** The model each choice runs on; both rows must exist in the price table with the same tier. */
export const REDIACC_DEFAULT_MODELS: Readonly<Record<RediaccTier, string>> = {
  standard: 'workers-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast',
  premium: 'anthropic/claude-sonnet-4-5',
};

export const REDIACC_CHOICE_PREFIX = 'rediacc:';

/** The profile name that selects `tier`. */
export function rediaccChoice(tier: RediaccTier): string {
  return `${REDIACC_CHOICE_PREFIX}${tier}`;
}

/** The tier a profile name selects, or undefined when the name is not a Rediacc choice. */
export function parseRediaccChoice(name: string): RediaccTier | undefined {
  return REDIACC_TIERS.find((tier) => name === rediaccChoice(tier));
}

/** The keyless profile of `tier`, aimed at the metered intercept. */
export function buildRediaccProfile(tier: RediaccTier): Profile {
  const model = REDIACC_DEFAULT_MODELS[tier];
  if (findPriceRow(model)?.tier !== tier) {
    throw new Error(
      `rediacc ${tier} default model ${model} is not a ${tier} row of the price table`
    );
  }
  return {
    format: 'openai-chat',
    baseURL: REDIACC_AI_BASE_URL,
    authScheme: 'bearer',
    model,
    preset: 'rediacc',
    byokOnly: true,
    capabilities: { tools: true, streaming: true, parallelToolCalls: false, vision: false },
  };
}

/** Whether `profile` is one the tier builds: the metered base URL under the `rediacc` preset. */
export function isRediaccProfile(profile: Pick<Profile, 'baseURL' | 'preset'>): boolean {
  return profile.preset === 'rediacc' && profile.baseURL === REDIACC_AI_BASE_URL;
}

/** The ledger's reserve refusals (workers/account/src/credit-ledger.ts) and the egress's own refusals. */
export const CREDIT_REFUSAL_MESSAGES = {
  PLAN_NOT_ENTITLED: 'Rediacc AI credits need an enterprise plan.',
  ORG_BLOCKED: 'Rediacc AI is switched off for this organization.',
  GLOBAL_PAUSED: 'Rediacc AI is paused for every organization at the moment.',
  MODEL_NOT_ALLOWED: 'This model is not sold on the Rediacc tier.',
  INSUFFICIENT_CREDITS: 'The organization has too few AI credits left for this request.',
  DAILY_CAP: 'The organization reached its daily AI credit cap.',
  TOO_MANY_STREAMS: 'Too many AI responses are running at once for this organization.',
  CONVERSATION_TOKEN_CAP: 'This conversation reached its token cap. Start a new one.',
  LOOP_DEPTH: 'This conversation reached its call limit. Start a new one.',
  'route-not-allowed': 'The Rediacc AI endpoint refused this request path.',
  'ai-unconfigured': 'Rediacc AI is not configured in this region.',
  'body-too-large': 'The request is too large for the Rediacc AI endpoint.',
  'invalid-request': 'The Rediacc AI endpoint could not read this request.',
  'model-not-allowed': 'This model is not sold on the Rediacc tier.',
  'ledger-unavailable': 'The credit ledger did not answer, so no AI call was made.',
} as const;

export type CreditRefusalCode = keyof typeof CREDIT_REFUSAL_MESSAGES;

/** `code` as a refusal code, or undefined when the egress did not name a known one. */
export function asCreditRefusalCode(code: unknown): CreditRefusalCode | undefined {
  return typeof code === 'string' && Object.hasOwn(CREDIT_REFUSAL_MESSAGES, code)
    ? (code as CreditRefusalCode)
    : undefined;
}

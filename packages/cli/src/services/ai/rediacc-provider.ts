/**
 * Rediacc tier provider (AC6 of PLAN-console-ai-credits): an AI SDK model that chats through
 * `http://ai.internal/compat/chat/completions`, the metered intercept of the proxy Worker.
 *
 * The container holds no key, so no auth header is sent and any the SDK sets is removed. The request
 * goes only to the intercept host under its base URL, redirects are refused, and two identifier headers
 * name the user and conversation for the ledger's per-user and per-conversation caps; the org comes from
 * the proxy's own props and is never sent.
 *
 * A refusal the ledger or the egress answers before any gateway call (a body of
 * `{ code, error: { code, message } }`) becomes a {@link RediaccRefusalError}; {@link rediaccErrorEvent}
 * maps it to the `error` event of the stream, with a code the UI can name (`AI_CREDITS_<CODE>`). Any
 * other non-2xx answer is the gateway's and passes through untouched.
 */
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';
import {
  asCreditRefusalCode,
  CREDIT_REFUSAL_MESSAGES,
  type CreditRefusalCode,
  isRediaccProfile,
  type Profile,
  REDIACC_AI_BASE_URL,
} from '@rediacc/shared/ai';
import type { AiEvent } from '@rediacc/shared/cli-contract/wire';
import type { LanguageModel } from 'ai';

type FetchFunction = typeof globalThis.fetch;

/** Headers the proxy reads for the ledger's per-user and per-conversation caps (workers/proxy/src/ai-egress.ts). */
export const AI_USER_HEADER = 'x-rediacc-ai-user';
export const AI_CONVERSATION_HEADER = 'x-rediacc-ai-conversation';

/** Prefix of the `error` event code of a credit refusal; the refusal code follows. */
const AI_CREDITS_ERROR_PREFIX = 'AI_CREDITS_';

const ID_RE = /^[A-Za-z0-9_.:-]{1,128}$/;

export interface RediaccModelOptions {
  /** The user the call is made for; shape-checked, the proxy refuses a call without one. */
  userId: string;
  /** The conversation the call belongs to. */
  conversationId: string;
  /** The fetch the guarded requests go out through; `globalThis.fetch` when omitted. */
  fetch?: FetchFunction;
}

/** A call the ledger or the egress refused before any gateway request. */
export class RediaccRefusalError extends Error {
  readonly refusal: CreditRefusalCode;
  readonly statusCode: number;

  constructor(refusal: CreditRefusalCode, statusCode: number) {
    super(CREDIT_REFUSAL_MESSAGES[refusal]);
    this.name = 'RediaccRefusalError';
    this.refusal = refusal;
    this.statusCode = statusCode;
  }
}

/** The `error` event of a refusal, or undefined when `error` is not one. */
export function rediaccErrorEvent(error: unknown): AiEvent | undefined {
  if (!(error instanceof RediaccRefusalError)) return undefined;
  return {
    type: 'error',
    message: error.message,
    code: `${AI_CREDITS_ERROR_PREFIX}${error.refusal}`,
  };
}

function requestUrl(input: Parameters<FetchFunction>[0]): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  throw new TypeError('the Rediacc AI fetch takes a URL and an init, not a Request');
}

/** The refusal an answer carries, or undefined for a success or a gateway error. */
async function refusalOf(response: Response): Promise<RediaccRefusalError | undefined> {
  if (response.ok) return undefined;
  try {
    const body: unknown = await response.clone().json();
    const code = asCreditRefusalCode((body as { code?: unknown } | null)?.code);
    return code === undefined ? undefined : new RediaccRefusalError(code, response.status);
  } catch {
    return undefined;
  }
}

/** The fetch of the tier: intercept host only, no auth, the identifier headers, no redirects, refusals thrown. */
export function rediaccFetch(options: RediaccModelOptions): FetchFunction {
  if (!ID_RE.test(options.userId) || !ID_RE.test(options.conversationId)) {
    throw new TypeError(
      'the Rediacc AI tier needs a user id and a conversation id of 1-128 safe characters'
    );
  }
  const base = options.fetch ?? globalThis.fetch;
  const prefix = `${REDIACC_AI_BASE_URL}/`;
  return async (input, init) => {
    const url = requestUrl(input);
    if (!url.startsWith(prefix)) {
      throw new TypeError(`the Rediacc AI fetch only reaches ${REDIACC_AI_BASE_URL}`);
    }
    const headers = new Headers(init?.headers);
    headers.delete('authorization');
    headers.delete('x-api-key');
    headers.set(AI_USER_HEADER, options.userId);
    headers.set(AI_CONVERSATION_HEADER, options.conversationId);
    const response = await base(url, { ...init, headers, redirect: 'error' });
    const refusal = await refusalOf(response);
    if (refusal) throw refusal;
    return response;
  };
}

/** The AI SDK model of a Rediacc tier profile. */
export function createRediaccModel(profile: Profile, options: RediaccModelOptions): LanguageModel {
  if (!isRediaccProfile(profile)) {
    throw new TypeError('createRediaccModel takes a profile built by the Rediacc tier');
  }
  return createOpenAICompatible({
    name: 'rediacc',
    baseURL: REDIACC_AI_BASE_URL,
    includeUsage: true,
    fetch: rediaccFetch(options),
  }).chatModel(profile.model);
}

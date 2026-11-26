/**
 * Provider adapter (AP5 of PLAN-console-ai-providers): a customer AI profile
 * becomes an AI SDK language model.
 *
 * `anthropic-messages` profiles run on `@ai-sdk/anthropic`, `openai-chat`
 * profiles on `@ai-sdk/openai-compatible`, both aimed at the profile's
 * `baseURL`. The headers of every request are this module's alone: the auth
 * header the profile's `authScheme` names (`x-api-key: <key>` or
 * `Authorization: Bearer <key>`) plus the profile's own `headers`. Whatever the
 * SDK set for auth is removed first, so the Anthropic SDK's fallback to the
 * `ANTHROPIC_API_KEY` environment variable can never send the executor's key on
 * a `byokOnly` profile that carries none.
 *
 * The D5 base URL guard runs twice for a customer profile: on the profile when the model is built
 * (`validateProfile`), and on every request URL at call time, which must also
 * stay under the profile's `baseURL`. A Rediacc tier profile skips the build-time check (its
 * `ai.internal` host would fail it) and has only the call-time prefix check of rediacc-provider.ts.
 * Redirects are refused, so a provider answer cannot forward the key to another host.
 */
import { createAnthropic } from '@ai-sdk/anthropic';
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';
import {
  isRediaccProfile,
  type Profile,
  type ProfileIssue,
  validateBaseUrl,
  validateProfile,
} from '@rediacc/shared/ai';
import type { LanguageModel } from 'ai';
import { createRediaccModel } from './rediacc-provider.js';

type FetchFunction = typeof globalThis.fetch;

/** A profile the adapter refuses to build, or a request the call-time guard refuses to send. */
export class ProviderProfileError extends Error {
  readonly issues: ProfileIssue[];

  constructor(issues: ProfileIssue[]) {
    super(`AI provider profile refused: ${issues.map((i) => `${i.path} ${i.message}`).join('; ')}`);
    this.name = 'ProviderProfileError';
    this.issues = issues;
  }
}

export interface ProviderModelOptions {
  /**
   * The fetch the guarded requests go out through; `globalThis.fetch` when
   * omitted. Tests pass one that reaches a local mock server, after the guard
   * has checked the profile's real URL.
   */
  fetch?: FetchFunction;
  /**
   * Who a Rediacc tier call is for (`rediacc:standard` and `rediacc:premium` profiles): the ledger's
   * per-user and per-conversation caps key on these. Required to build a profile of that tier.
   */
  rediacc?: { userId: string; conversationId: string };
}

/** The provider name the OpenAI-compatible SDK reports when a profile names no preset. */
const OPENAI_COMPATIBLE_PROVIDER_NAME = 'openai-compatible';

/**
 * Placeholder handed to the Anthropic SDK so it never reads `ANTHROPIC_API_KEY`
 * from the environment. The guarded fetch strips the header it lands in before
 * any request leaves.
 */
const SDK_KEY_PLACEHOLDER = 'rediacc-profile-auth';

const AUTH_HEADER_NAMES = ['x-api-key', 'authorization'] as const;

/** The auth header of a profile: none on a `byokOnly` profile without a key. */
function authHeaders(profile: Profile): Record<string, string> {
  if (profile.key === undefined) return {};
  return profile.authScheme === 'x-api-key'
    ? { 'x-api-key': profile.key }
    : { authorization: `Bearer ${profile.key}` };
}

/** Every header a request of this profile carries, refusing a profile header that collides with its auth header. */
function profileHeaders(profile: Profile): Record<string, string> {
  const auth = authHeaders(profile);
  const extra = profile.headers ?? {};
  const authNames = new Set(Object.keys(auth));
  const clash = Object.keys(extra).find((name) => authNames.has(name.toLowerCase()));
  if (clash !== undefined) {
    throw new ProviderProfileError([
      {
        path: `/headers/${clash}`,
        message: `header ${clash} collides with the ${profile.authScheme} auth header the key sets`,
      },
    ]);
  }
  return { ...auth, ...extra };
}

/** `base` with exactly one trailing slash, for the prefix check. */
function asPrefix(base: string): string {
  return base.endsWith('/') ? base : `${base}/`;
}

/**
 * The URL of a request. The SDKs call fetch with a URL and an init; a Request
 * object would carry its method and body where the guard does not forward
 * them, so it is refused rather than sent without them.
 */
function requestUrl(input: Parameters<FetchFunction>[0]): string {
  if (typeof input === 'string') return input;
  if (input instanceof URL) return input.href;
  throw new TypeError('the guarded AI provider fetch takes a URL and an init, not a Request');
}

/** Why the call-time guard refuses `url`, or null when it may go out. */
function refusalOf(url: string, prefix: string): ProviderProfileError | null {
  const check = validateBaseUrl(url);
  if (!check.ok) {
    return new ProviderProfileError([
      { path: '/baseURL', message: check.message, refusal: check.reason },
    ]);
  }
  if (!check.url.href.startsWith(prefix)) {
    return new ProviderProfileError([
      {
        path: '/baseURL',
        message: `request URL ${check.url.origin} is outside the profile's baseURL`,
      },
    ]);
  }
  return null;
}

/** The request's headers with the SDK's auth headers replaced by the profile's. */
function outgoingHeaders(init: RequestInit | undefined, headers: Record<string, string>): Headers {
  const outgoing = new Headers(init?.headers);
  for (const name of AUTH_HEADER_NAMES) outgoing.delete(name);
  for (const [name, value] of Object.entries(headers)) outgoing.set(name, value);
  return outgoing;
}

/**
 * The fetch every SDK request of `profile` goes through: the call-time D5 guard
 * on the request URL, the request kept under the profile's base URL, the SDK's
 * auth headers replaced by the profile's, and redirects refused.
 */
export function guardedFetch(
  profile: Profile,
  base: FetchFunction = globalThis.fetch
): FetchFunction {
  const headers = profileHeaders(profile);
  const prefix = asPrefix(new URL(profile.baseURL).href);
  return async (input, init) => {
    const url = requestUrl(input);
    const refusal = refusalOf(url, prefix);
    if (refusal) throw refusal;
    return await base(url, {
      ...init,
      headers: outgoingHeaders(init, headers),
      redirect: 'error',
    });
  };
}

/**
 * Build the AI SDK model of `profile`; a Rediacc tier profile goes to rediacc-provider.ts, which
 * skips the customer base URL guard its `ai.internal` host would fail. Throws ProviderProfileError when the
 * profile fails its shape check or the base URL guard, and a TypeError when a Rediacc tier's user or
 * conversation id is not 1-128 safe characters.
 */
export function createProviderModel(
  profile: Profile,
  options: ProviderModelOptions = {}
): LanguageModel {
  if (isRediaccProfile(profile)) {
    if (options.rediacc === undefined) {
      throw new ProviderProfileError([
        { path: '/preset', message: 'a Rediacc tier profile needs the user and conversation ids' },
      ]);
    }
    return createRediaccModel(profile, {
      ...options.rediacc,
      ...(options.fetch ? { fetch: options.fetch } : {}),
    });
  }
  const checked = validateProfile(profile);
  if (!checked.ok) throw new ProviderProfileError(checked.issues);
  const valid = checked.profile;
  const fetch = guardedFetch(valid, options.fetch);

  if (valid.format === 'anthropic-messages') {
    return createAnthropic({ baseURL: valid.baseURL, apiKey: SDK_KEY_PLACEHOLDER, fetch })(
      valid.model
    );
  }
  return createOpenAICompatible({
    name: valid.preset ?? OPENAI_COMPATIBLE_PROVIDER_NAME,
    baseURL: valid.baseURL,
    includeUsage: true,
    fetch,
  }).chatModel(valid.model);
}

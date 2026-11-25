/**
 * Confirmation state (agent/plans/PLAN-rmcp-remote-worker.md Design 6, D21).
 *
 * When the executor answers `NEEDS_CONFIRMATION` and the client declared elicitation, the Worker returns an `input_required` result whose `requestState` is sealed here: AES-256-GCM under a key derived from the Worker secret `CONFIRM_KEY`, carrying `{grantId, userId, tool, argsHash, nonce, exp}` with a two-minute life. The client echoes the state on the retry, where it is opened and refused when it is tampered with, expired, bound to another grant, user or tool, minted for other arguments, or already used. The nonce is burned through the grant's rate limiter (src/rate.ts), so one state is accepted once however many isolates see it.
 */
import type { RateLimiter } from './rate.js';

/** How long a sealed state is accepted. */
export const CONFIRM_TTL_MS = 120_000;

/** What a state is bound to: the retry must present the same grant, user, tool and arguments. */
export interface ConfirmBinding {
  grantId: string;
  userId: string;
  tool: string;
  argsHash: string;
}

interface Payload extends ConfirmBinding {
  nonce: string;
  exp: number;
  /** The value the executor named for its `confirm` argument; the retry sends it back. */
  confirmValue?: string;
}

export type OpenedState = { ok: true; confirmValue?: string } | { ok: false; reason: string };

export interface Confirmation {
  seal(binding: ConfirmBinding, confirmValue?: string): Promise<string>;
  open(state: string, binding: ConfirmBinding, limiter: RateLimiter): Promise<OpenedState>;
}

function toBase64Url(bytes: Uint8Array): string {
  let text = '';
  for (const b of bytes) text += String.fromCharCode(b);
  return btoa(text).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
}

function fromBase64Url(text: string): Uint8Array {
  const padded = text
    .replaceAll('-', '+')
    .replaceAll('_', '/')
    .padEnd(Math.ceil(text.length / 4) * 4, '=');
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (typeof value === 'object' && value !== null) {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== undefined)
      .sort(([a], [b]) => a.localeCompare(b, 'en'));
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

/** SHA-256 of the arguments in a canonical form, without `confirm`: the retry adds that argument and must still match. */
export async function hashArgs(args: Record<string, unknown>): Promise<string> {
  const { confirm: _confirm, ...rest } = args;
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical(rest)));
  return toBase64Url(new Uint8Array(digest));
}

/** The payload `state` seals, or undefined for anything the key did not seal. */
async function unseal(key: CryptoKey, state: string): Promise<Payload | undefined> {
  try {
    const raw = fromBase64Url(state);
    const plain = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: raw.slice(0, 12) },
      key,
      raw.slice(12)
    );
    return JSON.parse(new TextDecoder().decode(plain)) as Payload;
  } catch {
    return undefined;
  }
}

/** Why an opened payload does not fit this call, or undefined when it does. */
function refusalOf(payload: Payload, binding: ConfirmBinding, at: number): string | undefined {
  if (typeof payload.exp !== 'number' || payload.exp <= at) return 'expired';
  if (payload.grantId !== binding.grantId) return 'other-grant';
  if (payload.userId !== binding.userId) return 'other-user';
  if (payload.tool !== binding.tool) return 'other-tool';
  if (payload.argsHash !== binding.argsHash) return 'arguments-changed';
  return undefined;
}

export function createConfirmation(options: {
  /** The Worker secret `CONFIRM_KEY`. */
  key: string;
  now?: () => number;
}): Confirmation {
  const now = options.now ?? Date.now;
  const keyPromise = crypto.subtle
    .digest('SHA-256', new TextEncoder().encode(`rediacc-mcp-confirm-v1:${options.key}`))
    .then((raw) => crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['encrypt', 'decrypt']));

  return {
    async seal(binding, confirmValue) {
      const payload: Payload = {
        ...binding,
        nonce: toBase64Url(crypto.getRandomValues(new Uint8Array(16))),
        exp: now() + CONFIRM_TTL_MS,
        ...(confirmValue === undefined ? {} : { confirmValue }),
      };
      const iv = crypto.getRandomValues(new Uint8Array(12));
      const sealed = await crypto.subtle.encrypt(
        { name: 'AES-GCM', iv },
        await keyPromise,
        new TextEncoder().encode(JSON.stringify(payload))
      );
      const out = new Uint8Array(iv.length + sealed.byteLength);
      out.set(iv);
      out.set(new Uint8Array(sealed), iv.length);
      return toBase64Url(out);
    },

    async open(state, binding, limiter) {
      const payload = await unseal(await keyPromise, state);
      if (!payload) return { ok: false, reason: 'tampered' };
      const refusal = refusalOf(payload, binding, now());
      if (refusal) return { ok: false, reason: refusal };
      if (!(await limiter.burn(binding.grantId, payload.nonce, payload.exp))) {
        return { ok: false, reason: 'replayed' };
      }
      return {
        ok: true,
        ...(payload.confirmValue === undefined ? {} : { confirmValue: payload.confirmValue }),
      };
    },
  };
}

/**
 * Agent grants: a split secret that hands one config's content key to an MCP agent
 * (PLAN-rmcp-agent-grants.md Design 1, D9, D56).
 *
 * The browser draws `S` (32 random bytes) and shows it once as the bearer `rmcp_<grantId>.<base64url(S)>`.
 *
 *   authTag  = HMAC-SHA256(S, "rediacc-agent-grant-auth-v1")          the account server stores SHA-256(authTag) only
 *   K        = HKDF-SHA256(S, salt = grantId, info = "rediacc-agent-grant-wrap-v1")
 *   slot key = HKDF-SHA256(K || serverSecret, salt = grantId,
 *                info = "rediacc-agent-grant-slot-v1|" grantId "|" storeId "|" cekGeneration "|" configId)
 *
 * What the slot key wraps is the config's own content key (config-key.ts), never the org CEK, with the
 * existing AES-GCM wrap. The AAD of that wrap pins it to its grant, store, config, team, content-key version
 * and CEK generation, so a wrap moved to another grant or config, relabelled, or carried past a CEK rotation
 * does not open. Neither half alone opens it: the account server holds `serverSecret` and the tag hash, the
 * agent holds `S`, and the executor derives the slot key only while it holds both.
 *
 * The same slot key also wraps the grant's policy keys (policy-record.ts `derivePolicyKey`, AG-P1): the policy
 * key of the grant's own config and the one of the org-level config, so the executor opens exactly the two
 * policy records its human would read and never the CEK. That wrap's AAD carries its own label
 * (`rediacc-agent-grant-policy-key-v1`) and names the policy record's pointer beside the grant's config, so a
 * content-key wrap presented as a policy-key wrap, or the reverse, or one pointer's wrap presented for another,
 * does not open.
 *
 * The account server imports only `parseAgentBearer` and `hashAuthTag`; it never calls the wrap or the unwrap.
 */

import {
  aesDecryptFromString,
  aesEncryptToString,
  exportAesKey,
  randomBytes,
  toBase64,
} from './aes.js';
import { canonicalize } from './canonical.js';
import { ConfigIntegrityError } from './errors.js';
import type { PolicyKey } from './policy-record.js';

/** Length in bytes of the agent secret `S`, of `authTag`, of `K` and of the slot key. */
export const AGENT_GRANT_SECRET_BYTES = 32;

/** Prefix of the bearer form. */
export const AGENT_BEARER_PREFIX = 'rmcp_';

/** Domain-separation strings of the three derivations and of the wrap AAD. */
export const AGENT_GRANT_INFO = {
  AUTH: 'rediacc-agent-grant-auth-v1',
  WRAP: 'rediacc-agent-grant-wrap-v1',
  SLOT: 'rediacc-agent-grant-slot-v1',
  WRAP_AAD: 'rediacc-agent-grant-key-v1',
  POLICY_WRAP_AAD: 'rediacc-agent-grant-policy-key-v1',
} as const;

/** A grant id: the region prefix and the id, letters, digits, `_` and `-` only (no `.`, which ends it in the bearer). */
const GRANT_ID_RE = /^[A-Za-z0-9_-]{1,128}$/;
const BASE64URL_RE = /^[A-Za-z0-9_-]+$/;

const utf8 = (text: string): Uint8Array => new TextEncoder().encode(text);

/** Extract ArrayBuffer from Uint8Array for Web Crypto API compatibility. */
function buf(data: Uint8Array): ArrayBuffer {
  if (data.byteOffset === 0 && data.byteLength === data.buffer.byteLength) {
    return data.buffer as ArrayBuffer;
  }
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength) as ArrayBuffer;
}

function concat(a: Uint8Array, b: Uint8Array): Uint8Array {
  const out = new Uint8Array(a.byteLength + b.byteLength);
  out.set(a, 0);
  out.set(b, a.byteLength);
  return out;
}

function toBase64Url(bytes: Uint8Array): string {
  return toBase64(bytes).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}

/** Strict base64url (no padding) decode; null when the text is not canonical base64url. */
function fromBase64Url(text: string): Uint8Array | null {
  if (!BASE64URL_RE.test(text) || text.length % 4 === 1) return null;
  const b64 = text.replaceAll('-', '+').replaceAll('_', '/');
  const bytes = Uint8Array.from(atob(b64 + '='.repeat((4 - (b64.length % 4)) % 4)), (c) =>
    c.charCodeAt(0)
  );
  // Non-canonical trailing bits decode to the same bytes as another text; refuse them.
  return toBase64Url(bytes) === text ? bytes : null;
}

function assertSecret(name: string, value: Uint8Array): void {
  if (!(value instanceof Uint8Array) || value.byteLength !== AGENT_GRANT_SECRET_BYTES) {
    throw new Error(`${name} must be ${AGENT_GRANT_SECRET_BYTES} bytes`);
  }
}

function assertGrantId(grantId: string): void {
  if (typeof grantId !== 'string' || !GRANT_ID_RE.test(grantId)) {
    throw new Error('grantId must be 1-128 characters of [A-Za-z0-9_-]');
  }
}

function assertInteger(name: string, value: number, min: number): void {
  if (!Number.isInteger(value) || value < min) {
    throw new Error(`${name} must be an integer >= ${min} (got ${value})`);
  }
}

/**
 * HKDF-SHA256 (RFC 5869) over byte strings, `length` bytes of output. The derivations below go through
 * this one helper, which the tests pin to RFC 5869 test case 1.
 */
export async function agentGrantHkdf(
  ikm: Uint8Array,
  salt: Uint8Array,
  info: Uint8Array,
  length: number
): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey('raw', buf(ikm), 'HKDF', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits(
    { name: 'HKDF', hash: 'SHA-256', salt: buf(salt), info: buf(info) },
    key,
    length * 8
  );
  return new Uint8Array(bits);
}

/** What a grant's wrapped content key is bound to. */
export interface AgentGrantBinding {
  grantId: string;
  storeId: string;
  configId: string;
  /** The config's team, or null/absent for the org-level config. */
  teamId?: string | null;
  /** The wrapped content key's version (config-key.ts `ConfigKeyBinding.configKeyVersion`). */
  configKeyVersion: number;
  /** The store's CEK generation the grant was made under. */
  cekGeneration: number;
}

/**
 * What a grant's wrapped policy key is bound to. `grantId`, `storeId`, `configId` and `cekGeneration` name the
 * grant (they derive the slot key); `policyConfigId` and `policyTeamId` name the policy record whose key is
 * wrapped: the grant's own config, or the store's org-level config (team null).
 */
export interface AgentGrantPolicyKeyBinding {
  grantId: string;
  storeId: string;
  /** The grant's config (the slot key's). */
  configId: string;
  /** The store's CEK generation the grant was made under, which the policy key is derived for too. */
  cekGeneration: number;
  /** The config whose policy record the wrapped key opens. */
  policyConfigId: string;
  /** That config's team, or null/absent for the org-level config. */
  policyTeamId?: string | null;
}

/** A parsed bearer. */
export interface AgentBearer {
  grantId: string;
  secret: Uint8Array;
}

/** Draw a fresh agent secret `S` (32 random bytes). */
export function newAgentGrantSecret(): Uint8Array {
  return randomBytes(AGENT_GRANT_SECRET_BYTES);
}

/** The bearer form `rmcp_<grantId>.<base64url(S)>`. */
export function formatAgentBearer(grantId: string, secret: Uint8Array): string {
  assertGrantId(grantId);
  assertSecret('secret', secret);
  return `${AGENT_BEARER_PREFIX}${grantId}.${toBase64Url(secret)}`;
}

/**
 * Parse a bearer. Returns null for anything that is not exactly `rmcp_<grantId>.<base64url of 32 bytes>`:
 * a wrong prefix, an empty or malformed grant id, an empty secret, a body that is not canonical base64url,
 * or a secret of the wrong length.
 */
export function parseAgentBearer(bearer: string): AgentBearer | null {
  if (typeof bearer !== 'string' || !bearer.startsWith(AGENT_BEARER_PREFIX)) return null;
  const rest = bearer.slice(AGENT_BEARER_PREFIX.length);
  const dot = rest.indexOf('.');
  if (dot < 0) return null;
  const grantId = rest.slice(0, dot);
  const body = rest.slice(dot + 1);
  if (!GRANT_ID_RE.test(grantId) || body.length === 0) return null;
  const secret = fromBase64Url(body);
  if (!secret || secret.byteLength !== AGENT_GRANT_SECRET_BYTES) return null;
  return { grantId, secret };
}

/** `authTag = HMAC-SHA256(S, "rediacc-agent-grant-auth-v1")`, as base64url (43 characters). */
export async function deriveAuthTag(secret: Uint8Array): Promise<string> {
  assertSecret('secret', secret);
  const key = await crypto.subtle.importKey(
    'raw',
    buf(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const tag = await crypto.subtle.sign('HMAC', key, buf(utf8(AGENT_GRANT_INFO.AUTH)));
  return toBase64Url(new Uint8Array(tag));
}

/**
 * What the account server stores and compares: base64url of SHA-256 over the 32 raw bytes of `authTag`.
 * Rejects, as an async function does, on a tag that is not base64url of 32 bytes, so a malformed request never reaches the lookup; a caller awaits the call inside its try.
 */
export async function hashAuthTag(authTag: string): Promise<string> {
  const raw = typeof authTag === 'string' ? fromBase64Url(authTag) : null;
  if (!raw || raw.byteLength !== AGENT_GRANT_SECRET_BYTES) {
    throw new Error('authTag must be base64url of 32 bytes');
  }
  return toBase64Url(new Uint8Array(await crypto.subtle.digest('SHA-256', buf(raw))));
}

/** `K = HKDF-SHA256(S, salt = grantId, info = "rediacc-agent-grant-wrap-v1")`, 32 raw bytes. */
export function deriveAgentGrantKey(secret: Uint8Array, grantId: string): Promise<Uint8Array> {
  assertSecret('secret', secret);
  assertGrantId(grantId);
  return agentGrantHkdf(
    secret,
    utf8(grantId),
    utf8(AGENT_GRANT_INFO.WRAP),
    AGENT_GRANT_SECRET_BYTES
  );
}

/** The HKDF info of the slot key (see the header). */
export function agentGrantSlotInfo(
  binding: Pick<AgentGrantBinding, 'grantId' | 'storeId' | 'configId' | 'cekGeneration'>
): string {
  assertGrantId(binding.grantId);
  assertInteger('cekGeneration', binding.cekGeneration, 0);
  return [
    AGENT_GRANT_INFO.SLOT,
    binding.grantId,
    binding.storeId,
    String(binding.cekGeneration),
    binding.configId,
  ].join('|');
}

/** The slot key's 32 raw bytes, from `K` and `serverSecret` (see the header). */
export function deriveAgentGrantSlotKeyRaw(
  grantKey: Uint8Array,
  serverSecret: Uint8Array,
  binding: Pick<AgentGrantBinding, 'grantId' | 'storeId' | 'configId' | 'cekGeneration'>
): Promise<Uint8Array> {
  assertSecret('K', grantKey);
  assertSecret('serverSecret', serverSecret);
  return agentGrantHkdf(
    concat(grantKey, serverSecret),
    utf8(binding.grantId),
    utf8(agentGrantSlotInfo(binding)),
    AGENT_GRANT_SECRET_BYTES
  );
}

/** The additional authenticated data of a grant's content-key wrap. */
export function agentGrantWrapAad(binding: AgentGrantBinding): Uint8Array {
  assertGrantId(binding.grantId);
  assertInteger('configKeyVersion', binding.configKeyVersion, 1);
  assertInteger('cekGeneration', binding.cekGeneration, 0);
  const body = canonicalize({
    grantId: binding.grantId,
    storeId: binding.storeId,
    configId: binding.configId,
    teamId: binding.teamId ?? null,
    configKeyVersion: binding.configKeyVersion,
    cekGeneration: binding.cekGeneration,
  });
  return concat(utf8(`${AGENT_GRANT_INFO.WRAP_AAD}\0`), body);
}

/** The additional authenticated data of a grant's policy-key wrap (a label distinct from the content-key wrap). */
export function agentGrantPolicyWrapAad(binding: AgentGrantPolicyKeyBinding): Uint8Array {
  assertGrantId(binding.grantId);
  assertInteger('cekGeneration', binding.cekGeneration, 0);
  const body = canonicalize({
    grantId: binding.grantId,
    storeId: binding.storeId,
    configId: binding.configId,
    policyConfigId: binding.policyConfigId,
    policyTeamId: binding.policyTeamId ?? null,
    cekGeneration: binding.cekGeneration,
  });
  return concat(utf8(`${AGENT_GRANT_INFO.POLICY_WRAP_AAD}\0`), body);
}

async function slotKey(
  secret: Uint8Array,
  serverSecret: Uint8Array,
  binding: Pick<AgentGrantBinding, 'grantId' | 'storeId' | 'configId' | 'cekGeneration'>,
  usage: 'encrypt' | 'decrypt'
): Promise<CryptoKey> {
  const raw = await deriveAgentGrantSlotKeyRaw(
    await deriveAgentGrantKey(secret, binding.grantId),
    serverSecret,
    binding
  );
  return crypto.subtle.importKey('raw', buf(raw), { name: 'AES-GCM', length: 256 }, false, [usage]);
}

/**
 * Wrap a config's content key for a grant. Runs in the browser, which holds `S`, `serverSecret` (from the
 * config session) and the content key it unwrapped with the CEK. Returns base64(iv + ciphertext).
 */
export async function wrapConfigKeyForAgentGrant(
  configKey: CryptoKey,
  secret: Uint8Array,
  serverSecret: Uint8Array,
  binding: AgentGrantBinding
): Promise<string> {
  const key = await slotKey(secret, serverSecret, binding, 'encrypt');
  return aesEncryptToString(key, await exportAesKey(configKey), agentGrantWrapAad(binding));
}

/**
 * Unwrap a grant's content key into a NON-extractable AES-GCM key. Runs in the executor, which holds `S`
 * for the request and the `agent-session` answer (`serverSecret`, the wrap and its binding).
 *
 * @throws Error when `S` or `serverSecret` is not 32 bytes.
 * @throws ConfigIntegrityError when the wrap does not open under this grant's slot key and binding.
 */
export async function unwrapConfigKeyForAgentGrant(
  wrappedConfigKey: string,
  secret: Uint8Array,
  serverSecret: Uint8Array,
  binding: AgentGrantBinding
): Promise<CryptoKey> {
  const key = await slotKey(secret, serverSecret, binding, 'decrypt');
  let raw: Uint8Array;
  try {
    raw = await aesDecryptFromString(key, wrappedConfigKey, agentGrantWrapAad(binding));
  } catch {
    throw new ConfigIntegrityError(
      'Agent grant key integrity check failed: the wrapped content key was not sealed for this grant, config and CEK generation.'
    );
  }
  try {
    return await crypto.subtle.importKey('raw', buf(raw), { name: 'AES-GCM', length: 256 }, false, [
      'encrypt',
      'decrypt',
    ]);
  } finally {
    raw.fill(0);
  }
}

/**
 * Wrap a policy key (policy-record.ts `derivePolicyKey`) for a grant. Runs in the browser, which holds `S`,
 * `serverSecret` and the CEK the policy key was derived from. Returns base64(iv + ciphertext).
 */
export async function wrapPolicyKeyForAgentGrant(
  policyKey: PolicyKey,
  secret: Uint8Array,
  serverSecret: Uint8Array,
  binding: AgentGrantPolicyKeyBinding
): Promise<string> {
  const aad = agentGrantPolicyWrapAad(binding);
  const key = await slotKey(secret, serverSecret, binding, 'encrypt');
  const raw = await exportAesKey(policyKey.key);
  try {
    return await aesEncryptToString(key, raw, aad);
  } finally {
    raw.fill(0);
  }
}

/**
 * Unwrap a grant's policy key into a NON-extractable, decrypt-only key that `decryptPolicyRecord` accepts in
 * place of the CEK. Runs in the executor.
 *
 * @throws Error when `S` or `serverSecret` is not 32 bytes.
 * @throws ConfigIntegrityError when the wrap does not open under this grant's slot key and binding.
 */
export async function unwrapPolicyKeyForAgentGrant(
  wrappedPolicyKey: string,
  secret: Uint8Array,
  serverSecret: Uint8Array,
  binding: AgentGrantPolicyKeyBinding
): Promise<PolicyKey> {
  const aad = agentGrantPolicyWrapAad(binding);
  const key = await slotKey(secret, serverSecret, binding, 'decrypt');
  let raw: Uint8Array;
  try {
    raw = await aesDecryptFromString(key, wrappedPolicyKey, aad);
  } catch {
    throw new ConfigIntegrityError(
      'Agent grant policy key integrity check failed: the wrapped policy key was not sealed for this grant, policy record and CEK generation.'
    );
  }
  try {
    return {
      kind: 'policy-key',
      key: await crypto.subtle.importKey('raw', buf(raw), { name: 'AES-GCM', length: 256 }, false, [
        'decrypt',
      ]),
    };
  } finally {
    raw.fill(0);
  }
}

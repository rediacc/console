/**
 * Host-side SHA-256 fingerprints over config values.
 *
 * These three helpers stayed behind when the rest of the schema machinery moved
 * to `@rediacc/shared/config-schema`, for one reason: they must be
 * SYNCHRONOUS. Web Crypto only exposes an async digest, and making these async
 * would turn `evaluateMutations` (the single chokepoint every config mutation
 * flows through) and `redactClone` (a pure tree clone) into async functions for
 * no gain. Both consumers run on a host with node:crypto available: CLI
 * redaction output and the MutationGate knowledge check. The web console never
 * calls them, since it holds the CEK and edits real values.
 *
 * Fingerprints produced here are UNKEYED SHA-256, safe for UX stubs like
 * `<redacted:sha256:abc12345>` because SHA-256 preimage resistance holds.
 * The server-side FCK-keyed HMAC commitments live in
 * `packages/shared/src/config-crypto/commitments.ts`; do not conflate.
 */

import { createHash } from 'node:crypto';
import {
  canonicalJson,
  deepClone,
  getByPointer,
  setByPointer,
  walkSensitive,
} from '@rediacc/shared/config-schema';

/**
 * Short fingerprint used in redaction stubs (`<redacted:sha256:abc12345>`).
 *
 * Uses the first 8 hex chars of SHA-256 over the canonical JSON of the value.
 * `null` and missing values produce distinct fingerprints so redaction stubs
 * don't collide across those two states.
 */
export function shortFingerprint(value: unknown): string {
  const json = canonicalJson(value);
  const hash = createHash('sha256').update(json).digest('hex');
  return hash.slice(0, 8);
}

/**
 * Full SHA-256 digest of the value at a specific pointer. Returns undefined if
 * the pointer does not exist in the config.
 *
 * Used by MutationGate for the client-side knowledge check: the `--current`
 * value the agent supplied is canonicalized and hashed, then compared against
 * the digest of the currently-stored value at that pointer. Comparison is
 * constant-time irrelevant here since both sides originate on the same host.
 */
export function digestForPointer(root: unknown, pointer: string): string | undefined {
  const value = getByPointer(root, pointer);
  if (value === undefined) return undefined;
  return createHash('sha256').update(canonicalJson(value)).digest('hex');
}

/**
 * Produce a deep-cloned config with every sensitive leaf replaced by its
 * redaction stub. Public fields are passed through unchanged. Unregistered
 * leaves are passed through (fail-open for display); the CI gate
 * check:ci-schema-coverage catches missing annotations before they ship.
 */
export function redactClone<T>(config: T): T {
  let result: unknown = deepClone(config);
  for (const { pointer, value, meta } of walkSensitive(config)) {
    if (meta.kind === 'public') continue;
    const stub =
      value === null || value === undefined
        ? null
        : `${meta.redactAs ?? `<redacted:${meta.kind}>`}:${shortFingerprint(value)}`;
    result = setByPointer(result, pointer, stub);
  }
  return result as T;
}

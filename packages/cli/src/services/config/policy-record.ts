/**
 * The CLI read path of the policy record (agent/plans/PLAN-rmcp-policy-record.md Design 5).
 *
 * A remote config's authorization policy is not part of the config document: it is its own record,
 * sealed under the store CEK (packages/shared/src/config-crypto/policy-record.ts), served beside the
 * config on every pull (`policy: {version, cekGeneration, blob} | null`) and on
 * `GET /configs/:id/policy`. The effective policy of a config is the org policy (the record of the
 * org-level config) as a ceiling, narrowed by the team policy (the record of the team's config):
 * `mergePolicies` in packages/shared/src/policy/merge.ts.
 *
 * ROLLBACK GUARD. A record's version is authenticated by its AAD, so a reader that has seen version
 * N of a record refuses any lower version: a server replaying an older, wider policy is caught. The
 * CLI keeps the high-water marks in its token file (`SyncRecord.policyHighWater`), the executor in
 * RAM for the life of its container.
 *
 * KEYS. A CEK holder opens every record (the per-pointer policy key is derived from the CEK on the
 * spot). An agent grant holds no CEK: it carries one derived policy key per pointer it may read (its
 * own config's and the org-level config's, agent-grant.ts), so its reader passes a resolver that
 * answers the key of the pointer asked for and refuses any other.
 *
 * A LOCAL-file config (no `remote` block) keeps its own `policy` field as a ceiling (D24): it has no
 * record to read, and `localPolicyCeiling` turns the field into the same effective shape.
 *
 * Nothing here consults `config.policy` of a remote config: the schema refuses the field there, and
 * an executor or CLI that read it would let any member with write access rewrite the policy.
 */

import {
  decryptPolicyRecord,
  type PolicyKey,
  type PolicyRecord,
} from '@rediacc/shared/config-crypto';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import {
  type EffectivePolicy,
  mergePolicies,
  type PolicyDocument,
  PolicyDocumentSchema,
} from '@rediacc/shared/policy';

/** Where one policy record lives: its store, config and team (null for the org-level config). */
export interface PolicyPointer {
  storeId: string;
  configId: string;
  teamId: string | null;
}

/** A pulled record older than one this reader already opened. */
export class PolicyRollbackError extends Error {
  constructor(
    readonly pointer: PolicyPointer,
    readonly version: number,
    readonly highWater: number
  ) {
    super(
      `The policy record of config ${pointer.configId}${pointer.teamId ? ` (team ${pointer.teamId})` : ''} came back at version ${version}, older than version ${highWater} already read. The server served a stale policy; refusing it.`
    );
    this.name = 'PolicyRollbackError';
  }
}

/** A record that opened but does not hold a well-formed policy document. */
export class PolicyRecordInvalidError extends Error {
  constructor(pointer: PolicyPointer, details: string) {
    super(
      `The policy record of config ${pointer.configId} is not a valid policy document, so nothing can be authorized against it. Fix it in the console under Permissions. Details: ${details}`
    );
    this.name = 'PolicyRecordInvalidError';
  }
}

/**
 * The key that opens one pointer's records: the CEK itself, or the policy key derived for that
 * pointer (an agent grant's). A resolver that has no key for the pointer throws.
 */
type PolicyKeyResolver = (pointer: PolicyPointer) => Promise<CryptoKey | PolicyKey>;

/** The key a pointer's high-water mark is kept under. */
export function policyPointerKey(pointer: PolicyPointer): string {
  return `${pointer.storeId}/${pointer.configId}/${pointer.teamId ?? ''}`;
}

/**
 * The `policy` field of a pull response or the body of `GET /configs/:id/policy`: a record, or null
 * when none is saved. Any other shape is a protocol error, never read as "no policy".
 */
export function parsePolicyRecordField(raw: unknown): PolicyRecord | null {
  if (raw === null) return null;
  if (raw !== undefined && typeof raw === 'object') {
    const { version, cekGeneration, blob } = raw as Record<string, unknown>;
    if (
      Number.isInteger(version) &&
      (version as number) >= 1 &&
      Number.isInteger(cekGeneration) &&
      (cekGeneration as number) >= 0 &&
      typeof blob === 'string' &&
      blob.length > 0
    ) {
      return { version: version as number, cekGeneration: cekGeneration as number, blob };
    }
  }
  throw new Error(
    `The server answered a malformed policy record (expected {version, cekGeneration, blob} or null, got ${raw === undefined ? 'nothing' : JSON.stringify(raw).slice(0, 120)}).`
  );
}

/**
 * High-water marks of the records a reader has opened, by `policyPointerKey`. `get` reads a mark and
 * `raise` records a newer one; `openPolicyRecord` refuses a version below the mark. The store behind
 * it decides where the marks persist.
 */
export interface PolicyHighWater {
  get(key: string): number | undefined;
  raise(key: string, version: number): void | Promise<void>;
}

/** A RAM-only high-water store (the executor's; it lives as long as its container). */
export function memoryPolicyHighWater(): PolicyHighWater {
  const marks = new Map<string, number>();
  return {
    get: (key) => marks.get(key),
    raise: (key, version) => {
      if (version > (marks.get(key) ?? 0)) marks.set(key, version);
    },
  };
}

/**
 * Open one record: check it against the high-water mark, decrypt it under `key` (the CEK, or the
 * policy key derived for this pointer) and its own pointer, validate the document, then raise the mark.
 *
 * @throws PolicyRollbackError for a version below the mark
 * @throws PolicyRecordIntegrityError when the blob was not sealed for this pointer, version and CEK
 * @throws PolicyRecordInvalidError when the plaintext is not a policy document
 */
export async function openPolicyRecord(
  record: PolicyRecord,
  key: CryptoKey | PolicyKey,
  pointer: PolicyPointer,
  highWater: PolicyHighWater
): Promise<PolicyDocument> {
  const markKey = policyPointerKey(pointer);
  const mark = highWater.get(markKey);
  if (mark !== undefined && record.version < mark) {
    throw new PolicyRollbackError(pointer, record.version, mark);
  }
  const plaintext = await decryptPolicyRecord(record, key, pointer);
  const parsed = PolicyDocumentSchema.safeParse(plaintext);
  if (!parsed.success) {
    throw new PolicyRecordInvalidError(
      pointer,
      parsed.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ')
    );
  }
  await highWater.raise(markKey, record.version);
  return parsed.data;
}

/** What `loadEffectivePolicy` needs to reach the records. */
export interface EffectivePolicySource {
  storeId: string;
  /** The config whose effective policy is wanted. */
  config: { configId: string; teamId: string | null };
  /** The record that rode with the config's own pull (`undefined`: not pulled, fetch it). */
  pulled?: PolicyRecord | null;
  /** The store's org-level config, whose record is the org policy; null when the store has none. */
  orgConfigId: string | null;
  /** `GET /configs/:id/policy` for a pointer: the record, or null on 404 `policy_not_found`. */
  fetchRecord(configId: string, teamId: string | null): Promise<PolicyRecord | null>;
  /** The CEK, which opens every pointer, or a resolver answering each pointer's own policy key. */
  key: CryptoKey | PolicyKeyResolver;
  highWater: PolicyHighWater;
}

/**
 * The effective policy of a remote config: the org policy from the org-level config's record,
 * narrowed by the team policy from the team config's record (Design 4). An org-level config's own
 * record IS the org policy.
 */
export async function loadEffectivePolicy(source: EffectivePolicySource): Promise<EffectivePolicy> {
  const { storeId, config, highWater } = source;
  const keyFor: PolicyKeyResolver =
    typeof source.key === 'function' ? source.key : () => Promise.resolve(source.key as CryptoKey);
  const own: PolicyPointer = { storeId, configId: config.configId, teamId: config.teamId };
  const ownRecord =
    source.pulled === undefined
      ? await source.fetchRecord(config.configId, config.teamId)
      : source.pulled;
  const ownDocument = ownRecord
    ? await openPolicyRecord(ownRecord, await keyFor(own), own, highWater)
    : undefined;

  if (config.teamId === null) return mergePolicies(ownDocument);

  let orgDocument: PolicyDocument | undefined;
  if (source.orgConfigId !== null) {
    const orgPointer: PolicyPointer = { storeId, configId: source.orgConfigId, teamId: null };
    const orgRecord = await source.fetchRecord(source.orgConfigId, null);
    if (orgRecord) {
      orgDocument = await openPolicyRecord(
        orgRecord,
        await keyFor(orgPointer),
        orgPointer,
        highWater
      );
    }
  }
  return mergePolicies(orgDocument, ownDocument);
}

/**
 * The ceiling of a LOCAL-file config (D24): its own `policy` field as the org policy. A config with
 * a `remote` block never reaches here with a policy (the schema refuses it), and is refused here too
 * so a caller that skipped the parse cannot read a forged field.
 */
export function localPolicyCeiling(config: RdcConfig): EffectivePolicy {
  if (config.remote !== undefined) {
    throw new Error(
      'A remote config takes its policy from the policy record, never from a policy field in the document.'
    );
  }
  const raw = config.policy;
  if (raw === undefined) return mergePolicies();
  const parsed = PolicyDocumentSchema.safeParse(raw);
  if (!parsed.success) {
    throw new Error(
      `The policy in this config is not valid: ${parsed.error.issues
        .map((i) => `${i.path.join('.')}: ${i.message}`)
        .join('; ')}`
    );
  }
  return mergePolicies(parsed.data);
}

/**
 * The effective policy bound to a loaded config document. The executor binds the policy it read
 * from the records to the config it serves, so the authorizer reads the record's verdict and never
 * the document's own `policy` field.
 */
const bound = new WeakMap<object, EffectivePolicy>();

export function bindEffectivePolicy(config: RdcConfig, effective: EffectivePolicy): void {
  bound.set(config, effective);
}

export function boundEffectivePolicy(config: RdcConfig): EffectivePolicy | undefined {
  return bound.get(config);
}

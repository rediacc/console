/**
 * Per-field sensitivity registry.
 *
 * Declarative source-of-truth for every sensitive (or explicitly public) field
 * path in the config schema, keyed by JSON Pointer (RFC 6901) template.
 * Template segments may be `*` to match any record key or array index.
 *
 * Consumed by:
 *   - packages/cli/src/schema/walker.ts — walkSensitive, redactClone, pathsToCommit, digestForPointer
 *   - packages/cli/src/services/mutation-gate.ts — which paths require --current knowledge
 *   - packages/cli/src/services/resource-state.ts — which paths encrypt at rest
 *   - packages/shared/src/config-crypto/commitments.ts — which paths commit to the server envelope
 *
 * Invariant: every sensitive leaf in schemas.ts MUST have a corresponding
 * template entry here. The CI gate `check:ci-schema-coverage` (Step 15) will
 * fail closed on any Zod leaf introduced without a registry entry.
 *
 * Convention: prefer one entry per template. Use `*` wildcards freely; the
 * walker expands them against live config values at lookup time.
 */

export type SensitivityKind =
  | 'secret' // tokens, API keys, passwords — encrypt-at-rest
  | 'credential' // SSH keys, passphrases, certificates — encrypt-at-rest
  | 'pii' // emails, IPs, usernames — redact but don't encrypt
  | 'identifier' // UUIDs, store/config IDs — capability-bearing, redact from agents
  | 'public'; // explicitly non-sensitive; excluded from commitments + redaction

export interface SensitivityMeta {
  kind: SensitivityKind;
  /** String shown in place of the real value. Default: `<redacted:{kind}>`. */
  redactAs?: string;
  /** Include in server-side field-commitment envelope. Default: true for non-public. */
  commit?: boolean;
  /** Encrypt this value in the local file when encryption.mode === 'master-password'. Default: true for secret/credential. */
  encryptAtRest?: boolean;
}

export type PointerTemplate = string;

/** Default-fill derived fields based on kind. */
function withDefaults(meta: SensitivityMeta): Required<SensitivityMeta> {
  return {
    kind: meta.kind,
    redactAs: meta.redactAs ?? `<redacted:${meta.kind}>`,
    commit: meta.commit ?? meta.kind !== 'public',
    encryptAtRest: meta.encryptAtRest ?? (meta.kind === 'secret' || meta.kind === 'credential'),
  };
}

/**
 * Raw sensitivity declarations. Converted to a fully-populated Map below.
 *
 * Order: grouped by top-level section in the order they appear in RdcConfig v2.
 */
const RAW_REGISTRY: Record<PointerTemplate, SensitivityMeta> = {
  // ── Account (cloud/experimental credentials) ─────────────────────────────
  '/account/apiUrl': { kind: 'identifier' },
  '/account/token': { kind: 'secret' },
  '/account/userEmail': { kind: 'pii' },
  '/account/accountServer': { kind: 'identifier' },

  // ── Defaults ─────────────────────────────────────────────────────────────
  '/defaults/universalUser': { kind: 'pii' },

  // ── Credentials ──────────────────────────────────────────────────────────
  '/credentials/ssh/privateKey': { kind: 'credential' },
  '/credentials/ssh/knownHosts': { kind: 'pii' },
  '/credentials/cfDnsApiToken': { kind: 'secret' },
  '/credentials/masterPasswordVerifier': { kind: 'secret' },

  // ── Machines ─────────────────────────────────────────────────────────────
  '/resources/machines/*/ip': { kind: 'pii' },
  '/resources/machines/*/user': { kind: 'pii' },
  '/resources/machines/*/datastore': { kind: 'pii' },
  '/resources/machines/*/knownHosts': { kind: 'pii' },
  '/resources/machines/*/infra/publicIPv4': { kind: 'pii' },
  '/resources/machines/*/infra/publicIPv6': { kind: 'pii' },
  '/resources/machines/*/ceph/pool': { kind: 'identifier' },
  '/resources/machines/*/ceph/image': { kind: 'identifier' },
  '/resources/machines/*/ceph/clusterName': { kind: 'identifier' },

  // ── Storages ─────────────────────────────────────────────────────────────
  '/resources/storages/*/vaultContent': { kind: 'secret' },

  // ── Repositories ─────────────────────────────────────────────────────────
  '/resources/repositories/*/repositoryGuid': { kind: 'identifier' },
  '/resources/repositories/*/credential': { kind: 'credential' },
  '/resources/repositories/*/grandGuid': { kind: 'identifier' },
  '/resources/repositories/*/parentGuid': { kind: 'identifier' },
  '/resources/repositories/*/sshPrivateKey': { kind: 'credential' },
  '/resources/repositories/*/sshPublicKey': { kind: 'public' },
  '/resources/repositories/*/secrets/*/value': { kind: 'secret' },
  '/resources/repositories/*/secrets/*/mode': { kind: 'public' },

  // ── Deleted (archived) repositories ──────────────────────────────────────
  '/resources/deletedRepositories/*/repositoryGuid': { kind: 'identifier' },
  '/resources/deletedRepositories/*/credential': { kind: 'credential' },
  '/resources/deletedRepositories/*/grandGuid': { kind: 'identifier' },
  '/resources/deletedRepositories/*/parentGuid': { kind: 'identifier' },
  '/resources/deletedRepositories/*/sshPrivateKey': { kind: 'credential' },
  '/resources/deletedRepositories/*/sshPublicKey': { kind: 'public' },

  // ── Cloud providers ──────────────────────────────────────────────────────
  '/resources/cloudProviders/*/apiToken': { kind: 'secret' },
  '/resources/cloudProviders/*/sshUser': { kind: 'pii' },

  // ── Infra ────────────────────────────────────────────────────────────────
  '/infra/certEmail': { kind: 'pii' },
  '/infra/cfDnsZoneId': { kind: 'identifier' },
  '/infra/acmeCertCache/*/data': { kind: 'credential' },

  // ── Remote (config store pointer) ────────────────────────────────────────
  '/remote/apiUrl': { kind: 'identifier' },
  '/remote/storeId': { kind: 'identifier' },
  '/remote/configId': { kind: 'identifier' },
  '/remote/teamId': { kind: 'identifier' },
  '/remote/storageKeyId': { kind: 'identifier' },

  // ── Local binary override ────────────────────────────────────────────────
  // renetPath is a user-set filesystem override (e.g. /opt/bin/renet). It is
  // not a secret — marking it public lets `config show` surface the actual
  // value so scripts and tests can verify which binary is in use. A user who
  // embeds their home directory ("/home/alice/bin/renet") accepts that the
  // path surfaces like any other resource path they chose.
  '/renetPath': { kind: 'public' },
};

/**
 * Fully-populated registry, keyed by template. All fields in SensitivityMeta
 * are non-optional on values (defaults filled in).
 */
export const SENSITIVITY_REGISTRY: Map<PointerTemplate, Required<SensitivityMeta>> = new Map(
  Object.entries(RAW_REGISTRY).map(([k, v]) => [k, withDefaults(v)])
);

/**
 * Read-only list of all sensitivity templates. Useful for tests and coverage gates.
 */
export function listSensitivityTemplates(): readonly PointerTemplate[] {
  return [...SENSITIVITY_REGISTRY.keys()];
}

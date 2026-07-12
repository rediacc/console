/**
 * Per-field sensitivity registry.
 *
 * Declarative source-of-truth for every sensitive (or explicitly public) field
 * path in the config schema, keyed by JSON Pointer (RFC 6901) template.
 * Template segments may be `*` to match any record key or array index.
 *
 * Consumed by:
 *   - packages/cli/src/config-schema/walker.ts (walkSensitive, pathsToCommit) + packages/cli/src/schema/fingerprint.ts (redactClone, digestForPointer)
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

type SensitivityKind =
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

  // ── Authorization policy (executor-enforced) ─────────────────────────────
  // Registered as a single leaf: the whole document is one committed value, so
  // ANY edit to ANY rule changes the commitment and a push that rewrites the
  // rules without knowing the current value is rejected by the server.
  //
  // Not 'public' (public fields are excluded from pathsToCommit, which would
  // leave the rules tamper-able) and not 'secret' either: the threat here is not
  // someone reading the rules, it is someone quietly rewriting them.
  '/policy': { kind: 'identifier' },
  // The verifier is what the CLI uses to CHECK the master password BEFORE any
  // decryption can happen. Encrypting it under the password it verifies is a
  // bootstrapping deadlock, so it is stored in the clear by explicit override
  // (spec 04 §2.3 [P0-DECIDED]). It is a verifier, not a recoverable secret.
  //
  // commit:false because it is HOST-LOCAL to the master-password at-rest mode and
  // must never enter the remote config envelope. A remote config is stored under
  // the CEK, not a master password, so the verifier is meaningless there — and
  // committing it (without also syncing it, which we must not) would drop a
  // committed pointer on every push/rotation round trip and brick the re-push.
  // Not synced, therefore not committed: the two must agree.
  '/credentials/masterPasswordVerifier': {
    kind: 'secret',
    encryptAtRest: false,
    commit: false,
  },

  // ── Machines ─────────────────────────────────────────────────────────────
  '/resources/machines/*/ip': { kind: 'pii' },
  '/resources/machines/*/user': { kind: 'pii' },
  '/resources/machines/*/datastore': { kind: 'pii' },
  '/resources/machines/*/knownHosts': { kind: 'pii' },
  '/resources/machines/*/infra/publicIPv4': { kind: 'pii' },
  '/resources/machines/*/infra/publicIPv6': { kind: 'pii' },
  // Cluster backref on materialized pool members — non-secret inventory.
  '/resources/machines/*/cluster/cluster': { kind: 'public' },
  '/resources/machines/*/cluster/pool': { kind: 'public' },

  // ── Datastores (named local/rbd registry; unencrypted by design, 02 §5) ────
  '/resources/datastores/*/backend/kind': { kind: 'public' },
  '/resources/datastores/*/backend/machine': { kind: 'public' },
  '/resources/datastores/*/backend/path': { kind: 'public' },
  '/resources/datastores/*/backend/pool': { kind: 'public' },
  '/resources/datastores/*/backend/image': { kind: 'public' },
  '/resources/datastores/*/cluster': { kind: 'public' },
  '/resources/datastores/*/size': { kind: 'public' },
  '/resources/datastores/*/parent/datastore': { kind: 'public' },
  '/resources/datastores/*/parent/snapshot': { kind: 'public' },

  // ── Clusters (SSH-reachable inventory; no live credentials by design, D15) ──
  '/resources/clusters/*/provider': { kind: 'public' },
  '/resources/clusters/*/network/primitive': { kind: 'public' },
  '/resources/clusters/*/network/cidr': { kind: 'public' },
  '/resources/clusters/*/network/mtu': { kind: 'public' },
  '/resources/clusters/*/pools/*/name': { kind: 'public' },
  '/resources/clusters/*/pools/*/role': { kind: 'public' },
  '/resources/clusters/*/pools/*/count': { kind: 'public' },
  '/resources/clusters/*/pools/*/size': { kind: 'public' },
  '/resources/clusters/*/pools/*/disks/*/purpose': { kind: 'public' },
  '/resources/clusters/*/pools/*/disks/*/size': { kind: 'public' },
  '/resources/clusters/*/pools/*/disks/*/count': { kind: 'public' },
  '/resources/clusters/*/pools/*/labels/*': { kind: 'public' },
  '/resources/clusters/*/kubernetes/distro': { kind: 'public' },
  '/resources/clusters/*/kubernetes/version': { kind: 'public' },
  '/resources/clusters/*/registry/enabled': { kind: 'public' },
  '/resources/clusters/*/registry/upstreams/*': { kind: 'public' },
  '/resources/clusters/*/ceph/pool': { kind: 'public' },
  '/resources/clusters/*/controlNode': { kind: 'public' },

  // ── Storages ─────────────────────────────────────────────────────────────
  '/resources/storages/*/vaultContent': { kind: 'secret' },

  // ── Repositories (structural tags: name -> tags -> tag -> record) ──────────
  '/resources/repositories/*/grand': { kind: 'public' },
  '/resources/repositories/*/placement/datastore': { kind: 'public' },
  '/resources/repositories/*/placement/machine': { kind: 'public' },
  '/resources/repositories/*/tags/*/repositoryGuid': { kind: 'identifier' },
  '/resources/repositories/*/tags/*/credential': { kind: 'credential' },
  '/resources/repositories/*/tags/*/grandGuid': { kind: 'identifier' },
  '/resources/repositories/*/tags/*/parentGuid': { kind: 'identifier' },
  '/resources/repositories/*/tags/*/immutable': { kind: 'public' },
  '/resources/repositories/*/tags/*/sshPrivateKey': { kind: 'credential' },
  '/resources/repositories/*/tags/*/sshPublicKey': { kind: 'public' },
  '/resources/repositories/*/tags/*/secrets/*/value': { kind: 'secret' },
  '/resources/repositories/*/tags/*/secrets/*/mode': { kind: 'public' },

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

  // ── State (runtime status half; never pushed) ──────────────────────────────
  // ACME cert cache moved from /infra/acmeCertCache. `commit:false` because
  // state never enters the server envelope.
  '/state/certCache/*/data': { kind: 'credential', commit: false },

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

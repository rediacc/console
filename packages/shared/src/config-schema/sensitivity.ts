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
 * Invariant: every primitive leaf in schemas.ts MUST resolve to a template
 * entry here (exact, wildcard, or a registered ancestor container), except the
 * envelope fields the coverage gate explicitly excludes (schemaVersion, id,
 * version, encryption). The CI gate `check:ci-schema-coverage`
 * (scripts/check-schema-coverage.ts) walks RdcConfigSchema and fails closed on
 * any Zod leaf introduced without a registry entry — and on any registry entry
 * whose template no longer matches a schema node (stale residue).
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
  // ── Account ──────────────────────────────────────────────────────────────
  '/account/userEmail': { kind: 'pii' },
  '/account/accountServer': { kind: 'identifier' },
  '/account/e2ePublicKey': { kind: 'public' }, // public half of server keypair by construction
  '/account/updateChannel': { kind: 'public' },
  '/account/releasesUrl': { kind: 'identifier' }, // on-prem endpoint, mirror accountServer
  // Retired cloud-adapter residue (R2-F9): the v2→v3 migration strips team and
  // region and nothing repopulates them. Registered public so the coverage
  // gate stays strict until P4 deletes the fields with the dead command
  // surface.
  '/account/team': { kind: 'public' },
  '/account/region': { kind: 'public' },

  // ── Defaults ─────────────────────────────────────────────────────────────
  '/defaults/universalUser': { kind: 'pii' },
  // Operator preferences: UI language, default datastore sizing, prune grace.
  '/defaults/language': { kind: 'public' },
  '/defaults/datastoreSize': { kind: 'public' },
  '/defaults/pruneGraceDays': { kind: 'public' },
  // Retired residue (R2-F9), same story as /account/team above.
  '/defaults/machine': { kind: 'public' },

  // ── Credentials ──────────────────────────────────────────────────────────
  '/credentials/ssh/privateKey': { kind: 'credential' },
  // Public half of the keypair, shareable by construction — mirrors
  // /resources/repositories/*/tags/*/sshPublicKey.
  '/credentials/ssh/publicKey': { kind: 'public' },
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
  '/resources/machines/*/port': { kind: 'public' },
  '/resources/machines/*/datastore': { kind: 'pii' },
  '/resources/machines/*/knownHosts': { kind: 'pii' },
  '/resources/machines/*/infra/publicIPv4': { kind: 'pii' },
  '/resources/machines/*/infra/publicIPv6': { kind: 'pii' },
  // Published DNS, but it identifies the deployment exactly like the sibling
  // public IPs it resolves to — same kind, or redacting the IPs is pointless.
  '/resources/machines/*/infra/baseDomain': { kind: 'pii' },
  // Firewall topology (arrays of primitives registered at the array level,
  // like backupStrategies/*/include below).
  '/resources/machines/*/infra/tcpPorts': { kind: 'public' },
  '/resources/machines/*/infra/udpPorts': { kind: 'public' },
  // Strategy names; the strategies themselves are registered below.
  '/resources/machines/*/backupStrategies': { kind: 'public' },
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
  // Local KVM topology — libvirt network naming + a registry hostname; no
  // credentials by design (D15: kubeconfigs/join tokens never enter the config).
  '/resources/clusters/*/kvm/netName': { kind: 'public' },
  '/resources/clusters/*/kvm/netBase': { kind: 'public' },
  '/resources/clusters/*/kvm/netOffset': { kind: 'public' },
  '/resources/clusters/*/kvm/controlId': { kind: 'public' },
  '/resources/clusters/*/kvm/dockerRegistry': { kind: 'public' },

  // ── Backup strategies (scheduling topology; storage creds live in vaultContent) ──
  // A strategy references storages by NAME; the credentials are in
  // /resources/storages/*/vaultContent (secret). Folder paths and include/
  // exclude globs are location topology, same sensitivity as datastore paths.
  '/resources/backupStrategies/*/schedule': { kind: 'public' },
  '/resources/backupStrategies/*/mode': { kind: 'public' },
  '/resources/backupStrategies/*/enabled': { kind: 'public' },
  '/resources/backupStrategies/*/bandwidthLimit': { kind: 'public' },
  '/resources/backupStrategies/*/include': { kind: 'public' },
  '/resources/backupStrategies/*/exclude': { kind: 'public' },
  '/resources/backupStrategies/*/destinations/*/name': { kind: 'public' },
  '/resources/backupStrategies/*/destinations/*/storage': { kind: 'public' },
  '/resources/backupStrategies/*/destinations/*/enabled': { kind: 'public' },
  '/resources/backupStrategies/*/destinations/*/bandwidthLimit': { kind: 'public' },
  '/resources/backupStrategies/*/destinations/*/folder': { kind: 'public' },

  // ── Storages ─────────────────────────────────────────────────────────────
  '/resources/storages/*/provider': { kind: 'public' },
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
  '/resources/deletedRepositories/*/immutable': { kind: 'public' },
  '/resources/deletedRepositories/*/name': { kind: 'public' },
  '/resources/deletedRepositories/*/tag': { kind: 'public' },
  '/resources/deletedRepositories/*/deletedAt': { kind: 'public' },

  // ── Cloud providers ──────────────────────────────────────────────────────
  '/resources/cloudProviders/*/apiToken': { kind: 'secret' },
  '/resources/cloudProviders/*/sshUser': { kind: 'pii' },
  // Provider-catalog plumbing: OpenTofu module source/attribute names and
  // instance/image/region labels. The only live secrets in this family are
  // apiToken and the operator identity in sshUser, above.
  '/resources/cloudProviders/*/provider': { kind: 'public' },
  '/resources/cloudProviders/*/source': { kind: 'public' },
  '/resources/cloudProviders/*/region': { kind: 'public' },
  '/resources/cloudProviders/*/instanceType': { kind: 'public' },
  '/resources/cloudProviders/*/image': { kind: 'public' },
  '/resources/cloudProviders/*/version': { kind: 'public' },
  '/resources/cloudProviders/*/tokenAttr': { kind: 'public' },
  '/resources/cloudProviders/*/resource': { kind: 'public' },
  '/resources/cloudProviders/*/labelAttr': { kind: 'public' },
  '/resources/cloudProviders/*/regionAttr': { kind: 'public' },
  '/resources/cloudProviders/*/sizeAttr': { kind: 'public' },
  '/resources/cloudProviders/*/imageAttr': { kind: 'public' },
  '/resources/cloudProviders/*/ipv4Output': { kind: 'public' },
  '/resources/cloudProviders/*/ipv6Output': { kind: 'public' },
  '/resources/cloudProviders/*/sshKey/attr': { kind: 'public' },
  '/resources/cloudProviders/*/sshKey/format': { kind: 'public' },
  '/resources/cloudProviders/*/sshKey/keyResource': { kind: 'public' },

  // ── Infra ────────────────────────────────────────────────────────────────
  '/infra/certEmail': { kind: 'pii' },
  '/infra/cfDnsZoneId': { kind: 'identifier' },

  // ── State (runtime status half; never pushed) ──────────────────────────────
  // payload.ts strips `state` before push, so nothing here may carry a
  // commitment: any non-public entry below MUST set `commit: false` (a
  // committed-but-not-carried pointer is dropped on the first pull and bricks
  // the re-push — same doctrine as masterPasswordVerifier). Runtime
  // observations are registered `public` so the coverage gate forces a
  // conscious sensitivity choice whenever a new runtime field lands; records
  // and arrays whose values are primitives are registered at the container
  // level (same style as backupStrategies/*/include).
  '/state/datastores/*/attachedTo': { kind: 'public' },
  '/state/datastores/*/writes': { kind: 'public' },
  '/state/datastores/*/mounted': { kind: 'public' },
  '/state/datastores/*/mountPath': { kind: 'public' },
  '/state/datastores/*/attachedAt': { kind: 'public' },
  '/state/datastores/*/holders/loops': { kind: 'public' },
  '/state/datastores/*/holders/dm': { kind: 'public' },
  '/state/datastores/*/holders/volumes': { kind: 'public' },
  '/state/machines/*/lastSeenAt': { kind: 'public' },
  '/state/machines/*/renetVersion': { kind: 'public' },
  '/state/clusters/*/memberIds': { kind: 'public' },
  '/state/clusters/*/k3sVersion': { kind: 'public' },
  '/state/clusters/*/nodes/*/k3sVersion': { kind: 'public' },
  '/state/clusters/*/nodes/*/lastSeenAt': { kind: 'public' },
  '/state/repos/*/*/networkId': { kind: 'public' },
  '/state/repos/*/*/registryPort': { kind: 'public' },
  '/state/repos/*/*/pushState/*/verifiedBase': { kind: 'public' },
  '/state/repos/*/*/pushState/*/lastPushAt': { kind: 'public' },
  '/state/repos/*/*/pushState/*/method': { kind: 'public' },
  '/state/repos/*/*/headCommit': { kind: 'public' },
  '/state/repos/*/*/commitMessage': { kind: 'public' },
  '/state/repos/*/*/commitAuthor': { kind: 'public' },
  '/state/repos/*/*/commitParent': { kind: 'public' },
  '/state/repos/*/*/head': { kind: 'public' },
  '/state/repos/*/*/branches': { kind: 'public' },
  '/state/repos/*/*/reflog/*/ref': { kind: 'public' },
  '/state/repos/*/*/reflog/*/from': { kind: 'public' },
  '/state/repos/*/*/reflog/*/to': { kind: 'public' },
  '/state/repos/*/*/reflog/*/at': { kind: 'public' },
  '/state/repos/*/*/reflog/*/message': { kind: 'public' },
  '/state/networkIds/next': { kind: 'public' },
  // Per-machine epoch-ms of the last opportunistic licence-refresh attempt.
  // Public: a rate-limiting timestamp keyed by a machine name the config
  // already lists in the clear, carrying no credential and no repo identity.
  '/state/licenseRefresh/*': { kind: 'public' },
  // Per-machine renet provision/verify cache: version/hash/arch/timestamps of
  // the last proven-current provision. Public: a binary hash and timestamps
  // keyed by host:port the config already lists in the clear — no credential.
  '/state/renetProvision/*/version': { kind: 'public' },
  '/state/renetProvision/*/hash': { kind: 'public' },
  '/state/renetProvision/*/arch': { kind: 'public' },
  '/state/renetProvision/*/verifiedAt': { kind: 'public' },
  '/state/renetProvision/*/setupVerifiedAt': { kind: 'public' },
  '/state/renetProvision/*/srcMtimeMs': { kind: 'public' },
  '/state/renetProvision/*/srcSize': { kind: 'public' },
  // ACME cert cache moved from /infra/acmeCertCache. `data` is the compressed
  // acme.json dump — Traefik resolver state with private keys inside —
  // `commit:false` because state never enters the server envelope. The fields
  // beside it are the domain/expiry inventory and transfer bookkeeping.
  '/state/certCache/*/baseDomain': { kind: 'public' },
  '/state/certCache/*/updatedAt': { kind: 'public' },
  '/state/certCache/*/sourceMachine': { kind: 'public' },
  '/state/certCache/*/certCount': { kind: 'public' },
  '/state/certCache/*/certs': { kind: 'public' },
  '/state/certCache/*/data': { kind: 'credential', commit: false },
  '/state/certCache/*/rawSize': { kind: 'public' },
  // Managed replica/canary sets (spec 05, R2-F17). repoGuid mirrors the
  // spec-side repositoryGuid (identifier there), so it gets the same
  // agent-redaction here; commit:false per the state rule above.
  '/state/replicaSets/*/repo': { kind: 'public' },
  '/state/replicaSets/*/repoGuid': { kind: 'identifier', commit: false },
  '/state/replicaSets/*/datastore': { kind: 'public' },
  '/state/replicaSets/*/cluster': { kind: 'public' },
  '/state/replicaSets/*/replicas/*/index': { kind: 'public' },
  '/state/replicaSets/*/replicas/*/fork': { kind: 'public' },
  '/state/replicaSets/*/replicas/*/node': { kind: 'public' },
  '/state/replicaSets/*/headless': { kind: 'public' },
  '/state/replicaSets/*/refresh': { kind: 'public' },
  '/state/replicaSets/*/snapshot': { kind: 'public' },
  '/state/replicaSets/*/createdAt': { kind: 'public' },
  '/state/replicaSets/*/refreshedAt': { kind: 'public' },
  '/state/canaries/*/repo': { kind: 'public' },
  '/state/canaries/*/cluster': { kind: 'public' },
  '/state/canaries/*/service': { kind: 'public' },
  '/state/canaries/*/image': { kind: 'public' },
  '/state/canaries/*/port': { kind: 'public' },
  '/state/canaries/*/replicas': { kind: 'public' },
  '/state/canaries/*/weight': { kind: 'public' },
  '/state/canaries/*/undoSnapshot': { kind: 'public' },
  '/state/canaries/*/createdAt': { kind: 'public' },
  '/state/canaries/*/updatedAt': { kind: 'public' },
  '/state/reconciledAt': { kind: 'public' },

  // ── Remote (config store pointer) ────────────────────────────────────────
  // HOST-LOCAL bootstrap data: how THIS host reaches the store. It is never
  // carried in the blob (a pulled config self-evidently already knows its
  // store; the wire identity lives in the plaintext envelope), so it must not
  // be committed either — the CLI pushes its on-disk document with `remote`
  // present, and a committed-but-not-carried pointer is dropped by the first
  // pull, making the re-push fail anti-downgrade. Same doctrine as
  // masterPasswordVerifier: not synced, therefore not committed.
  '/remote/apiUrl': { kind: 'identifier', commit: false },
  '/remote/storeId': { kind: 'identifier', commit: false },
  '/remote/configId': { kind: 'identifier', commit: false },
  '/remote/teamId': { kind: 'identifier', commit: false },
  '/remote/storageKeyId': { kind: 'identifier', commit: false },
  // Region display label ("eu"/"us"); public, so never committed either —
  // consistent with the host-local doctrine of its siblings above.
  '/remote/dataRegion': { kind: 'public' },
  // Offline read-cache metadata (last pulled server version + timestamp).
  // Host-local observations, same doctrine as dataRegion: public, not committed.
  '/remote/cachedVersion': { kind: 'public' },
  '/remote/cachedAt': { kind: 'public' },

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

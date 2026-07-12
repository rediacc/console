/**
 * Rediacc CLI config schema (v3).
 *
 * Zod is the single source of truth for structure and validation. Sensitivity
 * annotations live in sensitivity.ts as a declarative registry keyed by JSON
 * Pointer template; the two must be kept in sync manually (CI gate
 * `check:ci-schema-coverage`).
 *
 * v3 splits the document into a SPEC half (declared intent — machines,
 * datastores, repositories-as-families, clusters, providers, strategies) and a
 * STATE half (`state`, runtime observations that must not bump the version
 * counter or push to a remote store). Repositories are keyed by name into
 * families of structural tags; per-field encryption-at-rest replaces the v2
 * compound `/resources` blob (see services/config/resource-state.ts and
 * adapters/config-field-crypto.ts).
 */

import { z } from 'zod';
import { ValidationError } from '../errors/index.js';
import { PolicyDocumentSchema } from '../policy/schema.js';
import type { AcmeCertCache, RdcState, ReflogEntry, RepoRuntimeState } from './state-schema.js';
import { StateSchema } from './state-schema.js';

// =============================================================================
// Primitive validators
// =============================================================================

/**
 * Portable replacement for node:net's `isIP`, so this module runs unchanged on
 * Node, Cloudflare Workers, and browsers. Same contract: 4, 6, or 0 for
 * "not an IP address". Backed by zod's own IP validators rather than a
 * hand-rolled regex.
 */
const ipv4Check = z.ipv4();
const ipv6Check = z.ipv6();

function ipVersion(value: string): 0 | 4 | 6 {
  if (ipv4Check.safeParse(value).success) return 4;
  if (ipv6Check.safeParse(value).success) return 6;
  return 0;
}

/**
 * Byte length of a UTF-8 string without Node's Buffer, so the secret size caps
 * below evaluate identically in the browser and in Workers.
 */
const utf8Encoder = new TextEncoder();

export function utf8ByteLength(value: string): number {
  return utf8Encoder.encode(value).length;
}

const CRON_RANGES: [number, number][] = [
  [0, 59],
  [0, 23],
  [1, 31],
  [1, 12],
  [0, 7],
];

function isValidCronField(field: string, min: number, max: number): boolean {
  if (field === '*') return true;
  if (field.startsWith('*/')) {
    const step = Number.parseInt(field.slice(2), 10);
    return Number.isInteger(step) && step >= 1 && step <= max;
  }
  return field.split(',').every((part) => {
    const rangeMatch = /^(\d+)-(\d+)$/.exec(part);
    if (rangeMatch) {
      const lo = Number.parseInt(rangeMatch[1], 10);
      const hi = Number.parseInt(rangeMatch[2], 10);
      return lo >= min && hi <= max && lo <= hi;
    }
    const num = Number.parseInt(part, 10);
    return Number.isInteger(num) && num >= min && num <= max;
  });
}

function isValidCron(expr: string): boolean {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return false;
  return parts.every((field, i) => isValidCronField(field, CRON_RANGES[i][0], CRON_RANGES[i][1]));
}

const resourceName = z
  .string()
  .min(1, 'Name cannot be empty')
  .max(63, 'Name must be 63 characters or fewer')
  .regex(
    /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/,
    'Must be lowercase alphanumeric with hyphens, starting and ending with alphanumeric'
  );

/**
 * Structural repository tag. ':' and '@' are structurally impossible in a key
 * that matches this regex, which is the create-time validation for the tag
 * position (06 §6.4) — composite `name:tag` keys can no longer exist.
 */
const TagName = z
  .string()
  .min(1)
  .max(63)
  .regex(/^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/, 'Tag must be lowercase alphanumeric with hyphens');

const ipOrHostname = z
  .string()
  .min(1, 'IP address or hostname cannot be empty')
  .refine(
    (v) => ipVersion(v) !== 0 || /^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$/.test(v),
    'Must be a valid IP address or hostname'
  );

const absolutePath = z.string().refine((v) => v.startsWith('/'), 'Must be an absolute path');

const domain = z
  .string()
  .min(1)
  .regex(/^[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}$/, 'Must be a valid domain (e.g. example.com)');

const port = z
  .number()
  .int('Port must be an integer')
  .min(1, 'Port minimum is 1')
  .max(65535, 'Port maximum is 65535');

const uuid = z.uuid('Must be a valid UUID');

// =============================================================================
// Encrypted-field blob (per-field encryption-at-rest)
// =============================================================================

/**
 * A single AES-GCM ciphertext. `data` is the base64 of salt+iv+ciphertext+tag
 * as produced by `nodeCryptoProvider.encrypt` (adapters/crypto.ts). v2 stored a
 * single compound blob under the `/resources` pointer with a broken
 * `nonce:tag:ciphertext` split; v3 stores one entry per concrete leaf pointer.
 */
const EncryptedBlobSchema = z.object({
  data: z.string().min(1),
});

// =============================================================================
// Cloud provider sub-schemas
// =============================================================================

const ProviderSSHKeyConfigSchema = z.object({
  attr: z.string(),
  format: z.enum(['inline_list', 'resource_id']),
  keyResource: z.string().optional(),
});

const CloudProviderConfigSchema = z.object({
  provider: z.string().optional(),
  source: z.string().optional(),
  apiToken: z.string(),
  region: z.string().optional(),
  instanceType: z.string().optional(),
  image: z.string().optional(),
  sshUser: z.string().optional(),
  version: z.string().optional(),
  tokenAttr: z.string().optional(),
  resource: z.string().optional(),
  labelAttr: z.string().optional(),
  regionAttr: z.string().optional(),
  sizeAttr: z.string().optional(),
  imageAttr: z.string().optional(),
  ipv4Output: z.string().optional(),
  ipv6Output: z.string().optional(),
  sshKey: ProviderSSHKeyConfigSchema.optional(),
});

// =============================================================================
// Storage (rclone backup targets — disjoint from the `datastores` registry)
// =============================================================================

const StorageConfigSchema = z.object({
  provider: z.string(),
  vaultContent: z.record(z.string(), z.unknown()),
});

// =============================================================================
// Repository (families of structural tags) + per-repo secrets
// =============================================================================

// Per-repo secrets. Two delivery modes:
//   env  → injected as REDIACC_SECRET_<KEY> in the renet shell (compose `${VAR}`).
//   file → tmpfs file at /var/run/rediacc/secrets/<networkId>/<KEY> on the
//          target machine, referenced by Docker compose `secrets:` block.
// Fork isolation: registerFork does NOT copy `secrets`; a fork's map is empty.
const SECRET_KEY_REGEX = /^[A-Z][A-Z0-9_]*$/;

// Size caps (gate C11, merged with spec 05). The config file is atomically
// rewritten and remote-pushed WHOLE on every mutation, and each mode
// materializes as one k8s Secret object per repo namespace (~1 MiB apiserver
// cap), so anything larger is a file the data plane should carry.
export const SECRET_ENV_VALUE_MAX_BYTES = 32 * 1024; // 32 KiB per env value
export const SECRET_FILE_VALUE_MAX_BYTES = 256 * 1024; // 256 KiB per file value
export const SECRET_AGGREGATE_MAX_BYTES = 512 * 1024; // 512 KiB per repo per mode

export const SecretEntrySchema = z
  .object({
    mode: z.enum(['env', 'file']),
    value: z.string().min(1, 'Secret value cannot be empty'),
  })
  .superRefine((entry, ctx) => {
    const bytes = utf8ByteLength(entry.value);
    const cap = entry.mode === 'env' ? SECRET_ENV_VALUE_MAX_BYTES : SECRET_FILE_VALUE_MAX_BYTES;
    if (bytes > cap) {
      ctx.addIssue({
        code: 'custom',
        path: ['value'],
        message: `Secret value is ${bytes} bytes; the ${entry.mode}-mode cap is ${cap} bytes. Carry larger payloads on the data plane, not in config.`,
      });
    }
  });

export const SecretKeySchema = z
  .string()
  .min(1)
  .max(64, 'Secret key must be 64 characters or fewer')
  .regex(SECRET_KEY_REGEX, 'Secret key must be UPPER_SNAKE_CASE (uppercase letter then [A-Z0-9_])');

const SecretsRecordSchema = z.record(SecretKeySchema, SecretEntrySchema).superRefine((rec, ctx) => {
  let envTotal = 0;
  let fileTotal = 0;
  for (const entry of Object.values(rec)) {
    const bytes = utf8ByteLength(entry.value);
    if (entry.mode === 'env') envTotal += bytes;
    else fileTotal += bytes;
  }
  if (envTotal > SECRET_AGGREGATE_MAX_BYTES) {
    ctx.addIssue({
      code: 'custom',
      message: `env-mode secrets total ${envTotal} bytes; the per-repo aggregate cap is ${SECRET_AGGREGATE_MAX_BYTES} bytes.`,
    });
  }
  if (fileTotal > SECRET_AGGREGATE_MAX_BYTES) {
    ctx.addIssue({
      code: 'custom',
      message: `file-mode secrets total ${fileTotal} bytes; the per-repo aggregate cap is ${SECRET_AGGREGATE_MAX_BYTES} bytes.`,
    });
  }
});

/**
 * On-disk repository record — one per structural tag. Runtime status
 * (networkId, pushState, branching refs) has moved to `state.repos`; this
 * record is the operator's declared intent only.
 */
const RepoRecordSchema = z.object({
  repositoryGuid: uuid,
  credential: z.string().optional(),
  grandGuid: z.string().optional(),
  parentGuid: z.string().optional(),
  // Marks a fork read-only (refuses to mount on the machine). Producer:
  // `repo fork --immutable`. The machine-side mirror is authoritative.
  immutable: z.boolean().optional(),
  sshPrivateKey: z.string().optional(),
  sshPublicKey: z.string().optional(),
  secrets: SecretsRecordSchema.optional(),
});

// Placement (R2-F1): the two `repo create` flags, one-to-one.
const PlacementSchema = z.union([
  z.object({ datastore: resourceName }), // a NAMED datastore (registry entry)
  z.object({ machine: resourceName }), // that machine's IMPLICIT default datastore
]);

const RepoFamilySchema = z.object({
  // Optional ONLY for migrated configs; every derived-machine op REQUIRES it.
  placement: PlacementSchema.optional(),
  grand: TagName, // which tag key is the production line
  tags: z.record(TagName, RepoRecordSchema),
});

// Archives OMIT secrets — archiveRepository scrubs them. `tag` splits out of
// the v2 composite `name` string (migration transform 9).
const ArchivedRepositorySchema = RepoRecordSchema.omit({ secrets: true }).extend({
  name: z.string(),
  tag: z.string(),
  deletedAt: z.string(),
});

// =============================================================================
// Datastore registry (NEW — named local/rbd pools; implicit defaults not here)
// =============================================================================

const DatastoreBackendSchema = z.union([
  z.object({
    kind: z.literal('local'),
    machine: resourceName, // the anchor; local datastores do not move
    path: absolutePath,
  }),
  z.object({
    kind: z.literal('rbd'), // RBD image; mobile among machines that reach its Ceph
    pool: z.string().min(1),
    image: z.string().min(1),
  }),
]);

const DatastoreConfigSchema = z.object({
  backend: DatastoreBackendSchema,
  // Cluster backref (gate C7): top-level, orthogonal to the backend union.
  // Set at `datastore create --cluster <name>`, immutable thereafter. Set =>
  // kubernetes-world datastore; unset => docker-world datastore.
  cluster: resourceName.optional(),
  size: z.string().optional(),
  parent: z
    .object({
      datastore: resourceName,
      snapshot: z.string().optional(),
    })
    .optional(),
});

// =============================================================================
// Machine (SSH + infra) — v2 `ceph` retired (Ceph is now a datastore backend)
// =============================================================================

const InfraConfigSchema = z.object({
  publicIPv4: z
    .string()
    .refine((v) => ipVersion(v) === 4, 'Must be a valid IPv4 address')
    .optional(),
  publicIPv6: z
    .string()
    .refine((v) => ipVersion(v) === 6, 'Must be a valid IPv6 address')
    .optional(),
  baseDomain: domain.optional(),
  tcpPorts: z.array(port).optional(),
  udpPorts: z.array(port).optional(),
});

const MachineClusterRefSchema = z.object({
  cluster: resourceName,
  pool: resourceName,
});

const MachineConfigSchema = z.object({
  ip: ipOrHostname,
  user: z.string().min(1, 'SSH user cannot be empty'),
  port: port.optional(),
  datastore: absolutePath.optional(), // implicit default datastore mount path
  knownHosts: z.string().optional(),
  infra: InfraConfigSchema.optional(),
  backupStrategies: z.array(z.string()).optional(),
  cluster: MachineClusterRefSchema.optional(),
});

// =============================================================================
// Cluster (a named set of node pools; members materialize into resources.machines)
// =============================================================================

const ClusterPoolDiskSchema = z.object({
  purpose: z.string().min(1),
  size: z.string().min(1),
  count: z.number().int().min(1).optional(),
});

const ClusterPoolSchema = z.object({
  name: resourceName,
  role: z.enum(['ceph', 'k8s-server', 'k8s-agent', 'hyperconverged']),
  count: z.number().int().min(1),
  size: z.string().optional(),
  disks: z.array(ClusterPoolDiskSchema).optional(),
  labels: z.record(z.string(), z.string()).optional(),
});

const ClusterNetworkSchema = z.object({
  primitive: z.string().min(1),
  cidr: z.string().optional(),
  mtu: z.number().int().optional(),
});

const ClusterKubernetesSchema = z.object({
  distro: z.enum(['k3s', 'external']).optional(),
  version: z.string().optional(),
});

const ClusterRegistrySchema = z.object({
  enabled: z.boolean().optional(),
  upstreams: z.array(z.string()).optional(),
});

const ClusterCephRefSchema = z.object({
  pool: z.string().optional(),
});

// Local KVM topology. `renet ops` addresses VMs by numeric id; `memberIds` (the
// booted-VM allocation ledger) has moved to `state.clusters[*].memberIds` (R2-F2)
// so per-boot allocation churn no longer bumps the version counter.
const ClusterKvmSchema = z.object({
  netName: z.string().min(1),
  netBase: z.string().min(1),
  netOffset: z.number().int().min(0).optional(),
  controlId: z.number().int().min(1),
  dockerRegistry: z.string().optional(),
});

const ClusterConfigSchema = z.object({
  provider: z.string().min(1),
  network: ClusterNetworkSchema.optional(),
  pools: z.array(ClusterPoolSchema).min(1, 'A cluster needs at least one pool'),
  kubernetes: ClusterKubernetesSchema.optional(),
  registry: ClusterRegistrySchema.optional(),
  ceph: ClusterCephRefSchema.optional(),
  controlNode: resourceName.optional(),
  kvm: ClusterKvmSchema.optional(),
});

// =============================================================================
// Backup strategy
// =============================================================================

const BackupDestinationSchema = z.object({
  name: z.string().min(1, 'Destination name cannot be empty'),
  storage: z.string().min(1, 'Storage name cannot be empty'),
  enabled: z.boolean().optional(),
  bandwidthLimit: z.string().optional(),
  folder: z.string().optional(),
});

const BackupStrategyConfigSchema = z.object({
  destinations: z.array(BackupDestinationSchema),
  schedule: z.string().refine(isValidCron, 'Must be a valid 5-field cron expression'),
  mode: z.enum(['hot', 'cold']).optional(),
  enabled: z.boolean().optional(),
  bandwidthLimit: z.string().optional(),
  include: z.array(z.string()).optional(),
  exclude: z.array(z.string()).optional(),
});

// =============================================================================
// Top-level buckets (spec half)
// =============================================================================

const AccountSchema = z.object({
  userEmail: z.string().optional(),
  accountServer: z.string().optional(),
  // team/region are retired cloud-adapter residue (R2-F9). The v2→v3 migration
  // strips them and nothing repopulates them; kept optional only so the dead
  // `config set/clear team|region` command surface compiles until P4 removes it.
  team: z.string().optional(),
  region: z.string().optional(),
});

const DefaultsSchema = z.object({
  language: z.string().optional(),
  universalUser: z.string().optional(),
  datastoreSize: z.string().optional(),
  pruneGraceDays: z.number().int().optional(),
  // Retired residue (R2-F9); see AccountSchema note. Migration strips it.
  machine: z.string().optional(),
});

const SSHCredentialsSchema = z.object({
  privateKey: z.string(),
  publicKey: z.string().optional(),
  knownHosts: z.string().optional(),
});

const CredentialsSchema = z.object({
  ssh: SSHCredentialsSchema.optional(),
  cfDnsApiToken: z.string().optional(),
  masterPasswordVerifier: z.string().optional(),
});

const ResourcesSchema = z.object({
  machines: z.record(resourceName, MachineConfigSchema).optional(),
  datastores: z.record(resourceName, DatastoreConfigSchema).optional(),
  storages: z.record(resourceName, StorageConfigSchema).optional(),
  repositories: z.record(resourceName, RepoFamilySchema).optional(),
  deletedRepositories: z.array(ArchivedRepositorySchema).optional(),
  backupStrategies: z.record(resourceName, BackupStrategyConfigSchema).optional(),
  cloudProviders: z.record(resourceName, CloudProviderConfigSchema).optional(),
  clusters: z.record(resourceName, ClusterConfigSchema).optional(),
});

const InfraTopSchema = z.object({
  certEmail: z.email().optional(),
  cfDnsZoneId: z.string().optional(),
});

const EncryptionSchema = z.object({
  mode: z.enum(['plaintext', 'master-password']),
  encryptedFields: z.record(z.string(), EncryptedBlobSchema).optional(),
});

const RemoteConfigSchema = z.object({
  apiUrl: z.string(),
  storeId: uuid,
  configId: uuid,
  teamId: uuid.optional(),
  storageKeyId: z.string(),
  dataRegion: z.string().optional(),
});

// =============================================================================
// Top-level RdcConfig v3
// =============================================================================

/**
 * `.loose()` preserves unknown top-level keys instead of stripping them, so a
 * newer CLI's additions round-trip through an older CLI untouched.
 */
export const RdcConfigSchema = z
  .object({
    schemaVersion: z.literal(3),
    id: uuid,
    version: z.number().int().min(1),
    account: AccountSchema.optional(),
    defaults: DefaultsSchema.optional(),
    credentials: CredentialsSchema.optional(),
    resources: ResourcesSchema.optional(),
    infra: InfraTopSchema.optional(),
    encryption: EncryptionSchema.optional(),
    remote: RemoteConfigSchema.optional(),
    renetPath: z.string().optional(),
    state: StateSchema.optional(),
    /**
     * Authorization rules the EXECUTOR enforces (`rdc serve`).
     *
     * It lives inside the config, which means it lives inside the encrypted
     * blob, which means Rediacc cannot read an organization's rules. It is also
     * field-committed (see sensitivity.ts '/policy'), so the server rejects a
     * push that rewrites it without knowing the current value. That matters more
     * than secrecy here: the threat is not someone READING the rules, it is
     * someone quietly REWRITING them to grant themselves access.
     */
    policy: PolicyDocumentSchema.optional(),
  })
  .loose();

// =============================================================================
// Types
// =============================================================================

export type RdcConfig = z.infer<typeof RdcConfigSchema>;
export type MachineConfig = z.infer<typeof MachineConfigSchema>;
export type StorageConfig = z.infer<typeof StorageConfigSchema>;
export type Placement = z.infer<typeof PlacementSchema>;
export type RepoRecord = z.infer<typeof RepoRecordSchema>;
export type RepoFamily = z.infer<typeof RepoFamilySchema>;
export type SecretEntry = z.infer<typeof SecretEntrySchema>;
export type SecretMode = SecretEntry['mode'];
export type InfraConfig = z.infer<typeof InfraConfigSchema>;
export type BackupDestination = z.infer<typeof BackupDestinationSchema>;
export type BackupStrategyConfig = z.infer<typeof BackupStrategyConfigSchema>;
export type CloudProviderConfig = z.infer<typeof CloudProviderConfigSchema>;
export type ClusterConfig = z.infer<typeof ClusterConfigSchema>;
export type ClusterPool = z.infer<typeof ClusterPoolSchema>;
export type ClusterKvm = z.infer<typeof ClusterKvmSchema>;
export type ClusterPoolRole = ClusterPool['role'];
export type RemoteConfig = z.infer<typeof RemoteConfigSchema>;
export type EncryptedBlob = z.infer<typeof EncryptedBlobSchema>;
export type EncryptionState = z.infer<typeof EncryptionSchema>;
export type { AcmeCertCache, RdcState };

/**
 * Flattened in-memory repository view. `ResourceState` presents repositories to
 * the command layer keyed by the legacy composite `name` / `name:tag` string
 * with spec (RepoRecord) and status (state.repos) fields merged, so command
 * consumers compile unchanged while the on-disk shape is v3 families + state.
 * The command layer's own reshape to the structural view is P4.
 */
export type RepositoryConfig = RepoRecord & {
  tag?: string;
  placement?: Placement;
  networkId?: number;
  registryPort?: number;
  pushState?: RepoRuntimeState['pushState'];
  headCommit?: string;
  commitMessage?: string;
  commitAuthor?: string;
  commitParent?: string;
  head?: string;
  branches?: Record<string, string>;
  reflog?: ReflogEntry[];
};

export type ArchivedRepository = z.infer<typeof ArchivedRepositorySchema>;

// =============================================================================
// Create an empty v3 config
// =============================================================================

export function createEmptyRdcConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: globalThis.crypto.randomUUID(),
    version: 1,
    defaults: { language: 'en', datastoreSize: '95%' },
    encryption: { mode: 'plaintext' },
  };
}

// =============================================================================
// Remote config detection helpers
// =============================================================================

export function hasRemoteConfig(
  config: RdcConfig | null | undefined
): config is RdcConfig & { remote: RemoteConfig } {
  return Boolean(config?.remote?.apiUrl && config.remote.storeId && config.remote.configId);
}

// =============================================================================
// Parse helpers
// =============================================================================

export function parseConfig<T>(schema: z.ZodType<T>, data: unknown, context: string): T {
  const result = schema.safeParse(data);
  if (result.success) return result.data;
  const issues = result.error.issues
    .map((i) => {
      const path = i.path.length > 0 ? `${i.path.join('.')}: ` : '';
      return `  ${path}${i.message}`;
    })
    .join('\n');
  throw new ValidationError(`Invalid ${context}:\n${issues}`);
}

// =============================================================================
// Deterministic JSON key ordering for v3 config
// =============================================================================

// Spec half first, `state` last (R2-F8: diffs read spec-first).
const CONFIG_KEY_ORDER_V3 = [
  'schemaVersion',
  'id',
  'version',
  'account',
  'defaults',
  'credentials',
  'resources',
  'infra',
  'encryption',
  'remote',
  'renetPath',
  'state',
] as const;

function orderedReplacer(this: unknown, _key: string, value: unknown): unknown {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return value;
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj);
  const isRootConfig = 'schemaVersion' in obj && 'id' in obj && 'version' in obj;
  let sortedKeys: string[];
  if (isRootConfig) {
    const orderMap = new Map<string, number>(CONFIG_KEY_ORDER_V3.map((k, i) => [k, i]));
    const inOrder = keys
      .filter((k) => orderMap.has(k))
      .sort((a, b) => orderMap.get(a)! - orderMap.get(b)!);
    const rest = keys.filter((k) => !orderMap.has(k)).sort();
    sortedKeys = [...inOrder, ...rest];
  } else {
    sortedKeys = [...keys].sort();
  }
  const sorted: Record<string, unknown> = {};
  for (const k of sortedKeys) {
    if (obj[k] !== undefined) sorted[k] = obj[k];
  }
  return sorted;
}

export function stringifyConfig(config: RdcConfig): string {
  return JSON.stringify(config, orderedReplacer, 2);
}

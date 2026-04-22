/**
 * Rediacc CLI config schema (v2).
 *
 * Zod is the single source of truth for structure and validation. Sensitivity
 * annotations live in sensitivity.ts as a declarative registry keyed by JSON
 * Pointer template; the two must be kept in sync manually (CI gate
 * `check:ci-schema-coverage` — Step 15 — enforces this).
 *
 * Structure (top-level bucketing):
 *   schemaVersion (literal 2 discriminator)
 *   id, version (metadata)
 *   account?      — cloud/experimental credentials
 *   defaults?     — language, counters, user settings
 *   credentials?  — SSH keys, CF DNS token, master password verifier
 *   resources?    — machines, storages, repositories, deletedRepositories,
 *                   backupStrategies, cloudProviders
 *   infra?        — TLS email, DNS zone, ACME cert cache
 *   encryption?   — mode + per-field encryption-at-rest blobs
 *   remote?       — config store pointer
 *   renetPath?    — local binary override
 */

import { isIP } from 'node:net';
import { randomUUID } from 'node:crypto';
import { z } from 'zod';
import { ValidationError } from '@rediacc/shared/errors';
import { t } from '../i18n/index.js';

// ValidationError comes from a zero-dep shared package.
// t() comes from the CLI's i18n module, which does NOT import back through
// types/index.ts (it only imports i18next + JSON locale files + shared/i18n).
// These two imports together sidestep the schema ↔ utils/errors ↔ types/index
// cycle that previously forced us to inline stubs.

// =============================================================================
// Primitive validators
// =============================================================================

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

export function isValidCron(expr: string): boolean {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return false;
  return parts.every((field, i) => isValidCronField(field, CRON_RANGES[i][0], CRON_RANGES[i][1]));
}

export const resourceName = z
  .string()
  .min(1, 'Name cannot be empty')
  .max(63, 'Name must be 63 characters or fewer')
  .regex(
    /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/,
    'Must be lowercase alphanumeric with hyphens, starting and ending with alphanumeric'
  );

const ipOrHostname = z
  .string()
  .min(1, 'IP address or hostname cannot be empty')
  .refine(
    (v) => isIP(v) !== 0 || /^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$/.test(v),
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
// Repository reference parsing (name:tag)
// =============================================================================

const DEFAULT_TAG = 'latest';

export function parseRepoRef(ref: string): { name: string; tag: string } {
  const colonIndex = ref.indexOf(':');
  if (colonIndex === -1) return { name: ref, tag: DEFAULT_TAG };
  return { name: ref.slice(0, colonIndex), tag: ref.slice(colonIndex + 1) };
}

export function compositeKey(name: string, tag: string): string {
  return `${name}:${tag}`;
}

// =============================================================================
// Encrypted-field blob (per-field encryption-at-rest)
// =============================================================================

const EncryptedBlobSchema = z.object({
  ciphertext: z.string().min(1),
  nonce: z.string().min(1),
  tag: z.string().min(1),
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
// Storage
// =============================================================================

export const StorageConfigSchema = z.object({
  provider: z.string(),
  vaultContent: z.record(z.string(), z.unknown()),
});

// =============================================================================
// Repository (and archived repository)
// =============================================================================

export const RepositoryConfigSchema = z.object({
  repositoryGuid: uuid,
  tag: z.string().optional(),
  credential: z.string().optional(),
  networkId: z.number().int().optional(),
  grandGuid: z.string().optional(),
  parentGuid: z.string().optional(),
  sshPrivateKey: z.string().optional(),
  sshPublicKey: z.string().optional(),
});

export const ArchivedRepositorySchema = RepositoryConfigSchema.extend({
  name: z.string(),
  deletedAt: z.string(),
});

// =============================================================================
// Machine (SSH + infra + ceph)
// =============================================================================

const CephConfigSchema = z.object({
  pool: z.string(),
  image: z.string(),
  clusterName: z.string().optional(),
});

export const InfraConfigSchema = z.object({
  publicIPv4: z
    .string()
    .refine((v) => isIP(v) === 4, 'Must be a valid IPv4 address')
    .optional(),
  publicIPv6: z
    .string()
    .refine((v) => isIP(v) === 6, 'Must be a valid IPv6 address')
    .optional(),
  baseDomain: domain.optional(),
  tcpPorts: z.array(port).optional(),
  udpPorts: z.array(port).optional(),
});

export const MachineConfigSchema = z.object({
  ip: ipOrHostname,
  user: z.string().min(1, 'SSH user cannot be empty'),
  port: port.optional(),
  datastore: absolutePath.optional(),
  knownHosts: z.string().optional(),
  infra: InfraConfigSchema.optional(),
  ceph: CephConfigSchema.optional(),
  backupStrategies: z.array(z.string()).optional(),
});

// =============================================================================
// Backup strategy
// =============================================================================

export const BackupDestinationSchema = z.object({
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
// ACME cert cache
// =============================================================================

const AcmeCertCacheSchema = z.object({
  baseDomain: z.string(),
  updatedAt: z.string(),
  sourceMachine: z.string(),
  certCount: z.number().int(),
  certs: z.record(z.string(), z.string()),
  data: z.union([z.string(), z.array(z.string())]),
  rawSize: z.number().int(),
});

// =============================================================================
// Top-level buckets
// =============================================================================

const AccountSchema = z.object({
  apiUrl: z.string().optional(),
  token: z.string().optional(),
  userEmail: z.string().optional(),
  team: z.string().optional(),
  region: z.string().optional(),
  bridge: z.string().optional(),
  accountServer: z.string().optional(),
});

const DefaultsSchema = z.object({
  language: z.string().optional(),
  machine: z.string().optional(),
  universalUser: z.string().optional(),
  datastoreSize: z.string().optional(),
  pruneGraceDays: z.number().int().optional(),
  nextNetworkId: z.number().int().optional(),
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
  storages: z.record(resourceName, StorageConfigSchema).optional(),
  repositories: z.record(z.string(), RepositoryConfigSchema).optional(),
  deletedRepositories: z.array(ArchivedRepositorySchema).optional(),
  backupStrategies: z.record(resourceName, BackupStrategyConfigSchema).optional(),
  cloudProviders: z.record(resourceName, CloudProviderConfigSchema).optional(),
});

const InfraTopSchema = z.object({
  certEmail: z.email().optional(),
  cfDnsZoneId: z.string().optional(),
  acmeCertCache: z.record(z.string(), AcmeCertCacheSchema).optional(),
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
// Top-level RdcConfig v2
// =============================================================================

export const RdcConfigSchema = z.object({
  schemaVersion: z.literal(2),
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
});

export type RdcConfig = z.infer<typeof RdcConfigSchema>;
export type MachineConfig = z.infer<typeof MachineConfigSchema>;
export type StorageConfig = z.infer<typeof StorageConfigSchema>;
export type RepositoryConfig = z.infer<typeof RepositoryConfigSchema>;
export type ArchivedRepository = z.infer<typeof ArchivedRepositorySchema>;
export type InfraConfig = z.infer<typeof InfraConfigSchema>;
export type BackupDestination = z.infer<typeof BackupDestinationSchema>;
export type BackupStrategyConfig = z.infer<typeof BackupStrategyConfigSchema>;
export type CloudProviderConfig = z.infer<typeof CloudProviderConfigSchema>;
export type AcmeCertCache = z.infer<typeof AcmeCertCacheSchema>;
export type RemoteConfig = z.infer<typeof RemoteConfigSchema>;
export type EncryptedBlob = z.infer<typeof EncryptedBlobSchema>;
export type EncryptionState = z.infer<typeof EncryptionSchema>;

// =============================================================================
// Create an empty v2 config
// =============================================================================

export function createEmptyRdcConfig(): RdcConfig {
  return {
    schemaVersion: 2,
    id: randomUUID(),
    version: 1,
    defaults: { language: 'en', datastoreSize: '95%' },
    encryption: { mode: 'plaintext' },
  };
}

// =============================================================================
// Remote config detection helpers
// =============================================================================

export function hasCloudCredentials(config: RdcConfig | null | undefined): boolean {
  return Boolean(config?.account?.apiUrl && config.account.token);
}

export function hasCloudIntent(config: RdcConfig | null | undefined): boolean {
  return Boolean(config?.account?.apiUrl);
}

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

export function assertResourceName(name: string): void {
  const result = resourceName.safeParse(name);
  if (!result.success) {
    const msg = result.error.issues.map((i) => i.message).join('; ');
    throw new ValidationError(`Invalid resource name "${name}": ${msg}`);
  }
}

export async function assertStorageExists(storageName: string): Promise<void> {
  const { configService } = await import('../services/config-resources.js');
  const storages = await configService.listStorages();
  const names = storages.map((s) => s.name);
  if (!names.includes(storageName)) {
    throw new ValidationError(
      t('errors.config.storageNotFound', {
        name: storageName,
        available: names.length > 0 ? names.join(', ') : '(none)',
      })
    );
  }
}

export async function assertMachineExists(machineName: string): Promise<void> {
  const { configService } = await import('../services/config-resources.js');
  const machines = await configService.listMachines();
  const names = machines.map((m) => m.name);
  if (!names.includes(machineName)) {
    throw new ValidationError(
      t('errors.config.machineNotFound', {
        name: machineName,
        available: names.length > 0 ? names.join(', ') : '(none)',
      })
    );
  }
}

// =============================================================================
// Input normalization
// =============================================================================

export function normalizeIp(value: string): string {
  return value.trim();
}

export function normalizeDomain(value: string): string {
  return value.trim().toLowerCase();
}

export function normalizeEmail(value: string): string {
  return value.trim().toLowerCase();
}

export function normalizePath(value: string): string {
  return value.trim().replace(/\/+$/, '') || '/';
}

// =============================================================================
// Deterministic JSON key ordering for v2 config
// =============================================================================

const CONFIG_KEY_ORDER_V2 = [
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
] as const;

export function orderedReplacer(this: unknown, _key: string, value: unknown): unknown {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return value;
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj);
  const isRootConfig = 'schemaVersion' in obj && 'id' in obj && 'version' in obj;
  let sortedKeys: string[];
  if (isRootConfig) {
    const orderMap = new Map<string, number>(CONFIG_KEY_ORDER_V2.map((k, i) => [k, i]));
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

export const CertEmailSchema = z.email('Must be a valid email address');

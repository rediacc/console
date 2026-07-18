/**
 * Zod schemas for config JSON validation, key ordering, and input normalization.
 *
 * Mirrors TypeScript interfaces in types/index.ts.
 * Used by config write commands for fail-fast validation.
 */
import { isIP } from 'node:net';
import { splitRef } from '@rediacc/shared/ref';
import { z } from 'zod';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import type { RdcConfig } from '../types/index.js';
import { ValidationError } from './errors.js';

// ── Reusable refinements ──────────────────────────────────────────

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

// ── Config type schemas ───────────────────────────────────────────

export const MachineConfigSchema = z.object({
  ip: ipOrHostname,
  user: z.string().min(1, 'SSH user cannot be empty'),
  port: port.optional(),
  datastore: absolutePath.optional(),
});

// ── Per-repo secrets ──────────────────────────────────────────────
//
// Single source of truth for the secret schemas + size caps is
// config-schema/schemas.ts in packages/shared (spec 04 §5.1: the caps must live in one place). Imported
// and re-exported here so the flat `RepositoryConfigSchema` below (used by
// `config repository add` validation) and existing importers keep working.
import { SecretEntrySchema, SecretKeySchema } from '@rediacc/shared/config-schema';

export { SecretEntrySchema, SecretKeySchema };

export const RepositoryConfigSchema = z.object({
  repositoryGuid: z.uuid('Must be a valid UUID'),
  tag: z.string().optional(),
  credential: z.string().optional(),
  networkId: z.number().int().optional(),
  grandGuid: z.string().optional(),
  parentGuid: z.string().optional(),
  sshPrivateKey: z.string().optional(),
  sshPublicKey: z.string().optional(),
  secrets: z.record(SecretKeySchema, SecretEntrySchema).optional(),
});

// ── Repository name:tag utilities ──────────────────────────────────────────

const DEFAULT_TAG = 'latest';

/**
 * Parse a repository reference into name and tag.
 * "marketing:staging" → { name: "marketing", tag: "staging" }
 * "marketing"         → { name: "marketing", tag: "latest" }
 *
 * Delegates to the shared lenient {@link splitRef}. The legacy `latest` default
 * tag universe stays separate from the P4 `base` grammar (parseRef): these are
 * config-key strings, not user-typed refs.
 */
export function parseRepoRef(ref: string): { name: string; tag: string } {
  const { name, tag } = splitRef(ref, DEFAULT_TAG);
  return { name, tag: tag ?? DEFAULT_TAG };
}

/**
 * Build a composite config key from name and tag.
 * ("marketing", "staging") → "marketing:staging"
 */
export function compositeKey(name: string, tag: string): string {
  return `${name}:${tag}`;
}

/**
 * Reject the reserved `latest` tag for any operation that registers a fork.
 * A fork registered under `<name>:latest` collides with the grand and makes
 * bare `--name` ambiguous for destructive commands. Pass the translated
 * message to keep this utility free of i18n imports (would be circular).
 */
export function assertNonLatestForkTag(tag: string, errorMessage: string): void {
  if (tag === DEFAULT_TAG) {
    throw new Error(errorMessage);
  }
}

/** The reserved tag that identifies the grand (production) repository. */
export const RESERVED_GRAND_TAG = DEFAULT_TAG;

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

export const BackupDestinationSchema = z.object({
  name: z.string().min(1, 'Destination name cannot be empty'),
  storage: z.string().min(1, 'Storage name cannot be empty'),
  enabled: z.boolean().optional(),
  bandwidthLimit: z.string().optional(),
  folder: z.string().optional(),
});

export const CertEmailSchema = z.email('Must be a valid email address');

// ── Parse helper ──────────────────────────────────────────────────

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

// ── Cross-reference checks ────────────────────────────────────────

export async function assertStorageExists(storageName: string): Promise<void> {
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

// ── Input normalization ───────────────────────────────────────────

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

// ── Deterministic JSON key ordering ───────────────────────────────

/**
 * Canonical key order for RdcConfig JSON serialization.
 * Keys not listed here are appended alphabetically after the ordered keys.
 */
const CONFIG_KEY_ORDER = [
  // Metadata
  'id',
  'version',

  // Cloud
  'apiUrl',
  'token',
  'userEmail',
  'team',
  'region',

  // Defaults
  'machine',
  'language',
  'universalUser',
  'nextNetworkId',

  // SSH
  'ssh',
  'sshContent',
  'renetPath',

  // Resources
  'machines',
  'storages',
  'repositories',
  'deletedRepositories',

  // Infrastructure
  'certEmail',
  'cfDnsApiToken',
  'cfDnsZoneId',
  'acmeCertCache',

  // Backup
  'backupStrategy',

  // Cloud providers
  'cloudProviders',

  // Encryption
  'encrypted',
  'encryptedResources',
  'masterPassword',

  // S3
  's3',
] as const;

/**
 * JSON.stringify replacer that sorts object keys in a deterministic order.
 * Top-level RdcConfig keys follow CONFIG_KEY_ORDER; all other object keys are alphabetical.
 */
function orderedReplacer(this: unknown, _key: string, value: unknown): unknown {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return value;
  }

  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj);

  // Determine if this is the root config object (has 'id' and 'version')
  const isRootConfig = 'id' in obj && 'version' in obj;

  let sortedKeys: string[];
  if (isRootConfig) {
    const orderMap = new Map<string, number>(CONFIG_KEY_ORDER.map((k, i) => [k, i]));
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
    if (obj[k] !== undefined) {
      sorted[k] = obj[k];
    }
  }
  return sorted;
}

/**
 * Stringify a config object with deterministic key ordering and 2-space indent.
 */
export function stringifyConfig(config: RdcConfig): string {
  return JSON.stringify(config, orderedReplacer, 2);
}

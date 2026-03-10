/**
 * Zod schemas for config JSON validation, key ordering, and input normalization.
 *
 * Mirrors TypeScript interfaces in types/index.ts.
 * Used by config write commands for fail-fast validation.
 */
import { isIP } from 'node:net';
import { z } from 'zod';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import type { RdcConfig } from '../types/index.js';
import { ValidationError } from './errors.js';

// ── Cron validation ───────────────────────────────────────────────

const CRON_RANGES: [number, number][] = [
  [0, 59], // minute
  [0, 23], // hour
  [1, 31], // day of month
  [1, 12], // month
  [0, 7], // day of week (0 and 7 = Sunday)
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

const cronExpr = z.string().refine(isValidCron, 'Must be a valid 5-field cron expression');

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

export const RepositoryConfigSchema = z.object({
  repositoryGuid: z.uuid('Must be a valid UUID'),
  tag: z.string().optional(),
  credential: z.string().optional(),
  networkId: z.number().int().optional(),
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

export const BackupDestinationSchema = z.object({
  storage: z.string().min(1, 'Storage name cannot be empty'),
  schedule: cronExpr.optional(),
  enabled: z.boolean().optional(),
});

export const BackupScheduleSchema = z.object({
  schedule: cronExpr.optional(),
  enabled: z.boolean().optional(),
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
  'bridge',

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
export function orderedReplacer(this: unknown, _key: string, value: unknown): unknown {
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

/**
 * `rdc config access add|remove|ranges|list`: the config's `access` bucket, the
 * SSH keys rdc installs with a `from=` source-range restriction
 * (agent/plans/PLAN-ssh-key-source-ranges.md, Design 4). The machine side,
 * binding a key to a machine and pushing it, is `rdc machine access`.
 */

import { readFile } from 'node:fs/promises';
import { HOSTED_EXECUTOR_SOURCE_RANGES } from '@rediacc/shared/config';
import {
  ACCESS_KEY_TYPES,
  type AccessConfig,
  AccessSchema,
  parseOpenSshPublicKey,
  type SourceRanges,
} from '@rediacc/shared/config-schema';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import type { OutputFormat } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { omitKey } from '../utils/omit-key.js';

/** The range flags shared by `config access add|ranges` and `machine access set`. */
export interface RangeOptions {
  ipv4?: string;
  ipv6?: string;
  hostedExecutor?: boolean;
}

function splitList(value: string | undefined): string[] {
  if (value === undefined) return [];
  return value
    .split(',')
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
}

/** A flag that was given but names no CIDR is a mistake, never "no ranges". */
function assertRangeFlagsNamed(options: RangeOptions): void {
  const given: [string, string | undefined][] = [
    ['--ipv4', options.ipv4],
    ['--ipv6', options.ipv6],
  ];
  for (const [flag, value] of given) {
    if (value !== undefined && splitList(value).length === 0) {
      throw new ValidationError(t('commands.config.access.emptyRangeFlag', { flag }));
    }
  }
}

/**
 * The ranges named by the flags, or undefined when none was given. A given
 * `--ipv4` or `--ipv6` that names no CIDR throws a ValidationError.
 * `--hosted-executor` seeds both lists with the observed hosted-executor egress
 * ranges; `--ipv4`/`--ipv6` add to them. Repeats are dropped; the schema
 * validates each entry.
 */
export function rangesFromOptions(options: RangeOptions): SourceRanges | undefined {
  const ipv4 = new Set<string>(options.hostedExecutor ? HOSTED_EXECUTOR_SOURCE_RANGES.ipv4 : []);
  const ipv6 = new Set<string>(options.hostedExecutor ? HOSTED_EXECUTOR_SOURCE_RANGES.ipv6 : []);
  assertRangeFlagsNamed(options);
  for (const entry of splitList(options.ipv4)) ipv4.add(entry);
  for (const entry of splitList(options.ipv6)) ipv6.add(entry);
  if (ipv4.size === 0 && ipv6.size === 0) return undefined;
  return {
    ...(ipv4.size > 0 && { ipv4: [...ipv4] }),
    ...(ipv6.size > 0 && { ipv6: [...ipv6] }),
  };
}

/** Refuse an `access` bucket the schema rejects, naming every issue. */
export function assertValidAccess(access: AccessConfig): AccessConfig {
  const result = AccessSchema.safeParse(access);
  if (result.success) return access;
  const issues = result.error.issues.map((issue) => {
    const path = issue.path.length > 0 ? `access.${issue.path.join('.')}: ` : 'access: ';
    return `${path}${issue.message}`;
  });
  throw new ValidationError(issues.join('; '));
}

/** `--public-key` takes the key line itself, or a path to a file holding it. */
async function readPublicKeyOption(value: string): Promise<string> {
  const inline = value.trim();
  const type = parseOpenSshPublicKey(inline)?.type;
  if (type !== undefined && (ACCESS_KEY_TYPES as readonly string[]).includes(type)) return inline;
  try {
    return (await readFile(inline, 'utf8')).trim();
  } catch {
    throw new ValidationError(t('commands.config.access.add.publicKeyUnreadable', { value }));
  }
}

interface AddAccessKeyInput {
  publicKey: string;
  ranges?: SourceRanges;
  restrict: boolean;
}

/**
 * Add the key, or update an existing one in place (public key, restriction,
 * and its ranges when given), keeping its machine bindings.
 */
function addAccessKey(access: AccessConfig, name: string, input: AddAccessKeyInput): AccessConfig {
  const existing = access.keys?.[name];
  const base = omitKey(existing ?? {}, 'restrict');
  const key = {
    ...base,
    publicKey: input.publicKey,
    ...(input.restrict ? {} : { restrict: false }),
    ...(input.ranges && { sourceRanges: input.ranges }),
  };
  return assertValidAccess({ ...access, keys: { ...(access.keys ?? {}), [name]: key } });
}

/** Drop the key; refuses an unknown one. */
function removeAccessKey(access: AccessConfig, name: string): AccessConfig {
  if (access.keys?.[name] === undefined) {
    throw new ValidationError(t('commands.config.access.keyNotFound', { key: name }));
  }
  const keys = omitKey(access.keys, name);
  return assertValidAccess({ ...access, keys });
}

/** Set (or with `undefined`, clear) the config-wide default ranges. */
function setDefaultRanges(access: AccessConfig, ranges: SourceRanges | undefined): AccessConfig {
  const rest = omitKey(access, 'sourceRanges');
  return assertValidAccess(ranges ? { ...rest, sourceRanges: ranges } : rest);
}

function formatRanges(ranges: SourceRanges | undefined): string {
  if (ranges === undefined) return '-';
  return [...(ranges.ipv4 ?? []), ...(ranges.ipv6 ?? [])].join(', ');
}

/** One row per access key, for `config access list`. */
function accessKeyRows(access: AccessConfig | undefined): Record<string, unknown>[] {
  return Object.entries(access?.keys ?? {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, key]) => {
      const parsed = parseOpenSshPublicKey(key.publicKey.trim());
      return {
        key: name,
        type: parsed?.type ?? '-',
        comment: parsed?.comment ?? '',
        restrict: key.restrict !== false,
        sourceRanges: key.sourceRanges ?? null,
        machines: Object.keys(key.machines ?? {}).sort((a, b) => a.localeCompare(b)),
      };
    });
}

function registerAdd(access: Command): void {
  access
    .command('add')
    .argument('<key>', t('commands.config.access.argKey'))
    .summary(t('commands.config.access.add.descriptionShort'))
    .description(t('commands.config.access.add.description'))
    .requiredOption('--public-key <key>', t('commands.config.access.add.optionPublicKey'))
    .option('--hosted-executor', t('commands.config.access.optionHostedExecutor'))
    .option('--ipv4 <cidrs>', t('commands.config.access.optionIpv4'))
    .option('--ipv6 <cidrs>', t('commands.config.access.optionIpv6'))
    .option('--no-restrict', t('commands.config.access.add.optionNoRestrict'))
    .action(async (name: string, options) => {
      try {
        const publicKey = await readPublicKeyOption(options.publicKey);
        const ranges = rangesFromOptions(options);
        const existed = (await configService.getAccess())?.keys?.[name] !== undefined;
        await configService.updateAccess((current) =>
          addAccessKey(current, name, { publicKey, ranges, restrict: options.restrict !== false })
        );
        outputService.success(
          existed
            ? t('commands.config.access.add.updated', { key: name })
            : t('commands.config.access.add.success', { key: name })
        );
      } catch (error) {
        handleError(error);
      }
    });
}

function registerRemove(access: Command): void {
  access
    .command('remove')
    .argument('<key>', t('commands.config.access.argKey'))
    .description(t('commands.config.access.remove.description'))
    .action(async (name: string) => {
      try {
        const machines = Object.keys(
          (await configService.getAccess())?.keys?.[name]?.machines ?? {}
        );
        await configService.updateAccess((current) => removeAccessKey(current, name));
        outputService.success(t('commands.config.access.remove.success', { key: name }));
        if (machines.length > 0) {
          outputService.warn(
            t('commands.config.access.remove.pushHint', {
              machines: machines.sort((a, b) => a.localeCompare(b)).join(', '),
            })
          );
        }
      } catch (error) {
        handleError(error);
      }
    });
}

function registerRanges(access: Command, program: Command): void {
  access
    .command('ranges')
    .summary(t('commands.config.access.ranges.descriptionShort'))
    .description(t('commands.config.access.ranges.description'))
    .option('--hosted-executor', t('commands.config.access.optionHostedExecutor'))
    .option('--ipv4 <cidrs>', t('commands.config.access.optionIpv4'))
    .option('--ipv6 <cidrs>', t('commands.config.access.optionIpv6'))
    .option('--clear', t('commands.config.access.ranges.optionClear'))
    .action(async (options: RangeOptions & { clear?: boolean }) => {
      try {
        await runRanges(options, program.opts().output as OutputFormat);
      } catch (error) {
        handleError(error);
      }
    });
}

/** Print the config-wide ranges (the bare `config access ranges`). */
async function showDefaultRanges(format: OutputFormat): Promise<void> {
  const current = (await configService.getAccess())?.sourceRanges;
  if (format !== 'table') {
    outputService.print(current ?? {}, format);
    return;
  }
  if (current) {
    outputService.info(
      t('commands.config.access.ranges.current', { ranges: formatRanges(current) })
    );
  } else {
    outputService.info(t('commands.config.access.ranges.none'));
  }
}

async function runRanges(
  options: RangeOptions & { clear?: boolean },
  format: OutputFormat
): Promise<void> {
  const ranges = rangesFromOptions(options);
  if (options.clear && ranges) {
    throw new ValidationError(t('commands.config.access.ranges.clearConflict'));
  }
  if (options.clear) {
    await configService.updateAccess((current) => setDefaultRanges(current, undefined));
    outputService.success(t('commands.config.access.ranges.cleared'));
    return;
  }
  if (!ranges) {
    await showDefaultRanges(format);
    return;
  }
  await configService.updateAccess((current) => setDefaultRanges(current, ranges));
  outputService.success(
    t('commands.config.access.ranges.success', { ranges: formatRanges(ranges) })
  );
}

function registerList(access: Command, program: Command): void {
  access
    .command('list')
    .description(t('commands.config.access.list.description'))
    .action(async () => {
      try {
        const current = await configService.getAccess();
        const rows = accessKeyRows(current);
        const format = program.opts().output as OutputFormat;
        if (format !== 'table') {
          outputService.print(rows, format);
          return;
        }
        if (current?.sourceRanges) {
          outputService.info(
            t('commands.config.access.ranges.current', {
              ranges: formatRanges(current.sourceRanges),
            })
          );
        }
        if (rows.length === 0) {
          outputService.info(t('commands.config.access.list.noKeys'));
          return;
        }
        const display = rows.map((row) => ({
          ...row,
          restrict: row.restrict ? 'yes' : 'no',
          sourceRanges: row.sourceRanges ? formatRanges(row.sourceRanges as SourceRanges) : '-',
          machines: (row.machines as string[]).join(', ') || '-',
        }));
        outputService.print(outputService.format(display, format));
      } catch (error) {
        handleError(error);
      }
    });
}

export function registerAccessCommands(config: Command, program: Command): void {
  const access = config
    .command('access')
    .summary(t('commands.config.access.descriptionShort'))
    .description(t('commands.config.access.description'));
  registerAdd(access);
  registerRemove(access);
  registerRanges(access, program);
  registerList(access, program);
}

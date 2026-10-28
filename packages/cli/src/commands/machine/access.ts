/**
 * `rdc machine access set|remove|show|push <machine>`: bind the config's access
 * keys to a machine and write them into its authorized_keys
 * (agent/plans/PLAN-ssh-key-source-ranges.md, Design 4). `set`, `remove` and
 * `show` edit or read the config only; `push` reaches the machine. Mirrors
 * `machine infra set|show|push` (infra.ts).
 */

import {
  type AccessConfig,
  type AccessKeyBinding,
  bindingSourceRanges,
  resolveAccessSourceRanges,
  type SourceRanges,
} from '@rediacc/shared/config-schema';
import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import type { AccessPushReport } from '../../services/machine/access-push.js';
import type { OutputFormat } from '../../types/index.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { omitKey } from '../../utils/omit-key.js';
import { assertValidAccess, type RangeOptions, rangesFromOptions } from '../config-access.js';

/**
 * Bind `keyName` to `machineName`. Given ranges replace the binding's own
 * (`{ sourceRanges }`); `clearRanges` drops them so the key's (or the config's)
 * ranges apply (`true`); neither keeps what the binding had, and a new binding
 * without ranges is `true`.
 */
export function bindAccessKey(
  access: AccessConfig,
  machineName: string,
  keyName: string,
  options: { ranges?: SourceRanges; clearRanges?: boolean }
): AccessConfig {
  const key = access.keys?.[keyName];
  if (key === undefined) {
    throw new ValidationError(t('commands.config.access.keyNotFound', { key: keyName }));
  }
  let binding: AccessKeyBinding = key.machines?.[machineName] ?? true;
  if (options.ranges !== undefined) binding = { sourceRanges: options.ranges };
  else if (options.clearRanges) binding = true;
  return assertValidAccess({
    ...access,
    keys: {
      ...access.keys,
      [keyName]: { ...key, machines: { ...(key.machines ?? {}), [machineName]: binding } },
    },
  });
}

/**
 * Drop the binding. The machine need not exist any more, so a binding left
 * behind by an interrupted `machine remove` can still be dropped.
 */
function unbindAccessKey(access: AccessConfig, machineName: string, keyName: string): AccessConfig {
  const key = access.keys?.[keyName];
  if (key === undefined) {
    throw new ValidationError(t('commands.config.access.keyNotFound', { key: keyName }));
  }
  if (key.machines?.[machineName] === undefined) {
    throw new ValidationError(
      t('commands.machine.access.notBound', { key: keyName, name: machineName })
    );
  }
  const machines = omitKey(key.machines, machineName);
  return assertValidAccess({
    ...access,
    keys: { ...access.keys, [keyName]: { ...key, machines } },
  });
}

/** Where a binding's ranges come from: the binding, the key, or the config. */
function rangesSource(access: AccessConfig, keyName: string, machineName: string): string {
  const key = access.keys?.[keyName];
  if (bindingSourceRanges(key?.machines?.[machineName])) return 'machine';
  if (key?.sourceRanges) return 'key';
  return 'config';
}

/** One row per access key bound to `machineName`, with the ranges it resolves to there. */
function machineAccessRows(
  access: AccessConfig | undefined,
  machineName: string
): Record<string, unknown>[] {
  if (access === undefined) return [];
  return Object.entries(access.keys ?? {})
    .filter(([, key]) => key.machines?.[machineName] !== undefined)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, key]) => ({
      key: name,
      restrict: key.restrict !== false,
      sourceRanges: resolveAccessSourceRanges(access, name, machineName) ?? null,
      rangesFrom: rangesSource(access, name, machineName),
    }));
}

function formatRanges(ranges: SourceRanges | null | undefined): string {
  if (!ranges) return '-';
  return [...(ranges.ipv4 ?? []), ...(ranges.ipv6 ?? [])].join(', ');
}

/** The table-mode rendering of a push report: one line per change, then the outcome. */
function printPushReport(report: AccessPushReport, dryRun: boolean): void {
  for (const change of report.changes) {
    outputService.info(
      t('commands.machine.access.push.change', {
        action: change.action,
        line: change.line,
        key: change.key,
      })
    );
  }
  const params = { name: report.machine, path: report.path };
  if (dryRun) outputService.info(t('commands.machine.access.push.dryRun', params));
  else if (report.written) outputService.success(t('commands.machine.access.push.success', params));
  else outputService.info(t('commands.machine.access.push.unchanged', params));
}

function registerSet(access: Command): void {
  access
    .command('set')
    .argument('<machine>', t('options.machine'))
    .summary(t('commands.machine.access.set.descriptionShort'))
    .description(t('commands.machine.access.set.description'))
    .requiredOption('--key <key>', t('commands.machine.access.optionKey'))
    .option('--ipv4 <cidrs>', t('commands.config.access.optionIpv4'))
    .option('--ipv6 <cidrs>', t('commands.config.access.optionIpv6'))
    .option('--clear-ranges', t('commands.machine.access.set.optionClearRanges'))
    .action(async (machineName: string, options: RangeOptions & Record<string, unknown>) => {
      try {
        // An unknown machine is refused before anything is written.
        await configService.getLocalMachine(machineName);
        const ranges = rangesFromOptions({ ipv4: options.ipv4, ipv6: options.ipv6 });
        if (options.clearRanges && ranges) {
          throw new ValidationError(t('commands.machine.access.set.clearConflict'));
        }
        const keyName = String(options.key);
        await configService.updateAccess((current) =>
          bindAccessKey(current, machineName, keyName, {
            ranges,
            clearRanges: options.clearRanges === true,
          })
        );
        outputService.success(
          t('commands.machine.access.set.success', { key: keyName, name: machineName })
        );
      } catch (error) {
        handleError(error);
      }
    });
}

function registerRemove(access: Command): void {
  access
    .command('remove')
    .argument('<machine>', t('options.machine'))
    .description(t('commands.machine.access.remove.description'))
    .requiredOption('--key <key>', t('commands.machine.access.optionKey'))
    .action(async (machineName: string, options: { key: string }) => {
      try {
        await configService.updateAccess((current) =>
          unbindAccessKey(current, machineName, options.key)
        );
        outputService.success(
          t('commands.machine.access.remove.success', { key: options.key, name: machineName })
        );
      } catch (error) {
        handleError(error);
      }
    });
}

function registerShow(access: Command, program: Command): void {
  access
    .command('show')
    .argument('<machine>', t('options.machine'))
    .description(t('commands.machine.access.show.description'))
    .action(async (machineName: string) => {
      try {
        const machine = await configService.getLocalMachine(machineName);
        const rows = machineAccessRows(await configService.getAccess(), machineName);
        const format = program.opts().output as OutputFormat;
        if (format !== 'table') {
          outputService.print(rows, format);
          return;
        }
        outputService.info(
          t('commands.machine.access.show.path', { user: machine.user, name: machineName })
        );
        if (rows.length === 0) {
          outputService.info(t('commands.machine.access.show.noKeys', { name: machineName }));
          return;
        }
        const display = rows.map((row) => ({
          ...row,
          restrict: row.restrict ? 'yes' : 'no',
          sourceRanges: formatRanges(row.sourceRanges as SourceRanges | null),
        }));
        outputService.print(outputService.format(display, format));
      } catch (error) {
        handleError(error);
      }
    });
}

function registerPush(access: Command, program: Command): void {
  access
    .command('push')
    .argument('<machine>', t('options.machine'))
    .summary(t('commands.machine.access.push.descriptionShort'))
    .description(t('commands.machine.access.push.description'))
    .option('--dry-run', t('commands.machine.access.push.optionDryRun'))
    .action(async (machineName: string, options: { dryRun?: boolean }) => {
      try {
        await configService.getLocalMachine(machineName);
        const { pushAccess } = await import('../../services/machine/access-push.js');
        const dryRun = options.dryRun === true;
        const report = await pushAccess(machineName, { dryRun });
        const format = program.opts().output as OutputFormat;
        if (format === 'table') printPushReport(report, dryRun);
        else outputService.print(report, format);
      } catch (error) {
        handleError(error);
      }
    });
}

/** `machine access set|remove|show|push <machine>`. */
export function registerAccessCommands(machine: Command, program: Command): void {
  const access = machine
    .command('access')
    .summary(t('commands.machine.access.descriptionShort'))
    .description(t('commands.machine.access.description'));
  registerSet(access);
  registerRemove(access);
  registerShow(access, program);
  registerPush(access, program);
}

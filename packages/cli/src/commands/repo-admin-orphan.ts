/**
 * `repo admin orphan {list,delete}`: repository images on a machine that no config entry names (worklist #48d790e1).
 *
 * `repo delete` resolves its ref through the config, so an image whose GUID left every config (no entry, no archived
 * record) had no verb that could remove it. `list` shows every image on the machine with the verdict
 * `machine prune --orphaned-repos` would reach; `delete` removes exactly one orphan by GUID through the same renet
 * `repository_delete` call, after refusing a GUID any readable config names, a mounted or running image (unless
 * --force-delete-mounted, the flag `machine prune` uses for the same preflight), and, for an agent, an image the
 * machine does not mark as a fork (the grand guard).
 *
 * What it deliberately does NOT do, unlike `repo delete`: it re-renders no backup schedules (reconcileBackupSchedules
 * renders from the config's repositories, and an orphan delete changes none of them, so a re-render would only
 * rewrite unrelated units), and it settles no config entry, cloud backup lineage or licence on the account server,
 * because there is no config record to read any of them from. renet's delete removes the machine-side licence blobs
 * and backup state of the GUID itself.
 */

import { isValidGuid } from '@rediacc/shared/validation';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import {
  applyExecutorEvents,
  classifyMachineRepos,
  deleteRepoImageByGuid,
  readExecutorEvents,
} from '../services/repo/orphan-repos.js';
import { notFound, stateMismatch } from '../utils/cli-exit-error.js';
import { CMD, enforceResolvedTarget } from '../utils/command-policy.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { assertMachineExists } from './_validate.js';

interface OrphanDeleteOptions {
  yes?: boolean;
  dryRun?: boolean;
  forceDeleteMounted?: boolean;
  debug?: boolean;
}

/** Split `<guid>@<machine>`; the GUID is lowercased because renet and the vault name images in lowercase. */
function parseOrphanRef(ref: string): { guid: string; machine: string } {
  const at = ref.lastIndexOf('@');
  const guid = at > 0 ? ref.slice(0, at) : '';
  const machine = at > 0 ? ref.slice(at + 1) : '';
  if (!isValidGuid(guid) || machine === '') {
    throw new ValidationError(t('commands.repo.admin.orphan.delete.badRef', { ref }));
  }
  return { guid: guid.toLowerCase(), machine };
}

async function handleOrphanList(
  machine: string,
  options: { debug?: boolean; executorEvents?: string }
): Promise<void> {
  await assertMachineExists(machine);
  const classified = await classifyMachineRepos(machine, options);
  const rows = options.executorEvents
    ? applyExecutorEvents(classified, await readExecutorEvents(options.executorEvents), machine)
    : classified;
  const format = getOutputFormat();
  if (rows.length === 0 && format === 'table') {
    outputService.info(t('commands.repo.admin.orphan.list.none', { machine }));
    return;
  }
  outputService.print(rows, format);
}

/**
 * The decision for an orphan delete. The config names no orphan, so the machine's own fork marker
 * says grand or fork: an image renet does not mark as a fork is judged as a grand, and an agent
 * needs REDIACC_ALLOW_GRAND_REPO=<guid> (or `*`). The ops VM fleet is exempt by the machine.
 */
function enforceOrphanDelete(guid: string, machine: string, isFork: boolean): Promise<void> {
  return enforceResolvedTarget(CMD.REPO_ADMIN_ORPHAN_DELETE, {
    machine,
    identified: { name: guid, state: isFork ? 'fork' : 'grand' },
  });
}

async function handleOrphanDelete(ref: string, options: OrphanDeleteOptions): Promise<void> {
  const { guid, machine } = parseOrphanRef(ref);
  await assertMachineExists(machine);
  const rows = await classifyMachineRepos(machine, { debug: options.debug });
  const row = rows.find((r) => r.guid.toLowerCase() === guid);
  if (!row) {
    throw notFound(t('commands.repo.admin.orphan.delete.notOnMachine', { guid, machine }));
  }
  if (row.verdict === 'protected') {
    throw stateMismatch(
      t('commands.repo.admin.orphan.delete.protected', { guid, reason: row.reason })
    );
  }
  if ((row.mounted || row.running) && !options.forceDeleteMounted) {
    throw stateMismatch(
      t('commands.repo.admin.orphan.delete.mounted', {
        guid,
        machine,
        containers: row.containers,
      })
    );
  }
  await enforceOrphanDelete(guid, machine, row.isFork);

  if (options.dryRun) {
    outputService.print(
      {
        dryRun: true,
        guid,
        machine,
        mounted: row.mounted,
        running: row.running,
        containers: row.containers,
        size: row.size,
      },
      getOutputFormat()
    );
    return;
  }

  if (!options.yes) {
    const { askConfirm } = await import('../utils/prompt.js');
    const confirmed = await askConfirm(
      t('commands.repo.admin.orphan.delete.confirm', { guid, machine, size: row.size })
    );
    if (!confirmed) {
      outputService.info(t('status.cancelled'));
      return;
    }
  }

  outputService.info(t('commands.repo.admin.orphan.delete.starting', { guid, machine }));
  const result = await deleteRepoImageByGuid(machine, guid, { debug: options.debug });
  if (!result.success) {
    renderLocalExecutionFailure(result, t('commands.repo.admin.orphan.delete.failed', { guid }));
    return;
  }
  outputService.success(t('commands.repo.admin.orphan.delete.completed', { guid, machine }));
}

/** Register `repo admin orphan {list,delete}` onto the `repo admin` parent. */
export function registerRepoAdminOrphan(admin: Command): void {
  const orphan = admin.command('orphan').description(t('commands.repo.admin.orphan.description'));

  orphan
    .command('list')
    .summary(t('commands.repo.admin.orphan.list.descriptionShort'))
    .description(t('commands.repo.admin.orphan.list.description'))
    .argument('<machine>', t('options.machineName'))
    .option('--executor-events <file>', t('commands.repo.admin.orphan.list.executorEventsOption'))
    .option('--debug', t('options.debug'))
    .action(async (machine: string, options: { debug?: boolean; executorEvents?: string }) => {
      try {
        await handleOrphanList(machine, options);
      } catch (error) {
        handleError(error);
      }
    });

  orphan
    .command('delete')
    .summary(t('commands.repo.admin.orphan.delete.descriptionShort'))
    .description(t('commands.repo.admin.orphan.delete.description'))
    .argument('<ref>', t('commands.repo.admin.orphan.delete.refArg'))
    .option('--force-delete-mounted', t('commands.repo.admin.orphan.delete.forceOption'))
    .option('-y, --yes', t('options.yes'))
    .option('--dry-run', t('options.dryRun'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string, options: OrphanDeleteOptions) => {
      try {
        await handleOrphanDelete(ref, options);
      } catch (error) {
        handleError(error);
      }
    });
}

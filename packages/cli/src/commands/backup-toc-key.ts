/**
 * `rdc backup toc-key sync <repo> [--replace] [--dry-run]`: install or re-issue the browse-listing
 * public key on the machine that holds a repository.
 *
 * The key is derived from the repository credential here, so only the public line reaches the
 * machine. The credential travels on stdin, and only for `--replace`, because renet proves the
 * passphrase before it swaps a key it already holds. The comparison and install logic is the
 * schedule deploy's (services/backup/backup-schedule-toc-key.ts); this is the on-demand entry.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { DEFAULT_DATASTORE } from '../services/account/license-machine.js';
import {
  syncTocKeys,
  type TocKeyResult,
  type TocKeyTransport,
  tocKeyWarnings,
} from '../services/backup/backup-schedule-toc-key.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { machineConnections } from '../services/machine/machine-connection.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';

/** Outcomes that leave the machine without the key this credential derives. */
const FAILING = new Set<TocKeyResult['outcome']>([
  'differs',
  'no-credential',
  'refused',
  'unreadable',
]);

function execTransport(sftp: {
  execStreaming(
    command: string,
    options: { stdin?: string; onStdout: (d: Buffer) => void; onStderr: (d: Buffer) => void }
  ): Promise<number>;
}): TocKeyTransport {
  return {
    async run(command, stdin) {
      let stdout = '';
      const exitCode = await sftp.execStreaming(command, {
        ...(stdin === undefined ? {} : { stdin }),
        onStdout: (data) => {
          stdout += data.toString();
        },
        onStderr: () => {},
      });
      return { exitCode, stdout };
    },
  };
}

/** Sync the key of one repository. Exit 1 unless the machine ends up holding the derived key. */
async function runTocKeySync(
  repoRef: string,
  options: { replace?: boolean; dryRun?: boolean }
): Promise<TocKeyResult[]> {
  const { repoKey, machineName } = await resolveRepoRef(repoRef);
  const repo = await configService.getRepository(repoKey);
  if (!repo) throw new ValidationError(`Repository "${repoKey}" not found in this config.`);
  const placed = await recordedDatastoreMount(repoKey);
  const lease = await machineConnections.acquire(machineName);
  try {
    const target = {
      ref: repoKey,
      guid: repo.repositoryGuid,
      lineage: repo.grandGuid ?? repo.repositoryGuid,
      credential: repo.credential,
      datastore: placed ?? lease.machine.datastore ?? DEFAULT_DATASTORE,
    };
    return await syncTocKeys(
      execTransport(lease.sftp),
      DEFAULTS.CONTEXT.RENET_BINARY,
      [target],
      options
    );
  } finally {
    lease.release();
  }
}

export function registerBackupTocKey(backup: Command): void {
  const tocKey = backup.command('toc-key').description(t('commands.backup.tocKey.description'));
  tocKey
    .command('sync')
    .argument('<repo-ref>', t('options.repoRef'))
    .description(t('commands.backup.tocKey.syncDescription'))
    .option('--replace', t('commands.backup.tocKey.optionReplace'))
    .option('--dry-run', t('commands.backup.tocKey.optionDryRun'))
    .action(async (repoRef: string, options: { replace?: boolean; dryRun?: boolean }) => {
      try {
        const results = await runTocKeySync(repoRef, options);
        const format = getOutputFormat();
        outputService.print({ results }, format === 'table' ? 'json' : format);
        for (const warning of tocKeyWarnings(results)) outputService.warn(warning);
        if (results.some((r) => FAILING.has(r.outcome))) setExitCode(1);
      } catch (error) {
        handleError(error);
      }
    });
}

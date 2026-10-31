import { join, resolve as resolvePath } from 'node:path';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { runStoreFetch } from '../services/backup-image/store-fetch.js';
import { runDownload, runUpload } from '../services/backup-image/transfer.js';
import { configService } from '../services/config/config-resources.js';
import { setExitCode, writeStdout } from '../services/core/request-context.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { resolveRepoRefLocal } from '../utils/repo-target.js';
import {
  kibps,
  parseRetries,
  realDownloadDeps,
  realStoreFetchDeps,
  realUploadDeps,
  withInterrupt,
} from './backup-image-deps.js';

export { hashFile, selectAllTargets } from './backup-image-deps.js';
export { runDownload, runUpload };

function assertStoreSelection(refs: string[], options: DownloadCliOptions): void {
  if (options.machine) throw new ValidationError(t('errors.backupImage.storeRefusesMachine'));
  if (options.checkpoint) throw new ValidationError(t('errors.backupImage.storeRefusesCheckpoint'));
  if (options.includeForks || options.all) {
    throw new ValidationError(t('errors.backupImage.storeRefusesForks'));
  }
  if (refs.length !== 1) throw new ValidationError(t('errors.backupImage.storeNeedsOneRef'));
  // The machine download's transfer controls do not reach the store fetch;
  // refusing them beats silently running unlimited or unverified-looking.
  const ignored: [unknown, string][] = [
    [options.bwlimit, '--bwlimit'],
    [options.retries, '--retries'],
    [options.skipVerify, '--skip-verify'],
    [options.skipSpaceCheck, '--skip-space-check'],
  ];
  const given = ignored.find(([value]) => value !== undefined && value !== false);
  if (given)
    throw new ValidationError(t('errors.backupImage.storeRefusesOption', { option: given[1] }));
}

interface DownloadCliOptions {
  to: string;
  all?: boolean;
  machine?: string;
  includeForks?: boolean;
  bwlimit?: string;
  checkpoint?: boolean;
  retries?: string;
  skipVerify?: boolean;
  skipSpaceCheck?: boolean;
  store?: boolean;
  at?: string;
}

/** Repositories by name, or `--all -m <machine>`; never both, never neither. */
function assertDownloadSelection(refs: string[], options: DownloadCliOptions): void {
  if (options.all && refs.length > 0) {
    throw new ValidationError(t('errors.backupImage.allWithRefs'));
  }
  if (options.all && !options.machine) {
    throw new ValidationError(t('errors.backupImage.allNeedsMachine'));
  }
  if (!options.all && refs.length === 0) {
    throw new ValidationError(t('errors.backupImage.refsRequired'));
  }
}

/** The --store branch: no machine, so the machine-path options are refused by name. */
async function runStoreDownloadCommand(refs: string[], options: DownloadCliOptions): Promise<void> {
  assertStoreSelection(refs, options);
  const json = getOutputFormat() === 'json';
  const { name, tag, repoKey } = await resolveRepoRefLocal(refs[0]);
  const dest = join(resolvePath(options.to), `${name}.${tag}.img`);
  const result = await withInterrupt((signal) =>
    runStoreFetch({ ref: repoKey, dest, at: options.at, signal }, realStoreFetchDeps())
  );
  const { record } = result;
  if (json) {
    writeStdout(
      `${JSON.stringify({ status: record.status, image: dest, snapshotId: result.snapshotId, bytesFetched: record.bytesFetched ?? 0 })}\n`
    );
    return;
  }
  writeStdout(
    `${t('commands.backup.download.storeDone', { repo: repoKey, snapshot: result.snapshotId, image: dest, bytes: String(record.bytesFetched ?? 0) })}\n`
  );
  if (process.platform !== 'linux') {
    writeStdout(`${t('commands.backup.download.storeOfflineNote')}\n`);
  }
}

function registerDownload(backup: Command): void {
  backup
    .command('download')
    .argument('[refs...]', t('commands.backup.download.argRefs'))
    .description(t('commands.backup.download.description'))
    .requiredOption('--to <dir>', t('commands.backup.download.optionTo'))
    .option('--all', t('commands.backup.download.optionAll'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--include-forks', t('commands.backup.download.optionIncludeForks'))
    .option('--bwlimit <rate>', t('commands.backup.download.optionBwlimit'))
    .option('--checkpoint', t('commands.backup.download.optionCheckpoint'))
    .option('--retries <n>', t('commands.backup.download.optionRetries'))
    .option('--skip-verify', t('commands.backup.download.optionSkipVerify'))
    .option('--skip-space-check', t('commands.backup.download.optionSkipSpaceCheck'))
    .option('--store', t('commands.backup.download.optionStore'))
    .option('--at <time|snapshot>', t('commands.backup.download.optionAt'))
    .action(async (refs: string[], options: DownloadCliOptions) => {
      try {
        if (options.store) {
          await runStoreDownloadCommand(refs, options);
          return;
        }
        if (options.at) throw new ValidationError(t('errors.backupImage.atNeedsStore'));
        assertDownloadSelection(refs, options);
        const json = getOutputFormat() === 'json';
        const { exitCode } = await withInterrupt((signal) =>
          runDownload(
            {
              to: resolvePath(options.to),
              refs,
              config: configService.getEffectiveConfigName(),
              all: options.all ? options.machine : undefined,
              includeForks: options.includeForks,
              bwlimitKiBps: kibps(options.bwlimit),
              checkpoint: options.checkpoint,
              retries: parseRetries(options.retries),
              skipVerify: options.skipVerify,
              skipSpaceCheck: options.skipSpaceCheck,
              output: json ? 'json' : 'human',
            },
            realDownloadDeps(signal, { checkpoint: options.checkpoint, json })
          )
        );
        setExitCode(exitCode);
      } catch (error) {
        handleError(error);
      }
    });
}

interface UploadCliOptions {
  to: string;
  as?: string;
  datastore?: string;
  fromRepo?: string;
  bwlimit?: string;
  retries?: string;
  up?: boolean;
  skipVerify?: boolean;
  debug?: boolean;
}

function registerUpload(backup: Command): void {
  backup
    .command('upload')
    .argument('<image-file>', t('commands.backup.upload.argImage'))
    .description(t('commands.backup.upload.description'))
    .requiredOption('--to <machine>', t('commands.backup.upload.optionTo'))
    .option('--as <name>', t('commands.backup.upload.optionAs'))
    .option('--datastore <name>', t('commands.backup.upload.optionDatastore'))
    .option('--from-repo <name>', t('commands.backup.upload.optionFromRepo'))
    .option('--bwlimit <rate>', t('commands.backup.download.optionBwlimit'))
    .option('--retries <n>', t('commands.backup.download.optionRetries'))
    .option('--up', t('commands.backup.upload.optionUp'))
    .option('--skip-verify', t('commands.backup.upload.optionSkipVerify'))
    .option('--debug', t('options.debug'))
    .action(async (image: string, options: UploadCliOptions) => {
      try {
        const json = getOutputFormat() === 'json';
        const { exitCode } = await withInterrupt(async (signal) =>
          runUpload(
            {
              image: resolvePath(image),
              to: options.to,
              as: options.as,
              datastore: options.datastore,
              fromRepo: options.fromRepo,
              skipVerify: options.skipVerify,
              bwlimitKiBps: kibps(options.bwlimit),
              retries: parseRetries(options.retries),
              up: options.up,
              config: configService.getEffectiveConfigName(),
              output: json ? 'json' : 'human',
            },
            await realUploadDeps(signal, {
              datastore: options.datastore,
              debug: options.debug,
              json,
            })
          )
        );
        setExitCode(exitCode);
      } catch (error) {
        handleError(error);
      }
    });
}

/** Registers `backup download` and `backup upload` under the `backup` noun. */
export function registerBackupImageCommands(backup: Command): void {
  registerDownload(backup);
  registerUpload(backup);
}

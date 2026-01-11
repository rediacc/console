import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { createTempSSHKeyFile, removeTempSSHKeyFile } from '@rediacc/shared-desktop/ssh';
import {
  executeRsync,
  getRsyncPreview,
  formatChangesSummary,
  formatDetailedChanges,
  type RsyncExecutorOptions,
  type RsyncChanges,
} from '@rediacc/shared-desktop/sync';
import chalk from 'chalk';
import { Command } from 'commander';
import ora from 'ora';
import { t } from '../i18n/index.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { getConnectionVaults } from '../utils/connectionDetails.js';
import { handleError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import type { SyncProgress } from '@rediacc/shared-desktop/types';

interface SyncUploadOptions {
  team?: string;
  machine?: string;
  repository?: string;
  local?: string;
  remote?: string;
  mirror?: boolean;
  verify?: boolean;
  confirm?: boolean;
  exclude?: string[];
  dryRun?: boolean;
  [key: string]: unknown;
}

interface SyncDownloadOptions {
  team?: string;
  machine?: string;
  repository?: string;
  local?: string;
  remote?: string;
  mirror?: boolean;
  verify?: boolean;
  confirm?: boolean;
  exclude?: string[];
  dryRun?: boolean;
  [key: string]: unknown;
}

interface RsyncConnectionDetails {
  host: string;
  user: string;
  port: number;
  privateKey: string;
  remotePath: string;
  known_hosts: string;
  universalUser?: string;
}

/**
 * Gets rsync connection details from the API using type-safe endpoints
 */
async function getRsyncConnectionDetails(
  teamName: string,
  machineName: string,
  repositoryName: string
): Promise<RsyncConnectionDetails> {
  // Fetch vault data using type-safe API
  const { machineVault, teamVault, repositoryVault } = await getConnectionVaults(
    teamName,
    machineName,
    repositoryName
  );

  const host = (machineVault.ip ?? machineVault.host) as string | undefined;
  const port = (machineVault.port ?? 22) as number;
  const privateKey = (teamVault.SSH_PRIVATE_KEY ?? teamVault.sshPrivateKey) as string | undefined;
  const knownHosts = (machineVault.known_hosts ?? '') as string;
  const datastore = (machineVault.datastore ?? '/mnt/rediacc') as string;
  const universalUser = machineVault.universalUser as string | undefined;

  if (!host) {
    throw new Error(t('errors.sync.noIpAddress', { machine: machineName }));
  }

  if (!privateKey) {
    throw new Error(t('errors.sync.noPrivateKey', { team: teamName }));
  }

  if (!knownHosts) {
    throw new Error(t('errors.sync.noHostKey', { machine: machineName }));
  }

  const repoVault = repositoryVault ?? {};
  const repositoryPath = (repoVault.path ?? `/home/${repositoryName}`) as string;

  // Build remote path: datastore/repository_path
  const remotePath = `${datastore}${repositoryPath}`;

  return {
    host,
    user: repositoryName, // Use repository name as SSH user
    port,
    privateKey,
    remotePath,
    known_hosts: knownHosts,
    universalUser,
  };
}

/**
 * Formats bytes to human-readable string
 */
function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${Number.parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

/**
 * Interactive confirmation loop with details option (matches Python CLI behavior)
 * Prompts [y/N/d(etails)] and allows viewing detailed file list before confirming
 *
 * @param changes - The rsync changes to confirm
 * @returns Promise<boolean> - true if user confirms, false if cancelled
 */
async function interactiveConfirmation(changes: RsyncChanges): Promise<boolean> {
  const readline = await import('node:readline');

  // Show summary first
  // eslint-disable-next-line no-console
  console.log(formatChangesSummary(changes));

  // Create readline interface
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  const ask = (): Promise<string> =>
    new Promise((resolve) => {
      rl.question(t('prompts.syncConfirm'), resolve);
    });

  // Interactive loop
  let answered = false;
  let proceed = false;

  while (!answered) {
    const answer = (await ask()).toLowerCase().trim();

    switch (answer) {
      case 'y':
      case 'yes':
        proceed = true;
        answered = true;
        break;
      case 'n':
      case 'no':
      case '':
        proceed = false;
        answered = true;
        break;
      case 'd':
      case 'details':
        // Show detailed file list with colorized output
        // eslint-disable-next-line no-console
        console.log(
          formatDetailedChanges(changes, {
            colorNew: chalk.green,
            colorModified: chalk.yellow,
            colorDeleted: chalk.red,
            colorDim: chalk.dim,
          })
        );
        // eslint-disable-next-line no-console
        console.log(`\n${formatChangesSummary(changes)}`);
        // Loop continues to ask again
        break;
      default:
        // eslint-disable-next-line no-console
        console.log(t('prompts.syncConfirmHelp'));
    }
  }

  rl.close();
  return proceed;
}

function hasNoChanges(changes: RsyncChanges): boolean {
  return (
    changes.newFiles.length === 0 &&
    changes.modifiedFiles.length === 0 &&
    changes.deletedFiles.length === 0
  );
}

async function handleConfirmMode(
  rsyncOptions: RsyncExecutorOptions,
  options: { confirm?: boolean; dryRun?: boolean }
): Promise<boolean> {
  if (!options.confirm || options.dryRun) return true;

  // eslint-disable-next-line no-console
  console.log(t('commands.sync.previewingChanges'));

  const changes = await getRsyncPreview(rsyncOptions);

  if (hasNoChanges(changes)) {
    // eslint-disable-next-line no-console
    console.log(t('commands.sync.noChanges'));
    return false;
  }

  const proceed = await interactiveConfirmation(changes);
  if (!proceed) {
    // eslint-disable-next-line no-console
    console.log(t('commands.sync.cancelled'));
    return false;
  }

  return true;
}

async function handleDryRun(rsyncOptions: RsyncExecutorOptions): Promise<void> {
  // eslint-disable-next-line no-console
  console.log(t('commands.sync.dryRunHeader'));
  const changes = await getRsyncPreview(rsyncOptions);
  // eslint-disable-next-line no-console
  console.log(formatChangesSummary(changes));
}

function displaySyncResult(
  result: {
    success: boolean;
    filesTransferred: number;
    bytesTransferred: number;
    duration: number;
    errors: string[];
  },
  spinner: ReturnType<typeof ora>,
  mode: 'upload' | 'download'
): void {
  if (result.success) {
    spinner.succeed(t(`commands.sync.${mode}.completed`, { count: result.filesTransferred }));
    if (result.bytesTransferred > 0) {
      // eslint-disable-next-line no-console
      console.log(t('commands.sync.totalSize', { size: formatBytes(result.bytesTransferred) }));
    }
    // eslint-disable-next-line no-console
    console.log(t('commands.sync.duration', { seconds: (result.duration / 1000).toFixed(1) }));
  } else {
    spinner.fail(t(`commands.sync.${mode}.failed`));
    if (result.errors.length > 0) {
      console.error(t('commands.sync.errors'));
      for (const err of result.errors) {
        console.error(`  ${err}`);
      }
    }
    process.exitCode = 1;
  }
}

async function executeSyncWithProgress(
  rsyncOptions: RsyncExecutorOptions,
  mode: 'upload' | 'download'
): Promise<void> {
  const spinner = ora(t(`commands.sync.${mode}.starting`)).start();

  rsyncOptions.onProgress = (progress: SyncProgress) => {
    spinner.text = t(`commands.sync.${mode}.progress`, {
      percentage: progress.percentage,
      file: progress.currentFile,
      speed: progress.speed,
    });
  };

  const result = await executeRsync(rsyncOptions);
  displaySyncResult(result, spinner, mode);
}

/**
 * Uploads files to a repository
 */
async function syncUpload(options: SyncUploadOptions): Promise<void> {
  const opts = await contextService.applyDefaults(options);

  if (!opts.team) {
    throw new Error(t('errors.teamRequired'));
  }
  if (!opts.machine) {
    throw new Error(t('errors.machineRequired'));
  }
  if (!opts.repository) {
    throw new Error(t('errors.repositoryRequired'));
  }

  let localPath = resolve(options.local ?? process.cwd());

  if (!existsSync(localPath)) {
    throw new Error(t('errors.sync.localPathNotFound', { path: localPath }));
  }

  if (!localPath.endsWith('/')) {
    localPath += '/';
  }

  const connectionDetails = await withSpinner(t('commands.sync.fetchingDetails'), () =>
    getRsyncConnectionDetails(opts.team!, opts.machine!, opts.repository!)
  );

  const remotePath = options.remote
    ? `${connectionDetails.remotePath}/${options.remote}`
    : connectionDetails.remotePath;

  const keyFilePath = await createTempSSHKeyFile(connectionDetails.privateKey);

  try {
    const sshOptions = `-o StrictHostKeyChecking=yes -o UserKnownHostsFile=/dev/null -p ${connectionDetails.port} -i "${keyFilePath}"`;

    const rsyncOptions: RsyncExecutorOptions = {
      sshOptions,
      source: localPath,
      destination: `${connectionDetails.user}@${connectionDetails.host}:${remotePath}`,
      mirror: options.mirror,
      verify: options.verify,
      exclude: options.exclude,
      universalUser: connectionDetails.universalUser,
    };

    const shouldContinue = await handleConfirmMode(rsyncOptions, options);
    if (!shouldContinue) return;

    if (options.dryRun) {
      await handleDryRun(rsyncOptions);
      return;
    }

    await executeSyncWithProgress(rsyncOptions, 'upload');
  } finally {
    await removeTempSSHKeyFile(keyFilePath);
  }
}

/**
 * Downloads files from a repository
 */
async function syncDownload(options: SyncDownloadOptions): Promise<void> {
  const opts = await contextService.applyDefaults(options);

  if (!opts.team) {
    throw new Error(t('errors.teamRequired'));
  }
  if (!opts.machine) {
    throw new Error(t('errors.machineRequired'));
  }
  if (!opts.repository) {
    throw new Error(t('errors.repositoryRequired'));
  }

  const localPath = resolve(options.local ?? process.cwd());

  const connectionDetails = await withSpinner(t('commands.sync.fetchingDetails'), () =>
    getRsyncConnectionDetails(opts.team!, opts.machine!, opts.repository!)
  );

  const remotePath = options.remote
    ? `${connectionDetails.remotePath}/${options.remote}/`
    : `${connectionDetails.remotePath}/`;

  const keyFilePath = await createTempSSHKeyFile(connectionDetails.privateKey);

  try {
    const sshOptions = `-o StrictHostKeyChecking=yes -o UserKnownHostsFile=/dev/null -p ${connectionDetails.port} -i "${keyFilePath}"`;

    const rsyncOptions: RsyncExecutorOptions = {
      sshOptions,
      source: `${connectionDetails.user}@${connectionDetails.host}:${remotePath}`,
      destination: localPath,
      mirror: options.mirror,
      verify: options.verify,
      exclude: options.exclude,
      universalUser: connectionDetails.universalUser,
    };

    const shouldContinue = await handleConfirmMode(rsyncOptions, options);
    if (!shouldContinue) return;

    if (options.dryRun) {
      await handleDryRun(rsyncOptions);
      return;
    }

    await executeSyncWithProgress(rsyncOptions, 'download');
  } finally {
    await removeTempSSHKeyFile(keyFilePath);
  }
}

/**
 * Registers the sync commands
 */
export function registerSyncCommands(program: Command): void {
  const sync = program.command('sync').description(t('commands.sync.description'));

  sync
    .command('upload')
    .description(t('commands.sync.upload.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('-r, --repository <name>', t('options.repository'))
    .option('-l, --local <path>', t('options.localPath'))
    .option('--remote <path>', t('options.remotePath'))
    .option('--mirror', t('options.mirrorUpload'))
    .option('--verify', t('options.verifyChecksum'))
    .option('--confirm', t('options.confirmSync'))
    .option('--exclude <patterns...>', t('options.excludePatterns'))
    .option('--dry-run', t('options.dryRun'))
    .action(async (options: SyncUploadOptions) => {
      try {
        await authService.requireAuth();
        await syncUpload(options);
      } catch (error) {
        handleError(error);
      }
    });

  sync
    .command('download')
    .description(t('commands.sync.download.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('-r, --repository <name>', t('options.repository'))
    .option('-l, --local <path>', t('options.localPath'))
    .option('--remote <path>', t('options.remotePath'))
    .option('--mirror', t('options.mirrorDownload'))
    .option('--verify', t('options.verifyChecksum'))
    .option('--confirm', t('options.confirmSync'))
    .option('--exclude <patterns...>', t('options.excludePatterns'))
    .option('--dry-run', t('options.dryRun'))
    .action(async (options: SyncDownloadOptions) => {
      try {
        await authService.requireAuth();
        await syncDownload(options);
      } catch (error) {
        handleError(error);
      }
    });

  sync
    .command('status')
    .description(t('commands.sync.status.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('-r, --repository <name>', t('options.repository'))
    .option('-l, --local <path>', t('options.localPath'))
    .option('--remote <path>', t('options.remotePath'))
    .action(async (options: SyncDownloadOptions) => {
      try {
        await authService.requireAuth();
        // Run dry-run to see differences
        await syncDownload({ ...options, dryRun: true });
      } catch (error) {
        handleError(error);
      }
    });
}

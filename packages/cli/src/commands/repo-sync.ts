import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  createTempKnownHostsFile,
  createTempSSHKeyFile,
  removeTempKnownHostsFile,
  removeTempSSHKeyFile,
} from '@rediacc/shared-desktop/ssh';
import {
  executeRsync,
  formatChangesSummary,
  formatDetailedChanges,
  getRsyncPreview,
  type RsyncChanges,
  type RsyncExecutorOptions,
} from '@rediacc/shared-desktop/sync';
import type { SyncProgress } from '@rediacc/shared-desktop/types';
import chalk from 'chalk';
import type { Command } from 'commander';
import ora from 'ora';
import { t } from '../i18n/index.js';
import { getStateProvider } from '../providers/index.js';
import { authService } from '../services/auth.js';
import { configService } from '../services/config-resources.js';
import { deployRepoKeyIfNeeded } from '../services/repo-key-deployment.js';
import { provisionRenetToRemote, readSSHKey } from '../services/renet-execution.js';
import { getSSHConnectionDetails } from '../services/ssh-connection.js';
import { assertCommandPolicy, CMD, validateRemotePath } from '../utils/command-policy.js';
import { handleError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';

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

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${Number.parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

async function interactiveConfirmation(changes: RsyncChanges): Promise<boolean> {
  const readline = await import('node:readline');
  process.stdout.write(`${formatChangesSummary(changes)}\n`);

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  const ask = (): Promise<string> =>
    new Promise((resolve) => {
      rl.question(t('prompts.syncConfirm'), resolve);
    });

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
        process.stdout.write(
          `${formatDetailedChanges(changes, {
            colorNew: chalk.green,
            colorModified: chalk.yellow,
            colorDeleted: chalk.red,
            colorDim: chalk.dim,
          })}\n`
        );
        process.stdout.write(`\n${formatChangesSummary(changes)}\n`);
        break;
      default:
        process.stdout.write(`${t('prompts.syncConfirmHelp')}\n`);
    }
  }

  rl.close();
  return proceed;
}

function resolveUploadLocalPath(local: string | undefined): string {
  let localPath = resolve(local ?? process.cwd());
  if (!existsSync(localPath)) {
    throw new Error(t('errors.sync.localPathNotFound', { path: localPath }));
  }
  if (!localPath.endsWith('/')) {
    localPath += '/';
  }
  return localPath;
}

function hasNoChanges(changes: RsyncChanges): boolean {
  return (
    changes.newFiles.length === 0 &&
    changes.modifiedFiles.length === 0 &&
    changes.deletedFiles.length === 0
  );
}

async function ensureRenetProvisioned(machineName: string): Promise<void> {
  try {
    const localConfig = await configService.getLocalConfig();
    const machine = localConfig.machines[machineName];
    if (!machine) return;
    const teamKey = localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
    await provisionRenetToRemote(localConfig, machine, teamKey, {});
  } catch {
    // Non-fatal — sync may still work with existing renet on remote
  }
}

async function handleConfirmMode(
  rsyncOptions: RsyncExecutorOptions,
  options: { confirm?: boolean; dryRun?: boolean }
): Promise<boolean> {
  if (!options.confirm || options.dryRun) return true;

  process.stdout.write(`${t('commands.sync.previewingChanges')}\n`);

  const changes = await getRsyncPreview(rsyncOptions);

  if (hasNoChanges(changes)) {
    process.stdout.write(`${t('commands.sync.noChanges')}\n`);
    return false;
  }

  const proceed = await interactiveConfirmation(changes);
  if (!proceed) {
    process.stdout.write(`${t('commands.sync.cancelled')}\n`);
    return false;
  }

  return true;
}

async function handleDryRun(rsyncOptions: RsyncExecutorOptions): Promise<void> {
  process.stdout.write(`${t('commands.sync.dryRunHeader')}\n`);
  const changes = await getRsyncPreview(rsyncOptions);
  process.stdout.write(`${formatChangesSummary(changes)}\n`);
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
      process.stdout.write(
        `${t('commands.sync.totalSize', { size: formatBytes(result.bytesTransferred) })}\n`
      );
    }
    process.stdout.write(
      `${t('commands.sync.duration', { seconds: (result.duration / 1000).toFixed(1) })}\n`
    );
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

async function syncUpload(options: SyncUploadOptions): Promise<void> {
  const opts = await configService.applyDefaults(options);

  const provider = await getStateProvider();
  if (provider.isCloud && !opts.team) {
    throw new Error(t('errors.teamRequired'));
  }
  if (!opts.machine) {
    throw new Error(t('errors.machineRequired'));
  }
  if (!opts.repository) {
    throw new Error(t('errors.repositoryRequired'));
  }

  await assertCommandPolicy(CMD.REPO_SYNC_UPLOAD, opts.repository);
  if (options.remote) validateRemotePath(options.remote);

  const localPath = resolveUploadLocalPath(options.local);

  await ensureRenetProvisioned(opts.machine!);

  if (opts.repository) {
    await deployRepoKeyIfNeeded(opts.repository, opts.machine);
  }

  const details = await withSpinner(t('commands.sync.fetchingDetails'), () =>
    getSSHConnectionDetails(opts.team!, opts.machine!, opts.repository)
  );

  const baseRemotePath =
    details.workingDirectory ?? `${details.datastore}/mounts/${opts.repository}`;
  const remotePath = options.remote ? `${baseRemotePath}/${options.remote}` : baseRemotePath;

  const keyFilePath = await createTempSSHKeyFile(details.privateKey);
  const knownHostsPath = await createTempKnownHostsFile(details.known_hosts);

  try {
    const sshOptions = `-o StrictHostKeyChecking=yes -o UserKnownHostsFile="${knownHostsPath}" -p ${details.port} -i "${keyFilePath}"`;

    const rsyncOptions: RsyncExecutorOptions = {
      sshOptions,
      source: localPath,
      destination: `${details.user}@${details.host}:${remotePath}`,
      mirror: options.mirror,
      verify: options.verify,
      exclude: options.exclude,
      universalUser: details.universalUser,
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
    await removeTempKnownHostsFile(knownHostsPath);
  }
}

async function syncDownload(options: SyncDownloadOptions): Promise<void> {
  const opts = await configService.applyDefaults(options);

  const provider = await getStateProvider();
  if (provider.isCloud && !opts.team) {
    throw new Error(t('errors.teamRequired'));
  }
  if (!opts.machine) {
    throw new Error(t('errors.machineRequired'));
  }
  if (!opts.repository) {
    throw new Error(t('errors.repositoryRequired'));
  }

  await assertCommandPolicy(CMD.REPO_SYNC_DOWNLOAD, opts.repository);
  if (options.remote) validateRemotePath(options.remote);

  const localPath = resolve(options.local ?? process.cwd());

  await ensureRenetProvisioned(opts.machine!);

  if (opts.repository) {
    await deployRepoKeyIfNeeded(opts.repository, opts.machine);
  }

  const details = await withSpinner(t('commands.sync.fetchingDetails'), () =>
    getSSHConnectionDetails(opts.team!, opts.machine!, opts.repository)
  );

  const baseRemotePath =
    details.workingDirectory ?? `${details.datastore}/mounts/${opts.repository}`;
  const remotePath = options.remote ? `${baseRemotePath}/${options.remote}/` : `${baseRemotePath}/`;

  const keyFilePath = await createTempSSHKeyFile(details.privateKey);
  const knownHostsPath = await createTempKnownHostsFile(details.known_hosts);

  try {
    const sshOptions = `-o StrictHostKeyChecking=yes -o UserKnownHostsFile="${knownHostsPath}" -p ${details.port} -i "${keyFilePath}"`;

    const rsyncOptions: RsyncExecutorOptions = {
      sshOptions,
      source: `${details.user}@${details.host}:${remotePath}`,
      destination: localPath,
      mirror: options.mirror,
      verify: options.verify,
      exclude: options.exclude,
      universalUser: details.universalUser,
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
    await removeTempKnownHostsFile(knownHostsPath);
  }
}

/**
 * Register sync commands under repo:
 * - repo sync upload      (file transfer upload)
 * - repo sync download    (file transfer download)
 * - repo sync status      (file transfer status)
 */
export function registerRepoSyncCommands(repoCommand: Command): void {
  const sync = repoCommand.command('sync').description(t('commands.repo.sync.description'));

  sync.addHelpText(
    'after',
    `
${t('help.examples')}
  $ rdc repo sync upload -m server-1 -r my-app --local ./src  ${t('help.sync.upload')}
  $ rdc repo sync download -m server-1 -r my-app --local ./data  ${t('help.sync.download')}
`
  );

  // sync upload
  sync
    .command('upload')
    .summary(t('commands.sync.upload.descriptionShort'))
    .description(t('commands.sync.upload.description'))
    .option('-t, --team <name>', t('options.team'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
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
        const provider = await getStateProvider();
        if (provider.isCloud) {
          await authService.requireAuth();
        }
        await syncUpload(options);
      } catch (error) {
        handleError(error);
      }
    });

  // sync download
  sync
    .command('download')
    .summary(t('commands.sync.download.descriptionShort'))
    .description(t('commands.sync.download.description'))
    .option('-t, --team <name>', t('options.team'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
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
        const provider = await getStateProvider();
        if (provider.isCloud) {
          await authService.requireAuth();
        }
        await syncDownload(options);
      } catch (error) {
        handleError(error);
      }
    });

  // sync status
  sync
    .command('status')
    .summary(t('commands.sync.status.descriptionShort'))
    .description(t('commands.sync.status.description'))
    .option('-t, --team <name>', t('options.team'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .option('-r, --repository <name>', t('options.repository'))
    .option('-l, --local <path>', t('options.localPath'))
    .option('--remote <path>', t('options.remotePath'))
    .action(async (options: SyncDownloadOptions) => {
      try {
        const provider = await getStateProvider();
        if (provider.isCloud) {
          await authService.requireAuth();
        }
        await syncDownload({ ...options, dryRun: true });
      } catch (error) {
        handleError(error);
      }
    });
}

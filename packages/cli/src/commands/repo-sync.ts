import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
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
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';

/** Accumulate repeatable option values into an array. */
function collect(val: string, prev: string[]): string[] {
  return [...prev, val];
}

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

async function getRsyncConnectionDetails(
  teamName: string,
  machineName: string,
  repositoryName: string
): Promise<RsyncConnectionDetails> {
  const provider = await getStateProvider();
  const { machineVault, teamVault, repositoryVault } = await provider.vaults.getConnectionVaults(
    teamName,
    machineName,
    repositoryName
  );

  const host = (machineVault.ip ?? machineVault.host) as string | undefined;
  const port = (machineVault.port ?? DEFAULTS.SSH.PORT) as number;
  const privateKey = (teamVault.SSH_PRIVATE_KEY ?? teamVault.sshPrivateKey) as string | undefined;
  const knownHosts = (machineVault.known_hosts ?? '') as string;
  const datastore = (machineVault.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH) as string;
  const universalUser = (machineVault.universalUser ??
    DEFAULTS.REPOSITORY.UNIVERSAL_USER) as string;
  const sshUser = (machineVault.user ?? universalUser) as string;

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
  const remotePath = (repoVault.workingDirectory ??
    `${datastore}/mounts/${repoVault.repositoryGuid ?? repositoryName}`) as string;

  return {
    host,
    user: sshUser,
    port,
    privateKey,
    remotePath,
    known_hosts: knownHosts,
    universalUser,
  };
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
  const knownHostsPath = await createTempKnownHostsFile(connectionDetails.known_hosts);

  try {
    const sshOptions = `-o StrictHostKeyChecking=yes -o UserKnownHostsFile="${knownHostsPath}" -p ${connectionDetails.port} -i "${keyFilePath}"`;

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

  const localPath = resolve(options.local ?? process.cwd());

  const connectionDetails = await withSpinner(t('commands.sync.fetchingDetails'), () =>
    getRsyncConnectionDetails(opts.team!, opts.machine!, opts.repository!)
  );

  const remotePath = options.remote
    ? `${connectionDetails.remotePath}/${options.remote}/`
    : `${connectionDetails.remotePath}/`;

  const keyFilePath = await createTempSSHKeyFile(connectionDetails.privateKey);
  const knownHostsPath = await createTempKnownHostsFile(connectionDetails.known_hosts);

  try {
    const sshOptions = `-o StrictHostKeyChecking=yes -o UserKnownHostsFile="${knownHostsPath}" -p ${connectionDetails.port} -i "${keyFilePath}"`;

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
    await removeTempKnownHostsFile(knownHostsPath);
  }
}

/** Resolve an array of repo names to their corresponding GUIDs. */
async function resolveRepoGUIDs(repoNames: string[]): Promise<string[]> {
  const guids: string[] = [];
  for (const repoName of repoNames) {
    const repoConfig = await configService.getRepository(repoName);
    if (!repoConfig) {
      throw new ValidationError(t('errors.repositoryNotFound', { name: repoName }));
    }
    guids.push(repoConfig.repositoryGuid);
  }
  return guids;
}

/**
 * Register sync commands under repo:
 * - repo sync push-all   (bulk push repos to storage)
 * - repo sync pull-all   (bulk pull repos from storage)
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
  $ rdc repo sync push-all --to my-storage -m server-1   ${t('help.repo.sync.pushAll')}
  $ rdc repo sync pull-all --from my-storage -m server-1  ${t('help.repo.sync.pullAll')}
  $ rdc repo sync upload -m server-1 -r my-app --local ./src  ${t('help.sync.upload')}
  $ rdc repo sync download -m server-1 -r my-app --local ./data  ${t('help.sync.download')}
`
  );

  // sync push-all
  sync
    .command('push-all')
    .description(t('commands.repo.sync.pushAll.description'))
    .requiredOption('--to <storage>', t('commands.repo.sync.pushAll.optionTo'))
    .option('--repo <name>', t('commands.repo.sync.pushAll.optionRepo'), collect, [])
    .option('-m, --machine <name>', t('options.machine'))
    .option('--debug', t('options.debug'))
    .action(async (options) => {
      try {
        const repoGUIDs = await resolveRepoGUIDs(options.repo as string[]);
        const repos = repoGUIDs.length > 0 ? repoGUIDs : undefined;

        const { runBackupSyncPush } = await import('../services/backup-sync.js');
        await runBackupSyncPush({
          storageName: options.to,
          machine: options.machine,
          repos,
          debug: options.debug,
        });
        outputService.success(t('commands.repo.sync.pushAll.success'));
      } catch (error) {
        handleError(error);
      }
    });

  // sync pull-all
  sync
    .command('pull-all')
    .description(t('commands.repo.sync.pullAll.description'))
    .requiredOption('--from <storage>', t('commands.repo.sync.pullAll.optionFrom'))
    .option('--repo <name>', t('commands.repo.sync.pullAll.optionRepo'), collect, [])
    .option('--override', t('commands.repo.sync.pullAll.optionOverride'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--debug', t('options.debug'))
    .action(async (options) => {
      try {
        const repoGUIDs = await resolveRepoGUIDs(options.repo as string[]);
        const repos = repoGUIDs.length > 0 ? repoGUIDs : undefined;

        const { runBackupSyncPull } = await import('../services/backup-sync.js');
        await runBackupSyncPull({
          storageName: options.from,
          machine: options.machine,
          repos,
          override: options.override,
          debug: options.debug,
        });
        outputService.success(t('commands.repo.sync.pullAll.success'));
      } catch (error) {
        handleError(error);
      }
    });

  // sync upload
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
    .description(t('commands.sync.status.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('-m, --machine <name>', t('options.machine'))
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

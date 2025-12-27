import { existsSync } from 'fs';
import { resolve } from 'path';
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
import { apiClient } from '../services/api.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
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
  hostEntry: string;
  universalUser?: string;
}

/**
 * Gets rsync connection details from the API
 */
async function getRsyncConnectionDetails(
  teamName: string,
  machineName: string,
  repositoryName: string
): Promise<RsyncConnectionDetails> {
  // Get machine details
  const machineResponse = (await apiClient.post('GetMachineDetails', {
    teamName,
    machineName,
  })) as { machineVault?: Record<string, unknown>; teamVault?: Record<string, unknown> };

  const machineVault = machineResponse.machineVault ?? {};
  const teamVault = machineResponse.teamVault ?? {};

  const host = (machineVault.ip ?? machineVault.host) as string | undefined;
  const port = (machineVault.sshPort ?? 22) as number;
  const privateKey = (teamVault.SSH_PRIVATE_KEY ?? teamVault.sshPrivateKey) as string | undefined;
  const hostEntry = (machineVault.hostEntry ?? machineVault.SSH_HOST_KEY ?? '') as string;
  const datastorePath = (machineVault.datastorePath ?? '/mnt/datastore') as string;
  const universalUser = machineVault.universalUser as string | undefined;

  if (!host) {
    throw new Error(`Machine '${machineName}' does not have an IP address configured`);
  }

  if (!privateKey) {
    throw new Error(`Team '${teamName}' does not have an SSH private key configured`);
  }

  if (!hostEntry) {
    throw new Error(`Machine '${machineName}' does not have a host key configured in the vault`);
  }

  // Get repository details
  const repoResponse = (await apiClient.post('GetRepositoryDetails', {
    teamName,
    machineName,
    repositoryName,
  })) as { repositoryVault?: Record<string, unknown> };

  const repoVault = repoResponse.repositoryVault ?? {};
  const repoPath = (repoVault.path ?? `/home/${repositoryName}`) as string;

  // Build remote path: datastore/repository_path
  const remotePath = `${datastorePath}${repoPath}`;

  return {
    host,
    user: repositoryName, // Use repository name as SSH user
    port,
    privateKey,
    remotePath,
    hostEntry,
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
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

/**
 * Interactive confirmation loop with details option (matches Python CLI behavior)
 * Prompts [y/N/d(etails)] and allows viewing detailed file list before confirming
 *
 * @param changes - The rsync changes to confirm
 * @returns Promise<boolean> - true if user confirms, false if cancelled
 */
async function interactiveConfirmation(changes: RsyncChanges): Promise<boolean> {
  const readline = await import('readline');

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
      rl.question('\nProceed with sync? [y/N/d(etails)] ', resolve);
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
        console.log('Please enter y (yes), n (no), or d (details)');
    }
  }

  rl.close();
  return proceed;
}

/**
 * Uploads files to a repository
 */
async function syncUpload(options: SyncUploadOptions): Promise<void> {
  const opts = await contextService.applyDefaults(options);

  if (!opts.machine) {
    throw new Error('Machine name is required. Use --machine <name> or set a default context.');
  }

  if (!opts.repository) {
    throw new Error('Repository name is required. Use --repository <name>.');
  }

  const teamName = opts.team ?? 'Default';
  const machineName = opts.machine as string;
  const repositoryName = opts.repository as string;

  // Determine local path
  let localPath = options.local ?? process.cwd();
  localPath = resolve(localPath);

  if (!existsSync(localPath)) {
    throw new Error(`Local path does not exist: ${localPath}`);
  }

  // Ensure trailing slash for directory sync
  if (!localPath.endsWith('/')) {
    localPath += '/';
  }

  // Get connection details
  const connectionDetails = await withSpinner('Fetching connection details...', () =>
    getRsyncConnectionDetails(teamName, machineName, repositoryName)
  );

  // Determine remote path
  const remotePath = options.remote
    ? `${connectionDetails.remotePath}/${options.remote}`
    : connectionDetails.remotePath;

  // Create temp SSH key file
  const keyFilePath = await createTempSSHKeyFile(connectionDetails.privateKey);

  try {
    // Build SSH options string for rsync
    const sshOptions = `-o StrictHostKeyChecking=yes -o UserKnownHostsFile=/dev/null -p ${connectionDetails.port} -i "${keyFilePath}"`;

    // Build rsync options
    const rsyncOptions: RsyncExecutorOptions = {
      sshOptions,
      source: localPath,
      destination: `${connectionDetails.user}@${connectionDetails.host}:${remotePath}`,
      mirror: options.mirror,
      verify: options.verify,
      exclude: options.exclude,
      universalUser: connectionDetails.universalUser,
    };

    // If confirm mode, show preview first with interactive confirmation
    if (options.confirm && !options.dryRun) {
      // eslint-disable-next-line no-console
      console.log('\nPreviewing changes...\n');

      const changes = await getRsyncPreview(rsyncOptions);

      if (
        changes.newFiles.length === 0 &&
        changes.modifiedFiles.length === 0 &&
        changes.deletedFiles.length === 0
      ) {
        // eslint-disable-next-line no-console
        console.log('No changes to sync.');
        return;
      }

      // Use interactive confirmation with details option
      const proceed = await interactiveConfirmation(changes);
      if (!proceed) {
        // eslint-disable-next-line no-console
        console.log('Sync cancelled.');
        return;
      }
    }

    // If dry-run, just show preview
    if (options.dryRun) {
      // eslint-disable-next-line no-console
      console.log('\nDry run - showing what would be transferred:\n');
      const changes = await getRsyncPreview(rsyncOptions);
      // eslint-disable-next-line no-console
      console.log(formatChangesSummary(changes));
      return;
    }

    // Execute sync
    const spinner = ora('Starting upload...').start();

    rsyncOptions.onProgress = (progress: SyncProgress) => {
      spinner.text = `Uploading: ${progress.percentage}% - ${progress.currentFile} (${progress.speed})`;
    };

    const result = await executeRsync(rsyncOptions);

    if (result.success) {
      spinner.succeed(`Upload completed: ${result.filesTransferred} files transferred`);
      if (result.bytesTransferred > 0) {
        // eslint-disable-next-line no-console
        console.log(`Total size: ${formatBytes(result.bytesTransferred)}`);
      }
      // eslint-disable-next-line no-console
      console.log(`Duration: ${(result.duration / 1000).toFixed(1)}s`);
    } else {
      spinner.fail('Upload failed');
      if (result.errors.length > 0) {
        console.error('Errors:');
        for (const err of result.errors) {
          console.error(`  ${err}`);
        }
      }
      process.exitCode = 1;
    }
  } finally {
    await removeTempSSHKeyFile(keyFilePath);
  }
}

/**
 * Downloads files from a repository
 */
async function syncDownload(options: SyncDownloadOptions): Promise<void> {
  const opts = await contextService.applyDefaults(options);

  if (!opts.machine) {
    throw new Error('Machine name is required. Use --machine <name> or set a default context.');
  }

  if (!opts.repository) {
    throw new Error('Repository name is required. Use --repository <name>.');
  }

  const teamName = opts.team ?? 'Default';
  const machineName = opts.machine as string;
  const repositoryName = opts.repository as string;

  // Determine local path
  let localPath = options.local ?? process.cwd();
  localPath = resolve(localPath);

  // Get connection details
  const connectionDetails = await withSpinner('Fetching connection details...', () =>
    getRsyncConnectionDetails(teamName, machineName, repositoryName)
  );

  // Determine remote path (with trailing slash to sync contents)
  const remotePath = options.remote
    ? `${connectionDetails.remotePath}/${options.remote}/`
    : `${connectionDetails.remotePath}/`;

  // Create temp SSH key file
  const keyFilePath = await createTempSSHKeyFile(connectionDetails.privateKey);

  try {
    // Build SSH options string for rsync
    const sshOptions = `-o StrictHostKeyChecking=yes -o UserKnownHostsFile=/dev/null -p ${connectionDetails.port} -i "${keyFilePath}"`;

    // Build rsync options
    const rsyncOptions: RsyncExecutorOptions = {
      sshOptions,
      source: `${connectionDetails.user}@${connectionDetails.host}:${remotePath}`,
      destination: localPath,
      mirror: options.mirror,
      verify: options.verify,
      exclude: options.exclude,
      universalUser: connectionDetails.universalUser,
    };

    // If confirm mode, show preview first with interactive confirmation
    if (options.confirm && !options.dryRun) {
      // eslint-disable-next-line no-console
      console.log('\nPreviewing changes...\n');

      const changes = await getRsyncPreview(rsyncOptions);

      if (
        changes.newFiles.length === 0 &&
        changes.modifiedFiles.length === 0 &&
        changes.deletedFiles.length === 0
      ) {
        // eslint-disable-next-line no-console
        console.log('No changes to sync.');
        return;
      }

      // Use interactive confirmation with details option
      const proceed = await interactiveConfirmation(changes);
      if (!proceed) {
        // eslint-disable-next-line no-console
        console.log('Sync cancelled.');
        return;
      }
    }

    // If dry-run, just show preview
    if (options.dryRun) {
      // eslint-disable-next-line no-console
      console.log('\nDry run - showing what would be transferred:\n');
      const changes = await getRsyncPreview(rsyncOptions);
      // eslint-disable-next-line no-console
      console.log(formatChangesSummary(changes));
      return;
    }

    // Execute sync
    const spinner = ora('Starting download...').start();

    rsyncOptions.onProgress = (progress: SyncProgress) => {
      spinner.text = `Downloading: ${progress.percentage}% - ${progress.currentFile} (${progress.speed})`;
    };

    const result = await executeRsync(rsyncOptions);

    if (result.success) {
      spinner.succeed(`Download completed: ${result.filesTransferred} files transferred`);
      if (result.bytesTransferred > 0) {
        // eslint-disable-next-line no-console
        console.log(`Total size: ${formatBytes(result.bytesTransferred)}`);
      }
      // eslint-disable-next-line no-console
      console.log(`Duration: ${(result.duration / 1000).toFixed(1)}s`);
    } else {
      spinner.fail('Download failed');
      if (result.errors.length > 0) {
        console.error('Errors:');
        for (const err of result.errors) {
          console.error(`  ${err}`);
        }
      }
      process.exitCode = 1;
    }
  } finally {
    await removeTempSSHKeyFile(keyFilePath);
  }
}

/**
 * Registers the sync commands
 */
export function registerSyncCommands(program: Command): void {
  const sync = program
    .command('sync')
    .description('File synchronization with repositories using rsync');

  sync
    .command('upload')
    .description('Upload files to a repository')
    .option('-t, --team <name>', 'Team name')
    .option('-m, --machine <name>', 'Machine name')
    .option('-r, --repository <name>', 'Repository name')
    .option('-l, --local <path>', 'Local directory path (default: current directory)')
    .option('--remote <path>', 'Remote subdirectory path within repository')
    .option('--mirror', 'Mirror mode - delete remote files not present locally')
    .option('--verify', 'Verify files using checksums after sync')
    .option('--confirm', 'Preview changes and ask for confirmation before syncing')
    .option('--exclude <patterns...>', 'Patterns to exclude from sync')
    .option('--dry-run', 'Show what would be transferred without actually syncing')
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
    .description('Download files from a repository')
    .option('-t, --team <name>', 'Team name')
    .option('-m, --machine <name>', 'Machine name')
    .option('-r, --repository <name>', 'Repository name')
    .option('-l, --local <path>', 'Local directory path (default: current directory)')
    .option('--remote <path>', 'Remote subdirectory path within repository')
    .option('--mirror', 'Mirror mode - delete local files not present on remote')
    .option('--verify', 'Verify files using checksums after sync')
    .option('--confirm', 'Preview changes and ask for confirmation before syncing')
    .option('--exclude <patterns...>', 'Patterns to exclude from sync')
    .option('--dry-run', 'Show what would be transferred without actually syncing')
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
    .description('Check sync status and compare local/remote files')
    .option('-t, --team <name>', 'Team name')
    .option('-m, --machine <name>', 'Machine name')
    .option('-r, --repository <name>', 'Repository name')
    .option('-l, --local <path>', 'Local directory path (default: current directory)')
    .option('--remote <path>', 'Remote subdirectory path within repository')
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

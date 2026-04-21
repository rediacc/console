import {
  createTempKnownHostsFile,
  createTempSSHKeyFile,
  removeTempKnownHostsFile,
  removeTempSSHKeyFile,
} from '@rediacc/shared-desktop/ssh';
import {
  executeRsync,
  type RsyncExecutorOptions,
  sftpDownloadDirectory,
  sftpDownloadFile,
  sftpUploadPaths,
  type SftpUploadSource,
} from '@rediacc/shared-desktop/sync';
import type { SyncProgress } from '@rediacc/shared-desktop/types';
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
import { auditService } from '../services/audit.js';
import { handleError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import {
  formatBytes,
  handleConfirmMode,
  handleDryRun,
  resolveUploadLocalPaths,
  type SyncDownloadOptions,
  type SyncUploadOptions,
  validateDownloadOptions,
  withTrailingSlash,
} from './repo-sync-helpers.js';

export { resolveUploadLocalPaths } from './repo-sync-helpers.js';
export type { ResolvedLocalSource } from './repo-sync-helpers.js';

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

interface ValidatedSyncOptions {
  team: string | undefined;
  machine: string;
  repository: string;
}

async function validateSyncOptions(
  options: SyncUploadOptions | SyncDownloadOptions,
  command: typeof CMD.REPO_SYNC_UPLOAD | typeof CMD.REPO_SYNC_DOWNLOAD
): Promise<ValidatedSyncOptions> {
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

  await assertCommandPolicy(command, opts.repository);
  if (options.remote) validateRemotePath(options.remote);

  return { team: opts.team, machine: opts.machine, repository: opts.repository };
}

interface SyncConnectionContext {
  details: Awaited<ReturnType<typeof getSSHConnectionDetails>>;
  remotePath: string;
  sftpRemotePath: string;
  sftpConfig: { host: string; port: number; username: string; privateKey: string };
}

async function prepareSyncConnection(
  validated: ValidatedSyncOptions,
  remoteSubPath: string | undefined,
  opts: { isFile?: boolean } = {}
): Promise<SyncConnectionContext> {
  await ensureRenetProvisioned(validated.machine);
  await deployRepoKeyIfNeeded(validated.repository, validated.machine);

  const details = await withSpinner(t('commands.sync.fetchingDetails'), () =>
    getSSHConnectionDetails(validated.team!, validated.machine, validated.repository)
  );

  const baseRemotePath =
    details.workingDirectory ?? `${details.datastore}/mounts/${validated.repository}`;

  let remotePath: string;
  let sftpRemotePath: string;
  if (opts.isFile) {
    // Single-file mode: no trailing slash so rsync treats source/dest as a file.
    const sub = remoteSubPath ?? '';
    remotePath = `${baseRemotePath}/${sub}`;
    sftpRemotePath = sub;
  } else {
    remotePath = remoteSubPath ? `${baseRemotePath}/${remoteSubPath}/` : `${baseRemotePath}/`;
    sftpRemotePath = remoteSubPath ? `${remoteSubPath}/` : '.';
  }

  const sftpConfig = {
    host: details.host,
    port: details.port,
    username: details.user,
    privateKey: details.privateKey,
    knownHosts: details.known_hosts,
  };

  return { details, remotePath, sftpRemotePath, sftpConfig };
}

function isRsyncNotFoundError(err: unknown): boolean {
  return err instanceof Error && err.message.includes('rsync not found');
}

function displaySftpDryRunResult(result: {
  filesTransferred: number;
  bytesTransferred: number;
}): void {
  process.stdout.write(
    `\nSFTP fallback (rsync not available):\n  Files to transfer: ${result.filesTransferred}\n  Total size: ${formatBytes(result.bytesTransferred)}\n`
  );
}

async function withTempSshFiles<T>(
  details: { privateKey: string; known_hosts: string },
  fn: (keyFilePath: string, knownHostsPath: string) => Promise<T>
): Promise<T> {
  const keyFilePath = await createTempSSHKeyFile(details.privateKey);
  const knownHostsPath = await createTempKnownHostsFile(details.known_hosts);
  try {
    return await fn(keyFilePath, knownHostsPath);
  } finally {
    await removeTempSSHKeyFile(keyFilePath);
    await removeTempKnownHostsFile(knownHostsPath);
  }
}

function buildSshOptions(knownHostsPath: string, port: number, keyFilePath: string): string {
  return `-o StrictHostKeyChecking=yes -o UserKnownHostsFile="${knownHostsPath}" -p ${port} -i "${keyFilePath}"`;
}

async function handleDryRunWithSftpFallback(
  rsyncOptions: RsyncExecutorOptions,
  sftpTransfer: () => Promise<{ filesTransferred: number; bytesTransferred: number }>
): Promise<void> {
  try {
    await handleDryRun(rsyncOptions);
  } catch (err: unknown) {
    if (!isRsyncNotFoundError(err)) throw err;
    const result = await sftpTransfer();
    displaySftpDryRunResult(result);
  }
}

async function executeSyncWithSftpFallback(
  rsyncOptions: RsyncExecutorOptions,
  mode: 'upload' | 'download',
  sftpTransfer: (spinner: ReturnType<typeof ora>) => Promise<{
    success: boolean;
    filesTransferred: number;
    bytesTransferred: number;
    duration: number;
    errors: string[];
  }>
): Promise<void> {
  try {
    await executeSyncWithProgress(rsyncOptions, mode);
  } catch (err: unknown) {
    if (!isRsyncNotFoundError(err)) throw err;
    const spinner = ora('rsync not available, using SFTP transfer (no delta sync)...').start();
    const result = await sftpTransfer(spinner);
    displaySyncResult(result, spinner, mode);
  }
}

async function syncUpload(options: SyncUploadOptions): Promise<void> {
  const startTime = Date.now();
  const validated = await validateSyncOptions(options, CMD.REPO_SYNC_UPLOAD);
  const sources = resolveUploadLocalPaths(options.local);
  if (options.mirror && sources.some((s) => s.isFile)) {
    throw new Error(t('errors.sync.mirrorWithFile'));
  }
  const ctx = await prepareSyncConnection(validated, options.remote);

  // rsync accepts either a single source string (dir with trailing slash or a file)
  // or an array of sources when the user passes multiple --local paths.
  const rsyncSource: string | string[] =
    sources.length === 1 ? sources[0].path : sources.map((s) => s.path);
  const sftpSources: SftpUploadSource[] = sources.map((s) => ({
    path: s.rawPath,
    isFile: s.isFile,
  }));

  let success = true;
  let error: string | undefined;
  try {
    await withTempSshFiles(ctx.details, async (keyFilePath, knownHostsPath) => {
      const rsyncOptions: RsyncExecutorOptions = {
        sshOptions: buildSshOptions(knownHostsPath, ctx.details.port, keyFilePath),
        source: rsyncSource,
        destination: `${ctx.details.user}@${ctx.details.host}:${ctx.remotePath}`,
        mirror: options.mirror,
        verify: options.verify,
        exclude: options.exclude,
        universalUser: ctx.details.universalUser,
        isUpload: true,
      };

      const shouldContinue = await handleConfirmMode(rsyncOptions, options);
      if (!shouldContinue) return;

      if (options.dryRun) {
        await handleDryRunWithSftpFallback(rsyncOptions, () =>
          sftpUploadPaths(sftpSources, ctx.sftpRemotePath, ctx.sftpConfig, {
            exclude: options.exclude,
            dryRun: true,
          })
        );
        return;
      }

      await executeSyncWithSftpFallback(rsyncOptions, 'upload', (spinner) =>
        sftpUploadPaths(sftpSources, ctx.sftpRemotePath, ctx.sftpConfig, {
          exclude: options.exclude,
          onProgress: (file) => {
            spinner.text = `Uploading: ${file}`;
          },
        })
      );
    });
  } catch (err) {
    success = false;
    error = err instanceof Error ? err.message : String(err);
    throw err;
  } finally {
    if (!options.dryRun) {
      auditService.recordOperation({
        functionName: 'sync_upload',
        machineName: validated.machine,
        repoName: validated.repository,
        success,
        exitCode: success ? 0 : 1,
        durationMs: Date.now() - startTime,
        error,
      });
    }
  }
}

function sftpDownloadTransfer(
  isFileMode: boolean,
  ctx: SyncConnectionContext,
  localPath: string,
  sftpOptions: Parameters<typeof sftpDownloadDirectory>[3]
): ReturnType<typeof sftpDownloadDirectory> {
  return isFileMode
    ? sftpDownloadFile(ctx.sftpRemotePath, localPath, ctx.sftpConfig, sftpOptions)
    : sftpDownloadDirectory(ctx.sftpRemotePath, localPath, ctx.sftpConfig, sftpOptions);
}

async function syncDownload(options: SyncDownloadOptions): Promise<void> {
  const startTime = Date.now();
  const validated = await validateSyncOptions(options, CMD.REPO_SYNC_DOWNLOAD);
  const { localPath, isFileMode } = validateDownloadOptions(options);
  const ctx = await prepareSyncConnection(validated, options.remoteFile ?? options.remote, {
    isFile: isFileMode,
  });
  const destination = isFileMode ? withTrailingSlash(localPath) : localPath;

  let success = true;
  let error: string | undefined;
  try {
    await withTempSshFiles(ctx.details, async (keyFilePath, knownHostsPath) => {
      const rsyncOptions: RsyncExecutorOptions = {
        sshOptions: buildSshOptions(knownHostsPath, ctx.details.port, keyFilePath),
        source: `${ctx.details.user}@${ctx.details.host}:${ctx.remotePath}`,
        destination,
        mirror: options.mirror,
        verify: options.verify,
        exclude: options.exclude,
        universalUser: ctx.details.universalUser,
      };

      const shouldContinue = await handleConfirmMode(rsyncOptions, options);
      if (!shouldContinue) return;

      if (options.dryRun) {
        await handleDryRunWithSftpFallback(rsyncOptions, () =>
          sftpDownloadTransfer(isFileMode, ctx, localPath, { dryRun: true })
        );
        return;
      }

      await executeSyncWithSftpFallback(rsyncOptions, 'download', (spinner) =>
        sftpDownloadTransfer(isFileMode, ctx, localPath, {
          onProgress: (file) => {
            spinner.text = `Downloading: ${file}`;
          },
        })
      );
    });
  } catch (err) {
    success = false;
    error = err instanceof Error ? err.message : String(err);
    throw err;
  } finally {
    if (!options.dryRun) {
      auditService.recordOperation({
        functionName: 'sync_download',
        machineName: validated.machine,
        repoName: validated.repository,
        success,
        exitCode: success ? 0 : 1,
        durationMs: Date.now() - startTime,
        error,
      });
    }
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
    .option('--local <paths...>', t('options.localPaths'))
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
    .option('--local <path>', t('options.localPath'))
    .option('--remote <path>', t('options.remotePath'))
    .option('--remote-file <path>', t('options.remoteFile'))
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
    .option('--local <path>', t('options.localPath'))
    .option('--remote <path>', t('options.remotePath'))
    .option('--remote-file <path>', t('options.remoteFile'))
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

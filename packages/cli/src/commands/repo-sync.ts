import type { Command } from 'commander';
import ora from 'ora';
import { t } from '../i18n/index.js';
import {
  createTempKnownHostsFile,
  createTempSSHKeyFile,
  removeTempKnownHostsFile,
  removeTempSSHKeyFile,
} from '../remote/ssh/index.js';
import {
  executeRsync,
  type RsyncExecutorOptions,
  rsyncUnusableReason,
  type SftpUploadSource,
  sftpDownloadDirectory,
  sftpDownloadFile,
  sftpUploadFile,
  sftpUploadPaths,
} from '../remote/sync/index.js';
import type { SyncProgress } from '../remote/types/index.js';
import { namedDatastoreMount } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import { auditService } from '../services/core/audit.js';
import { writeStderr } from '../services/core/request-context.js';
import { withPooledSftp } from '../services/machine/machine-connection.js';
import { getSSHConnectionDetails } from '../services/machine/ssh-connection.js';
import {
  acquireRemoteRenet,
  type RenetAccess,
  readSSHKey,
} from '../services/renet/renet-execution.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { assertRepoMountedOnMachine } from '../services/repo/repo-mount-check.js';
import { validateRemotePath } from '../utils/command-policy.js';
import { handleError } from '../utils/errors.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { oraOptions, withSpinner } from '../utils/spinner.js';
import {
  displaySftpDryRunResult,
  displaySyncResult,
  SSH_KEY_FAILURE_PATTERN,
  sshKeyDiagnostic,
} from './repo-sync-display.js';
import {
  buildSyncRemotePaths,
  handleConfirmMode,
  handleDryRun,
  isRsyncNotFoundError,
  type SyncConnectionContext,
  type SyncDownloadOptions,
  type SyncUploadOptions,
  validateDownloadOptions,
  validateUploadOptions,
  withTrailingSlash,
} from './repo-sync-helpers.js';
import { ensureUploadParents } from './repo-sync-parents.js';

async function ensureRenetProvisioned(machineName: string, access: RenetAccess): Promise<void> {
  try {
    const localConfig = await configService.getLocalConfig();
    const machine = localConfig.machines[machineName];
    if (!machine) return;
    const teamKey = localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));
    await acquireRemoteRenet(access, localConfig, machine, teamKey, { machineName });
  } catch {
    // Non-fatal, sync may still work with existing renet on remote
  }
}

async function executeSyncWithProgress(
  rsyncOptions: RsyncExecutorOptions,
  mode: 'upload' | 'download',
  keyDiagnostic?: string
): Promise<{ filesTransferred: number; bytesTransferred: number }> {
  const spinner = ora(oraOptions(t(`commands.sync.${mode}.starting`))).start();

  rsyncOptions.onProgress = (progress: SyncProgress) => {
    spinner.text = t(`commands.sync.${mode}.progress`, {
      percentage: progress.percentage,
      file: progress.currentFile,
      speed: progress.speed,
    });
  };

  const result = await executeRsync(rsyncOptions);
  if (
    !result.success &&
    keyDiagnostic &&
    result.errors.some((e) => SSH_KEY_FAILURE_PATTERN.test(e))
  ) {
    result.errors.push(keyDiagnostic);
  }
  displaySyncResult(result, spinner, mode);
  return {
    filesTransferred: result.filesTransferred,
    bytesTransferred: result.bytesTransferred,
  };
}

interface ValidatedSyncOptions {
  machine: string;
  /** The config/renet identifier (name[:tag]) derived from the positional ref. */
  repository: string;
  /** The repo family name (no tag), the kube arm's on-datastore folder name. */
  repoName: string;
  /**
   * Set ONLY for a kubernetes-placed repo: the named DATA datastore backing it.
   * Its presence selects the kube sync arm (files land in the repo's folder on
   * the datastore, not in a docker per-repo GUID mount, which a k8s repo has
   * none of).
   */
  kubeDatastore?: string;
}

async function validateSyncOptions(
  ref: string,
  options: SyncUploadOptions | SyncDownloadOptions,
  resolveOptions: Parameters<typeof resolveRepoRef>[1] = {}
): Promise<ValidatedSyncOptions> {
  // Sync is a plain SSH/rsync/SFTP transfer against a machine's filesystem: no renet function call, so there is no executor sink to thread a kubeCluster marker into (and no control-node rerouting, the executor's kubeCluster override does not apply here). resolveRepoRef derives the machine that actually HOLDS the data (the datastore's attach machine), which is exactly the host
  // these bytes must land on for either runtime.
  const { name, repoKey, machineName, kubeCluster, datastore } = await resolveRepoRef(
    ref,
    resolveOptions
  );

  if (options.remote) validateRemotePath(options.remote);
  if (options.remoteFile) validateRemotePath(options.remoteFile);

  return {
    machine: machineName,
    repository: repoKey,
    repoName: name,
    ...(kubeCluster !== undefined && datastore !== undefined && { kubeDatastore: datastore }),
  };
}

async function prepareSyncConnection(
  validated: ValidatedSyncOptions,
  remoteSubPath: string | undefined,
  opts: { isFile?: boolean; access: RenetAccess }
): Promise<SyncConnectionContext> {
  await ensureRenetProvisioned(validated.machine, opts.access);

  const repoConfig = await configService.getRepository(validated.repository);

  // The docker per-repo GUID mount check and the per-repo SSH key deployment are BOTH docker-world concepts: a kubernetes repo has no per-repo dockerd and no GUID mount, its files live in a plain folder on the named datastore. Running them on the kube arm would fail the mount check on a perfectly healthy repo.
  const kubeArm = validated.kubeDatastore !== undefined;

  // The renet check (above) must precede any renet use, so it stays a barrier. After it, these steps are independent of one another: the mount check is a renet call over SSH, the repo-key deployment is an SFTP write, and the connection-detail lookup is a local config read. Run them concurrently instead of serial round-trips. The machine connection pool is refcounted and shares one
  // SSH session across these leases, and each renet/SFTP exec opens its own ssh2 channel, so concurrent execution is safe. deployRepoKeyIfNeeded
  // swallows its own errors (non-fatal); a failed mount check still aborts the
  // whole setup because Promise.all rejects.
  const [details] = await Promise.all([
    withSpinner(t('commands.sync.fetchingDetails'), () =>
      getSSHConnectionDetails('', validated.machine, validated.repository)
    ),
    repoConfig && !kubeArm
      ? assertRepoMountedOnMachine(
          validated.repository,
          repoConfig.repositoryGuid,
          validated.machine
        )
      : Promise.resolve(),
    kubeArm ? Promise.resolve() : deployRepoKeyIfNeeded(validated.repository, validated.machine),
  ]);

  // Kube arm: a cluster repo's files (its manifests, and anything else it keeps) live at <named-datastore-mount>/repos/<name>/ on the machine that holds the datastore, NOT in a docker GUID mount. Targeting the GUID mount is what made an anchor manifest never reach where `repo up` reads it (bug B1 hit).
  const baseRemotePath = validated.kubeDatastore
    ? `${namedDatastoreMount(validated.kubeDatastore)}/repos/${validated.repoName}`
    : (details.workingDirectory ?? `${details.datastore}/mounts/${validated.repository}`);

  const { remotePath, sftpRemotePath } = buildSyncRemotePaths(
    baseRemotePath,
    remoteSubPath,
    opts.isFile ?? false
  );

  const sftpConfig = {
    host: details.host,
    port: details.port,
    username: details.user,
    privateKey: details.privateKey,
    knownHosts: details.known_hosts,
  };

  return { details, remotePath, sftpRemotePath, baseRemotePath, sftpConfig };
}

async function withTempSshFiles<T>(
  details: { privateKey: string; known_hosts: string; host: string; port: number },
  fn: (keyFilePath: string, knownHostsPath: string) => Promise<T>
): Promise<T> {
  const keyFilePath = await createTempSSHKeyFile(details.privateKey);
  const knownHostsPath = await createTempKnownHostsFile(details.known_hosts, {
    host: details.host,
    port: details.port,
  });
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

export async function handleDryRunWithSftpFallback(
  rsyncOptions: RsyncExecutorOptions,
  sftpTransfer: () => Promise<{ filesTransferred: number; bytesTransferred: number }>,
  localOnly = false
): Promise<void> {
  try {
    if (await warnIfRsyncUnusable()) {
      displaySftpDryRunResult(await sftpTransfer());
      noteLocalOnlyUnavailable(localOnly);
      return;
    }
    await handleDryRun(rsyncOptions, { localOnly });
  } catch (err: unknown) {
    if (!isRsyncNotFoundError(err)) throw err;
    const result = await sftpTransfer();
    displaySftpDryRunResult(result);
    noteLocalOnlyUnavailable(localOnly);
  }
}

/** True (after warning on stderr with the reason) when rsync is installed but cannot start, so the transfer takes the SFTP path. */
async function warnIfRsyncUnusable(sftpFallback = true): Promise<boolean> {
  const reason = await rsyncUnusableReason();
  if (reason === undefined) return false;
  // A run that refuses instead of falling back must not announce an SFTP transfer (4f037bc9.3).
  const key = sftpFallback
    ? 'commands.sync.rsyncUnusable'
    : 'commands.sync.rsyncUnusableNoFallback';
  writeStderr(`${t(key, { reason })}\n`);
  return true;
}

/** The SFTP dry run has no local-only comparison, so `status` says so rather than reporting a clean sync (4f037bc9.1). */
function noteLocalOnlyUnavailable(localOnly: boolean): void {
  if (localOnly) writeStderr(`${t('commands.sync.status.localOnlyNeedsRsync')}\n`);
}

export async function executeSyncWithSftpFallback(
  rsyncOptions: RsyncExecutorOptions,
  mode: 'upload' | 'download',
  sftpTransfer: (spinner: ReturnType<typeof ora>) => Promise<{
    success: boolean;
    filesTransferred: number;
    bytesTransferred: number;
    duration: number;
    errors: string[];
  }>,
  keyDiagnostic?: string,
  beforeRsync?: () => Promise<void>
): Promise<{ filesTransferred: number; bytesTransferred: number }> {
  const runSftp = async (): Promise<{ filesTransferred: number; bytesTransferred: number }> => {
    // The SFTP path has no delete step: running it for a mirror would leave the extra files and report a clean sync.
    if (rsyncOptions.mirror) throw new Error(t('errors.sync.mirrorNeedsRsync'));
    const spinner = ora(
      oraOptions('rsync not available, using SFTP transfer (no delta sync)...')
    ).start();
    const result = await sftpTransfer(spinner);
    displaySyncResult(result, spinner, mode);
    return {
      filesTransferred: result.filesTransferred,
      bytesTransferred: result.bytesTransferred,
    };
  };
  try {
    await beforeRsync?.();
    if (await warnIfRsyncUnusable(rsyncOptions.mirror !== true)) return await runSftp();
    return await executeSyncWithProgress(rsyncOptions, mode, keyDiagnostic);
  } catch (err: unknown) {
    if (!isRsyncNotFoundError(err)) throw err;
    return await runSftp();
  }
}

/**
 * Dispatch single-file vs multi-source upload via SFTP. Exported for tests.
 * The transfer runs on a pooled connection held only for its duration.
 */
export function sftpUploadTransfer(
  isFileMode: boolean,
  sftpSources: SftpUploadSource[],
  ctx: SyncConnectionContext,
  sftpOptions: Parameters<typeof sftpUploadPaths>[3]
): ReturnType<typeof sftpUploadPaths> {
  return withPooledSftp(ctx.sftpConfig, (sftp) =>
    isFileMode
      ? sftpUploadFile(sftpSources[0].path, ctx.sftpRemotePath, sftp, sftpOptions)
      : sftpUploadPaths(sftpSources, ctx.sftpRemotePath, sftp, sftpOptions)
  );
}

async function syncUpload(ref: string, options: SyncUploadOptions): Promise<void> {
  const startTime = Date.now();
  const validated = await validateSyncOptions(ref, options);
  const { isFileMode, sources } = validateUploadOptions(options);
  const ctx = await prepareSyncConnection(validated, options.remoteFile ?? options.remote, {
    isFile: isFileMode,
    access: 'provision',
  });

  // rsync accepts either a single source string (dir with trailing slash or a file) or an array of sources when the user passes multiple --local paths.
  const rsyncSource: string | string[] =
    sources.length === 1 ? sources[0].path : sources.map((s) => s.path);
  const sftpSources: SftpUploadSource[] = sources.map((s) => ({
    path: s.rawPath,
    isFile: s.isFile,
  }));

  let success = true;
  let error: string | undefined;
  let filesTransferred: number | undefined;
  let bytesTransferred: number | undefined;
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
        mkpath: isFileMode,
      };

      const shouldContinue = await handleConfirmMode(rsyncOptions, options);
      if (!shouldContinue) return;

      if (options.dryRun) {
        await handleDryRunWithSftpFallback(rsyncOptions, () =>
          sftpUploadTransfer(isFileMode, sftpSources, ctx, {
            exclude: options.exclude,
            verify: options.verify,
            dryRun: true,
          })
        );
        return;
      }

      const counts = await executeSyncWithSftpFallback(
        rsyncOptions,
        'upload',
        (spinner) =>
          sftpUploadTransfer(isFileMode, sftpSources, ctx, {
            exclude: options.exclude,
            verify: options.verify,
            onProgress: (file) => {
              spinner.text = `Uploading: ${file}`;
            },
          }),
        sshKeyDiagnostic(ctx.details.privateKey),
        () => ensureUploadParents(ctx, options.remoteFile ?? options.remote, rsyncOptions)
      );
      filesTransferred = counts.filesTransferred;
      bytesTransferred = counts.bytesTransferred;
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
        filesTransferred,
        bytesTransferred,
      });
    }
  }
}

/**
 * Dispatch single-file vs directory download via SFTP. Exported for tests.
 * The transfer runs on a pooled connection held only for its duration.
 */
export function sftpDownloadTransfer(
  isFileMode: boolean,
  ctx: SyncConnectionContext,
  localPath: string,
  sftpOptions: Parameters<typeof sftpDownloadDirectory>[3]
): ReturnType<typeof sftpDownloadDirectory> {
  return withPooledSftp(ctx.sftpConfig, (sftp) =>
    isFileMode
      ? sftpDownloadFile(ctx.sftpRemotePath, localPath, sftp, sftpOptions)
      : sftpDownloadDirectory(ctx.sftpRemotePath, localPath, sftp, sftpOptions)
  );
}

async function syncDownload(
  ref: string,
  options: SyncDownloadOptions,
  resolveOptions: Parameters<typeof resolveRepoRef>[1] = {}
): Promise<void> {
  const startTime = Date.now();
  const validated = await validateSyncOptions(ref, options, resolveOptions);
  const { localPath, isFileMode } = validateDownloadOptions(options);
  // Download (and `sync status`, its dry run) only reads: never replace the machine's renet.
  const ctx = await prepareSyncConnection(validated, options.remoteFile ?? options.remote, {
    isFile: isFileMode,
    access: 'read-only',
  });
  const destination = isFileMode ? withTrailingSlash(localPath) : localPath;

  let success = true;
  let error: string | undefined;
  let filesTransferred: number | undefined;
  let bytesTransferred: number | undefined;
  try {
    await withTempSshFiles(ctx.details, async (keyFilePath, knownHostsPath) => {
      const rsyncOptions: RsyncExecutorOptions = {
        sshOptions: buildSshOptions(knownHostsPath, ctx.details.port, keyFilePath),
        source: `${ctx.details.user}@${ctx.details.host}:${ctx.remotePath}`,
        destination,
        // status lists what only the local side holds, which rsync reports only as a deletion of a mirror run.
        mirror: options.mirror === true || (options.dryRun === true && options.localOnly === true),
        verify: options.verify,
        exclude: options.exclude,
        universalUser: ctx.details.universalUser,
      };

      const shouldContinue = await handleConfirmMode(rsyncOptions, options);
      if (!shouldContinue) return;

      if (options.dryRun) {
        await handleDryRunWithSftpFallback(
          rsyncOptions,
          () =>
            sftpDownloadTransfer(isFileMode, ctx, localPath, {
              verify: options.verify,
              dryRun: true,
            }),
          options.localOnly === true
        );
        return;
      }

      const counts = await executeSyncWithSftpFallback(
        rsyncOptions,
        'download',
        (spinner) =>
          sftpDownloadTransfer(isFileMode, ctx, localPath, {
            verify: options.verify,
            onProgress: (file) => {
              spinner.text = `Downloading: ${file}`;
            },
          }),
        sshKeyDiagnostic(ctx.details.privateKey)
      );
      filesTransferred = counts.filesTransferred;
      bytesTransferred = counts.bytesTransferred;
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
        filesTransferred,
        bytesTransferred,
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
  $ rdc repo sync upload my-app --local ./src  ${t('help.sync.upload')}
  $ rdc repo sync upload my-app --local ./config.toml --remote-file etc/config.toml
  $ rdc repo sync download my-app --local ./data  ${t('help.sync.download')}
  $ rdc repo sync download my-app --local ./out --remote-file etc/config.toml
`
  );

  // sync upload
  sync
    .command('upload')
    .summary(t('commands.sync.upload.descriptionShort'))
    .description(t('commands.sync.upload.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--local <paths...>', t('options.localPaths'))
    .option('--remote <path>', t('options.remotePath'))
    .option('--remote-file <path>', t('options.remoteFileUpload'))
    .option('--mirror', t('options.mirrorUpload'))
    .option('--verify', t('options.verifyChecksum'))
    .option('--confirm', t('options.confirmSync'))
    .option('--exclude <patterns...>', t('options.excludePatterns'))
    .option('--dry-run', t('options.dryRun'))
    .action(async (ref: string, options: SyncUploadOptions) => {
      try {
        await syncUpload(ref, options);
      } catch (error) {
        handleError(error);
      }
    });

  // sync download
  sync
    .command('download')
    .summary(t('commands.sync.download.descriptionShort'))
    .description(t('commands.sync.download.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--local <path>', t('options.localPath'))
    .option('--remote <path>', t('options.remotePath'))
    .option('--remote-file <path>', t('options.remoteFile'))
    .option('--mirror', t('options.mirrorDownload'))
    .option('--verify', t('options.verifyChecksum'))
    .option('--confirm', t('options.confirmSync'))
    .option('--exclude <patterns...>', t('options.excludePatterns'))
    .option('--dry-run', t('options.dryRun'))
    .action(async (ref: string, options: SyncDownloadOptions) => {
      try {
        await syncDownload(ref, options);
      } catch (error) {
        handleError(error);
      }
    });

  // sync status
  sync
    .command('status')
    .summary(t('commands.sync.status.descriptionShort'))
    .description(t('commands.sync.status.description'))
    .argument('<ref>', t('options.repoRef'))
    .option('--local <path>', t('options.localPath'))
    .option('--remote <path>', t('options.remotePath'))
    .option('--remote-file <path>', t('options.remoteFile'))
    .action(async (ref: string, options: SyncDownloadOptions) => {
      try {
        // Read-only: derive the machine, skip the mutating remote round-trip.
        await syncDownload(ref, { ...options, dryRun: true, localOnly: true }, { readOnly: true });
      } catch (error) {
        handleError(error);
      }
    });
}

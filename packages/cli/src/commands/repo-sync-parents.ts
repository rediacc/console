import {
  executeRsync,
  planMissingParents,
  type RsyncExecutorOptions,
  skeletonDestination,
  writeSkeleton,
} from '../remote/sync/index.js';
import { withPooledSftp } from '../services/machine/machine-connection.js';
import { debugLog } from '../utils/debug.js';
import { isRsyncNotFoundError, type SyncConnectionContext } from './repo-sync-helpers.js';

class RemoteFoldersError extends Error {}

export interface EnsureRemoteParentsArgs {
  baseRemotePath: string;
  /** The `--remote-file` or `--remote` value; its own last component is left to the transfer. */
  subPath: string;
  /** `user@host` of the rsync destination. */
  userHost: string;
  /** The upload's options; only ssh options and the universal user are reused. */
  rsyncOptions: RsyncExecutorOptions;
  probe: (remotePath: string) => Promise<boolean>;
  runRsync: (options: RsyncExecutorOptions) => Promise<{ success: boolean; errors: string[] }>;
}

/**
 * Creates the missing parent directories of an upload's destination with the universal user's ownership, in file mode and directory mode alike. The transfer's own rsync would create them as root (`--mkpath` under `sudo rsync`) or fail (directory mode, two or more missing levels). Only segments the probe found missing are sent, so existing directories keep their owner.
 * Returns the segments created.
 */
export async function ensureRemoteParents(args: EnsureRemoteParentsArgs): Promise<string[]> {
  const { existingAncestor, missing } = await planMissingParents(
    args.baseRemotePath,
    args.subPath,
    args.probe
  );
  if (missing.length === 0) return [];
  const skeleton = writeSkeleton(missing);
  try {
    const result = await args.runRsync({
      sshOptions: args.rsyncOptions.sshOptions,
      universalUser: args.rsyncOptions.universalUser,
      isUpload: true,
      source: skeleton.source,
      destination: skeletonDestination(args.userHost, existingAncestor, missing),
    });
    if (!result.success) {
      throw new RemoteFoldersError(
        `Creating remote folders failed: ${result.errors.join(' ').trim()}`
      );
    }
  } finally {
    skeleton.cleanup();
  }
  return missing;
}

/** Probes on one pooled SFTP connection; any failure to probe skips the step and the transfer proceeds as before. */
export async function ensureUploadParents(
  ctx: SyncConnectionContext,
  subPath: string | undefined,
  rsyncOptions: RsyncExecutorOptions
): Promise<void> {
  if (!subPath || !ctx.baseRemotePath) return;
  const baseRemotePath = ctx.baseRemotePath;
  try {
    await withPooledSftp(ctx.sftpConfig, (sftp) =>
      ensureRemoteParents({
        baseRemotePath,
        subPath,
        userHost: `${ctx.details.user}@${ctx.details.host}`,
        rsyncOptions,
        probe: (p) => sftp.exists(p),
        runRsync: executeRsync,
      })
    );
  } catch (err) {
    if (isRsyncNotFoundError(err)) throw err;
    if (err instanceof RemoteFoldersError) throw err;
    debugLog(`remote parent probe skipped: ${err instanceof Error ? err.message : String(err)}`);
  }
}

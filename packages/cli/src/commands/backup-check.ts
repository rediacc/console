/**
 * `rdc backup check <repo> [--path <file>]`: prove a stored snapshot opens with the passphrase.
 *
 * The scheduled unit holds no passphrase by design, so this runs from where the passphrase lives:
 * it browses the newest snapshot's sealed listing (which only the passphrase opens), restores ONE
 * file into a scratch directory (which opens the partial image with the passphrase and reads real
 * content), compares the bytes written with the listed size, and posts `test-open` as `proven` or
 * `failed`. The scratch directory is unique per run and is the only thing deleted afterwards.
 *
 * A snapshot with no stored listing cannot be checked this way. It is reported plainly and is never
 * `proven`, and nothing is posted: an absent index says nothing about whether the bytes are good.
 */

import { randomBytes } from 'node:crypto';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { assertHostedBackupAccount } from '../services/account/free-license.js';
import { DEFAULT_DATASTORE } from '../services/account/license-machine.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { machineConnections } from '../services/machine/machine-connection.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { shellQuote } from '../utils/shell-quote.js';
import { lineageOf, RENET_NO_LISTING_EXIT } from './backup-storage-browse.js';
import { type BrowseListing, parseBrowseResult } from './backup-storage-parser.js';
import type { BackupManifestsResponse } from './backup-storage.js';
import { postVerification, type VerificationAnswer } from './backup-verification.js';

/** The document the verb prints. */
interface CheckResult {
  repo: string;
  snapshotId: string;
  status: 'proven' | 'failed' | 'no-index';
  path?: string;
  /** The size the listing recorded for the file. */
  size?: number;
  bytesWritten?: number;
  reason?: string;
  /** What the server holds for the snapshot after the verdict was posted; absent when nothing was posted. */
  verificationState?: string;
}

/** Bytes the restore wrote, from `backup_restore_path`'s record. */
function parseBytesWritten(stdout: string | undefined): number | undefined {
  let found: number | undefined;
  for (const line of (stdout ?? '').split('\n')) {
    const start = line.indexOf('{');
    if (start === -1) continue;
    try {
      const parsed: unknown = JSON.parse(line.slice(start));
      if (parsed !== null && typeof parsed === 'object' && 'bytesWritten' in parsed) {
        found = Number((parsed as { bytesWritten: unknown }).bytesWritten);
      }
    } catch {
      // A partial line or a log prefix: not the record.
    }
  }
  return found;
}

/** The smallest non-empty regular file: the cheapest real content to read back. */
function pickFile(listing: BrowseListing): { path: string; size: number } | undefined {
  return listing.entries
    .filter((e) => e.type === 'file' && e.size > 0)
    .sort((a, b) => a.size - b.size)
    .at(0);
}

function normalizePath(p: string): string {
  return p.replace(/^\/+/, '').replace(/\/+$/, '');
}

/** Delete the scratch directory, and only that: the guard refuses anything not shaped like this verb's own. */
async function removeScratch(
  machineName: string,
  datastore: string,
  scratch: string
): Promise<void> {
  if (
    !new RegExp(
      `^${datastore.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/restores/check-[0-9a-f]{8}$`
    ).test(scratch)
  ) {
    throw new Error(
      `backup check refuses to delete "${scratch}": it is not its own scratch directory`
    );
  }
  const lease = await machineConnections.acquire(machineName);
  try {
    await lease.sftp.exec(`sudo rm -rf -- ${shellQuote(scratch)}`);
  } catch {
    outputService.warn(
      t('commands.backup.check.scratchLeft', { path: scratch, machine: machineName })
    );
    setExitCode(1);
  } finally {
    lease.release();
  }
}

/** The newest snapshot of the lineage, by parsed time. */
async function newestSnapshot(
  lineage: string
): Promise<BackupManifestsResponse['manifests'][number] | undefined> {
  assertHostedBackupAccount();
  const index = await accountServerFetch<BackupManifestsResponse>(
    `/account/api/v1/backups/manifests?lineage=${encodeURIComponent(lineage)}`
  );
  return [...index.manifests]
    .sort((a, b) => (Date.parse(b.createdAt) || 0) - (Date.parse(a.createdAt) || 0))
    .at(0);
}

const REASON_NO_INDEX = 'no stored listing';
const REASON_BROWSE_FAILED = 'the listing could not be opened with the passphrase';
const REASON_RESTORE_FAILED = 'the file could not be restored';

interface CheckTarget {
  repoKey: string;
  machineName: string;
  lineage: string;
  snapshotId: string;
  hasIndex: boolean;
  datastore: string | undefined;
  debug: boolean | undefined;
}

/** The repository, its credential and the newest snapshot, or a refusal that names the missing piece. */
async function resolveTarget(repoRef: string, debug: boolean | undefined): Promise<CheckTarget> {
  const { repoKey, machineName } = await resolveRepoRef(repoRef);
  const repo = await configService.getRepository(repoKey);
  if (!repo) throw new ValidationError(`Repository "${repoKey}" not found in this config.`);
  if (!repo.credential) {
    throw new ValidationError(t('commands.backup.check.needsCredential', { name: repoKey }));
  }
  const lineage = lineageOf(repo);
  const snapshot = await newestSnapshot(lineage);
  if (!snapshot)
    throw new ValidationError(t('commands.backup.check.noSnapshot', { name: repoKey }));
  return {
    repoKey,
    machineName,
    lineage,
    snapshotId: snapshot.snapshotId,
    hasIndex: snapshot.hasIndex !== false,
    datastore: await recordedDatastoreMount(repoKey),
    debug,
  };
}

type Browsed =
  | { kind: 'no-index' }
  | { kind: 'failed'; reason: string }
  | { kind: 'ok'; listing: BrowseListing };

/** Browse the snapshot's sealed listing; only the passphrase opens it. */
async function browseSnapshot(target: CheckTarget, path: string): Promise<Browsed> {
  const browse = await getExecutor().execute({
    functionName: 'backup_browse_at',
    machineName: target.machineName,
    datastore: target.datastore,
    params: {
      repository: target.repoKey,
      lineage: target.lineage,
      at: target.snapshotId,
      path,
      depth: '0',
      limit: '10000',
    },
    debug: target.debug,
    captureOutput: true,
    probe: true,
  });
  if (!browse.success && browse.exitCode === RENET_NO_LISTING_EXIT) return { kind: 'no-index' };
  const listing = browse.success ? parseBrowseResult(browse.stdout) : undefined;
  if (!listing) return { kind: 'failed', reason: browse.error ?? REASON_BROWSE_FAILED };
  return { kind: 'ok', listing };
}

/** The file to read back: the one named, or the cheapest real content. */
function chooseFile(
  listing: BrowseListing,
  wantedPath: string | undefined
): { path: string; size: number } | undefined {
  if (wantedPath === undefined) return pickFile(listing);
  return listing.entries
    .filter((e) => e.type === 'file' && normalizePath(e.path) === wantedPath)
    .map((e) => ({ path: normalizePath(e.path), size: e.size }))
    .at(0);
}

/** Restore one file into a unique scratch directory and report the bytes written; the scratch is always removed. */
async function restoreOneFile(
  target: CheckTarget,
  file: { path: string }
): Promise<{ written?: number; error?: string }> {
  const machineDatastore = await datastorePath(target.machineName);
  const scratch = `${machineDatastore}/restores/check-${randomBytes(4).toString('hex')}`;
  try {
    const restored = await getExecutor().execute({
      functionName: 'backup_restore_path',
      machineName: target.machineName,
      datastore: target.datastore,
      params: {
        repository: target.repoKey,
        lineage: target.lineage,
        at: target.snapshotId,
        path: file.path,
        to: scratch,
      },
      debug: target.debug,
      captureOutput: true,
      probe: true,
    });
    if (!restored.success) return { error: restored.error ?? REASON_RESTORE_FAILED };
    return { written: parseBytesWritten(restored.stdout) };
  } finally {
    await removeScratch(target.machineName, machineDatastore, scratch);
  }
}

/** Post the verdict and let the server's answer, not the post, decide what is printed. */
async function recordVerdict(
  base: { repo: string; snapshotId: string; path: string; size: number },
  written: number
): Promise<CheckResult> {
  const matches = written === base.size;
  const answer: VerificationAnswer = await postVerification(
    base.snapshotId,
    'test-open',
    matches ? 'proven' : 'failed'
  );
  // A `proven` post can come back `failed` while a failure on the snapshot still stands.
  if (matches && answer.verificationState === 'proven') {
    return { ...base, bytesWritten: written, status: 'proven', verificationState: 'proven' };
  }
  return {
    ...base,
    bytesWritten: written,
    status: 'failed',
    verificationState: answer.verificationState,
    reason: matches
      ? `the server holds this snapshot as ${answer.verificationState}`
      : `the file was listed at ${base.size} bytes and restored as ${written}`,
  };
}

/** The listing has nothing to read back: no non-empty file, or the named path is not a file in it. */
function noFileResult(
  repo: string,
  snapshotId: string,
  wantedPath: string | undefined
): CheckResult {
  return {
    repo,
    snapshotId,
    status: 'failed',
    ...(wantedPath !== undefined && { path: wantedPath }),
    reason:
      wantedPath === undefined
        ? 'the listing holds no non-empty file to restore'
        : 'the path is not a file in the listing',
  };
}

/** Run the check for one repository. */
async function runBackupCheck(
  repoRef: string,
  options: { path?: string; debug?: boolean }
): Promise<CheckResult> {
  const target = await resolveTarget(repoRef, options.debug);
  const { repoKey, snapshotId } = target;
  const noIndex = (): CheckResult => {
    outputService.warn(t('commands.backup.check.noIndex', { name: repoKey, snapshot: snapshotId }));
    return { repo: repoKey, snapshotId, status: 'no-index', reason: REASON_NO_INDEX };
  };
  if (!target.hasIndex) return noIndex();

  const wantedPath = options.path === undefined ? undefined : normalizePath(options.path);
  const browsed = await browseSnapshot(target, wantedPath ?? '');
  if (browsed.kind === 'no-index') return noIndex();
  if (browsed.kind === 'failed') {
    return { repo: repoKey, snapshotId, status: 'failed', reason: browsed.reason };
  }
  const file = chooseFile(browsed.listing, wantedPath);
  if (!file) return noFileResult(repoKey, snapshotId, wantedPath);

  const base = { repo: repoKey, snapshotId, path: file.path, size: file.size };
  const restored = await restoreOneFile(target, file);
  if (restored.written === undefined) {
    return { ...base, status: 'failed', reason: restored.error ?? REASON_RESTORE_FAILED };
  }
  return recordVerdict(base, restored.written);
}

/** The datastore mount the scratch directory lives under. */
async function datastorePath(machineName: string): Promise<string> {
  const lease = await machineConnections.acquire(machineName);
  try {
    return lease.machine.datastore ?? DEFAULT_DATASTORE;
  } finally {
    lease.release();
  }
}

export function registerBackupCheck(backup: Command): void {
  backup
    .command('check')
    .argument('<repo-ref>', t('options.repoRef'))
    .description(t('commands.backup.check.description'))
    .option('--path <file>', t('commands.backup.check.optionPath'))
    .option('--debug', t('options.debug'))
    .action(async (repoRef: string, options: { path?: string; debug?: boolean }) => {
      try {
        const result = await runBackupCheck(repoRef, options);
        const format = getOutputFormat();
        outputService.print(result, format === 'table' ? 'json' : format);
        if (result.status !== 'proven') setExitCode(1);
      } catch (error) {
        handleError(error);
      }
    });
}

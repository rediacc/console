/**
 * `rdc backup verify <repo> --restore-test`: the proof that a stored snapshot restores to the
 * bytes the machine holds. It restores the source's ANCHOR snapshot under a throwaway name with
 * `--no-seed`, so every byte comes from the store and none from a local image, compares the copy
 * with the anchor file, records the verdict on the snapshot, and deletes the copy.
 *
 * Three rules shape it. The copy is a fresh repository (fresh GUID, never the source's), and the
 * only delete this verb issues names that copy. The credential is the repository's own and reaches
 * renet through the vault and stdin, never argv or the step plan. And a verdict is only posted when
 * the comparison was about the snapshot restored: an anchor that moved mid-run says nothing about it.
 */

import { randomBytes, randomUUID } from 'node:crypto';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { assertHostedBackupAccount } from '../services/account/free-license.js';
import { DEFAULT_DATASTORE } from '../services/account/license-machine.js';
import { configService } from '../services/config/config-resources.js';
import { targetFloor } from '../services/config/network-id-discovery.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { machineConnections } from '../services/machine/machine-connection.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { assertResourceName, compositeKey } from '../utils/config-schema.js';
import { getOutputFormat, ValidationError } from '../utils/errors.js';
import { shellQuote } from '../utils/shell-quote.js';
import { readSourceAnchor } from './backup-restore-chunk.js';
import { lineageOf } from './backup-storage-browse.js';
import {
  type CompareRecord,
  parseCompareRecord,
  parseRestoreStats,
  type RestoreStats,
} from './backup-storage-parser.js';
import type { BackupManifestsResponse } from './backup-storage.js';
import { postVerification, type VerificationAnswer } from './backup-verification.js';
import { resolveRepoRef } from '../utils/repo-target.js';

/** The copy needs the image plus headroom for the staging file's metadata and the filesystem. */
export const RESTORE_TEST_SPACE_FACTOR = 1.2;

/** The one document the verb prints. */
export interface RestoreTestResult {
  repo: string;
  snapshotId: string;
  copy: string;
  copyGuid: string;
  status: 'proven' | 'failed';
  reason?: string;
  passphraseCheck?: string;
  compare?: CompareRecord;
  /** What the server holds for the snapshot after the verdict was posted; absent when nothing was posted. */
  verificationState?: string;
  cleanup: 'deleted' | 'failed';
}

interface SourceRepo {
  repositoryGuid: string;
  grandGuid?: string;
  credential?: string;
}

/** Free bytes on the machine's datastore, or undefined when the probe cannot answer. */
async function datastoreFreeBytes(machineName: string): Promise<number | undefined> {
  const lease = await machineConnections.acquire(machineName);
  try {
    const datastore = lease.machine.datastore ?? DEFAULT_DATASTORE;
    const out = await lease.sftp.exec(
      `df -B1 --output=avail ${shellQuote(datastore)} | tail -n 1`
    );
    const free = out.trim();
    return /^\d+$/.test(free) ? Number(free) : undefined;
  } finally {
    lease.release();
  }
}

/** The snapshot's image size, from the account's index; undefined when the index does not hold it. */
async function indexedImageBytes(lineage: string, snapshotId: string): Promise<number | undefined> {
  assertHostedBackupAccount();
  const index = await accountServerFetch<BackupManifestsResponse>(
    `/account/api/v1/backups/manifests?lineage=${encodeURIComponent(lineage)}`
  );
  return index.manifests.find((m) => m.snapshotId === snapshotId)?.totalBytes;
}

function copyName(): string {
  return `restoretest-${randomBytes(4).toString('hex')}`;
}

/** Delete the copy, and only the copy. A failure is said by name, since a stranded copy is a whole image on the datastore. */
async function deleteCopy(
  name: string,
  machineName: string,
  source: { key: string; guid: string },
  copyGuid: string
): Promise<'deleted' | 'failed'> {
  if (copyGuid === source.guid || name === source.key || !name.startsWith('restoretest-')) {
    // Unreachable by construction; refusing here is what keeps a future edit from turning this into a delete of the source.
    throw new Error(`restore-test refuses to delete "${name}": it is not the throwaway copy`);
  }
  let ok = false;
  try {
    const result = await getExecutor().execute({
      functionName: 'repository_delete',
      machineName,
      params: { repository: name },
    });
    ok = result.success;
  } catch {
    ok = false;
  }
  if (ok) {
    await configService.removeRepository(compositeKey(name, 'latest')).catch(() => undefined);
    return 'deleted';
  }
  outputService.warn(
    t('commands.backup.verify.restoreTestCleanupFailed', { copy: name, machine: machineName })
  );
  setExitCode(1);
  return 'failed';
}

interface Verdict {
  status: 'proven' | 'failed';
  reason?: string;
  passphraseCheck?: string;
  compare?: CompareRecord;
  /** Post `failed` to the server: only for a copy that provably differs. */
  postFailed: boolean;
}

/** Restore the snapshot into the copy and hold it to the anchor. Never throws on a verdict, only on infrastructure. */
async function restoreAndCompare(args: {
  copy: string;
  machine: string;
  lineage: string;
  snapshotId: string;
  sourceGuid: string;
}): Promise<Verdict> {
  const { copy, machine, lineage, snapshotId, sourceGuid } = args;
  await deployRepoKeyIfNeeded(copy, machine);
  const restore = await getExecutor().execute({
    functionName: 'backup_restore',
    machineName: machine,
    params: { repository: copy, lineage, at: snapshotId, dry_run: false, no_seed: true },
    captureOutput: true,
    probe: true,
  });
  const record: RestoreStats | undefined = parseRestoreStats(restore.stdout);
  if (!restore.success) {
    return {
      status: 'failed',
      reason: record?.reason ?? restore.error ?? 'the restore of the copy failed',
      passphraseCheck: record?.passphraseCheck,
      postFailed: false,
    };
  }
  const compare = await getExecutor().execute({
    functionName: 'backup_compare',
    machineName: machine,
    params: { repository: copy, against_anchor: sourceGuid },
    captureOutput: true,
    probe: true,
  });
  const verdict = parseCompareRecord(compare.stdout);
  const passphraseCheck = record?.passphraseCheck;
  if (!verdict) {
    return { status: 'failed', reason: compare.error ?? 'unreadable compare record', passphraseCheck, postFailed: false };
  }
  if (verdict.anchorSnapshotId !== snapshotId) {
    return {
      status: 'failed',
      reason: `the anchor moved from ${snapshotId} to ${verdict.anchorSnapshotId ?? '-'} during the test, so the copy cannot be compared; run it again`,
      passphraseCheck,
      compare: verdict,
      postFailed: false,
    };
  }
  if (verdict.status !== 'identical') {
    return { status: 'failed', reason: verdict.reason, passphraseCheck, compare: verdict, postFailed: verdict.status === 'different' };
  }
  if (passphraseCheck !== 'opened') {
    return {
      status: 'failed',
      reason: 'the copy matches the anchor but the passphrase did not open it, so it is not proven',
      passphraseCheck,
      compare: verdict,
      postFailed: false,
    };
  }
  return { status: 'proven', passphraseCheck, compare: verdict, postFailed: false };
}

/** Run the restore test for one repository and print its verdict. Exit 1 unless proven. */
export async function runRestoreTest(repoRef: string): Promise<void> {
  const { repoKey, machineName } = await resolveRepoRef(repoRef);
  const source = (await configService.getRepository(repoKey)) as SourceRepo | undefined;
  if (!source) throw new ValidationError(`Repository "${repoKey}" not found in this config.`);
  if (!source.credential) {
    throw new ValidationError(t('commands.backup.verify.restoreTestNeedsCredential', { name: repoKey }));
  }
  const lineage = lineageOf(source);
  const snapshotId = await readSourceAnchor({ repoName: repoKey, machine: machineName });
  if (!snapshotId) {
    throw new ValidationError(t('commands.backup.verify.restoreTestNoAnchor', { name: repoKey }));
  }
  const imageBytes = await indexedImageBytes(lineage, snapshotId);
  const free = await datastoreFreeBytes(machineName);
  if (imageBytes === undefined || free === undefined || free < imageBytes * RESTORE_TEST_SPACE_FACTOR) {
    throw new ValidationError(
      t('commands.backup.verify.restoreTestNoSpace', {
        snapshot: snapshotId,
        need: imageBytes === undefined ? '?' : Math.ceil(imageBytes * RESTORE_TEST_SPACE_FACTOR),
        free: free ?? '?',
      })
    );
  }

  const name = copyName();
  assertResourceName(name);
  const copyGuid = randomUUID();
  if (copyGuid === source.repositoryGuid) throw new Error('restore-test: the copy collides with the source');
  await configService.addRepository(compositeKey(name, 'latest'), {
    repositoryGuid: copyGuid,
    grandGuid: lineage,
    tag: 'latest',
    credential: source.credential,
    networkId: await configService.allocateNetworkId({
      floor: await targetFloor({ machine: machineName }),
    }),
    placement: { machine: machineName },
  });

  let verdict: Verdict;
  let answer: VerificationAnswer | undefined;
  let cleanup: 'deleted' | 'failed';
  try {
    verdict = await restoreAndCompare({
      copy: name,
      machine: machineName,
      lineage,
      snapshotId,
      sourceGuid: source.repositoryGuid,
    });
    if (verdict.status === 'proven' || verdict.postFailed) {
      answer = await postVerification(snapshotId, 'restore-test', verdict.status);
    }
  } finally {
    cleanup = await deleteCopy(
      name,
      machineName,
      { key: repoKey, guid: source.repositoryGuid },
      copyGuid
    );
  }

  // The server's answer is the verdict: a `proven` post can come back `failed` while a failure on the snapshot still stands.
  const held = answer?.verificationState;
  const proven = verdict.status === 'proven' && held === 'proven';
  const result: RestoreTestResult = {
    repo: repoKey,
    snapshotId,
    copy: name,
    copyGuid,
    status: proven ? 'proven' : 'failed',
    ...(proven ? {} : { reason: verdict.reason ?? `the server holds this snapshot as ${held ?? 'unrecorded'}` }),
    ...(verdict.passphraseCheck && { passphraseCheck: verdict.passphraseCheck }),
    ...(verdict.compare && { compare: verdict.compare }),
    ...(held && { verificationState: held }),
    cleanup,
  };
  const format = getOutputFormat();
  outputService.print(result, format === 'table' ? 'json' : format);
  if (!proven) setExitCode(1);
}

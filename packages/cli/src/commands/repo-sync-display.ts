import { createHash } from 'node:crypto';
import type ora from 'ora';
import { t } from '../i18n/index.js';
import { warnSkippedEntries } from '../remote/sync/index.js';
import { writeProgress } from '../services/core/progress-output.js';
import { setExitCode, writeStderr, writeStdout } from '../services/core/request-context.js';
import { formatBytes } from './repo-sync-helpers.js';

function writeDeletedCount(deleted: number | undefined): void {
  if (deleted !== undefined && deleted > 0) {
    writeProgress(`${t('commands.sync.deleted', { count: deleted })}\n`);
  }
}

export function displaySyncResult(
  result: {
    success: boolean;
    filesTransferred: number;
    bytesTransferred: number;
    duration: number;
    errors: string[];
    skipped?: string[];
    deleted?: number;
  },
  spinner: ReturnType<typeof ora>,
  mode: 'upload' | 'download'
): void {
  if (result.success) {
    spinner.succeed(t(`commands.sync.${mode}.completed`, { count: result.filesTransferred }));
    if (result.bytesTransferred > 0) {
      writeProgress(
        `${t('commands.sync.totalSize', { size: formatBytes(result.bytesTransferred) })}\n`
      );
    }
    writeDeletedCount(result.deleted);
    writeProgress(
      `${t('commands.sync.duration', { seconds: (result.duration / 1000).toFixed(1) })}\n`
    );
    warnSkippedEntries(result.skipped ?? [], t, writeStderr);
  } else {
    spinner.fail(t(`commands.sync.${mode}.failed`));
    if (result.errors.length > 0) {
      writeStderr(`${t('commands.sync.errors')}\n`);
      for (const err of result.errors) {
        writeStderr(`  ${err}\n`);
      }
    }
    setExitCode(1);
  }
}

/**
 * Non-secret shape summary of the SSH key the rsync leg will write to its temp
 * file: PEM header line, byte length, and a hash prefix. Appended to the error
 * output when the ssh client rejects the key ("Load key … error in libcrypto",
 * observed once in CI with no local reproduction) so the next occurrence
 * identifies WHICH key content was written without leaking any material.
 */
export function sshKeyDiagnostic(privateKey: string): string {
  const first = privateKey.trimStart().split('\n', 1)[0] ?? '';
  // Only a PEM armour line is printed: a key with no newline (the malformed case this diagnostic exists for) would otherwise print in full (8b24deb8.2).
  const header = /^-----BEGIN (?:(?:OPENSSH|RSA|EC|DSA|ENCRYPTED) )?PRIVATE KEY-----\r?$/.test(
    first
  )
    ? first.trimEnd()
    : '<not a PEM header>';
  const digest = createHash('sha256').update(privateKey).digest('hex').slice(0, 12);
  return `ssh key diagnostic: header="${header}" length=${privateKey.length} sha256=${digest}`;
}

export const SSH_KEY_FAILURE_PATTERN = /load key|libcrypto|permission denied \(publickey/i;

export function displaySftpDryRunResult(result: {
  filesTransferred: number;
  bytesTransferred: number;
}): void {
  writeStdout(
    `\nSFTP fallback (rsync not available):\n  Files to transfer: ${result.filesTransferred}\n  Total size: ${formatBytes(result.bytesTransferred)}\n`
  );
}

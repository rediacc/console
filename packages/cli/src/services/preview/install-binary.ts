/**
 * Replacing the installed `rdc` for `rdc preview use` and `leave` (PLAN-preview-signer.md D8). The updater's
 * own replace is tied to the running binary and to "newer only"; a preview switch installs a named binary at a
 * named path, forced, and keeps the CLI it replaces.
 */
import { promises as fs } from 'node:fs';
import { dirname } from 'node:path';
import { t } from '../../i18n/index.js';
import { ValidationError } from '../../utils/errors.js';
import { acquireUpdateLock } from '../../utils/platform.js';
import { computeSha256, downloadFile } from '../update/updater.js';
import type { PreviewBinary } from './build.js';

/** `<base>.old<ext>` beside `target`, the slot `rdc update --rollback` swaps back. */
function oldPathFor(target: string): string {
  const ext = process.platform === 'win32' ? '.exe' : '';
  return `${target.replace(/\.exe$/, '')}.old${ext}`;
}

/** Copy the running CLI to `dest`, returning where it was installed and its sha256. */
export async function keepCurrentBinary(
  dest: string,
  source = process.execPath
): Promise<{ installPath: string; sha256: string }> {
  await fs.mkdir(dirname(dest), { recursive: true });
  await fs.copyFile(source, dest);
  if (process.platform !== 'win32') await fs.chmod(dest, 0o755);
  const sha256 = await computeSha256(dest);
  if (sha256 !== (await computeSha256(source))) {
    throw new Error(`the kept copy at ${dest} does not match the running binary`);
  }
  return { installPath: source, sha256 };
}

/** Swap `staged` in over `target`, keeping the previous file as `.old` and restoring it when the swap fails. */
async function swapIn(staged: string, target: string): Promise<void> {
  const oldPath = oldPathFor(target);
  let hadTarget = true;
  try {
    await fs.unlink(oldPath).catch(() => undefined);
    await fs.rename(target, oldPath);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    hadTarget = false;
  }
  try {
    await fs.rename(staged, target);
  } catch (error) {
    if (hadTarget) {
      try {
        await fs.rename(oldPath, target);
      } catch (restoreError) {
        throw new Error(
          `the new binary could not be installed (${(error as Error).message}) and the previous one could not be put back from ${oldPath} (${(restoreError as Error).message})`
        );
      }
    }
    throw error;
  }
  if (process.platform !== 'win32') await fs.chmod(target, 0o755);
}

/** Download `binary`, check its sha256, and install it at `targetPath` under the update lock. Nothing is replaced on a mismatch. */
export async function installBinaryAtPath(
  targetPath: string,
  binary: PreviewBinary,
  onProgress?: (downloaded: number, total: number) => void
): Promise<void> {
  const release = await acquireUpdateLock({ waitMs: 3000 });
  if (!release) throw new ValidationError(t('commands.update.errors.lockFailed'));
  const staged = `${targetPath}.preview-${process.pid}-${Date.now()}.tmp`;
  try {
    await downloadFile(binary.url, staged, onProgress);
    if ((await computeSha256(staged)) !== binary.sha256) {
      throw new ValidationError(t('commands.update.errors.checksumMismatch'));
    }
    await swapIn(staged, targetPath);
  } finally {
    await fs.unlink(staged).catch(() => undefined);
    await release();
  }
}

/** Put the kept copy back at `targetPath` when it still hashes to `expectedSha256`. */
export async function restoreKeptBinary(
  keptPath: string,
  targetPath: string,
  expectedSha256: string
): Promise<void> {
  let actual: string;
  try {
    actual = await computeSha256(keptPath);
  } catch (error) {
    throw new Error(`the kept copy ${keptPath} cannot be read: ${(error as Error).message}`);
  }
  if (actual !== expectedSha256) {
    throw new Error(`the kept copy ${keptPath} no longer matches the CLI that was replaced`);
  }
  const staged = `${targetPath}.preview-${process.pid}-${Date.now()}.tmp`;
  try {
    await fs.copyFile(keptPath, staged);
    await swapIn(staged, targetPath);
  } finally {
    await fs.unlink(staged).catch(() => undefined);
  }
}

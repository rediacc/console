/**
 * The CLIENT host's identity: the id the account server records as
 * `clientMachineId` on issued blobs and feedback reports. Everything here reads
 * the local host only and never reaches a machine; the licensed machine's id
 * is read remotely by `readRemoteMachineId` in `license-machine.ts`.
 */

import { randomUUID } from 'node:crypto';
import { dirname, join } from 'node:path';
import { getConfigDir } from '@rediacc/shared/paths';
import { ERROR_CODES } from '../../types/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';

const CLIENT_MACHINE_ID_PATH = '/etc/machine-id';
const CLIENT_MACHINE_ID_DBUS_PATH = '/var/lib/dbus/machine-id';
const CLIENT_INSTALL_ID_FILE = 'client-machine-id';

export async function readLocalMachineId(): Promise<string> {
  if (process.platform === 'win32') {
    // Windows: use MachineGuid from the registry, hashed to match Linux format
    const { execSync } = await import('node:child_process');
    const { createHash } = await import('node:crypto');
    const output = execSync('reg query "HKLM\\SOFTWARE\\Microsoft\\Cryptography" /v MachineGuid', {
      encoding: 'utf-8',
    });
    const match = /MachineGuid\s+REG_SZ\s+(.+)/.exec(output);
    if (!match) throw new Error('Failed to read Windows MachineGuid from registry');
    return createHash('sha256').update(match[1].trim()).digest('hex');
  }
  if (process.platform === 'darwin') {
    // macOS: use IOPlatformUUID from I/O Kit, hashed to match Linux format
    const { execSync } = await import('node:child_process');
    const { createHash } = await import('node:crypto');
    const output = execSync('ioreg -rd1 -c IOPlatformExpertDevice | grep IOPlatformUUID', {
      encoding: 'utf-8',
    });
    const match = /"IOPlatformUUID"\s*=\s*"([^"]+)"/.exec(output);
    if (!match) throw new Error('Failed to read macOS IOPlatformUUID');
    return createHash('sha256').update(match[1].trim()).digest('hex');
  }
  return readLinuxClientMachineId();
}

export interface LinuxClientIdSources {
  /** Host identity files, tried in order. */
  hostPaths: string[];
  /** Where a generated per-install id is kept when no host file exists. */
  installIdPath: string;
}

/**
 * The client id on Linux. The account server stores `clientMachineId` as the
 * identity of the CLIENT host (it rides the signed blob and the audit log; it
 * is never compared, renet only carries the field). The licensed machine is
 * identified separately by `machineId`, read remotely as root.
 *
 * A caller without a host id is normal, not broken: a proxied command runs in
 * the executor container, which has no /etc/machine-id. It then uses a
 * generated id persisted in the CLI config dir, so the same install reports
 * the same client. When even that cannot be written, the failure is a named
 * PRECONDITION_MISMATCH, never a raw ENOENT.
 */
export async function readLinuxClientMachineId(
  sources: LinuxClientIdSources = {
    hostPaths: [CLIENT_MACHINE_ID_PATH, CLIENT_MACHINE_ID_DBUS_PATH],
    installIdPath: join(getConfigDir(), CLIENT_INSTALL_ID_FILE),
  }
): Promise<string> {
  // writeFile and mkdir are read only on the fallback path: a caller with a host id
  // (and a test that mocks node:fs/promises with readFile alone) never touches them.
  const fsp = await import('node:fs/promises');
  const { readFile } = fsp;
  let unreadable: CliExitError | undefined;
  for (const path of sources.hostPaths) {
    const id = await readFile(path, 'utf-8').then(
      (v) => v.trim(),
      (error: unknown) => {
        // Only an absent file means "no host id". An unreadable one (EACCES, EISDIR) is remembered and reported once no later candidate yields an id, since falling back to the generated id would make this host report an id other than its real one.
        if ((error as NodeJS.ErrnoException).code !== 'ENOENT') {
          unreadable ??= new CliExitError(
            ERROR_CODES.PRECONDITION_MISMATCH,
            `Cannot read the client machine id at ${path} (${error instanceof Error ? error.message : String(error)}).`
          );
        }
        return '';
      }
    );
    if (id) return id;
  }
  if (unreadable) throw unreadable;
  const existing = await readFile(sources.installIdPath, 'utf-8').then(
    (v) => v.trim(),
    () => ''
  );
  if (/^[a-f0-9]{64}$/.test(existing)) return existing;
  const generated = `${randomUUID()}${randomUUID()}`.replaceAll('-', '').slice(0, 64);
  try {
    return await persistInstallId(sources.installIdPath, generated);
  } catch (error) {
    throw new CliExitError(
      ERROR_CODES.PRECONDITION_MISMATCH,
      `No client machine id: ${sources.hostPaths.join(' and ')} are missing and a generated one could not be saved to ${sources.installIdPath} (${error instanceof Error ? error.message : String(error)}). Make the CLI config directory writable.`
    );
  }
}

/** Save a generated id with an exclusive create: of two first runs racing here, one id is persisted and both calls get it. */
async function persistInstallId(path: string, generated: string): Promise<string> {
  const fsp = await import('node:fs/promises');
  try {
    await fsp.mkdir(dirname(path), { recursive: true, mode: 0o700 });
    await fsp.writeFile(path, `${generated}\n`, { mode: 0o600, flag: 'wx' });
    return generated;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'EEXIST') {
      const persisted = await readRacedInstallId(path);
      if (persisted) return persisted;
      // Nothing valid ever appeared: the file is a corrupt leftover, not a winner's. One racer replaces it under an exclusive lock file, so two runs never both overwrite it with their own ids.
      return replaceCorruptInstallId(path, generated);
    }
    throw error;
  }
}

/** How long a replace lock may stand before it is taken for a crashed holder's. */
const REPLACE_LOCK_STALE_MS = 5000;

/**
 * One attempt at the replace lock. Undefined when the lock is now held; otherwise the id the holder persisted while
 * this run waited, or '' when the holder has not written one (a lock past REPLACE_LOCK_STALE_MS is then removed as a
 * crashed holder's, so the caller contends again).
 */
async function tryReplaceLock(path: string, lockPath: string): Promise<string | undefined> {
  const fsp = await import('node:fs/promises');
  try {
    await fsp.writeFile(lockPath, '', { mode: 0o600, flag: 'wx' });
    return undefined;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'EEXIST') throw error;
  }
  const persisted = await readRacedInstallId(path);
  if (persisted) return persisted;
  const lock = await fsp.stat(lockPath).catch(() => undefined);
  if (lock && Date.now() - lock.mtimeMs > REPLACE_LOCK_STALE_MS) {
    await fsp.rm(lockPath, { force: true });
  }
  return '';
}

/**
 * Replace a corrupt id file: the lock holder re-checks, then writes; a racer that lost the lock waits for what the
 * holder wrote. A lock older than REPLACE_LOCK_STALE_MS is taken for a crashed holder's and removed, and the racer then
 * contends for the lock again. The holder's critical section is one read and one write, so a holder stalled past that
 * age is the accepted limit of an age-based lock; the write is still the holder's own id or a valid one a racer left,
 * and the holder re-reads the file under the lock before it overwrites.
 */
async function replaceCorruptInstallId(path: string, generated: string): Promise<string> {
  const fsp = await import('node:fs/promises');
  const lockPath = `${path}.replace`;
  for (;;) {
    const outcome = await tryReplaceLock(path, lockPath);
    if (outcome === undefined) break;
    if (outcome) return outcome;
  }
  try {
    const current = (await fsp.readFile(path, 'utf-8').catch(() => '')).trim();
    if (/^[a-f0-9]{64}$/.test(current)) return current;
    await fsp.writeFile(path, `${generated}\n`, { mode: 0o600 });
    return generated;
  } finally {
    await fsp.rm(lockPath, { force: true });
  }
}

/** The id a racing first run persisted. The winner may still be writing, so a few short reads cover the gap between its create and its write. */
async function readRacedInstallId(path: string): Promise<string | undefined> {
  const { readFile } = await import('node:fs/promises');
  for (let attempt = 0; attempt < 5; attempt++) {
    const persisted = (await readFile(path, 'utf-8').catch(() => '')).trim();
    if (/^[a-f0-9]{64}$/.test(persisted)) return persisted;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  return undefined;
}

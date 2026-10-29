/**
 * Local state file of a downloaded repo image (`rdc backup download`/`upload`).
 *
 * Pure bookkeeping, no i18n and no network. The state file is the single truth about a local image:
 * `status` is `incomplete` from before rsync writes its first byte until a run is verified.
 * No credential ever enters the file; serialization copies an explicit field list.
 */

import { randomBytes } from 'node:crypto';
import {
  chmodSync,
  closeSync,
  existsSync,
  fsyncSync,
  mkdirSync,
  openSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeSync,
} from 'node:fs';
import { hostname } from 'node:os';
import { dirname, join } from 'node:path';

export const IMAGE_STATE_SCHEMA = 1;
export const IMAGE_STATE_KIND = 'rediacc-repo-image';
export const HISTORY_LIMIT = 12;

export type ImageStatus = 'incomplete' | 'complete';
export type RunOutcome = 'complete' | 'failed' | 'interrupted';
export type VerifyMode = 'sha256+rsync' | 'rsync';

export interface ImageRepoIdentity {
  name: string;
  tag: string;
  guid: string;
  grandGuid: string | null;
}

export interface ImageRunBlock {
  startedAt: string;
  snapshotTakenAt: string;
  snapshotName: string;
  apparentBytes: number;
  allocatedBytes: number;
  checkpoint: boolean;
  attempts: number;
  lastError: string | null;
}

export interface ImageCompleteBlock {
  snapshotTakenAt: string;
  finishedAt: string;
  apparentBytes: number;
  sha256: string;
  verify: VerifyMode;
  literalBytes: number;
  matchedBytes: number;
  durationMs: number;
}

export interface ImageUploadRecord {
  machine: string;
  name: string;
  guid: string;
  datastore: string;
  startedAt: string;
  status: 'staging' | 'finalized';
}

export interface ImageHistoryEntry {
  startedAt: string;
  finishedAt: string;
  outcome: RunOutcome;
  literalBytes: number;
}

export interface ImageState {
  schema: number;
  kind: string;
  status: ImageStatus;
  image: string;
  config: string;
  machine: string;
  repo: ImageRepoIdentity;
  run: ImageRunBlock;
  complete: ImageCompleteBlock | null;
  upload: ImageUploadRecord | null;
  history: ImageHistoryEntry[];
}

export interface LocalImagePaths {
  /** `<dir>/<machine>`, mode 0700. */
  machineDir: string;
  /** `<name>.<tag>`. */
  stem: string;
  image: string;
  state: string;
  lock: string;
}

export function localImagePaths(
  dir: string,
  machine: string,
  name: string,
  tag: string
): LocalImagePaths {
  const machineDir = join(dir, machine);
  const stem = `${name}.${tag}`;
  return {
    machineDir,
    stem,
    image: join(machineDir, `${stem}.img`),
    state: join(machineDir, `${stem}.state.json`),
    lock: join(machineDir, `${stem}.lock`),
  };
}

export function readImageState(statePath: string): ImageState | null {
  let raw: string;
  try {
    raw = readFileSync(statePath, 'utf8');
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null;
    throw error;
  }
  const parsed = JSON.parse(raw) as ImageState;
  if (parsed.kind !== IMAGE_STATE_KIND || parsed.schema !== IMAGE_STATE_SCHEMA) {
    throw new Error(`unrecognised image state file: ${statePath}`);
  }
  return parsed;
}

/** Copies the known fields only, so a stray field (a credential, say) is never persisted. */
export function sanitizeImageState(state: ImageState): ImageState {
  const run = state.run;
  const c = state.complete;
  const u = state.upload;
  return {
    schema: IMAGE_STATE_SCHEMA,
    kind: IMAGE_STATE_KIND,
    status: state.status,
    image: state.image,
    config: state.config,
    machine: state.machine,
    repo: {
      name: state.repo.name,
      tag: state.repo.tag,
      guid: state.repo.guid,
      grandGuid: state.repo.grandGuid ?? null,
    },
    run: {
      startedAt: run.startedAt,
      snapshotTakenAt: run.snapshotTakenAt,
      snapshotName: run.snapshotName,
      apparentBytes: run.apparentBytes,
      allocatedBytes: run.allocatedBytes,
      checkpoint: run.checkpoint,
      attempts: run.attempts,
      lastError: run.lastError ?? null,
    },
    complete: c
      ? {
          snapshotTakenAt: c.snapshotTakenAt,
          finishedAt: c.finishedAt,
          apparentBytes: c.apparentBytes,
          sha256: c.sha256,
          verify: c.verify,
          literalBytes: c.literalBytes,
          matchedBytes: c.matchedBytes,
          durationMs: c.durationMs,
        }
      : null,
    upload: u
      ? {
          machine: u.machine,
          name: u.name,
          guid: u.guid,
          datastore: u.datastore,
          startedAt: u.startedAt,
          status: u.status,
        }
      : null,
    history: state.history.slice(-HISTORY_LIMIT).map((h) => ({
      startedAt: h.startedAt,
      finishedAt: h.finishedAt,
      outcome: h.outcome,
      literalBytes: h.literalBytes,
    })),
  };
}

function fsyncDir(dir: string): void {
  try {
    const fd = openSync(dir, 'r');
    try {
      fsyncSync(fd);
    } finally {
      closeSync(fd);
    }
  } catch {
    // Directory fsync is unsupported on some platforms (Windows); the rename already happened.
  }
}

export interface WriteHooks {
  /** Test seam: runs after the temp file is durable and before the rename. */
  beforeRename?: () => void;
}

/** Atomic write: temp file in the same directory, fsync, rename, fsync of the directory. */
export function writeImageState(statePath: string, state: ImageState, hooks?: WriteHooks): void {
  const dir = dirname(statePath);
  if (!existsSync(dir)) {
    mkdirSync(dir, { mode: 0o700 });
    chmodSync(dir, 0o700);
  }
  const tmp = `${statePath}.tmp-${process.pid}-${randomBytes(4).toString('hex')}`;
  const body = `${JSON.stringify(sanitizeImageState(state), null, 2)}\n`;
  const fd = openSync(tmp, 'wx', 0o600);
  try {
    writeSync(fd, body);
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
  try {
    hooks?.beforeRename?.();
    renameSync(tmp, statePath);
  } catch (error) {
    try {
      unlinkSync(tmp);
    } catch {
      // The temp file may already be gone.
    }
    throw error;
  }
  fsyncDir(dir);
}

export interface BeginRunInput {
  config: string;
  machine: string;
  image: string;
  repo: ImageRepoIdentity;
  snapshotTakenAt: string;
  snapshotName: string;
  apparentBytes: number;
  allocatedBytes: number;
  checkpoint: boolean;
  now: string;
}

function pushHistory(history: ImageHistoryEntry[], entry: ImageHistoryEntry): ImageHistoryEntry[] {
  return [...history, entry].slice(-HISTORY_LIMIT);
}

/**
 * Starts a run: `incomplete` with a fresh `run` block. The previous `complete` block stays, and
 * describes a copy that is no longer on disk until this run completes. `attempts` counts
 * consecutive runs that started from an `incomplete` state.
 */
export function beginRun(prev: ImageState | null, input: BeginRunInput): ImageState {
  const attempts = prev && prev.status === 'incomplete' ? prev.run.attempts + 1 : 1;
  return {
    schema: IMAGE_STATE_SCHEMA,
    kind: IMAGE_STATE_KIND,
    status: 'incomplete',
    image: input.image,
    config: input.config,
    machine: input.machine,
    repo: input.repo,
    run: {
      startedAt: input.now,
      snapshotTakenAt: input.snapshotTakenAt,
      snapshotName: input.snapshotName,
      apparentBytes: input.apparentBytes,
      allocatedBytes: input.allocatedBytes,
      checkpoint: input.checkpoint,
      attempts,
      lastError: null,
    },
    complete: prev?.complete ?? null,
    upload: prev?.upload ?? null,
    history: prev?.history ?? [],
  };
}

export interface CompleteRunInput {
  sha256: string;
  verify: VerifyMode;
  literalBytes: number;
  matchedBytes: number;
  durationMs: number;
  now: string;
}

/** Marks the run complete. Call only after the verification has passed. */
export function completeRun(state: ImageState, input: CompleteRunInput): ImageState {
  return {
    ...state,
    status: 'complete',
    run: { ...state.run, lastError: null },
    complete: {
      snapshotTakenAt: state.run.snapshotTakenAt,
      finishedAt: input.now,
      apparentBytes: state.run.apparentBytes,
      sha256: input.sha256,
      verify: input.verify,
      literalBytes: input.literalBytes,
      matchedBytes: input.matchedBytes,
      durationMs: input.durationMs,
    },
    history: pushHistory(state.history, {
      startedAt: state.run.startedAt,
      finishedAt: input.now,
      outcome: 'complete',
      literalBytes: input.literalBytes,
    }),
  };
}

export interface FailRunInput {
  error: string;
  outcome?: 'failed' | 'interrupted';
  literalBytes?: number;
  now: string;
}

/** Records a failed or interrupted run. The status stays `incomplete`. */
export function failRun(state: ImageState, input: FailRunInput): ImageState {
  return {
    ...state,
    status: 'incomplete',
    run: { ...state.run, lastError: input.error },
    history: pushHistory(state.history, {
      startedAt: state.run.startedAt,
      finishedAt: input.now,
      outcome: input.outcome ?? 'failed',
      literalBytes: input.literalBytes ?? 0,
    }),
  };
}

export function recordUpload(state: ImageState, upload: ImageUploadRecord | null): ImageState {
  return { ...state, upload };
}

export interface LockInfo {
  pid: number;
  host: string;
  startedAt: string;
}

export interface LockDeps {
  pid?: number;
  host?: string;
  now?: string;
  isPidAlive?: (pid: number) => boolean;
}

export class ImageLockError extends Error {
  constructor(
    message: string,
    readonly holder: LockInfo | null
  ) {
    super(message);
    this.name = 'ImageLockError';
  }
}

export function defaultIsPidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === 'EPERM';
  }
}

function readLock(lockPath: string): LockInfo | null {
  try {
    const parsed = JSON.parse(readFileSync(lockPath, 'utf8')) as Partial<LockInfo>;
    if (typeof parsed.pid === 'number' && typeof parsed.host === 'string') {
      return { pid: parsed.pid, host: parsed.host, startedAt: parsed.startedAt ?? '' };
    }
  } catch {
    // Missing or unreadable: handled by the caller.
  }
  return null;
}

function isTakeoverable(
  holder: LockInfo | null,
  host: string,
  alive: (pid: number) => boolean
): boolean {
  return holder !== null && holder.host === host && !alive(holder.pid);
}

function lockRefusal(lockPath: string, holder: LockInfo | null): ImageLockError {
  return new ImageLockError(
    holder
      ? `another run holds ${lockPath} (pid ${holder.pid} on ${holder.host})`
      : `${lockPath} exists and is unreadable`,
    holder
  );
}

/** Creates the lock file exclusively; false when it already exists. */
function tryCreateLock(lockPath: string, info: LockInfo): boolean {
  try {
    const fd = openSync(lockPath, 'wx', 0o600);
    try {
      writeSync(fd, JSON.stringify(info));
      fsyncSync(fd);
    } finally {
      closeSync(fd);
    }
    return true;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'EEXIST') return false;
    throw error;
  }
}

/**
 * Takes `<stem>.lock` with O_EXCL. A lock from this host whose pid is dead is taken over;
 * a live holder, or one from another host, refuses the run.
 */
export function acquireLocalLock(lockPath: string, deps: LockDeps = {}): LockInfo {
  const info: LockInfo = {
    pid: deps.pid ?? process.pid,
    host: deps.host ?? hostname(),
    startedAt: deps.now ?? new Date().toISOString(),
  };
  const alive = deps.isPidAlive ?? defaultIsPidAlive;
  for (let attempt = 0; attempt < 2; attempt++) {
    if (tryCreateLock(lockPath, info)) return info;
    const holder = readLock(lockPath);
    if (!isTakeoverable(holder, info.host, alive)) throw lockRefusal(lockPath, holder);
    unlinkSync(lockPath);
  }
  throw new ImageLockError(`could not take ${lockPath}`, readLock(lockPath));
}

/** Removes the lock when this process owns it. */
export function releaseLocalLock(
  lockPath: string,
  deps: Pick<LockDeps, 'pid' | 'host'> = {}
): void {
  const holder = readLock(lockPath);
  if (!holder) return;
  if (holder.pid !== (deps.pid ?? process.pid) || holder.host !== (deps.host ?? hostname())) return;
  try {
    unlinkSync(lockPath);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
  }
}

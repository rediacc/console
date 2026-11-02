/**
 * The transfer loops behind `rdc backup download` and `rdc backup upload`
 * (agent/plans/PLAN-backup-local-image.md Design 3, 4 and 8).
 *
 * Every side effect (the machine session, rsync, hashing, the config) comes in through `deps`, so
 * the order of events is testable against fakes: the state file says `incomplete` before rsync
 * writes a byte, says `complete` only after the verification, and an upload registers the repo only
 * after the machine has finalized the image.
 */

import { accessSync, chmodSync, constants, existsSync, mkdirSync, statSync } from 'node:fs';
import { basename } from 'node:path';
import { t } from '../../i18n/index.js';
import { buildImageRsyncArgs, RETRYABLE_RSYNC_EXITS } from '../../remote/sync/image-rsync.js';
import { ValidationError } from '../../utils/errors.js';
import { checkSpace, probeSparse } from './preflight.js';
import { type ExportSession, remoteRsyncPath } from './session.js';
import {
  acquireLocalLock,
  beginRun,
  completeRun,
  failRun,
  type ImageState,
  type LocalImagePaths,
  localImagePaths,
  readImageState,
  releaseLocalLock,
  type VerifyMode,
  writeImageState,
} from './state.js';
import {
  backoff,
  DEFAULT_RETRIES,
  EXIT_INTERRUPTED,
  errorText,
  Interrupted,
  localAllocated,
  onceQuit,
  type RsyncOutcome,
  type RsyncRequest,
  remoteSpec,
  rsyncFailure,
  sshCommandOf,
} from './transfer-common.js';

export { DEFAULT_RETRIES } from './transfer-common.js';
export {
  type ImportTarget,
  type RegisterEntry,
  runUpload,
  type SourceRepo,
  type UploadDeps,
} from './upload.js';

export interface ImageTarget {
  repo: string;
  tag: string;
  machine: string;
  guid: string;
  grandGuid: string | null;
  datastore: string;
}

export interface DownloadDeps {
  assertRsyncCapable(): Promise<void>;
  resolveTargets(
    refs: string[],
    opts: { all?: string; includeForks?: boolean }
  ): Promise<ImageTarget[]>;
  openSession(target: ImageTarget): Promise<ExportSession>;
  runRsync(req: RsyncRequest): Promise<RsyncOutcome>;
  hashFile(path: string): Promise<string>;
  sleep(ms: number): Promise<void>;
  now(): Date;
  /** stdout: the summary, or the one JSON document. */
  write(text: string): void;
  /** stderr: progress and notes. Defaults to nothing. */
  progress?(text: string): void;
  signal?: AbortSignal;
}

export interface DownloadOptions {
  to: string;
  refs: string[];
  config: string;
  all?: string;
  includeForks?: boolean;
  bwlimitKiBps?: number;
  checkpoint?: boolean;
  retries?: number;
  skipVerify?: boolean;
  skipSpaceCheck?: boolean;
  output?: 'human' | 'json';
}

export interface DownloadResult {
  repo: string;
  tag: string;
  machine: string;
  guid: string;
  image: string;
  stateFile: string;
  status: 'complete' | 'incomplete' | 'failed';
  resumed: boolean;
  snapshotTakenAt: string | null;
  apparentBytes: number;
  allocatedBytes: number;
  literalBytes: number;
  matchedBytes: number;
  sha256: string | null;
  verify: VerifyMode | null;
  durationMs: number;
  error?: string;
}

/** `--to` must exist and be writable; it is never created (an unplugged drive's mount point would fill the root fs). */
function assertTargetDir(dir: string): void {
  let isDir = false;
  try {
    isDir = statSync(dir).isDirectory();
    if (isDir) accessSync(dir, constants.W_OK);
  } catch {
    throw new ValidationError(t('errors.backupImage.targetDirMissing', { dir }));
  }
  if (!isDir) throw new ValidationError(t('errors.backupImage.targetDirMissing', { dir }));
}

function ensureMachineDir(path: string): void {
  if (!existsSync(path)) mkdirSync(path, { mode: 0o700 });
  chmodSync(path, 0o700);
}

interface RepoRunContext {
  o: DownloadOptions;
  d: DownloadDeps;
  target: ImageTarget;
}

async function preflightSpace(
  ctx: RepoRunContext,
  session: ExportSession,
  image: string,
  dir: string
) {
  const localExists = existsSync(image);
  const check = await checkSpace({
    dir,
    apparent: session.ready.apparentBytes,
    allocated: session.ready.allocatedBytes,
    localExists,
    localAllocated: localExists ? localAllocated(image) : undefined,
    sparse: probeSparse(dir),
  });
  if (check.ok) return;
  const params = {
    need: String(check.need),
    free: String(check.free),
    apparent: String(session.ready.apparentBytes),
    allocated: String(session.ready.allocatedBytes),
  };
  const message =
    check.reason === 'fat32-file-limit'
      ? t('errors.backupImage.fat32Limit', params)
      : t('errors.backupImage.insufficientSpace', params);
  if (ctx.o.skipSpaceCheck) {
    ctx.d.progress?.(`${message}\n`);
    return;
  }
  throw new Error(message);
}

function readyRun(session: ExportSession) {
  return {
    snapshotTakenAt: session.ready.takenAt,
    snapshotName: basename(session.ready.snapshot),
    apparentBytes: session.ready.apparentBytes,
    allocatedBytes: session.ready.allocatedBytes,
  };
}

type RepoResult = DownloadResult & { interrupted?: boolean };

function emptyResult(target: ImageTarget, image: string, stateFile: string): RepoResult {
  return {
    repo: target.repo,
    tag: target.tag,
    machine: target.machine,
    guid: target.guid,
    image,
    stateFile,
    status: 'failed',
    resumed: false,
    snapshotTakenAt: null,
    apparentBytes: 0,
    allocatedBytes: 0,
    literalBytes: 0,
    matchedBytes: 0,
    sha256: null,
    verify: null,
    durationMs: 0,
  };
}

/** One repo: session, preflight, `incomplete`, rsync with retries, verification, `complete`. */
class DownloadRun {
  private readonly paths: LocalImagePaths;
  private readonly started: Date;
  readonly result: RepoResult;
  private state: ImageState | null = null;
  private session: ExportSession | null = null;

  constructor(private readonly ctx: RepoRunContext) {
    const { o, d, target } = ctx;
    this.started = d.now();
    this.paths = localImagePaths(o.to, target.machine, target.repo, target.tag);
    this.result = emptyResult(target, this.paths.image, this.paths.state);
  }

  private checkAbort(): void {
    if (this.ctx.d.signal?.aborted) throw new Interrupted();
  }

  private persist(): void {
    if (this.state) writeImageState(this.paths.state, this.state);
  }

  private adopt(session: ExportSession): ExportSession {
    this.session = onceQuit(session);
    this.result.snapshotTakenAt = session.ready.takenAt;
    this.result.apparentBytes = session.ready.apparentBytes;
    return this.session;
  }

  private finish(): RepoResult {
    this.result.durationMs = this.ctx.d.now().getTime() - this.started.getTime();
    this.result.allocatedBytes = localAllocated(this.paths.image);
    return this.result;
  }

  async run(): Promise<RepoResult> {
    ensureMachineDir(this.paths.machineDir);
    try {
      acquireLocalLock(this.paths.lock);
    } catch (error) {
      this.result.error = errorText(error);
      return this.finish();
    }
    try {
      await this.begin();
      await this.transfer();
      await this.verifyAndComplete();
    } catch (error) {
      this.fail(error);
    } finally {
      await this.session?.quit();
      releaseLocalLock(this.paths.lock);
    }
    return this.finish();
  }

  private async begin(): Promise<void> {
    const { o, d, target } = this.ctx;
    const prev = readImageState(this.paths.state);
    this.result.resumed = prev?.status === 'incomplete';
    if (this.result.resumed) {
      d.progress?.(`${t('commands.backup.download.resuming', { repo: target.repo })}\n`);
    }
    this.checkAbort();
    const session = this.adopt(await d.openSession(target));
    // --skip-space-check turns the refusal into a warning; the check itself always runs.
    await preflightSpace(this.ctx, session, this.paths.image, this.paths.machineDir);
    this.state = beginRun(prev, {
      config: o.config,
      machine: target.machine,
      image: basename(this.paths.image),
      repo: { name: target.repo, tag: target.tag, guid: target.guid, grandGuid: target.grandGuid },
      ...readyRun(session),
      checkpoint: o.checkpoint ?? false,
      now: this.started.toISOString(),
    });
    this.persist();
  }

  private async rsyncOnce(session: ExportSession): Promise<RsyncOutcome> {
    const { o, d } = this.ctx;
    const args = buildImageRsyncArgs({
      direction: 'download',
      freshDest: !existsSync(this.paths.image),
      sshCommand: sshCommandOf(session.transport),
      bwlimitKiBps: o.bwlimitKiBps,
      remoteRsyncPath: session.transport
        ? remoteRsyncPath(session.ready.rsyncPath, session.ready.lowPriority)
        : undefined,
    });
    const outcome = await d.runRsync({
      args,
      source: remoteSpec(session.transport, session.ready.snapshot),
      dest: this.paths.image,
    });
    this.result.literalBytes += outcome.literalBytes;
    this.result.matchedBytes += outcome.matchedBytes;
    return outcome;
  }

  /** Retries reuse the live session; a dead one lost its snapshot, and a fresh one converges the same way (Design 3). */
  private async transfer(): Promise<void> {
    const { o, d, target } = this.ctx;
    const retries = o.retries ?? DEFAULT_RETRIES;
    for (let attempt = 0; ; attempt++) {
      const session = this.session as ExportSession;
      const outcome = await this.rsyncOnce(session);
      this.checkAbort();
      if (outcome.exitCode === 0) return;
      const failure = rsyncFailure(outcome);
      if (!RETRYABLE_RSYNC_EXITS.has(outcome.exitCode) || attempt >= retries) {
        throw new Error(failure);
      }
      d.progress?.(
        `${t('commands.backup.download.retrying', { repo: target.repo, error: failure })}\n`
      );
      await d.sleep(backoff(attempt));
      this.checkAbort();
      if (await session.ping()) continue;
      await session.quit();
      const fresh = this.adopt(await d.openSession(target));
      const state = this.state as ImageState;
      this.state = { ...state, run: { ...state.run, ...readyRun(fresh) } };
      this.persist();
    }
  }

  private async verifyAndComplete(): Promise<void> {
    const { o, d } = this.ctx;
    const session = this.session as ExportSession;
    let sha256 = '';
    let verify: VerifyMode = 'rsync';
    if (!o.skipVerify) {
      const [remote, local] = await Promise.all([session.sha256(), d.hashFile(this.paths.image)]);
      this.checkAbort();
      if (remote !== local) {
        throw new Error(t('errors.backupImage.sha256Mismatch', { remote, local }));
      }
      sha256 = local;
      verify = 'sha256+rsync';
    }
    this.state = completeRun(this.state as ImageState, {
      sha256,
      verify,
      literalBytes: this.result.literalBytes,
      matchedBytes: this.result.matchedBytes,
      durationMs: d.now().getTime() - this.started.getTime(),
      now: d.now().toISOString(),
    });
    this.persist();
    this.result.status = 'complete';
    this.result.sha256 = sha256 || null;
    this.result.verify = verify;
  }

  private fail(error: unknown): void {
    const interrupted = error instanceof Interrupted;
    this.result.interrupted = interrupted;
    this.result.error = interrupted ? t('commands.backup.download.interrupted') : errorText(error);
    if (!this.state) return;
    this.state = failRun(this.state, {
      error: interrupted ? 'interrupted' : errorText(error),
      outcome: interrupted ? 'interrupted' : 'failed',
      literalBytes: this.result.literalBytes,
      now: this.ctx.d.now().toISOString(),
    });
    this.persist();
    this.result.status = 'incomplete';
  }
}

function downloadOne(ctx: RepoRunContext): Promise<RepoResult> {
  return new DownloadRun(ctx).run();
}

function formatBytes(n: number): string {
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB'];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${i === 0 ? v : v.toFixed(1)} ${units[i]}`;
}

function humanRow(r: DownloadResult): string {
  const lines = [
    t('commands.backup.download.summaryRow', {
      repo: `${r.repo}:${r.tag}`,
      machine: r.machine,
      status: r.status,
      image: r.image,
    }),
    t('commands.backup.download.summarySizes', {
      apparent: formatBytes(r.apparentBytes),
      allocated: formatBytes(r.allocatedBytes),
      literal: formatBytes(r.literalBytes),
      matched: formatBytes(r.matchedBytes),
      sha256: r.sha256 ? r.sha256.slice(0, 12) : '-',
    }),
  ];
  if (r.status === 'incomplete') lines.push(t('commands.backup.download.notUsable'));
  if (r.error) lines.push(t('commands.backup.download.summaryError', { error: r.error }));
  return `${lines.join('\n')}\n`;
}

/**
 * `rdc backup download`. Throws for a refusal that stops every repo (a missing `--to`, no capable
 * rsync); a per-repo failure is a result. Repos run one at a time; exit 0 when all complete,
 * 1 when any failed, 130 on Ctrl-C after the session is closed and the state written.
 */
export async function runDownload(
  o: DownloadOptions,
  d: DownloadDeps
): Promise<{ exitCode: number; results: DownloadResult[] }> {
  assertTargetDir(o.to);
  await d.assertRsyncCapable();
  const targets = await d.resolveTargets(o.refs, { all: o.all, includeForks: o.includeForks });
  if (targets.length === 0) throw new ValidationError(t('errors.backupImage.noTargets'));

  const results: DownloadResult[] = [];
  const exitCode = await downloadAll(o, d, targets, results);
  if (o.output === 'json') d.write(`${JSON.stringify({ results }, null, 2)}\n`);
  return { exitCode, results };
}

async function downloadAll(
  o: DownloadOptions,
  d: DownloadDeps,
  targets: ImageTarget[],
  results: DownloadResult[]
): Promise<number> {
  let exitCode = 0;
  for (const target of targets) {
    if (d.signal?.aborted) return EXIT_INTERRUPTED;
    const repo = `${target.repo}:${target.tag}`;
    d.progress?.(`${t('commands.backup.download.starting', { repo, machine: target.machine })}\n`);
    const { interrupted, ...r } = await downloadOne({ o, d, target });
    results.push(r);
    if (o.output !== 'json') d.write(humanRow(r));
    if (interrupted) return EXIT_INTERRUPTED;
    if (r.status !== 'complete') exitCode = 1;
  }
  return exitCode;
}

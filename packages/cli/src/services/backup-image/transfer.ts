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
import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { t } from '../../i18n/index.js';
import { buildImageRsyncArgs, RETRYABLE_RSYNC_EXITS } from '../../remote/sync/image-rsync.js';
import { ValidationError } from '../../utils/errors.js';
import { namedDatastoreMount } from '../cluster/cluster-target.js';
import { allocatedBytesOf, checkSpace, probeSparse } from './preflight.js';
import {
  type ExportSession,
  type ImportSession,
  type RsyncTransport,
  remoteRsyncPath,
} from './session.js';
import {
  acquireLocalLock,
  beginRun,
  completeRun,
  failRun,
  type ImageState,
  type ImageUploadRecord,
  type LocalImagePaths,
  localImagePaths,
  readImageState,
  recordUpload,
  releaseLocalLock,
  type VerifyMode,
  writeImageState,
} from './state.js';

/** Backoff before the first, second and third in-run retry. */
export const RETRY_BACKOFF_MS = [10_000, 30_000, 60_000] as const;
export const DEFAULT_RETRIES = 3;
export const EXIT_INTERRUPTED = 130;

export interface RsyncRequest {
  args: string[];
  source: string;
  dest: string;
}

export interface RsyncOutcome {
  exitCode: number;
  literalBytes: number;
  matchedBytes: number;
  stderr?: string;
}

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

/** Thrown inside a repo run to stop it as interrupted (Ctrl-C). */
class Interrupted extends Error {}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
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

function localAllocated(path: string): number {
  try {
    return allocatedBytesOf(statSync(path));
  } catch {
    return 0;
  }
}

function remoteSpec(transport: RsyncTransport | undefined, path: string): string {
  return transport ? `${transport.userHost}:${path}` : path;
}

function sshCommandOf(transport: RsyncTransport | undefined): string {
  return transport?.sshCommand ?? 'ssh';
}

function backoff(attempt: number): number {
  return RETRY_BACKOFF_MS[Math.min(attempt, RETRY_BACKOFF_MS.length - 1)];
}

/** Wraps a session so its quit runs at most once whatever path ends the run. */
function onceQuit<S extends { quit(): Promise<void> }>(s: S): S {
  let q: Promise<void> | null = null;
  const quit = () => {
    q ??= s.quit().catch(() => undefined);
    return q;
  };
  return Object.assign(Object.create(Object.getPrototypeOf(s) as object) as S, s, { quit });
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

function rsyncFailure(outcome: RsyncOutcome): string {
  const stderr = outcome.stderr?.trim();
  return t('errors.backupImage.rsyncExit', {
    code: String(outcome.exitCode),
    detail: stderr ? `: ${stderr}` : '',
  });
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

// ── upload ──────────────────────────────────────────────────────────────────

export interface ImportTarget {
  machine: string;
  guid: string;
  datastore: string;
  seedGuid?: string;
  allocatedBytes: number;
}

export interface SourceRepo {
  name: string;
  tag: string;
  credential?: string;
  grandGuid: string | null;
  guid: string;
}

export interface RegisterEntry {
  name: string;
  /** The source image's tag; the repo registers as `<name>:<tag>`. */
  tag: string;
  guid: string;
  machine: string;
  lineage: string | null;
  credential?: string;
  datastore?: string;
}

export interface UploadDeps {
  assertRsyncCapable(): Promise<void>;
  findRepoByGuid(guid: string): SourceRepo | undefined;
  findRepoByName(name: string): SourceRepo | undefined;
  mintGuid(): string;
  openImportSession(target: ImportTarget): Promise<ImportSession>;
  runRsync(req: RsyncRequest): Promise<RsyncOutcome>;
  hashFile(path: string): Promise<string>;
  /** Registers the finalized image in the config. Called only after `finalized`. */
  register(entry: RegisterEntry): Promise<void>;
  sleep(ms: number): Promise<void>;
  now(): Date;
  write(text: string): void;
  progress?(text: string): void;
  /** Tripped by Ctrl-C: the rsync stops, the import session is quit and the pending upload stays resumable. */
  signal?: AbortSignal;
  /** Absolute datastore path on the machine; defaults to the named mount or the default datastore. */
  datastorePath?(machine: string, datastore?: string): Promise<string>;
  /** The agent create-gate for the target name. */
  assertCreate?(name: string, machine: string): Promise<void>;
  /** `--up`: start the registered repo. */
  deploy?(name: string, machine: string): Promise<void>;
}

export interface UploadOptions {
  image: string;
  to: string;
  as?: string;
  datastore?: string;
  fromRepo?: string;
  skipVerify?: boolean;
  bwlimitKiBps?: number;
  retries?: number;
  up?: boolean;
  config: string;
  output?: 'human' | 'json';
}

function siblingPaths(image: string): { state: string; lock: string } {
  const stem = image.endsWith('.img') ? image.slice(0, -'.img'.length) : image;
  return { state: `${stem}.state.json`, lock: `${stem}.lock` };
}

function lookupSource(o: UploadOptions, d: UploadDeps, state: ImageState | null) {
  if (o.fromRepo) return d.findRepoByName(o.fromRepo);
  return state ? d.findRepoByGuid(state.repo.guid) : undefined;
}

function resolveSource(o: UploadOptions, d: UploadDeps, state: ImageState | null): SourceRepo {
  const source = lookupSource(o, d, state);
  if (source) return source;
  throw new ValidationError(
    o.fromRepo
      ? t('errors.backupImage.fromRepoUnknown', { name: o.fromRepo })
      : t('errors.backupImage.sourceRepoUnknown', { guid: state?.repo.guid ?? '-' })
  );
}

/** A state file for an image whose own one is lost (`--from-repo`), so the pending upload can be recorded. */
function synthesizeState(
  o: UploadOptions,
  d: UploadDeps,
  source: SourceRepo,
  sha256: string
): ImageState {
  const now = d.now().toISOString();
  const begun = beginRun(null, {
    config: o.config,
    machine: '',
    image: basename(o.image),
    repo: { name: source.name, tag: source.tag, guid: source.guid, grandGuid: source.grandGuid },
    snapshotTakenAt: now,
    snapshotName: '',
    apparentBytes: statSync(o.image).size,
    allocatedBytes: localAllocated(o.image),
    checkpoint: false,
    now,
  });
  return completeRun(begun, {
    sha256,
    verify: 'rsync',
    literalBytes: 0,
    matchedBytes: 0,
    durationMs: 0,
    now,
  });
}

interface UploadPlan {
  statePath: string;
  lock: string;
  state: ImageState | null;
  source: SourceRepo;
  name: string;
  pending: ImageUploadRecord | null;
}

/** Every refusal that needs no machine: the image, its state, the source identity, the name. */
/** The image's state: `complete`, or absent only when `--from-repo` names the identity. */
function readUsableState(o: UploadOptions, statePath: string): ImageState | null {
  if (!existsSync(o.image) || !statSync(o.image).isFile()) {
    throw new ValidationError(t('errors.backupImage.imageMissing', { image: o.image }));
  }
  const state = readImageState(statePath);
  if (!state && !o.fromRepo) {
    throw new ValidationError(t('errors.backupImage.stateMissing', { state: statePath }));
  }
  if (state && state.status !== 'complete') {
    throw new ValidationError(t('errors.backupImage.stateIncomplete', { image: o.image }));
  }
  return state;
}

function planUpload(o: UploadOptions, d: UploadDeps): UploadPlan {
  const { state: statePath, lock } = siblingPaths(o.image);
  const state = readUsableState(o, statePath);
  const source = resolveSource(o, d, state);
  const name = o.as ?? state?.repo.name ?? source.name;
  if (d.findRepoByName(name)) {
    throw new ValidationError(t('errors.backupImage.nameTaken', { name }));
  }
  const upload = state?.upload;
  const pending =
    upload?.status === 'staging' && upload.machine === o.to && upload.name === name ? upload : null;
  return { statePath, lock, state, source, name, pending };
}

/** The local image must still hash to the digest its download recorded. */
async function hashAndCheck(o: UploadOptions, d: UploadDeps, state: ImageState | null) {
  d.progress?.(`${t('commands.backup.upload.hashing', { image: o.image })}\n`);
  const localSha = await d.hashFile(o.image);
  if (state && !o.skipVerify && state.complete?.sha256 !== localSha) {
    throw new ValidationError(
      t('errors.backupImage.localSha256Mismatch', {
        image: o.image,
        expected: state.complete?.sha256 ?? '-',
        actual: localSha,
      })
    );
  }
  return localSha;
}

function uploadDatastore(o: UploadOptions, d: UploadDeps): Promise<string> {
  if (d.datastorePath) return d.datastorePath(o.to, o.datastore);
  return Promise.resolve(
    o.datastore ? namedDatastoreMount(o.datastore) : NETWORK_DEFAULTS.DATASTORE_PATH
  );
}

function uploadRsyncOnce(
  o: UploadOptions,
  d: UploadDeps,
  session: ImportSession
): Promise<RsyncOutcome> {
  // --sparse only into a fresh staging: the receiver is the machine's rsync, and 3.2.7 leaves old bytes under --sparse --inplace.
  const args = buildImageRsyncArgs({
    direction: 'upload',
    freshDest: session.ready.fresh,
    sshCommand: sshCommandOf(session.transport),
    bwlimitKiBps: o.bwlimitKiBps,
    remoteRsyncPath: session.transport ? remoteRsyncPath(session.ready.rsyncPath) : undefined,
  });
  return d.runRsync({
    args,
    source: o.image,
    dest: remoteSpec(session.transport, session.ready.staging),
  });
}

/** Stops an upload step as interrupted once Ctrl-C tripped the signal. */
function throwIfAborted(d: { signal?: AbortSignal }): void {
  if (d.signal?.aborted) throw new Interrupted();
}

function isAlive(session: ImportSession): Promise<boolean> {
  return session.ping ? session.ping() : Promise.resolve(false);
}

async function uploadRsyncLoop(
  o: UploadOptions,
  d: UploadDeps,
  target: ImportTarget,
  first: ImportSession
): Promise<ImportSession> {
  let session = first;
  const retries = o.retries ?? DEFAULT_RETRIES;
  for (let attempt = 0; ; attempt++) {
    const outcome = await uploadRsyncOnce(o, d, session);
    throwIfAborted(d);
    if (outcome.exitCode === 0) return session;
    const failure = rsyncFailure(outcome);
    if (!RETRYABLE_RSYNC_EXITS.has(outcome.exitCode) || attempt >= retries) {
      await session.quit();
      throw new Error(failure);
    }
    d.progress?.(`${t('commands.backup.upload.retrying', { error: failure })}\n`);
    await d.sleep(backoff(attempt));
    throwIfAborted(d);
    if (await isAlive(session)) continue;
    // The staging survives the session; a new one resumes into it.
    await session.quit();
    session = onceQuit(await d.openImportSession(target));
  }
}

/** Opens the import session, sends the bytes and has the machine finalize them. */
async function transferAndFinalize(
  o: UploadOptions,
  d: UploadDeps,
  target: ImportTarget,
  localSha: string
): Promise<{ path: string }> {
  let session: ImportSession = onceQuit(await d.openImportSession(target));
  try {
    session = await uploadRsyncLoop(o, d, target, session);
    return await session.finalize(localSha);
  } finally {
    await session.quit();
  }
}

/** Records the pending upload (resumed or freshly minted) in the state file before any byte moves. */
async function stageUpload(o: UploadOptions, d: UploadDeps, plan: UploadPlan, localSha: string) {
  const { pending } = plan;
  const upload: ImageUploadRecord = {
    machine: o.to,
    name: plan.name,
    guid: pending?.guid ?? d.mintGuid(),
    datastore: pending?.datastore ?? (await uploadDatastore(o, d)),
    startedAt: pending?.startedAt ?? d.now().toISOString(),
    status: 'staging',
  };
  const state = recordUpload(plan.state ?? synthesizeState(o, d, plan.source, localSha), upload);
  writeImageState(plan.statePath, state);
  if (pending) {
    d.progress?.(`${t('commands.backup.upload.resuming', { guid: upload.guid, machine: o.to })}\n`);
  }
  return { upload, state };
}

/** Registration happens only after the machine finalized the image; a failure names the orphan. */
async function registerUpload(
  o: UploadOptions,
  d: UploadDeps,
  plan: UploadPlan,
  guid: string
): Promise<void> {
  const { source } = plan;
  try {
    await d.register({
      name: plan.name,
      tag: plan.state?.repo.tag ?? source.tag,
      guid,
      machine: o.to,
      lineage: source.grandGuid ?? source.guid,
      credential: source.credential,
      datastore: o.datastore,
    });
  } catch (error) {
    throw new Error(
      t('errors.backupImage.registerFailed', { guid, machine: o.to, error: errorText(error) })
    );
  }
}

/**
 * `rdc backup upload`. Refuses an `incomplete` copy, a copy whose sha256 no longer matches its
 * state, a source identity it cannot find (naming `--from-repo`) and a taken name (naming `--as`).
 * Records the pending GUID before any byte moves, so a rerun with the same `--to`/`--as` resumes it.
 */
export async function runUpload(o: UploadOptions, d: UploadDeps): Promise<{ exitCode: number }> {
  const plan = planUpload(o, d);
  const { name, statePath } = plan;
  await d.assertCreate?.(name, o.to);
  await d.assertRsyncCapable();

  acquireLocalLock(plan.lock);
  try {
    const localSha = await hashAndCheck(o, d, plan.state);
    const staged = await stageUpload(o, d, plan, localSha);
    const { upload } = staged;
    const guid = upload.guid;
    let finalized: { path: string };
    try {
      finalized = await transferAndFinalize(
        o,
        d,
        {
          machine: o.to,
          guid,
          datastore: upload.datastore,
          seedGuid: staged.state.repo.guid || undefined,
          allocatedBytes: staged.state.run.allocatedBytes || localAllocated(o.image),
        },
        localSha
      );
    } catch (error) {
      if (!(error instanceof Interrupted)) throw error;
      // The staging record stays 'staging' (the remote bytes survive the quit), so a rerun resumes it.
      writeImageState(statePath, recordUpload(staged.state, { ...upload, status: 'staging' }));
      d.progress?.(`${t('commands.backup.download.interrupted')}\n`);
      return { exitCode: EXIT_INTERRUPTED };
    }
    await registerUpload(o, d, plan, guid);
    writeImageState(statePath, recordUpload(staged.state, { ...upload, status: 'finalized' }));

    const doc = { name, guid, machine: o.to, path: finalized.path, sha256: localSha };
    d.write(
      o.output === 'json'
        ? `${JSON.stringify(doc, null, 2)}\n`
        : `${t('commands.backup.upload.done', { name, machine: o.to, guid })}\n`
    );
    if (o.up) await d.deploy?.(name, o.to);
    return { exitCode: 0 };
  } finally {
    releaseLocalLock(plan.lock);
  }
}

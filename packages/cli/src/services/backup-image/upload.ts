/**
 * The upload loop behind `rdc backup upload`: state checks, staging, rsync with retries, finalize
 * and registration (agent/plans/PLAN-backup-local-image.md Design 4 and 8).
 */

import { existsSync, statSync } from 'node:fs';
import { basename } from 'node:path';
import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { t } from '../../i18n/index.js';
import { buildImageRsyncArgs, RETRYABLE_RSYNC_EXITS } from '../../remote/sync/image-rsync.js';
import { ValidationError } from '../../utils/errors.js';
import { namedDatastoreMount } from '../cluster/cluster-target.js';
import { type ImportSession, remoteRsyncPath } from './session.js';
import {
  acquireLocalLock,
  beginRun,
  completeRun,
  type ImageState,
  type ImageUploadRecord,
  readImageState,
  recordUpload,
  releaseLocalLock,
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

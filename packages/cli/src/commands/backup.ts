import { randomUUID } from 'node:crypto';
import type { Placement } from '@rediacc/shared/config-schema';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { parseRef } from '../services/addressing/ref-parser.js';
import { recordBackupRun } from '../services/backup/backup-runs-state.js';
import { warnIfConfigStorageUnenrolled } from '../services/backup/dr-nudge.js';
import { reconcileBackupSchedules } from '../services/backup/repo-change-hook.js';
import { namedDatastoreMount } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import { targetFloor } from '../services/config/network-id-discovery.js';
import { outputService } from '../services/core/output.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { bindStepHandler } from '../services/jobs/steps.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { assertAgentRepoCreate } from '../utils/agent-guard.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { assertResourceName, compositeKey } from '../utils/config-schema.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { resolveRemoteName } from '../utils/remote-resolve.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { assertMachineExists } from './_validate.js';
import { registerBackupImageCommands } from './backup-image.js';
import { registerBackupOpsCommands } from './backup-ops.js';
import { assertRestorePathFlags, isPathRoute, runRestorePath } from './backup-restore-path.js';
import { type BackupManifestsResponse, registerBackupStorageCommands } from './backup-storage.js';
import {
  parseRestoreStats,
  parseVerifyVerdict,
  type RestoreStats,
} from './backup-storage-parser.js';
import { registerBackupStrategyCommands } from './backup-strategy.js';
import { fetchBackupList, renderBackupList, type TaggedBackupEntry } from './repo-backup-list.js';

/** `backup list [artifact-ref]`, list backup artifacts on a machine. */
function registerBackupList(backup: Command): void {
  backup
    .command('list')
    .argument('[artifact-ref]', t('options.artifactRef'))
    .description(t('commands.backup.list.description'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--path <subdir>', t('commands.backup.list.optionPath'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        artifactRef: string | undefined,
        options: {
          machine?: string;
          path?: string;
          debug?: boolean;
        }
      ) => {
        try {
          if (!options.machine) {
            throw new ValidationError(t('commands.backup.list.placementRequired'));
          }
          const machine = options.machine;
          const ref = artifactRef ? parseRef(artifactRef) : undefined;

          // sourceType 'local' means the executor machine reads its OWN
          // datastore. It used to be 'machine' with from = the same machine,
          // which asked that machine to SSH to itself to read its own disk.
          const baseParams: Record<string, unknown> = { sourceType: 'local', from: machine };
          const explicitPath =
            typeof options.path === 'string' && options.path.trim().length > 0
              ? options.path.trim()
              : undefined;
          if (explicitPath) baseParams.path = explicitPath;

          outputService.info(t('commands.backup.list.listing'));
          // ONE call, and no hot/cold probe. renet enumerates the datastore now, which is what makes an artifact left by `repo push` at the root
          // visible; the old pair of probes only ever looked where SCHEDULED
          // runs write, so a real copy reported an empty table. The per-entry subdirectory comes back on the entry itself.
          const entries = await fetchBackupList(baseParams, { machine, debug: options.debug });
          const tagged: TaggedBackupEntry[] = entries.map((e) => ({ ...e, mode: e.path ?? '' }));

          const filtered = ref
            ? tagged.filter((e) => e.name === ref.name || e.name.startsWith(ref.name))
            : tagged;
          await renderBackupList(filtered);
        } catch (error) {
          handleError(error);
        }
      }
    );
}

interface RestoreOptions {
  as?: string;
  machine?: string;
  datastore?: string;
  at?: string;
  path?: string;
  to?: string;
  anyStream?: boolean;
  /** Commander stores `--no-seed` as `seed: false` (true when the flag is absent). */
  seed?: boolean;
  up?: boolean;
  healthWindow?: string;
  healthTimeout?: string;
  yes?: boolean;
  debug?: boolean;
}

/**
 * The placement a restore asks for, read from the flags alone for the agent create-gate (its ops VM exemption): no state lookup and no validation.
 * Both flags, or neither, is no placement, so the gate keeps its refusal and resolveRestoreMachine reports the flag error to a human.
 */
function restorePlacementOf(options: RestoreOptions): Placement | undefined {
  if (options.machine && options.datastore) return undefined;
  if (options.machine) return { machine: options.machine };
  if (options.datastore) return { datastore: options.datastore };
  return undefined;
}

/** Resolve which machine a restored repo lands on. */
async function resolveRestoreMachine(options: RestoreOptions): Promise<string> {
  if (options.machine && options.datastore) {
    throw new ValidationError(t('commands.backup.restore.placementExclusive'));
  }
  if (options.machine) {
    await assertMachineExists(options.machine);
    return options.machine;
  }
  if (options.datastore) {
    // A named datastore's current mounter is the routing hint in state; restore
    // lands where the datastore is attached (verified at up() time downstream).
    const config = await configService.getCurrent();
    const machine = config?.state?.datastores?.[options.datastore]?.attachedTo;
    if (!machine) {
      throw new ValidationError(
        t('commands.backup.restore.datastoreUnattached', { datastore: options.datastore })
      );
    }
    return machine;
  }
  throw new ValidationError(t('commands.backup.restore.placementRequired'));
}

/** `backup restore <artifact-ref>`, materialize a backup artifact into a live repo. */
function registerBackupRestore(backup: Command): void {
  backup
    .command('restore')
    .argument('<artifact-ref>', t('options.artifactRef'))
    .description(t('commands.backup.restore.description'))
    .option('--as <name>', t('commands.backup.restore.optionAs'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--datastore <name>', t('commands.backup.restore.optionDatastore'))
    .option('--at <time>', t('commands.backup.restore.optionAt'))
    .option('--any-stream', t('commands.backup.restore.optionAnyStream'))
    .option('--no-seed', t('commands.backup.restore.optionNoSeed'))
    .option('--path <file-or-dir>', t('commands.backup.restore.optionPath'))
    .option('--to <dir>', t('commands.backup.restore.optionTo'))
    .option('--up', t('commands.backup.restore.optionUp'))
    .option('--health-window <seconds>', t('options.healthWindow'))
    .option('--health-timeout <seconds>', t('options.healthTimeout'))
    .option('-y, --yes', t('options.yes'))
    .option('--debug', t('options.debug'))
    .action(async (artifactRef: string, options: RestoreOptions) => {
      try {
        assertRestorePathFlags(options);
        // One path out of a snapshot: no target record, network id or credential copy, so it branches before resolveRestoreTarget.
        if (isPathRoute(options) && options.path !== undefined && options.at) {
          await restorePathRoute(artifactRef, { ...options, path: options.path, at: options.at });
          return;
        }
        const { ref, targetName, source } = await resolveRestoreTarget(artifactRef, options);

        const targetMachine = await resolveRestoreMachine(options);
        const resolved = await resolveRemoteName(ref.place);
        const from = resolved.type === 'cluster' ? ref.place : resolved.name;
        const sourceType = 'machine';

        // No `--at`: a repo with a chunk-store lineage has no artifact on a machine to pull (the pull dies on a missing repositories/<guid>), so the restore means "the newest snapshot", exactly `--at <now>`. A repo with no manifests keeps the pull of its `repo push` artifact.
        const restoreAt =
          options.at ??
          ((await lineageHasSnapshots(source.grandGuid ?? source.repositoryGuid))
            ? new Date().toISOString()
            : undefined);
        // Only a snapshot restore has seeds to skip; refuse before the target is registered rather than ignore the flag.
        if (options.seed === false && !restoreAt) {
          throw new ValidationError(t('commands.backup.restore.noSeedNeedsSnapshot'));
        }

        // #74: `--datastore` was accepted, used to LOOK UP the holder machine, and then dropped, the pull ran against the machine's default, so a restore the operator asked to land on a named datastore landed somewhere else. Record the placement as the birth record (the same field `repo create` writes) so every later verb derives the right mount, and declare it on the transfer
        // below.
        const placement = options.datastore
          ? { datastore: options.datastore }
          : { machine: targetMachine };
        const datastore = options.datastore ? namedDatastoreMount(options.datastore) : undefined;

        // Refuse a bad target name before allocateNetworkId persists anything.
        assertResourceName(targetName);
        const networkId = await configService.allocateNetworkId({
          floor: await targetFloor({ machine: targetMachine }),
        });
        const lineage = source.grandGuid ?? source.repositoryGuid;
        await configService.addRepository(compositeKey(targetName, 'latest'), {
          ...restoredIdentity(lineage),
          tag: 'latest',
          // The image bytes are the source's ciphertext, so the restored repo unlocks with the source's passphrase whatever GUID it lands under. Inherit, exactly as `repo fork` does; under a fresh GUID this is a NEW credential map entry (the map is keyed by GUID), not a second claim on the source's slot.
          credential: source.credential,
          networkId,
          placement,
        });

        // DR nudge: a restore into a config with no config-storage enrollment cannot recover the repo credential (the LUKS passphrase) on a fresh host, warn, never block (spec/02 decision 14).
        await warnIfConfigStorageUnenrolled();

        // `--at` selects a point in time, which only the CHUNK store can answer: it addresses a snapshot in a manifest chain, not an artifact on a machine or a storage remote. So the flag routes to `backup_restore` rather than `backup_pull`. It is a route, not a second user-facing command: growing `rdc backup restore-snapshot` beside this one would make the operator choose between
        // two verbs that mean the same thing.
        const ok = restoreAt
          ? await runChunkRestore({
              targetName,
              targetMachine,
              datastore,
              lineage,
              at: restoreAt,
              anyStream: options.anyStream ?? false,
              noSeed: options.seed === false,
              source: { repoName: ref.name, machine: from },
              debug: options.debug,
            })
          : await runRestorePull({
              targetName,
              targetMachine,
              datastore,
              sourceType,
              from,
              sourceGuid: source.repositoryGuid,
              debug: options.debug,
              place: ref.place,
            });
        if (!ok) return;

        // G4: the restore registered a new repository on the target machine, so its backup units re-render.
        await reconcileBackupSchedules(targetMachine);

        if (options.up) {
          await restoreDeploy(targetName, targetMachine, datastore, options);
        }
      } catch (error) {
        handleError(error);
      }
    });
}

/** `restore --at <t> --path <p>`: resolve the ref's repo and machine, then hand off to `runRestorePath`. */
async function restorePathRoute(
  artifactRef: string,
  options: RestoreOptions & { path: string; at: string }
): Promise<void> {
  const ref = parseRef(artifactRef);
  if (!ref.place) {
    throw new ValidationError(t('commands.backup.restore.placeRequired'));
  }
  const place = await resolveRemoteName(ref.place);
  // The source machine owns the backup stream the snapshot is chosen from. A cluster place names no machine, so `-m` supplies it; a machine place is the source itself. `-m` otherwise only moves where the restore RUNS, as it does for a whole-image restore.
  if (place.type === 'cluster' && !options.machine) {
    throw new ValidationError(t('commands.backup.restore.pathNeedsMachine', { place: ref.place }));
  }
  const sourceMachine = place.type === 'cluster' ? (options.machine as string) : place.name;
  const repoKey = ref.tag ? `${ref.name}:${ref.tag}` : ref.name;
  const machineName = options.machine ?? sourceMachine;
  await runRestorePath({
    repoKey,
    machineName,
    at: options.at,
    path: options.path,
    to: options.to,
    debug: options.debug,
    resolveSnapshot: async (lineage, at) =>
      resolveSnapshotAt(
        lineage,
        at,
        await streamScopeFor({
          at,
          anyStream: options.anyStream ?? false,
          source: { repoName: repoKey, machine: sourceMachine },
          debug: options.debug,
        })
      ),
  });
}

/**
 * The identity a restored record is registered under (box E1).
 *
 * Every restore, `--at` or not, mints a FRESH GUID. Reusing the source's made
 * the restored image's path `repositories/<source-guid>`, so a restore on the
 * source's own machine wrote over the live source image; renet refuses that
 * unless `--replace <guid>` names the target on purpose, which left every
 * same-machine `--as` restore refused. A fresh GUID is a fresh path, and the
 * lineage (the grand GUID the snapshot's object keys namespace on) is carried
 * as grandGuid, so the restored repo's own snapshots dedup in the same family.
 *
 * The pull route addresses the source image by its own GUID (`backup_pull`'s
 * `src` parameter), separately from the destination name.
 */
function restoredIdentity(lineage: string): { repositoryGuid: string; grandGuid?: string } {
  return { repositoryGuid: randomUUID(), grandGuid: lineage };
}

/**
 * Validate a restore's artifact ref and resolve the source repo record.
 *
 * The ORDER here is load-bearing and unchanged from when this lived inline:
 * command policy runs before the target-exists check, and the agent create-gate
 * runs after it, because `assertCommandPolicy` returns early for a repo that is
 * not in config yet and would otherwise let a restore register a brand-new grand
 * repo without clearing the same gate `repo create` has to clear.
 *
 * `place` is asserted non-optional in the return type so the caller keeps the
 * narrowing the inline version got from the guard below.
 */
async function resolveRestoreTarget(
  artifactRef: string,
  options: RestoreOptions
): Promise<{
  ref: ReturnType<typeof parseRef> & { place: string };
  targetName: string;
  source: NonNullable<Awaited<ReturnType<typeof configService.getRepository>>>;
}> {
  const ref = parseRef(artifactRef);
  if (!ref.place) {
    throw new ValidationError(t('commands.backup.restore.placeRequired'));
  }
  const targetName = options.as ?? ref.name;
  await assertCommandPolicy(CMD.BACKUP_RESTORE, targetName);

  const existing = await configService.getRepository(targetName);
  if (existing) {
    throw new ValidationError(t('commands.backup.restore.targetExists', { name: targetName }));
  }
  await assertAgentRepoCreate(targetName, restorePlacementOf(options));

  // The artifact carries its source repo's identity; the pushed copy on <place>
  // is that repo under its GUID (06 §6.5). Look it up to learn the GUID we pull, then register the restored name as a fresh live record.
  const source = await configService.getRepository(ref.name);
  if (!source) {
    throw new ValidationError(t('commands.backup.restore.sourceUnknown', { name: ref.name }));
  }
  return { ref: { ...ref, place: ref.place }, targetName, source };
}

/**
 * Run the `backup_pull` for a restore, record the outcome (best-effort), and
 * render success/failure. Returns whether the pull succeeded. On failure it
 * unwinds the just-registered record so a retry is not blocked by target-exists.
 */
async function runRestorePull(args: {
  targetName: string;
  targetMachine: string;
  datastore: string | undefined;
  sourceType: 'machine';
  from: string;
  sourceGuid: string;
  debug?: boolean;
  place: string;
}): Promise<boolean> {
  const { targetName, targetMachine, datastore, sourceType, from, sourceGuid, debug, place } = args;
  outputService.info(t('commands.backup.restore.pulling', { name: targetName, place }));
  await deployRepoKeyIfNeeded(targetName, targetMachine);
  // No `at` here. `backup_pull` no longer declares the parameter, and the caller routes `--at` to `backup_restore` before reaching this function. Passing one anyway would fail schema validation, which is the honest outcome: a parameter wired to a verb that refuses it is how the next session concludes the path works.
  const pull = await getExecutor().execute({
    functionName: 'backup_pull',
    machineName: targetMachine,
    datastore,
    params: { repository: targetName, sourceType, from, src: sourceGuid },
    debug,
  });
  if (!pull.success) {
    await configService.removeRepository(compositeKey(targetName, 'latest'));
    await recordBackupRun(targetName, { kind: 'restore', status: 'failed' });
    renderLocalExecutionFailure(pull, t('commands.backup.restore.failed', { name: targetName }));
    return false;
  }
  await recordBackupRun(targetName, { kind: 'restore', status: 'ok' });
  outputService.success(
    t('commands.backup.restore.restored', { name: targetName, machine: targetMachine })
  );
  return true;
}

/**
 * Whether the account index holds any snapshot of the lineage. An unreachable
 * index or an unreadable answer is "no": the caller then takes the pull route,
 * which is what restore did before the chunk store existed.
 */
async function lineageHasSnapshots(lineage: string): Promise<boolean> {
  try {
    const result = await accountServerFetch<BackupManifestsResponse>(
      `/account/api/v1/backups/manifests?lineage=${encodeURIComponent(lineage)}`
    );
    return result.manifests.length > 0; // a malformed answer throws into the catch
  } catch {
    return false;
  }
}

/**
 * A snapshot id as `MintSnapshotID` writes it: RFC3339-basic UTC, a dash, and
 * 16 hex. Anything else in `--at` is a TIME, and resolving a time is the CLI's
 * job by explicit contract, the `backup_restore` FunctionDef says so in the
 * parameter description, because the machine has no manifest index to search.
 */
const SNAPSHOT_ID_RE = /^\d{8}T\d{6}Z-[0-9a-f]{16}$/;

/**
 * Turn `--at` into a snapshot id. A time selects the NEWEST snapshot at or
 * before it, which is the only reading that restores a point in time rather
 * than the point after it.
 *
 * `createdAt` is read from the manifest index rather than parsed out of the
 * snapshot id, even though the id is time-sortable: the id's timestamp is when
 * the id was MINTED, and the manifest commits when the upload finishes, so on a
 * long upload the two differ by the length of the transfer.
 */
export async function resolveSnapshotAt(
  lineage: string,
  at: string,
  // Omitted means every stream: read-only `backup browse --at` calls it this way (plan E4 scopes restore only). `restore --at` always passes a scope.
  scope: StreamScope = { anyStream: true }
): Promise<string> {
  if (SNAPSHOT_ID_RE.test(at)) return at;

  const when = new Date(at);
  if (Number.isNaN(when.getTime())) {
    throw new ValidationError(t('commands.backup.restore.atUnparsable', { at }));
  }

  const result = await accountServerFetch<BackupManifestsResponse>(
    `/account/api/v1/backups/manifests?lineage=${encodeURIComponent(lineage)}`
  );
  const streamId = scope.anyStream ? undefined : ownStreamOf(result.manifests, scope);
  const candidates = result.manifests
    .filter((m) => streamId === undefined || m.streamId === streamId)
    .filter((m) => new Date(m.createdAt).getTime() <= when.getTime())
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

  // `.at(0)` rather than `[0]`: this repo does not set noUncheckedIndexedAccess,
  // so `candidates[0]` is TYPED as always-present and eslint then calls the guard
  // below an unnecessary condition. It is not - an empty candidate list is the normal "no snapshot at or before this time" case, and dropping the guard to satisfy the linter would dereference undefined on the next line.
  const chosen = candidates.at(0);
  if (!chosen) {
    throw new ValidationError(t('commands.backup.restore.atNoSnapshot', { at }));
  }
  outputService.info(
    t('commands.backup.restore.atResolved', {
      at,
      snapshot: chosen.snapshotId,
      created: chosen.createdAt,
    })
  );
  return chosen.snapshotId;
}

/**
 * Which snapshots `--at` may pick from. The lineage is shared by every fork and
 * every machine that backs up a repo (that is what makes them dedup), so a time
 * alone can land on a snapshot some OTHER stream wrote, and the restore then
 * succeeds with the wrong machine's bytes. A stream is one (repo GUID, machine)
 * pair, minted by the server, so the default scope names it by the one snapshot
 * the source machine itself records as its anchor: that snapshot's stream is
 * this repo's stream on that machine. `--any-stream` widens it on purpose.
 */
export type StreamScope =
  | { anyStream: true }
  | { anyStream: false; anchorSnapshotId: string | undefined };

function ownStreamOf(
  manifests: BackupManifestsResponse['manifests'],
  scope: { anchorSnapshotId: string | undefined }
): string {
  const anchor = manifests.find((m) => m.snapshotId === scope.anchorSnapshotId);
  // A row without a streamId would make the caller's filter match every stream, the widening this scope exists to prevent.
  if (!anchor?.streamId) {
    throw new ValidationError(t('commands.backup.restore.streamUnknown'));
  }
  return anchor.streamId;
}

/**
 * The snapshot the SOURCE machine's journal anchors for this repo, read through
 * `backup_verify` (the verb already reports it). Undefined when the machine has
 * no committed snapshot, its verify fails, or the verdict cannot be read;
 * the streamUnknown refusal names both causes.
 */
async function readSourceAnchor(
  source: { repoName: string; machine: string },
  debug?: boolean
): Promise<string | undefined> {
  const result = await executeRepoFunction(
    'backup_verify',
    source.repoName,
    source.machine,
    { level: 'spot' },
    { debug, captureOutput: true },
    {
      starting: t('commands.backup.verify.starting', { name: source.repoName, level: 'spot' }),
      completed: t('commands.backup.verify.completed', { name: source.repoName }),
      failed: t('commands.backup.verify.failed', { name: source.repoName }),
    }
  );
  if (!result.success) return undefined;
  const verdict = parseVerifyVerdict(result.stdout) as { snapshotId?: string } | undefined;
  return verdict?.snapshotId;
}

/**
 * The stream scope `--at` resolves under, shared by the whole-image restore and `--path` so
 * the two cannot pick different snapshots for one time. An explicit snapshot id is a
 * deliberate choice and needs no scope; only a TIME does.
 */
async function streamScopeFor(args: {
  at: string;
  anyStream: boolean;
  source: { repoName: string; machine: string };
  debug?: boolean;
}): Promise<StreamScope> {
  if (args.anyStream || SNAPSHOT_ID_RE.test(args.at)) return { anyStream: true };
  return {
    anyStream: false,
    anchorSnapshotId: await readSourceAnchor(args.source, args.debug),
  };
}

/**
 * Run `backup_restore` for a point-in-time restore from the chunk store, and
 * unwind the just-registered record on failure exactly as the pull path does,
 * so a retry is not blocked by target-exists.
 */
async function runChunkRestore(args: {
  targetName: string;
  targetMachine: string;
  datastore: string | undefined;
  lineage: string;
  at: string;
  anyStream: boolean;
  noSeed: boolean;
  source: { repoName: string; machine: string };
  debug?: boolean;
}): Promise<boolean> {
  const { targetName, targetMachine, datastore, lineage, at, anyStream, noSeed, source, debug } =
    args;
  const scope = await streamScopeFor({ at, anyStream, source, debug });
  const snapshotId = await resolveSnapshotAt(lineage, at, scope);

  outputService.info(
    t('commands.backup.restore.restoringSnapshot', { name: targetName, snapshot: snapshotId })
  );
  await deployRepoKeyIfNeeded(targetName, targetMachine);
  const restore = await getExecutor().execute({
    functionName: 'backup_restore',
    machineName: targetMachine,
    datastore,
    params: {
      repository: targetName,
      lineage,
      at: snapshotId,
      dry_run: false,
      no_seed: noSeed,
    },
    debug,
    // The record on stdout carries the restore's measurements; without capture they are dropped.
    captureOutput: true,
  });
  if (!restore.success) {
    await configService.removeRepository(compositeKey(targetName, 'latest'));
    await recordBackupRun(targetName, {
      kind: 'restore',
      status: 'failed',
      snapshotId,
    });
    renderLocalExecutionFailure(restore, t('commands.backup.restore.failed', { name: targetName }));
    return false;
  }
  await recordBackupRun(targetName, { kind: 'restore', status: 'ok', snapshotId });
  outputService.success(
    t('commands.backup.restore.restored', { name: targetName, machine: targetMachine })
  );
  await reportRestoreStats(parseRestoreStats(restore.stdout));
  return true;
}

/**
 * The restore summary (plan L6): what was fetched, reused from a local seed or anchor, and punched
 * out, so a restore that moved little reads as one. Structured formats print the whole record.
 */
async function reportRestoreStats(stats: RestoreStats | undefined): Promise<void> {
  if (!stats) return;
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(stats, format);
    return;
  }
  const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
  const bytes = (n: number | undefined) => formatSizeBytes(n ?? 0);
  outputService.info(
    t('commands.backup.restore.stats', {
      fetched: stats.chunksFetched ?? 0,
      reused: stats.chunksReused ?? 0,
      known: stats.cellsKnown ?? 0,
      punched: stats.cellsPunched ?? 0,
      bytes: bytes(stats.bytesFetched),
      cellBytes: bytes(stats.cellBytes),
    })
  );
  if (stats.seed) {
    outputService.info(
      t('commands.backup.restore.statsSeed', {
        seed: stats.seed,
        guid: stats.seedGuid ?? '-',
        probe: bytes(stats.seedProbeBytes),
      })
    );
  }
  for (const skipped of stats.seedsSkipped ?? []) {
    outputService.info(t('commands.backup.restore.statsSeedSkipped', { skipped }));
  }
}

bindStepHandler('reportRestoreStats', ({ output }) =>
  reportRestoreStats(parseRestoreStats(output))
);

/** Deploy a restored repo (`--up`), rendering the health-gate outcome. */
async function restoreDeploy(
  name: string,
  machine: string,
  datastore: string | undefined,
  options: RestoreOptions
): Promise<void> {
  outputService.info(t('commands.backup.restore.deploying', { name, machine }));
  const params: Record<string, unknown> = { repository: name, mount: true };
  if (options.healthWindow) params.health_window = Number(options.healthWindow);
  if (options.healthTimeout) params.health_timeout = Number(options.healthTimeout);
  const up = await getExecutor().execute({
    functionName: 'repository_up',
    machineName: machine,
    // The same mount the pull wrote into (#74).
    datastore,
    params,
    debug: options.debug,
  });
  if (up.success) {
    outputService.success(t('commands.backup.restore.deployed', { name, machine }));
  } else {
    renderLocalExecutionFailure(up, t('commands.backup.restore.deployFailed', { name }));
  }
}

/**
 * `rdc backup`, one noun for named strategies, machine-scoped scheduled runs,
 * and the artifacts they produce (spec/03 §5.6). Unifies what used to live under
 * `machine backup`, `repo backup`, and `config backup-strategy`.
 */
export function registerBackupCommands(program: Command): void {
  const backup = program
    .command('backup')
    .summary(t('commands.backup.descriptionShort'))
    .description(t('commands.backup.description'));

  registerBackupStrategyCommands(backup);
  registerBackupOpsCommands(backup);
  registerBackupStorageCommands(backup);
  registerBackupList(backup);
  registerBackupImageCommands(backup);
  registerBackupRestore(backup);
}

import { randomUUID } from 'node:crypto';
import { DEFAULTS } from '@rediacc/shared/config';
import type { Placement } from '@rediacc/shared/config-schema';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { issueFreeRepoLicense, resolveLicenseAuthority } from '../services/account/free-license.js';
import { issueRepoLicense } from '../services/account/license.js';
import { DEFAULT_DATASTORE, measureRepoSizeGb } from '../services/account/license-machine.js';
import { authorizeSubscriptionViaDeviceCode } from '../services/account/subscription-device-auth.js';
import { parseRef } from '../services/addressing/ref-parser.js';
import { warnIfConfigStorageUnenrolled } from '../services/backup/dr-nudge.js';
import { namedDatastoreMount } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import { targetFloor } from '../services/config/network-id-discovery.js';
import { outputService } from '../services/core/output.js';
import {
  resolveRestoreLicenseContext,
  restoreLicenseAlreadyInstalled,
} from '../services/executor/repo-license-context.js';
import { runCommandJob } from '../services/jobs/command-job.js';
import { type PlannedStep, planStep } from '../services/jobs/steps.js';
import { machineConnections } from '../services/machine/machine-connection.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { assertAgentRepoCreate } from '../utils/agent-guard.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { assertResourceName, compositeKey } from '../utils/config-schema.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { resolveRemoteName } from '../utils/remote-resolve.js';
import { assertMachineExists } from './_validate.js';
import { registerBackupImageCommands } from './backup-image.js';
import { registerBackupOpsCommands } from './backup-ops.js';
import { registerBackupPurge } from './backup-purge.js';
import {
  resolveChunkSnapshot,
  resolveSnapshotAt,
  runChunkRestore,
  settleRestore,
  streamScopeFor,
} from './backup-restore-chunk.js';
import { assertRestorePathFlags, isPathRoute, runRestorePath } from './backup-restore-path.js';
import { sourceImageOnMachine } from './backup-restore-route.js';
import { type BackupManifestsResponse, registerBackupStorageCommands } from './backup-storage.js';
import { registerBackupStrategyCommands } from './backup-strategy.js';
import { listBackups } from './repo-backup-list.js';

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
          await listBackups(baseParams, { machine, debug: options.debug }, ref?.name);
        } catch (error) {
          handleError(error);
        }
      }
    );
}

export interface RestoreOptions {
  as?: string;
  machine?: string;
  datastore?: string;
  at?: string;
  path?: string;
  to?: string;
  anyStream?: boolean;
  /** Commander stores `--no-seed` as `seed: false` (true when the flag is absent). */
  seed?: boolean;
  /** Place an image the repository passphrase did not open. */
  allowUnopenable?: boolean;
  /** Continue past lost or corrupt chunks, leaving holes; needs `--as`. */
  salvage?: boolean;
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
    .option('--allow-unopenable', t('commands.backup.restore.optionAllowUnopenable'))
    .option('--salvage', t('commands.backup.restore.optionSalvage'))
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
        assertRestoreRepairFlags(options);
        // One path out of a snapshot: no target record, network id or credential copy, so it branches before resolveRestoreTarget.
        if (isPathRoute(options) && options.path !== undefined && options.at) {
          await restorePathRoute(artifactRef, { ...options, path: options.path, at: options.at });
          return;
        }
        const { ref, targetName, source, sourceKey } = await resolveRestoreTarget(
          artifactRef,
          options
        );

        const targetMachine = await resolveRestoreMachine(options);
        const resolved = await resolveRemoteName(ref.place);
        const from = resolved.type === 'cluster' ? ref.place : resolved.name;
        const sourceType = 'machine';
        const lineage = source.grandGuid ?? source.repositoryGuid;

        const restoreAt =
          options.at ??
          (await defaultRestoreAt({
            lineage,
            name: artifactRef,
            place: resolved.type === 'cluster' ? undefined : from,
            source,
          }));
        // Only a snapshot restore has seeds to skip; refuse before the target is registered rather than ignore the flag.
        if (options.seed === false && !restoreAt) {
          throw new ValidationError(t('commands.backup.restore.noSeedNeedsSnapshot'));
        }
        // Salvage is a chunk-store behaviour: the pull route has no chunks to lose.
        if (options.salvage && !restoreAt) {
          throw new ValidationError(t('commands.backup.restore.salvageNeedsSnapshot'));
        }

        // #74: `--datastore` was accepted, used to LOOK UP the holder machine, and then dropped, the pull ran against the machine's default, so a restore the operator asked to land on a named datastore landed somewhere else. Record the placement as the birth record (the same field `repo create` writes) so every later verb derives the right mount, and declare it on the transfer
        // below.
        const placement = options.datastore
          ? { datastore: options.datastore }
          : { machine: targetMachine };
        const datastore = options.datastore ? namedDatastoreMount(options.datastore) : undefined;

        // Refuse a bad target name before allocateNetworkId persists anything.
        assertResourceName(targetName);
        // The snapshot is chosen BEFORE the target is registered: the stream probe and the index lookup are where a chunk restore is refused, and a refusal after the registration left a config entry with no image behind it (live 2026-11-05).
        const chunk = restoreAt
          ? {
              snapshotId: await resolveChunkSnapshot({
                lineage,
                at: restoreAt,
                anyStream: options.anyStream ?? false,
                source: { repoName: sourceKey, machine: from },
                debug: options.debug,
              }),
            }
          : undefined;
        const networkId = await configService.allocateNetworkId({
          floor: await targetFloor({ machine: targetMachine }),
        });
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
        // The run record, the stats report, the registration rollback, the unit re-render (G4) and the `--up` deploy ride the job's ticket (PLAN-detached-jobs J4), so a backgrounded restore records nothing until it finishes and deploys only a restore that succeeded.
        const after = restoreTailSteps(targetName, targetMachine, datastore, options);
        if (chunk) {
          await runChunkRestore({
            targetName,
            targetMachine,
            datastore,
            lineage,
            snapshotId: chunk.snapshotId,
            noSeed: options.seed === false,
            allowUnopenable: options.allowUnopenable,
            salvage: options.salvage,
            debug: options.debug,
            after,
          });
        } else {
          await runRestorePull({
            targetName,
            targetMachine,
            datastore,
            sourceType,
            from,
            fromIsMachine: resolved.type !== 'cluster',
            sourceGuid: source.repositoryGuid,
            sourcePlacement: source.placement,
            debug: options.debug,
            place: ref.place,
            allowUnopenable: options.allowUnopenable,
            after,
          });
        }
      } catch (error) {
        handleError(error);
      }
    });
}

/**
 * Flag rules the salvage and unopenable options add. Salvage writes holes where chunks were lost,
 * so it only ever lands in a NEW repository (`--as`), never over a name that may hold a good image,
 * and it restores a whole image, not one path.
 */
export function assertRestoreRepairFlags(options: RestoreOptions): void {
  if (!options.salvage) return;
  if (!options.as) throw new ValidationError(t('commands.backup.restore.salvageNeedsAs'));
  if (options.path !== undefined || options.to !== undefined) {
    throw new ValidationError(t('commands.backup.restore.salvageWholeImage'));
  }
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
        }),
        // A path is read from the snapshot's listing, so a time with no listing falls back to the nearest one that has it.
        { indexed: true }
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
  /** The source's config key with its tag: `name:tag` for a fork, the bare name for a grand. */
  sourceKey: string;
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
  // The TAG is part of the source: a bare name resolves to the family's grand, so `observability:lab@m` pulled and probed the GRAND's GUID on a machine that only holds the lab fork's pushed image.
  const sourceKey = ref.tag ? `${ref.name}:${ref.tag}` : ref.name;
  const source = await configService.getRepository(sourceKey);
  if (!source) {
    throw new ValidationError(t('commands.backup.restore.sourceUnknown', { name: sourceKey }));
  }
  return { ref: { ...ref, place: ref.place }, targetName, source, sourceKey };
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
  fromIsMachine: boolean;
  sourceGuid: string;
  sourcePlacement?: Placement;
  debug?: boolean;
  place: string;
  allowUnopenable?: boolean;
  after: PlannedStep[];
}): Promise<void> {
  const { targetName, targetMachine, datastore, sourceType, from, sourceGuid, debug, place } = args;
  outputService.info(t('commands.backup.restore.pulling', { name: targetName, place }));
  try {
    await deployRepoKeyIfNeeded(targetName, targetMachine);
    await ensureRestorePullLicense({
      targetName,
      targetMachine,
      source: args.fromIsMachine
        ? { machine: from, guid: sourceGuid, placement: args.sourcePlacement }
        : undefined,
    });
  } catch (error) {
    // Nothing ran yet, so the job's rollback step never will: drop the registration here, or a retry meets target-exists.
    // A failing cleanup must not hide the deploy or licence error the user needs to see.
    await configService.removeRepository(compositeKey(targetName, 'latest')).catch(() => undefined);
    throw error;
  }
  // No `at` here. `backup_pull` no longer declares the parameter, and the caller routes `--at` to `backup_restore` before reaching this function. Passing one anyway would fail schema validation, which is the honest outcome: a parameter wired to a verb that refuses it is how the next session concludes the path works.
  const outcome = await runCommandJob(
    'backup restore',
    {
      functionName: 'backup_pull',
      machineName: targetMachine,
      datastore,
      params: {
        repository: targetName,
        sourceType,
        from,
        src: sourceGuid,
        ...(args.allowUnopenable ? { allow_unopenable: true } : {}),
      },
      debug,
    },
    [
      planStep('recordBackupRun', { repo: targetName, kind: 'restore', status: 'ok' }),
      planStep('recordBackupRunFailed', { repo: targetName, kind: 'restore' }),
      ...args.after,
    ]
  );
  settleRestore(outcome, targetName, targetMachine);
}

/**
 * Install the licence the pull's destination needs, BEFORE `backup_pull` runs.
 *
 * Every restore mints a fresh GUID (restoredIdentity), and `backup_pull` is
 * full-tier: renet validates the licence for the DESTINATION GUID, which no
 * machine holds yet. The executor's recovery cannot answer that refusal: for
 * a non-provisioning verb it runs the image-scanning batch refresh, and the
 * destination has no image until the pull lands it. So the licence is issued
 * here, for the minted GUID on the target machine, the way `repo create`'s
 * pre-flight issues one for a repo that does not exist yet: no identity proofs
 * (renet's later scans add them), and the same context and skip probe the
 * `--at` route's pre-flight uses for the same restored record.
 *
 * The requested size is the source image's, measured on the source machine:
 * that is what will arrive. A cluster source names no machine to measure on,
 * so it requests the floor; renet still enforces the licence's limit against
 * the staged image before committing it.
 */
async function ensureRestorePullLicense(args: {
  targetName: string;
  targetMachine: string;
  source: { machine: string; guid: string; placement?: Placement } | undefined;
}): Promise<void> {
  const renet = DEFAULTS.CONTEXT.RENET_BINARY;
  const lease = await machineConnections.acquire(args.targetMachine);
  try {
    const base = await resolveRestoreLicenseContext(
      args.targetMachine,
      { repository: args.targetName },
      lease.sftp,
      { remoteRenetPath: renet, required: true }
    );
    if (!base) throw new Error(t('errors.subscription.activationFailed'));
    if (await restoreLicenseAlreadyInstalled(base, lease.machine, renet, lease.sftp)) return;

    const requestedSizeGb = args.source ? await sourceImageSizeGb(args.source) : 1;
    const params = { ...base, requestedSizeGb };
    const authority = await resolveLicenseAuthority(() =>
      authorizeSubscriptionViaDeviceCode(undefined, {
        interactive: process.stdin.isTTY && process.stdout.isTTY,
        announceIntro: true,
      })
    );
    if (authority === 'free') {
      await issueFreeRepoLicense(
        args.targetMachine,
        lease.machine,
        lease.sshPrivateKey,
        params,
        renet,
        lease.sftp
      );
      return;
    }
    const issued = await issueRepoLicense(
      args.targetMachine,
      lease.machine,
      lease.sshPrivateKey,
      params,
      renet,
      lease.sftp
    );
    if (!issued) {
      throw new Error(t('errors.subscription.activationFailed'));
    }
  } finally {
    lease.release();
  }
}

/** The source image's size in GB on its machine (the floor, with a warning, when it cannot be measured). */
async function sourceImageSizeGb(source: {
  machine: string;
  guid: string;
  placement?: Placement;
}): Promise<number> {
  let lease: Awaited<ReturnType<typeof machineConnections.acquire>>;
  try {
    lease = await machineConnections.acquire(source.machine);
  } catch {
    outputService.warn(
      `Could not reach ${source.machine} to size the source image; requesting the 1 GB floor.`
    );
    return 1;
  }
  try {
    const placed =
      source.placement && 'datastore' in source.placement
        ? namedDatastoreMount(source.placement.datastore)
        : undefined;
    return await measureRepoSizeGb(lease.sftp, source.guid, [
      placed,
      lease.machine.datastore ?? DEFAULT_DATASTORE,
    ]);
  } catch {
    outputService.warn(
      `Could not measure the source image on ${source.machine}; requesting the 1 GB floor.`
    );
    return 1;
  } finally {
    lease.release();
  }
}

/**
 * The steps every restore route plans after its record: the stats report, the registration
 * rollback on failure, the backup-unit re-render (G4: the restore registered a new repository on
 * the target machine) and, with `--up`, the deploy.
 */
function restoreTailSteps(
  targetName: string,
  targetMachine: string,
  datastore: string | undefined,
  options: RestoreOptions
): PlannedStep[] {
  return [
    planStep('reportRestoreStats'),
    planStep('reportRestoreDamage'),
    planStep('rollbackRestoreRegistration', { repo: targetName }),
    planStep('reconcileBackupSchedules', { machine: targetMachine }),
    ...(options.up
      ? [
          planStep('restoreDeploy', {
            repo: targetName,
            ...(datastore === undefined ? {} : { datastore }),
            ...(options.healthWindow === undefined ? {} : { healthWindow: options.healthWindow }),
            ...(options.healthTimeout === undefined
              ? {}
              : { healthTimeout: options.healthTimeout }),
            debug: options.debug === true,
          }),
        ]
      : []),
  ];
}

/**
 * The restore point when `--at` is absent: undefined takes the pull route, a time the chunk route.
 *
 * A machine place that holds the source's image (the artifact `repo push --to <machine>` leaves)
 * is pulled, since that image is what the ref names. Only a place WITHOUT the image falls through
 * to the snapshot index, where a lineage with snapshots restores the newest one (`--at <now>`);
 * the pull would die there on a missing repositories/<guid>. A place that cannot be asked keeps
 * the index decision, as before the probe existed.
 */
async function defaultRestoreAt(args: {
  lineage: string;
  name: string;
  place: string | undefined;
  source: NonNullable<Awaited<ReturnType<typeof configService.getRepository>>>;
}): Promise<string | undefined> {
  if (args.place) {
    const held = await sourceImageOnMachine({
      machine: args.place,
      guid: args.source.repositoryGuid,
      placement: args.source.placement,
    });
    if (held) return undefined;
  }
  return (await lineageHasSnapshots(args.lineage, args.name))
    ? new Date().toISOString()
    : undefined;
}

/**
 * Whether the account index holds any snapshot of the lineage. An unreachable
 * index or an unreadable answer is "no": the caller then takes the pull route,
 * which is what restore did before the chunk store existed. That fallback is
 * said out loud, since on a chunk-store repo the pull has nothing to fetch.
 */
async function lineageHasSnapshots(lineage: string, name: string): Promise<boolean> {
  try {
    const result = await accountServerFetch<BackupManifestsResponse>(
      // Whether any row exists: one is enough, and the listing is capped per page.
      `/account/api/v1/backups/manifests?lineage=${encodeURIComponent(lineage)}&limit=1`
    );
    return result.manifests.length > 0; // a malformed answer throws into the catch
  } catch (error) {
    outputService.warn(
      t('commands.backup.restore.snapshotIndexUnreadable', {
        name,
        reason: error instanceof Error ? error.message : String(error),
      })
    );
    return false;
  }
}

export { resolveSnapshotAt, type StreamScope } from './backup-restore-chunk.js';

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
  registerBackupPurge(backup);
}

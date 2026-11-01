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
  resolveSnapshotAt,
  runChunkRestore,
  settleRestore,
  streamScopeFor,
} from './backup-restore-chunk.js';
import { assertRestorePathFlags, isPathRoute, runRestorePath } from './backup-restore-path.js';
import { type BackupManifestsResponse, registerBackupStorageCommands } from './backup-storage.js';
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
          ((await lineageHasSnapshots(source.grandGuid ?? source.repositoryGuid, artifactRef))
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
        // The run record, the stats report, the registration rollback, the unit re-render (G4) and the `--up` deploy ride the job's ticket (PLAN-detached-jobs J4), so a backgrounded restore records nothing until it finishes and deploys only a restore that succeeded.
        const after = restoreTailSteps(targetName, targetMachine, datastore, options);
        if (restoreAt) {
          await runChunkRestore({
            targetName,
            targetMachine,
            datastore,
            lineage,
            at: restoreAt,
            anyStream: options.anyStream ?? false,
            noSeed: options.seed === false,
            source: { repoName: ref.name, machine: from },
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
            after,
          });
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
  fromIsMachine: boolean;
  sourceGuid: string;
  sourcePlacement?: Placement;
  debug?: boolean;
  place: string;
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
    await configService.removeRepository(compositeKey(targetName, 'latest'));
    throw error;
  }
  // No `at` here. `backup_pull` no longer declares the parameter, and the caller routes `--at` to `backup_restore` before reaching this function. Passing one anyway would fail schema validation, which is the honest outcome: a parameter wired to a verb that refuses it is how the next session concludes the path works.
  const outcome = await runCommandJob(
    'backup restore',
    {
      functionName: 'backup_pull',
      machineName: targetMachine,
      datastore,
      params: { repository: targetName, sourceType, from, src: sourceGuid },
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
      await issueFreeRepoLicense(lease.machine, lease.sshPrivateKey, params, renet, lease.sftp);
      return;
    }
    if (!(await issueRepoLicense(lease.machine, lease.sshPrivateKey, params, renet, lease.sftp))) {
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
  const lease = await machineConnections.acquire(source.machine);
  try {
    const placed =
      source.placement && 'datastore' in source.placement
        ? namedDatastoreMount(source.placement.datastore)
        : undefined;
    return await measureRepoSizeGb(lease.sftp, source.guid, [
      placed,
      lease.machine.datastore ?? DEFAULT_DATASTORE,
    ]);
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
 * Whether the account index holds any snapshot of the lineage. An unreachable
 * index or an unreadable answer is "no": the caller then takes the pull route,
 * which is what restore did before the chunk store existed. That fallback is
 * said out loud, since on a chunk-store repo the pull has nothing to fetch.
 */
async function lineageHasSnapshots(lineage: string, name: string): Promise<boolean> {
  try {
    const result = await accountServerFetch<BackupManifestsResponse>(
      `/account/api/v1/backups/manifests?lineage=${encodeURIComponent(lineage)}`
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

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { parseRef } from '../services/addressing/ref-parser.js';
import { namedDatastoreMount } from '../services/cluster/cluster-target.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { assertAgentRepoCreate } from '../utils/agent-guard.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { compositeKey } from '../utils/config-schema.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { resolveRemoteName } from '../utils/remote-resolve.js';
import { assertMachineExists } from './_validate.js';
import { recordBackupRun } from '../services/backup/backup-runs-state.js';
import { warnIfConfigStorageUnenrolled } from '../services/backup/dr-nudge.js';
import { registerBackupOpsCommands } from './backup-ops.js';
import { registerBackupStorageCommands, type BackupManifestsResponse } from './backup-storage.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { registerBackupStrategyCommands } from './backup-strategy.js';
import { fetchBackupList, renderBackupList, type TaggedBackupEntry } from './repo-backup-list.js';

/** `backup list [artifact-ref]` — list backup artifacts on a machine or storage. */
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
          // ONE call, and no hot/cold probe. renet enumerates the datastore now,
          // which is what makes an artifact left by `repo push` at the root
          // visible; the old pair of probes only ever looked where SCHEDULED
          // runs write, so a real copy reported an empty table. The per-entry
          // subdirectory comes back on the entry itself.
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
  up?: boolean;
  healthWindow?: string;
  healthTimeout?: string;
  yes?: boolean;
  debug?: boolean;
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

/** `backup restore <artifact-ref>` — materialize a backup artifact into a live repo. */
function registerBackupRestore(backup: Command): void {
  backup
    .command('restore')
    .argument('<artifact-ref>', t('options.artifactRef'))
    .description(t('commands.backup.restore.description'))
    .option('--as <name>', t('commands.backup.restore.optionAs'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--datastore <name>', t('commands.backup.restore.optionDatastore'))
    .option('--at <time>', t('commands.backup.restore.optionAt'))
    .option('--up', t('commands.backup.restore.optionUp'))
    .option('--health-window <seconds>', t('options.healthWindow'))
    .option('--health-timeout <seconds>', t('options.healthTimeout'))
    .option('-y, --yes', t('options.yes'))
    .option('--debug', t('options.debug'))
    .action(async (artifactRef: string, options: RestoreOptions) => {
      try {
        const { ref, targetName, source } = await resolveRestoreTarget(artifactRef, options);

        const targetMachine = await resolveRestoreMachine(options);
        const resolved = await resolveRemoteName(ref.place);
        const from = resolved.type === 'cluster' ? ref.place : resolved.name;
        if (resolved.type === 'storage') {
          throw new ValidationError(t('commands.backup.restore.storageRetired'));
        }
        const sourceType = 'machine';

        // #74: `--datastore` was accepted, used to LOOK UP the holder machine, and
        // then dropped — the pull ran against the machine's default, so a restore
        // the operator asked to land on a named datastore landed somewhere else.
        // Record the placement as the birth record (the same field `repo create`
        // writes) so every later verb derives the right mount, and declare it on
        // the transfer below.
        const placement = options.datastore
          ? { datastore: options.datastore }
          : { machine: targetMachine };
        const datastore = options.datastore ? namedDatastoreMount(options.datastore) : undefined;

        const networkId = await configService.allocateNetworkId();
        await configService.addRepository(compositeKey(targetName, 'latest'), {
          repositoryGuid: source.repositoryGuid,
          tag: 'latest',
          // The restored record reuses the source's GUID, and the executor's
          // credential map is keyed by GUID, so a fresh credential here does not
          // give the restored repo its own key: it fights the source's over one
          // map slot and one of the two images stops unlocking. Inherit, exactly
          // as `repo fork` does.
          credential: source.credential,
          networkId,
          placement,
        });

        // DR nudge: a restore into a config with no config-storage enrollment
        // cannot recover the repo credential (the LUKS passphrase) on a fresh
        // host — warn, never block (spec/02 decision 14).
        await warnIfConfigStorageUnenrolled();

        // `--at` selects a point in time, which only the CHUNK store can answer:
        // it addresses a snapshot in a manifest chain, not an artifact on a
        // machine or a storage remote. So the flag routes to `backup_restore`
        // rather than `backup_pull`. It is a route, not a second user-facing
        // command: growing `rdc backup restore-snapshot` beside this one would
        // make the operator choose between two verbs that mean the same thing.
        const ok = options.at
          ? await runChunkRestore({
              targetName,
              targetMachine,
              datastore,
              lineage: source.grandGuid ?? source.repositoryGuid,
              at: options.at,
              debug: options.debug,
            })
          : await runRestorePull({
              targetName,
              targetMachine,
              datastore,
              sourceType,
              from,
              debug: options.debug,
              place: ref.place,
            });
        if (!ok) return;

        if (options.up) {
          await restoreDeploy(targetName, targetMachine, datastore, options);
        }
      } catch (error) {
        handleError(error);
      }
    });
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
  assertAgentRepoCreate(targetName);

  // The artifact carries its source repo's identity; the pushed copy on <place>
  // is that repo under its GUID (06 §6.5). Look it up to learn the GUID we pull,
  // then register the restored name as a fresh live record.
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
  sourceType: 'machine' | 'storage';
  from: string;
  debug?: boolean;
  place: string;
}): Promise<boolean> {
  const { targetName, targetMachine, datastore, sourceType, from, debug, place } = args;
  outputService.info(t('commands.backup.restore.pulling', { name: targetName, place }));
  await deployRepoKeyIfNeeded(targetName, targetMachine);
  // No `at` here. `backup_pull` no longer declares the parameter, and the
  // caller routes `--at` to `backup_restore` before reaching this function.
  // Passing one anyway would fail schema validation, which is the honest
  // outcome: a parameter wired to a verb that refuses it is how the next
  // session concludes the path works.
  const pull = await getExecutor().execute({
    functionName: 'backup_pull',
    machineName: targetMachine,
    datastore,
    params: { repository: targetName, sourceType, from },
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
 * A snapshot id as `MintSnapshotID` writes it: RFC3339-basic UTC, a dash, and
 * 16 hex. Anything else in `--at` is a TIME, and resolving a time is the CLI's
 * job by explicit contract — the `backup_restore` FunctionDef says so in the
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
export async function resolveSnapshotAt(lineage: string, at: string): Promise<string> {
  if (SNAPSHOT_ID_RE.test(at)) return at;

  const when = new Date(at);
  if (Number.isNaN(when.getTime())) {
    throw new ValidationError(t('commands.backup.restore.atUnparsable', { at }));
  }

  const result = await accountServerFetch<BackupManifestsResponse>(
    `/account/api/v1/backups/manifests?lineage=${encodeURIComponent(lineage)}`
  );
  const candidates = result.manifests
    .filter((m) => new Date(m.createdAt).getTime() <= when.getTime())
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());

  // `.at(0)` rather than `[0]`: this repo does not set noUncheckedIndexedAccess,
  // so `candidates[0]` is TYPED as always-present and eslint then calls the guard
  // below an unnecessary condition. It is not - an empty candidate list is the
  // normal "no snapshot at or before this time" case, and dropping the guard to
  // satisfy the linter would dereference undefined on the next line.
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
  debug?: boolean;
}): Promise<boolean> {
  const { targetName, targetMachine, datastore, lineage, at, debug } = args;
  const snapshotId = await resolveSnapshotAt(lineage, at);

  outputService.info(
    t('commands.backup.restore.restoringSnapshot', { name: targetName, snapshot: snapshotId })
  );
  await deployRepoKeyIfNeeded(targetName, targetMachine);
  const restore = await getExecutor().execute({
    functionName: 'backup_restore',
    machineName: targetMachine,
    datastore,
    params: { repository: targetName, lineage, at: snapshotId, dry_run: false },
    debug,
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
  return true;
}

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
 * `rdc backup` — one noun for named strategies, machine-scoped scheduled runs,
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
  registerBackupRestore(backup);
}

import { randomBytes } from 'node:crypto';
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
import { registerBackupOpsCommands } from './backup-ops.js';
import { registerBackupStrategyCommands } from './backup-strategy.js';
import { fetchBackupList, renderBackupList, type TaggedBackupEntry } from './repo-backup-list.js';

/** Resolve the executor machine for `backup list`. */
async function resolveListExecutor(opts: {
  machine?: string;
  storage?: string;
  place?: string;
}): Promise<{ machine: string; sourceType: 'machine' | 'storage'; from: string }> {
  if (opts.machine) {
    return { machine: opts.machine, sourceType: 'machine', from: opts.machine };
  }
  if (opts.storage) {
    // A storage listing still runs rclone on a machine. The artifact ref's
    // @place names it; otherwise the sole registered machine is used, else the
    // caller must qualify with @place.
    const machine = opts.place ?? (await soleMachineOrThrow());
    return { machine, sourceType: 'storage', from: opts.storage };
  }
  throw new ValidationError(t('commands.backup.list.placementRequired'));
}

async function soleMachineOrThrow(): Promise<string> {
  const machines = await configService.listMachines();
  if (machines.length === 1) return machines[0].name;
  throw new ValidationError(t('commands.backup.list.executorAmbiguous'));
}

/** `backup list [artifact-ref]` — list backup artifacts on a machine or storage. */
function registerBackupList(backup: Command): void {
  backup
    .command('list')
    .argument('[artifact-ref]', t('options.artifactRef'))
    .description(t('commands.backup.list.description'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--storage <name>', t('commands.backup.list.optionStorage'))
    .option('--path <subdir>', t('commands.backup.list.optionPath'))
    .option('-w, --watch', t('options.watch'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        artifactRef: string | undefined,
        options: {
          machine?: string;
          storage?: string;
          path?: string;
          watch?: boolean;
          debug?: boolean;
        }
      ) => {
        try {
          if (options.machine && options.storage) {
            throw new ValidationError(t('commands.backup.list.placementExclusive'));
          }
          const ref = artifactRef ? parseRef(artifactRef) : undefined;
          const { machine, sourceType, from } = await resolveListExecutor({
            machine: options.machine,
            storage: options.storage,
            place: ref?.place,
          });

          const baseParams: Record<string, unknown> = { sourceType, from };
          const explicitPath =
            typeof options.path === 'string' && options.path.trim().length > 0
              ? options.path.trim()
              : undefined;

          outputService.info(t('commands.backup.list.listing'));
          const runOpts = { machine, debug: options.debug };
          const tagged: TaggedBackupEntry[] = explicitPath
            ? (await fetchBackupList({ ...baseParams, path: explicitPath }, runOpts)).map((e) => ({
                ...e,
                mode: explicitPath,
              }))
            : (
                await Promise.all(
                  ['hot', 'cold'].map(async (mode) => {
                    const entries = await fetchBackupList(
                      { ...baseParams, path: mode },
                      runOpts
                    ).catch(() => []);
                    return entries.map((e) => ({ ...e, mode }));
                  })
                )
              ).flat();

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
    .option('--up', t('commands.backup.restore.optionUp'))
    .option('--health-window <seconds>', t('options.healthWindow'))
    .option('--health-timeout <seconds>', t('options.healthTimeout'))
    .option('-y, --yes', t('options.yes'))
    .option('--debug', t('options.debug'))
    .action(async (artifactRef: string, options: RestoreOptions) => {
      try {
        const ref = parseRef(artifactRef);
        if (!ref.place) {
          throw new ValidationError(t('commands.backup.restore.placeRequired'));
        }
        const targetName = options.as ?? ref.name;
        await assertCommandPolicy(CMD.BACKUP_RESTORE, targetName);

        const existing = await configService.getRepository(targetName);
        if (existing) {
          throw new ValidationError(
            t('commands.backup.restore.targetExists', { name: targetName })
          );
        }

        // Restore of a nonexistent target registers a brand-new grand repo, so it
        // must clear the same agent gate as `repo create`. assertCommandPolicy above
        // returns early here (the repo isn't in config yet), so gate it explicitly.
        assertAgentRepoCreate(targetName);

        // The artifact carries its source repo's identity; the pushed copy on
        // <place> is that repo under its GUID (06 §6.5). Look it up to learn the
        // GUID we pull, then register the restored name as a fresh live record.
        const source = await configService.getRepository(ref.name);
        if (!source) {
          throw new ValidationError(t('commands.backup.restore.sourceUnknown', { name: ref.name }));
        }

        const targetMachine = await resolveRestoreMachine(options);
        const resolved = await resolveRemoteName(ref.place);
        const from = resolved.type === 'cluster' ? ref.place : resolved.name;
        const sourceType = resolved.type === 'storage' ? 'storage' : 'machine';

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
          credential: randomBytes(24).toString('base64'),
          networkId,
          placement,
        });

        outputService.info(
          t('commands.backup.restore.pulling', { name: targetName, place: ref.place })
        );
        await deployRepoKeyIfNeeded(targetName, targetMachine);
        const pull = await getExecutor().execute({
          functionName: 'backup_pull',
          machineName: targetMachine,
          datastore,
          params: { repository: targetName, sourceType, from },
          debug: options.debug,
        });
        if (!pull.success) {
          await configService.removeRepository(compositeKey(targetName, 'latest'));
          renderLocalExecutionFailure(
            pull,
            t('commands.backup.restore.failed', { name: targetName })
          );
          return;
        }
        outputService.success(
          t('commands.backup.restore.restored', { name: targetName, machine: targetMachine })
        );

        if (options.up) {
          await restoreDeploy(targetName, targetMachine, datastore, options);
        }
      } catch (error) {
        handleError(error);
      }
    });
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
  registerBackupList(backup);
  registerBackupRestore(backup);
}

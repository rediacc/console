/**
 * The client-side step registry (PLAN-detached-jobs section 18).
 *
 * A machine job's follow-up work stays in the CLI (DNS and cert sync after an
 * up, schedule reconcile, run records, rollback, reports). Each piece is a
 * named step: a trigger (`success`, `failure`, or `marker:<name>`), the
 * non-secret params a plan may carry, and a handler that calls today's
 * function. A command plans its steps with {@link planStep}; the plan rides
 * to renet as `job start --steps <json>` and is mirrored on the local ticket,
 * so every observer runs the same plan, exactly once (run-job.ts).
 *
 * The registry, not the plan, is the authority for a step's trigger: the
 * ticket mirror only knows success and failure, so a marker step read back
 * from a ticket is re-resolved here by name.
 *
 * Handlers import their modules lazily, so the registry costs nothing to a
 * command that plans no steps. A step whose function is private to a command
 * module is bound by that module through {@link bindStepHandler}; the entry
 * names the module, and loading it binds the handler.
 */

import { isTerminalTicketState, type TicketState, type TicketStep } from './ticket-store.js';

type Scalar = string | number | boolean;

/** When a step runs. `marker:<name>` fires on a job event, not on the terminal state. */
export type StepTrigger = 'success' | 'failure' | `marker:${string}`;

/** What a handler receives. Every field comes from the plan or the observation, never from a secret. */
export interface StepContext {
  jobId: string;
  machine: string;
  params: Record<string, Scalar>;
  state: TicketState;
  /** The job's reconstructed stdout, for a step that declares `needsOutput`. Absent when the observer never saw it. */
  output?: string;
  /** When the job finished, if it has. */
  finishedAt?: string;
}

export type StepHandler = (ctx: StepContext) => Promise<void>;

export interface StepDefinition {
  name: string;
  on: StepTrigger;
  /** The param keys a plan may carry. Anything else is dropped at plan time. */
  params: readonly string[];
  needsOutput?: boolean;
  load(): Promise<StepHandler>;
}

/** One planned step, as `job start --steps` takes it. */
export interface SpoolStep {
  name: string;
  on: StepTrigger;
  params?: Record<string, Scalar>;
  needs_output?: boolean;
}

/** A step a command asked for, validated against the registry. */
export interface PlannedStep {
  name: string;
  on: StepTrigger;
  params: Record<string, Scalar>;
  needsOutput: boolean;
}

const STEP_NAME = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;
/** Drops one member record; only removeMachine's `Machine "<name>" not found` is benign, any other failure leaves the record behind and must surface. */
async function removeMemberRecord(member: string): Promise<void> {
  const { configService } = await import('../config/config-resources.js');
  try {
    await configService.removeMachine(member);
  } catch (error) {
    const message = error instanceof Error ? error.message : '';
    if (message !== `Machine "${member}" not found`) throw error;
  }
}

const SECRET_KEY = /secret|vault|password|passwd|token|credential|env|private|key/i;

export class StepHandlerUnboundError extends Error {
  constructor(readonly step: string) {
    super(
      `Step ${step} has no handler: the command module that owns its function did not bind one (bindStepHandler).`
    );
    this.name = 'StepHandlerUnboundError';
  }
}

const bound = new Map<string, StepHandler>();

/** Bind the handler of a step whose function is private to a command module. Called at that module's top level. */
export function bindStepHandler(name: string, handler: StepHandler): void {
  bound.set(name, handler);
}

/** A step whose handler the owning module binds when it loads. */
function boundStep(
  def: Omit<StepDefinition, 'load'>,
  loadModule: () => Promise<unknown>
): StepDefinition {
  return {
    ...def,
    load: async () => {
      if (!bound.has(def.name)) await loadModule();
      const handler = bound.get(def.name);
      if (!handler) throw new StepHandlerUnboundError(def.name);
      return handler;
    },
  };
}

function str(params: Record<string, Scalar>, key: string): string {
  const value = params[key];
  if (typeof value !== 'string' || value === '') {
    throw new Error(`step param "${key}" is missing`);
  }
  return value;
}

function optStr(params: Record<string, Scalar>, key: string): string | undefined {
  const value = params[key];
  return typeof value === 'string' && value !== '' ? value : undefined;
}

function optNum(params: Record<string, Scalar>, key: string): number | undefined {
  const value = params[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

/** A structured record a plan carries as a JSON string param (params are scalars). */
function jsonParam<T>(params: Record<string, Scalar>, key: string): T {
  const raw = str(params, key);
  try {
    return JSON.parse(raw) as T;
  } catch {
    throw new Error(`step param "${key}" is not JSON`);
  }
}

type BackupRunKind = 'snapshot' | 'restore' | 'verify';

function backupKind(params: Record<string, Scalar>): BackupRunKind {
  const kind = str(params, 'kind');
  if (kind !== 'snapshot' && kind !== 'restore' && kind !== 'verify') {
    throw new Error(`step param "kind" is ${JSON.stringify(kind)}`);
  }
  return kind;
}

type ConfigServiceType = typeof import('../config/config-resources.js').configService;
type RepoRecord = NonNullable<Awaited<ReturnType<ConfigServiceType['getRepository']>>>;
type DatastoreRecord = Parameters<
  typeof import('../config/config-datastores.js').recordDatastore
>[1];
type DatastoreStateRecord = NonNullable<
  Parameters<typeof import('../config/config-datastores.js').setDatastoreState>[1]
>;
type ClusterPatch = Parameters<ConfigServiceType['updateCluster']>[1];
type ClusterMembers = Parameters<
  typeof import('../config/config-cluster-ops.js').materializeClusterMachines
>[1];
type InfraPatch = Parameters<ConfigServiceType['setMachineInfra']>[1];
type ReplicaSetRecord = Parameters<
  typeof import('../cluster/repo-replicate.js').recordReplicaSet
>[1];

/** A step whose handler is rendering or recording code private to its module: the module binds it. */
function privateStep(
  name: string,
  on: StepTrigger,
  params: readonly string[],
  loadModule: () => Promise<unknown>,
  needsOutput = false
): StepDefinition {
  return boundStep({ name, on, params, ...(needsOutput ? { needsOutput } : {}) }, loadModule);
}

/**
 * The client-side steps of the conversion boxes J16-J20, column 4 of the J0b audit (PLAN-detached-jobs). JOB_PLANS
 * (plans.ts) names them per command. A step over an exported function loads it here; a step over a function private
 * to its module is bound by that module (steps-conversions.test.ts lists the binds still owed).
 */
const CONVERSION_STEPS: StepDefinition[] = [
  // J16: repo verbs.
  {
    // The working fork's tip after `repo merge` (the source commit) or `repo checkout` (the checked-out commit).
    name: 'advanceHeadCommit',
    on: 'success',
    params: ['repo', 'commit'],
    load: async () => {
      const { configService } = await import('../config/config-resources.js');
      return async (ctx) => {
        const repo = str(ctx.params, 'repo');
        const cfg = await configService.getRepository(repo);
        if (!cfg) throw new Error(`Repository "${repo}" is not in the config`);
        const key = (await configService.getRepositoryKey(repo)) ?? repo;
        await configService.addRepository(key, { ...cfg, headCommit: str(ctx.params, 'commit') });
      };
    },
  },
  {
    // `repo commit`: register the immutable commit object, then advance the working fork's tip to it.
    name: 'recordRepoCommit',
    on: 'success',
    params: ['repo', 'commit', 'message', 'author', 'parent'],
    load: async () => {
      const { configService } = await import('../config/config-resources.js');
      return async (ctx) => {
        const repo = str(ctx.params, 'repo');
        const commit = str(ctx.params, 'commit');
        const cfg: RepoRecord | undefined = await configService.getRepository(repo);
        if (!cfg) throw new Error(`Repository "${repo}" is not in the config`);
        await configService.addRepository(commit, {
          repositoryGuid: commit,
          networkId: cfg.networkId,
          credential: cfg.credential,
          grandGuid: cfg.grandGuid ?? cfg.repositoryGuid,
          parentGuid: cfg.repositoryGuid,
          immutable: true,
          commitMessage: optStr(ctx.params, 'message'),
          commitAuthor: optStr(ctx.params, 'author'),
          commitParent: optStr(ctx.params, 'parent'),
        });
        const key = (await configService.getRepositoryKey(repo)) ?? repo;
        await configService.addRepository(key, { ...cfg, headCommit: commit });
      };
    },
  },
  {
    // `repo delete`: SSH-config cleanup, config-entry settlement, schedule reconcile, cloud backups and license (handleDeleteSuccess).
    name: 'settleRepoDelete',
    on: 'success',
    params: ['repo', 'machine', 'originalRef', 'archiveConfig', 'purgeBackups'],
    load: async () => {
      const [{ handleDeleteSuccess }, { configService }] = await Promise.all([
        import('../../commands/repo-create-delete.js'),
        import('../config/config-resources.js'),
      ]);
      return async (ctx) => {
        const repo = str(ctx.params, 'repo');
        const cfg = await configService.getRepository(repo);
        if (!cfg) throw new Error(`Repository "${repo}" is not in the config`);
        await handleDeleteSuccess(
          repo,
          optStr(ctx.params, 'machine') ?? ctx.machine,
          cfg,
          ctx.params.archiveConfig === true,
          { success: true, stdout: '', stderr: '', exitCode: 0, durationMs: 0 },
          optStr(ctx.params, 'originalRef'),
          ctx.params.purgeBackups === true
        );
      };
    },
  },
  {
    name: 'recordReplicaSet',
    on: 'success',
    params: ['set', 'replicaSet'],
    load: async () => {
      const { recordReplicaSet } = await import('../cluster/repo-replicate.js');
      return (ctx) =>
        recordReplicaSet(
          str(ctx.params, 'set'),
          jsonParam<ReplicaSetRecord>(ctx.params, 'replicaSet')
        );
    },
  },
  {
    name: 'forgetReplicaSet',
    on: 'success',
    params: ['set'],
    load: async () => {
      const { forgetReplicaSet } = await import('../cluster/repo-replicate.js');
      return (ctx) => forgetReplicaSet(str(ctx.params, 'set'));
    },
  },
  privateStep(
    'renderAutostartList',
    'success',
    ['machine'],
    () => import('../../commands/repo-extended.js'),
    true
  ),
  privateStep(
    'reportRepoFsck',
    'success',
    ['machine'],
    () => import('../../commands/repo-maintenance.js'),
    true
  ),
  privateStep(
    'reportRepoGc',
    'success',
    ['machine'],
    () => import('../../commands/repo-maintenance.js'),
    true
  ),
  privateStep(
    'recordCanary',
    'success',
    ['set', 'canary'],
    () => import('../cluster/repo-release.js')
  ),
  privateStep('forgetCanary', 'success', ['set'], () => import('../cluster/repo-release.js')),
  privateStep('printRepoCat', 'success', [], () => import('../../commands/repo-cat.js'), true),
  privateStep(
    'renderRepoDiff',
    'success',
    ['mode', 'json'],
    () => import('../../commands/repo-diff.js'),
    true
  ),
  privateStep(
    'mirrorGpuGrants',
    'success',
    ['repo', 'verb', 'device'],
    () => import('../../commands/repo-gpu.js'),
    true
  ),
  privateStep(
    'renderRepoList',
    'success',
    ['machine'],
    () => import('../../commands/repo-batch-utils.js'),
    true
  ),
  privateStep(
    'renderRepoLog',
    'success',
    [],
    () => import('../../commands/repo-branching.js'),
    true
  ),
  privateStep(
    'renderPolicyResult',
    'success',
    [],
    () => import('../../commands/repo-policy.js'),
    true
  ),
  privateStep(
    'renderRepoPrune',
    'success',
    ['survey'],
    () => import('../../commands/repo-prune.js'),
    true
  ),
  privateStep('printRepoStatus', 'success', [], () => import('../../commands/repo.js'), true),
  privateStep(
    'renderRepoTrim',
    'success',
    ['reportOnly'],
    () => import('../../commands/repo-trim.js'),
    true
  ),

  // J17: backup verbs.
  {
    name: 'warnIfConfigStorageUnenrolled',
    on: 'success',
    params: [],
    load: async () => {
      const { warnIfConfigStorageUnenrolled } = await import('../backup/dr-nudge.js');
      return () => warnIfConfigStorageUnenrolled();
    },
  },
  privateStep(
    'renderBackupBrowse',
    'success',
    ['repo'],
    () => import('../../commands/backup-storage.js'),
    true
  ),
  privateStep(
    'renderBackupList',
    'success',
    ['machine'],
    () => import('../../commands/repo-backup-list.js'),
    true
  ),
  privateStep(
    'seedStrategyRetention',
    'success',
    ['strategies', 'machine'],
    () => import('../../commands/backup-ops.js')
  ),
  privateStep(
    'renderBackupStatus',
    'success',
    ['machine', 'strategy'],
    () => import('../../commands/backup-ops.js'),
    true
  ),

  // J18: machine verbs.
  {
    // `machine setup`: re-deploy repo keys, re-apply access keys, push infra (each non-fatal, as today).
    name: 'postSetupMachineTasks',
    on: 'success',
    params: ['machine', 'debug'],
    load: async () => {
      const { postSetupMachineTasks } = await import('../../commands/machine/register.js');
      return (ctx) =>
        postSetupMachineTasks(
          optStr(ctx.params, 'machine') ?? ctx.machine,
          ctx.params.debug === true
        );
    },
  },
  {
    // `machine provision`: record the infra source once the setup job has run.
    name: 'setMachineInfra',
    on: 'success',
    params: ['machine', 'infra'],
    load: async () => {
      const { configService } = await import('../config/config-resources.js');
      return (ctx) =>
        configService.setMachineInfra(
          optStr(ctx.params, 'machine') ?? ctx.machine,
          jsonParam<InfraPatch>(ctx.params, 'infra')
        );
    },
  },
  {
    name: 'purgeExpiredArchives',
    on: 'success',
    params: ['graceDays'],
    load: async () => {
      const { purgeExpiredArchives } = await import('../repo/prune.js');
      return async (ctx) => {
        await purgeExpiredArchives(optNum(ctx.params, 'graceDays'));
      };
    },
  },
  privateStep(
    'reconcileConfigState',
    'success',
    ['acceptObserved'],
    () => import('../../commands/config.js'),
    true
  ),
  privateStep(
    'settleConverge',
    'success',
    [],
    () => import('../../commands/machine/converge.js'),
    true
  ),
  privateStep(
    'settleConvergeFailed',
    'failure',
    [],
    () => import('../../commands/machine/converge.js'),
    true
  ),
  privateStep('renderGpuList', 'success', [], () => import('../../commands/machine/gpu.js'), true),
  privateStep(
    'renderMachineHealth',
    'success',
    [],
    () => import('../../commands/machine/health.js'),
    true
  ),
  privateStep(
    'ensureMachineDns',
    'success',
    ['machine'],
    () => import('../provision/infra-provision.js')
  ),
  privateStep(
    'cleanupSshArtifacts',
    'success',
    ['machine'],
    () => import('../../commands/machine/prune.js')
  ),
  privateStep(
    'renderPruneOutcome',
    'success',
    ['dryRun'],
    () => import('../../commands/machine/prune.js'),
    true
  ),
  privateStep(
    'renderRestartServices',
    'success',
    [],
    () => import('../../commands/machine/restart-services.js'),
    true
  ),
  privateStep(
    'renderMachineStatus',
    'success',
    [],
    () => import('../../commands/machine/status.js'),
    true
  ),

  // J19: datastore and cluster verbs.
  {
    name: 'recordDatastore',
    on: 'success',
    params: ['datastore', 'record'],
    load: async () => {
      const { recordDatastore } = await import('../config/config-datastores.js');
      return (ctx) =>
        recordDatastore(
          str(ctx.params, 'datastore'),
          jsonParam<DatastoreRecord>(ctx.params, 'record')
        );
    },
  },
  {
    // The routing hint after attach, detach or fork --attach-to. No `state` clears the entry. An attach whose plan
    // leaves out `attachedAt` is stamped with the job's finish, not the plan's start.
    name: 'setDatastoreState',
    on: 'success',
    params: ['datastore', 'state'],
    load: async () => {
      const { setDatastoreState } = await import('../config/config-datastores.js');
      return (ctx) => {
        const name = str(ctx.params, 'datastore');
        if (optStr(ctx.params, 'state') === undefined) return setDatastoreState(name, undefined);
        const state = jsonParam<DatastoreStateRecord>(ctx.params, 'state');
        const stamped =
          state.attachedTo && !state.attachedAt
            ? { ...state, attachedAt: ctx.finishedAt ?? new Date().toISOString() }
            : state;
        return setDatastoreState(name, stamped);
      };
    },
  },
  {
    name: 'forgetDatastore',
    on: 'success',
    params: ['datastore'],
    load: async () => {
      const { forgetDatastore } = await import('../config/config-datastores.js');
      return (ctx) => forgetDatastore(str(ctx.params, 'datastore'));
    },
  },
  {
    // `datastore status` on an attached datastore: the record plus the live status the job returned.
    name: 'renderDatastoreStatus',
    on: 'success',
    needsOutput: true,
    params: ['datastore'],
    load: async () => {
      const [{ getDatastore }, { parseCapturedJson }, { outputService }, { getOutputFormat }] =
        await Promise.all([
          import('../config/config-datastores.js'),
          import('../executor/renet-output.js'),
          import('../core/output.js'),
          import('../../utils/errors.js'),
        ]);
      return async (ctx) => {
        const name = str(ctx.params, 'datastore');
        const record = await getDatastore(name);
        outputService.print(
          {
            name,
            ...record,
            attachedTo: ctx.machine,
            live: parseCapturedJson<unknown>(ctx.output),
          },
          getOutputFormat()
        );
      };
    },
  },
  {
    // A read whose output is printed as data unchanged: `datastore snapshot list`, `cluster snapshot list`.
    name: 'printCapturedJson',
    on: 'success',
    needsOutput: true,
    params: [],
    load: async () => {
      const [{ parseCapturedJson }, { outputService }, { getOutputFormat }] = await Promise.all([
        import('../executor/renet-output.js'),
        import('../core/output.js'),
        import('../../utils/errors.js'),
      ]);
      return (ctx) => {
        outputService.print(parseCapturedJson<unknown>(ctx.output), getOutputFormat());
        return Promise.resolve();
      };
    },
  },
  {
    // `cluster create` (KVM ids) and `cluster scale` (pool counts).
    name: 'updateClusterRecord',
    on: 'success',
    params: ['cluster', 'patch'],
    load: async () => {
      const { configService } = await import('../config/config-resources.js');
      return (ctx) =>
        configService.updateCluster(
          str(ctx.params, 'cluster'),
          jsonParam<ClusterPatch>(ctx.params, 'patch')
        );
    },
  },
  {
    name: 'materializeClusterMachines',
    on: 'success',
    params: ['cluster', 'members'],
    load: async () => {
      const { materializeClusterMachines } = await import('../config/config-cluster-ops.js');
      return (ctx) =>
        materializeClusterMachines(
          str(ctx.params, 'cluster'),
          jsonParam<ClusterMembers>(ctx.params, 'members')
        );
    },
  },
  {
    // The membership backref after `cluster join` (cluster and pool given) or `cluster evict` (neither).
    name: 'updateMachineCluster',
    on: 'success',
    params: ['machine', 'cluster', 'pool'],
    load: async () => {
      const { configService } = await import('../config/config-resources.js');
      return (ctx) => {
        const cluster = optStr(ctx.params, 'cluster');
        const pool = optStr(ctx.params, 'pool');
        return configService.updateMachine(optStr(ctx.params, 'machine') ?? ctx.machine, {
          cluster: cluster && pool ? { cluster, pool } : undefined,
        });
      };
    },
  },
  {
    // `cluster scale` down: drop the member records above the new count. A record already gone is not an error.
    name: 'removeClusterMembers',
    on: 'success',
    params: ['cluster', 'pool', 'targetCount', 'currentCount'],
    load: () =>
      Promise.resolve(async (ctx: StepContext) => {
        const cluster = str(ctx.params, 'cluster');
        const pool = str(ctx.params, 'pool');
        const target = optNum(ctx.params, 'targetCount') ?? 0;
        for (let i = optNum(ctx.params, 'currentCount') ?? 0; i > target; i--) {
          await removeMemberRecord(`${cluster}-${pool}-${i}`);
        }
      }),
  },
  {
    // The audit record the cluster verbs write on success. The duration runs from the plan's start to the job's finish.
    name: 'recordClusterAudit',
    on: 'success',
    params: ['function', 'machine', 'startedAt'],
    load: async () => {
      const { auditService } = await import('../core/audit.js');
      return (ctx) => {
        const started = Date.parse(optStr(ctx.params, 'startedAt') ?? '');
        const finished = Date.parse(ctx.finishedAt ?? '') || Date.now();
        auditService.recordOperation({
          functionName: str(ctx.params, 'function'),
          machineName: optStr(ctx.params, 'machine') ?? ctx.machine,
          success: true,
          exitCode: 0,
          durationMs: Number.isNaN(started) ? 0 : Math.max(0, finished - started),
        });
        return Promise.resolve();
      };
    },
  },
  privateStep(
    'reportClusterSnapshot',
    'success',
    ['cluster', 'snapshot'],
    () => import('../cluster/cluster-snapshot.js'),
    true
  ),

  // J20: subscription verbs.
  privateStep(
    'renderSubscriptionRefresh',
    'success',
    ['machine', 'repo'],
    () => import('../../commands/subscription-actions.js'),
    true
  ),
  privateStep(
    'renderSubscriptionStatus',
    'success',
    ['machine'],
    () => import('../../commands/subscription-actions.js'),
    true
  ),
];

const DEFINITIONS: StepDefinition[] = [
  {
    name: 'postRepoUpTasks',
    on: 'success',
    params: ['repo', 'machine'],
    load: async () => {
      const { postRepoUpTasks } = await import('../../commands/repo-batch-utils.js');
      return (ctx) => postRepoUpTasks(str(ctx.params, 'repo'), ctx.machine);
    },
  },
  {
    name: 'reconcileBackupSchedules',
    on: 'success',
    params: ['machine'],
    load: async () => {
      const { reconcileBackupSchedules } = await import('../backup/repo-change-hook.js');
      return (ctx) => reconcileBackupSchedules(optStr(ctx.params, 'machine') ?? ctx.machine);
    },
  },
  {
    name: 'recordBackupRun',
    on: 'success',
    params: ['repo', 'kind', 'status', 'snapshotId'],
    load: async () => {
      const { recordBackupRun } = await import('../backup/backup-runs-state.js');
      return (ctx) =>
        recordBackupRun(str(ctx.params, 'repo'), {
          kind: backupKind(ctx.params),
          status: optStr(ctx.params, 'status') ?? 'ok',
          snapshotId: optStr(ctx.params, 'snapshotId'),
          lastRunAt: ctx.finishedAt,
        });
    },
  },
  {
    name: 'recordBackupRunFailed',
    on: 'failure',
    params: ['repo', 'kind', 'snapshotId'],
    load: async () => {
      const { recordBackupRun } = await import('../backup/backup-runs-state.js');
      return (ctx) =>
        recordBackupRun(str(ctx.params, 'repo'), {
          kind: backupKind(ctx.params),
          status: 'failed',
          snapshotId: optStr(ctx.params, 'snapshotId'),
          lastRunAt: ctx.finishedAt,
        });
    },
  },
  boundStep(
    {
      name: 'recordPushBase',
      on: 'success',
      params: ['repo', 'machine', 'method', 'verifiedBase'],
    },
    () => import('../../commands/repo-delta.js')
  ),
  {
    // Config registration that follows the job: repo migrate's placement rewrite, on the source job's cutover marker (J0 Surprise 4).
    name: 'migratePlacement',
    on: 'marker:cutover_complete',
    params: ['repo', 'machine'],
    load: async () => {
      const [{ configService }, { outputService }, { t }] = await Promise.all([
        import('../config/config-resources.js'),
        import('../core/output.js'),
        import('../../i18n/index.js'),
      ]);
      return async (ctx) => {
        const name = str(ctx.params, 'repo');
        const to = str(ctx.params, 'machine');
        await configService.setRepositoryPlacement(name, { machine: to });
        outputService.info(
          `  ${t('commands.repo.migrate.placementUpdated', { name, machine: to })}`
        );
      };
    },
  },
  boundStep(
    { name: 'rollbackCreate', on: 'failure', params: ['repo'] },
    () => import('../../commands/repo-create-delete.js')
  ),
  boundStep(
    { name: 'rollbackFork', on: 'failure', params: ['repo', 'machine', 'guid'] },
    () => import('../../commands/repo-fork.js')
  ),
  {
    // A failed restore drops the registration it made for the target (packages/cli/src/commands/backup.ts).
    name: 'rollbackRestoreRegistration',
    on: 'failure',
    params: ['repo'],
    load: async () => {
      const [{ configService }, { compositeKey }] = await Promise.all([
        import('../config/config-resources.js'),
        import('../../utils/config-schema.js'),
      ]);
      return async (ctx) => {
        await configService.removeRepository(compositeKey(str(ctx.params, 'repo'), 'latest'));
      };
    },
  },
  {
    // Warn-only, as today: a failed refresh never fails the command it follows.
    name: 'identityRefresh',
    on: 'success',
    params: [
      'function',
      'repository',
      'tag',
      'network_id',
      'checkpoint',
      'immutable',
      'up',
      'grand',
      'repo_name',
      'detach',
    ],
    load: async () => {
      const [{ localExecutorService }, { outputService }] = await Promise.all([
        import('../executor/local-executor.js'),
        import('../core/output.js'),
      ]);
      return async (ctx) => {
        const { function: functionName, ...params } = ctx.params;
        try {
          await localExecutorService.refreshIdentityFor(String(functionName), ctx.machine, params);
        } catch (error) {
          outputService.warn(
            `License identity refresh failed (non-fatal): ${error instanceof Error ? error.message : String(error)}`
          );
        }
      };
    },
  },
  {
    name: 'reportPushStats',
    on: 'success',
    needsOutput: true,
    params: ['repo', 'target', 'targetType', 'json'],
    load: async () => {
      const { reportPushStats } = await import('../../commands/repo-push-stats.js');
      return (ctx) => {
        const targetType = ctx.params.targetType === 'storage' ? 'storage' : 'machine';
        const local = { success: true, exitCode: 0, durationMs: 0, stdout: ctx.output };
        reportPushStats(
          str(ctx.params, 'repo'),
          str(ctx.params, 'target'),
          targetType,
          local,
          ctx.params.json === true
        );
        return Promise.resolve();
      };
    },
  },
  boundStep(
    { name: 'reportRestoreStats', on: 'success', needsOutput: true, params: [] },
    () => import('../../commands/backup.js')
  ),
  {
    // The verdict is printed as structured data in every mode, as `backup verify` does today.
    name: 'reportVerifyVerdict',
    on: 'success',
    needsOutput: true,
    params: ['level'],
    load: async () => {
      const [{ parseVerifyVerdict }, { outputService }, { getOutputFormat }] = await Promise.all([
        import('../../commands/backup-storage-parser.js'),
        import('../core/output.js'),
        import('../../utils/errors.js'),
      ]);
      return (ctx) => {
        const verdict = parseVerifyVerdict(ctx.output) ?? {
          status: 'verified',
          level: optStr(ctx.params, 'level'),
        };
        const format = getOutputFormat();
        outputService.print(verdict, format === 'table' ? 'json' : format);
        return Promise.resolve();
      };
    },
  },
  boundStep(
    { name: 'reportRestorePath', on: 'success', needsOutput: true, params: ['repo', 'snapshot'] },
    () => import('../../commands/backup-restore-path.js')
  ),
  ...CONVERSION_STEPS,
];

const REGISTRY = new Map(DEFINITIONS.map((def) => [def.name, def]));

export function getStepDefinition(name: string): StepDefinition | undefined {
  return REGISTRY.get(name);
}

export function listStepNames(): string[] {
  return [...REGISTRY.keys()];
}

/** Resolve a step's handler from the registry. */
export function resolveStepHandler(name: string): Promise<StepHandler> {
  const def = REGISTRY.get(name);
  if (!def) return Promise.reject(new Error(`Unknown step: ${name}`));
  return def.load();
}

/**
 * Plan one registered step. Params are filtered to the step's declared keys and
 * to scalars, and a key that looks like a secret is refused outright: a plan is
 * written to the machine spool and the local ticket, and a secret belongs in neither.
 */
export function planStep(name: string, params: Record<string, unknown> = {}): PlannedStep {
  const def = REGISTRY.get(name);
  if (!def) throw new Error(`Unknown step: ${name}`);
  const clean: Record<string, Scalar> = {};
  for (const [key, value] of Object.entries(params)) {
    if (SECRET_KEY.test(key)) {
      throw new Error(`Step ${name} refuses param "${key}": step plans never carry secrets.`);
    }
    if (!def.params.includes(key)) continue;
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      clean[key] = value;
    }
  }
  return { name, on: def.on, params: clean, needsOutput: def.needsOutput === true };
}

/** The `--steps` JSON form. */
export function toSpoolSteps(steps: PlannedStep[]): SpoolStep[] {
  return steps.map((s) => ({
    name: s.name,
    on: s.on,
    ...(Object.keys(s.params).length > 0 ? { params: s.params } : {}),
    ...(s.needsOutput ? { needs_output: true } : {}),
  }));
}

/** The ticket mirror form. A marker step is mirrored as `success`; its trigger is re-read from the registry. */
export function toTicketSteps(steps: PlannedStep[]): TicketStep[] {
  return steps.map((s) => ({
    name: s.name,
    on: s.on === 'failure' ? 'failure' : 'success',
    params: s.params,
  }));
}

/** A step's trigger: the registry's, falling back to the mirrored one for a name the registry no longer knows. */
export function triggerOf(step: Pick<TicketStep, 'name' | 'on'>): StepTrigger {
  return REGISTRY.get(step.name)?.on ?? step.on;
}

/**
 * Whether a step is due.
 *
 * - `success`: only when the job succeeded.
 * - `failure`: only when it failed or was cancelled.
 * - `marker:<name>`: once the marker was observed, in any state. When the
 *   observer saw no event stream (`markers` undefined), a succeeded job counts
 *   as having passed its marker: the marker is the source job's last step.
 */
export function stepIsDue(
  trigger: StepTrigger,
  state: TicketState,
  markers: readonly string[] | undefined
): boolean {
  if (trigger === 'success') return state === 'succeeded';
  if (trigger === 'failure') return state === 'failed' || state === 'cancelled';
  const marker = trigger.slice('marker:'.length);
  if (markers?.includes(marker)) return true;
  return markers === undefined && state === 'succeeded';
}

/** Steps of a ticket that are due and not yet recorded done. */
export function dueSteps(
  ticket: { steps: TicketStep[]; stepsDone: string[] },
  state: TicketState,
  markers?: readonly string[]
): TicketStep[] {
  return ticket.steps.filter(
    (s) =>
      STEP_NAME.test(s.name) &&
      !ticket.stepsDone.includes(s.name) &&
      stepIsDue(triggerOf(s), state, markers)
  );
}

/** The steps still owed by a finished ticket: what `rdc job list` and the notice show as pending. */
export function pendingStepNames(ticket: {
  steps: TicketStep[];
  stepsDone: string[];
  state: TicketState;
}): string[] {
  if (!isTerminalTicketState(ticket.state)) return [];
  return dueSteps(ticket, ticket.state).map((s) => s.name);
}

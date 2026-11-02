/** Client-side steps of the conversion boxes J18 to J20: machine, datastore, cluster and subscription verbs (see steps.ts). */

import {
  type ClusterMembers,
  type ClusterPatch,
  type DatastoreRecord,
  type InfraPatch,
  jsonParam,
  optNum,
  optStr,
  privateStep,
  removeMemberRecord,
  type StepContext,
  type StepDefinition,
  str,
} from './steps-support.js';

type DatastoreStateRecord = NonNullable<
  Parameters<typeof import('../config/config-datastores.js').setDatastoreState>[1]
>;

export const MACHINE_CONVERSION_STEPS: StepDefinition[] = [
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

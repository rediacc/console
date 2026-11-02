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

import { MACHINE_CONVERSION_STEPS } from './steps-conversions-machine.js';
import { REPO_CONVERSION_STEPS } from './steps-conversions-repo.js';
import {
  backupKind,
  boundStep,
  optNum,
  optStr,
  type PlannedStep,
  type Scalar,
  type SpoolStep,
  type StepDefinition,
  type StepHandler,
  type StepTrigger,
  str,
} from './steps-support.js';
import { isTerminalTicketState, type TicketState, type TicketStep } from './ticket-store.js';

export {
  bindStepHandler,
  type PlannedStep,
  type SpoolStep,
  type StepContext,
  type StepDefinition,
  type StepHandler,
  StepHandlerUnboundError,
  type StepTrigger,
} from './steps-support.js';

const STATUS_OK = 'ok';
const STATUS_FAILED = 'failed';

const STEP_NAME = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/;
/** A param name that looks like a secret; planStep refuses it. */
export const SECRET_KEY = /secret|vault|password|passwd|token|credential|env|private|key/i;

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
          status: optStr(ctx.params, 'status') ?? STATUS_OK,
          snapshotId: optStr(ctx.params, 'snapshotId'),
          lastRunAt: ctx.finishedAt,
        });
    },
  },
  {
    // `status` replaces `failed` (backup verify records `mismatch`); `quotaExit` is the exit code that records `quota-refused` (backup snapshot's renet quota refusal).
    name: 'recordBackupRunFailed',
    on: 'failure',
    params: ['repo', 'kind', 'snapshotId', 'status', 'quotaExit'],
    load: async () => {
      const { recordBackupRun } = await import('../backup/backup-runs-state.js');
      return (ctx) =>
        recordBackupRun(str(ctx.params, 'repo'), {
          kind: backupKind(ctx.params),
          status:
            ctx.exitCode !== undefined && ctx.exitCode === optNum(ctx.params, 'quotaExit')
              ? 'quota-refused'
              : (optStr(ctx.params, 'status') ?? STATUS_FAILED),
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
    { name: 'rollbackCreate', on: 'failure', params: ['repo', 'guid'] },
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
      'size',
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
    {
      // `repo migrate`: the per-phase bytes and durations and the downtime window, from the source job's `migrate_result` line.
      name: 'reportMigrateResult',
      on: 'success',
      needsOutput: true,
      params: [],
    },
    () => import('../../commands/repo-migrate.js')
  ),
  boundStep(
    {
      // `repo migrate`: the target up, DNS, the source delete and both unit re-renders, in order, once the source job succeeded.
      name: 'migrateComplete',
      on: 'success',
      params: ['repo', 'ref', 'source', 'target', 'skipDns', 'keepSource', 'datastore', 'debug'],
    },
    () => import('../../commands/repo-migrate.js')
  ),
  boundStep(
    {
      // `repo fork --checkpoint --up`: the up leg, as its own job once the fork succeeded.
      name: 'forkUp',
      on: 'success',
      params: ['repo', 'grand', 'detach', 'datastore', 'cluster', 'debug'],
    },
    () => import('../../commands/repo-fork.js')
  ),
  boundStep(
    {
      // `repo push` of an immutable commit: the `repository_commit_meta` successor on the target (J0 Surprise 7).
      name: 'syncCommitMeta',
      on: 'success',
      params: ['target', 'commit', 'message', 'author', 'parent', 'grand'],
    },
    () => import('../../commands/repo-delta.js')
  ),
  boundStep(
    {
      // `repo pull --up`: the deploy, as its own job once the pull succeeded.
      name: 'pullDeploy',
      on: 'success',
      params: ['repo', 'datastore', 'debug'],
    },
    () => import('../../commands/repo-backup.js')
  ),
  boundStep(
    {
      // `backup restore --up`: the deploy, as its own job once the restore succeeded.
      name: 'restoreDeploy',
      on: 'success',
      params: ['repo', 'datastore', 'healthWindow', 'healthTimeout', 'debug'],
    },
    () => import('../../commands/backup.js')
  ),
  boundStep(
    { name: 'reportRestorePath', on: 'success', needsOutput: true, params: ['repo', 'snapshot'] },
    () => import('../../commands/backup-restore-path.js')
  ),
  ...REPO_CONVERSION_STEPS,
  ...MACHINE_CONVERSION_STEPS,
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

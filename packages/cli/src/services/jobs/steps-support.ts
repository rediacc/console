/** Types, param readers and binders shared by the step registry (steps.ts) and its definition modules. */

import type { TicketState } from './ticket-store.js';

export type Scalar = string | number | boolean;

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
  /** The job's exit code, when the observer read it. */
  exitCode?: number;
  /** The `step_done` names the observer saw in the job's stream; undefined when it saw no stream from the start. */
  markers?: readonly string[];
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

/** Drops one member record; only removeMachine's MachineNotFoundError is benign, any other failure leaves the record behind and must surface. */
export async function removeMemberRecord(member: string): Promise<void> {
  const { configService, MachineNotFoundError } = await import('../config/config-resources.js');
  try {
    await configService.removeMachine(member);
  } catch (error) {
    if (!(error instanceof MachineNotFoundError)) throw error;
  }
}

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
export function boundStep(
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

export function str(params: Record<string, Scalar>, key: string): string {
  const value = params[key];
  if (typeof value !== 'string' || value === '') {
    throw new Error(`step param "${key}" is missing`);
  }
  return value;
}

export function optStr(params: Record<string, Scalar>, key: string): string | undefined {
  const value = params[key];
  return typeof value === 'string' && value !== '' ? value : undefined;
}

export function optNum(params: Record<string, Scalar>, key: string): number | undefined {
  const value = params[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

/** A structured record a plan carries as a JSON string param (params are scalars). */
export function jsonParam<T>(params: Record<string, Scalar>, key: string): T {
  const raw = str(params, key);
  try {
    return JSON.parse(raw) as T;
  } catch {
    throw new Error(`step param "${key}" is not JSON`);
  }
}

export type BackupRunKind = 'snapshot' | 'restore' | 'verify';

export function backupKind(params: Record<string, Scalar>): BackupRunKind {
  const kind = str(params, 'kind');
  if (kind !== 'snapshot' && kind !== 'restore' && kind !== 'verify') {
    throw new Error(`step param "kind" is ${JSON.stringify(kind)}`);
  }
  return kind;
}

export type ConfigServiceType = typeof import('../config/config-resources.js').configService;
export type DatastoreRecord = Parameters<
  typeof import('../config/config-datastores.js').recordDatastore
>[1];
export type ClusterPatch = Parameters<ConfigServiceType['updateCluster']>[1];
export type ClusterMembers = Parameters<
  typeof import('../config/config-cluster-ops.js').materializeClusterMachines
>[1];
export type InfraPatch = Parameters<ConfigServiceType['setMachineInfra']>[1];
export type ReplicaSetRecord = Parameters<
  typeof import('../cluster/repo-replicate.js').recordReplicaSet
>[1];

/** A step whose handler is rendering or recording code private to its module: the module binds it. */
export function privateStep(
  name: string,
  on: StepTrigger,
  params: readonly string[],
  loadModule: () => Promise<unknown>,
  needsOutput = false
): StepDefinition {
  return boundStep({ name, on, params, ...(needsOutput ? { needsOutput } : {}) }, loadModule);
}

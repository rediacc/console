import { type Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { parseCapturedJson } from '../services/executor/renet-output.js';
import { pendingExitCode, runCommandJob } from '../services/jobs/command-job.js';
import { requireStepOutput } from '../services/jobs/step-output.js';
import { bindStepHandler, planStep } from '../services/jobs/steps.js';
import { isAgentEnvironment } from '../utils/agent-guard.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { isRepoAllowedByGrandEnv } from '../utils/grand-env.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { isOverrideLegitimate } from '../utils/process-ancestry.js';
import { executeRepoFunction, recordedDatastoreMount } from '../utils/repo-executor.js';
import { resolveRepoRef, resolveRepoTarget } from '../utils/repo-target.js';
import { assertMachineExists } from './_validate.js';
import { parseDatastorePruneOutput } from './datastore-prune-parser.js';

interface PolicySetOptions {
  machine?: string;
  autoGrow?: string;
  maxQuota?: string;
  growThreshold?: string;
  growStep?: string;
  autoTrim?: string;
  trimInterval?: string;
  memoryMax?: string;
  memoryHigh?: string;
  cpuMax?: string;
  ioMax?: string;
  pidsMax?: string;
  ramVolume?: string;
  clearLimits?: boolean;
  force?: boolean;
  debug?: boolean;
}

/** The repository a single-repo policy ref names: what the limit functions and the agent guard need. */
interface PolicyRepo {
  name: string;
  repoKey: string;
  /** A fork's grandGuid is another repository's guid; a grand repository has none of its own to differ from. */
  grand: boolean;
}

/**
 * The resolved policy target: the execution machine plus the renet scope param.
 *
 * There is deliberately NO kubeCluster here. Size policy (auto-grow / auto-trim)
 * is a property of the VOLUME in a datastore, not of a container runtime: there is
 * no kubectl in this path, so there is nothing for a KUBECONFIG to do. The derived
 * machine is already the datastore's attach host, which is exactly where the policy
 * must be applied, for either runtime.
 */
interface PolicyTarget {
  machineName: string;
  /** Recorded datastore mount for a single-repo ref; undefined machine-wide (#74). */
  datastore?: string;
  /** `{ name: <guid> }` for a single-repo ref, `{}` for the machine-wide form. */
  params: Record<string, unknown>;
  /** The repository of a single-repo ref; undefined machine-wide. */
  repo?: PolicyRepo;
}

/**
 * Resolve a policy verb's target. A positional `<ref>` scopes to one repo and
 * derives its own machine (so `-m` alongside a ref is contradictory); no ref
 * addresses the machine-wide default policy on `-m`. Read-only verbs (get) pass
 * `readOnly` to skip the derived-machine remote check.
 */
async function resolvePolicyTarget(
  ref: string | undefined,
  machine: string | undefined,
  verb: string,
  readOnly: boolean
): Promise<PolicyTarget> {
  if (ref) {
    if (machine) {
      throw new ValidationError(t('commands.repo.refMachineConflict', { verb }));
    }
    const resolved = await resolveRepoRef(ref, { readOnly });
    const repo = await configService.getRepository(resolved.repoKey);
    if (!repo) {
      throw new Error(t('commands.repo.policy.repoNotFound', { name: resolved.name }));
    }
    return {
      machineName: resolved.machineName,
      // #74: the ref arm addresses ONE repo, so it must be read from the datastore that repo is recorded on. The machine-wide arm below addresses the machine's own default policy and correctly declares nothing.
      datastore: await recordedDatastoreMount(resolved.repoKey),
      params: { name: repo.repositoryGuid },
      repo: {
        name: resolved.name,
        repoKey: resolved.repoKey,
        grand: !(repo.grandGuid && repo.grandGuid !== repo.repositoryGuid),
      },
    };
  }

  // Machine-wide form: address the machine's default policy on -m (errors when -m is also absent, as before).
  const target = await resolveRepoTarget({ machine });
  return { machineName: target.machineName, params: {} };
}

/** Validate a tri-state boolean option value ('true' | 'false'). */
function parseBoolOption(flag: string, value: string | undefined): string | undefined {
  if (value === undefined) return undefined;
  if (value !== 'true' && value !== 'false') {
    throw new Error(t('commands.repo.policy.invalidBool', { flag, value }));
  }
  return value;
}

/**
 * Run the policy function; true when its answer reached this process finished and successful.
 * `merge` (json and yaml print one document) makes the settings step hold its document in `heldPolicy` for the limits step to fold in.
 */
async function runPolicyFunction(
  functionName: 'repository_policy_set' | 'repository_policy_get',
  target: PolicyTarget,
  debug: boolean | undefined,
  merge = false
): Promise<boolean> {
  await assertMachineExists(target.machineName);

  // The settings table is the job's step, so a ticket handed back early prints nothing half-done.
  const outcome = await runCommandJob(
    functionName === 'repository_policy_set' ? 'repo policy set' : 'repo policy get',
    {
      functionName,
      machineName: target.machineName,
      datastore: target.datastore,
      params: target.params,
      debug,
      captureOutput: true,
    },
    [planStep('renderPolicyResult', merge ? { merge } : {})]
  );
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return false;
  }
  if (!outcome.result.success) {
    renderLocalExecutionFailure(outcome.result, t('commands.repo.policy.failed'));
    return false;
  }
  return true;
}

/** The settings document a `repo policy get -o json|yaml` holds until its limits step folds it into the one printed document. */
let heldPolicy: Record<string, unknown> | undefined;

bindStepHandler('renderPolicyResult', ({ output, params }) => {
  const text = requireStepOutput(output, 'repo policy');
  if (text === undefined) return Promise.resolve();
  const parsed = parseDatastorePruneOutput(text);
  if (params.merge === true) {
    heldPolicy = parsed;
    return Promise.resolve();
  }
  return renderPolicyResult(parsed);
});

interface PolicyFields {
  auto_grow?: boolean | null;
  max_quota_bytes?: number | null;
  grow_when_used_percent?: number | null;
  grow_step?: string | null;
  auto_trim?: boolean | null;
  trim_interval_hours?: number | null;
}

/** Render the policy payload as a settings table (effective/override/default). */
async function renderPolicyResult(parsed: Record<string, unknown>): Promise<void> {
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(parsed, format);
    return;
  }

  const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
  const effective = (parsed.effective ?? {}) as PolicyFields;
  const override = parsed.repo_override as PolicyFields | null | undefined;
  const machineDefault = parsed.machine_default as PolicyFields | null | undefined;

  const fields: { key: keyof PolicyFields; label: string; fmt?: (v: unknown) => string }[] = [
    { key: 'auto_grow', label: 'Auto-grow' },
    { key: 'max_quota_bytes', label: 'Max quota', fmt: (v) => formatSizeBytes(v as number) },
    { key: 'grow_when_used_percent', label: 'Grow threshold', fmt: (v) => `${v}%` },
    { key: 'grow_step', label: 'Grow step' },
    { key: 'auto_trim', label: 'Auto-trim' },
    { key: 'trim_interval_hours', label: 'Trim interval', fmt: (v) => `${v}h` },
  ];
  const cell = (src: PolicyFields | null | undefined, f: (typeof fields)[number]): string => {
    const v = src?.[f.key];
    if (v === undefined || v === null) return '-';
    if (typeof v === 'boolean') return v ? 'yes' : 'no';
    return f.fmt ? f.fmt(v) : String(v);
  };

  const rows = fields.map((f) => ({
    setting: f.label,
    effective: cell(effective, f),
    override: cell(override, f),
    machineDefault: cell(machineDefault, f),
  }));
  outputService.print(rows, 'table');
}

/** The limit flags and the repository_limits_set param each maps to (PLAN-repo-resource-limits Decision 2). */
const LIMIT_FLAGS = [
  ['memoryMax', 'memory_max'],
  ['memoryHigh', 'memory_high'],
  ['cpuMax', 'cpu_max'],
  ['ioMax', 'io_max'],
  ['pidsMax', 'pids_max'],
  ['ramVolume', 'ram_volume'],
] as const;

/** The repository_limits_set params the options name; empty when no limit flag was given (--force alone changes nothing). */
export function limitParamsOf(options: PolicySetOptions): Record<string, unknown> {
  const params: Record<string, unknown> = {};
  for (const [option, param] of LIMIT_FLAGS) {
    const value = options[option];
    if (value !== undefined && value !== '') params[param] = value;
  }
  if (options.clearLimits) params.clear_limits = true;
  if (Object.keys(params).length > 0 && options.force) params.force = true;
  return params;
}

/** True when a size-policy flag was given, so `repository_policy_set` has something to change. */
function hasSizeFlags(options: PolicySetOptions): boolean {
  return [
    options.autoGrow,
    options.maxQuota,
    options.growThreshold,
    options.growStep,
    options.autoTrim,
    options.trimInterval,
  ].some((v) => v !== undefined);
}

/**
 * Refuse a limit change on a grand repository to an agent unless the operator set REDIACC_ALLOW_GRAND_REPO before the
 * agent started: the ancestry check `repo permission grant --path` makes. A limit decrease can OOM-kill the
 * repository's containers. A fork stays free.
 */
function assertLimitsChangeAllowed(repo: PolicyRepo): void {
  if (!isAgentEnvironment() || !repo.grand) return;
  if (!isRepoAllowedByGrandEnv(repo.name)) {
    throw new ValidationError(t('errors.agent.limitsGrantBlocked', { name: repo.name }));
  }
  if (!isOverrideLegitimate()) {
    throw new ValidationError(t('errors.agent.limitsGrantOverride', { name: repo.name }));
  }
}

/** Run repository_limits_set or _show for the ref's repository; the limits table is the job's step. */
async function runLimitsFunction(
  functionName: 'repository_limits_set' | 'repository_limits_show',
  target: PolicyTarget & { repo: PolicyRepo },
  params: Record<string, unknown>,
  debug: boolean | undefined,
  merge = false
): Promise<void> {
  const verb = functionName === 'repository_limits_set' ? 'repo policy set' : 'repo policy get';
  await executeRepoFunction(
    functionName,
    target.repo.repoKey,
    target.machineName,
    params,
    {
      debug,
      captureOutput: true,
      job: { verb, steps: [planStep('renderLimitsResult', merge ? { merge } : {})] },
    },
    {
      starting: t('commands.repo.policy.limits.starting', {
        repository: target.repo.name,
        machine: target.machineName,
      }),
      completed: t('commands.repo.policy.limits.completed', { repository: target.repo.name }),
      failed: t('commands.repo.policy.limits.failed'),
    }
  );
}

/** The limits half of the grant renet prints (`daemon grant --show`); a limit of 0 or absent is none. */
export interface GrantLimits {
  limits?: {
    memory_max?: number;
    memory_high?: number;
    cpu_max?: string;
    io_max?: { rbps?: number; wbps?: number; riops?: number; wiops?: number };
    pids_max?: number;
  };
  ram_volume?: { size?: number };
}

/** cpu.max "<quota> <period>" as cores ("2.5 cores"); the raw value when it is not that shape. */
export function cpuMaxCores(cpuMax: string): string {
  const [quota, period] = cpuMax.split(' ').map(Number);
  if (!(quota > 0 && period > 0)) return cpuMax;
  return `${Number((quota / period).toFixed(2))} cores`;
}

/** The limits table rows: one per limit, '-' when none is set. */
export async function limitRows(grant: GrantLimits): Promise<{ limit: string; value: string }[]> {
  const { formatSizeBytes } = await import('@rediacc/shared/renet-contract');
  const l = grant.limits ?? {};
  const size = (v: number | undefined) => (v ? formatSizeBytes(v) : '-');
  const io = l.io_max ?? {};
  const ioParts = [
    io.rbps ? `rbps=${formatSizeBytes(io.rbps)}` : '',
    io.wbps ? `wbps=${formatSizeBytes(io.wbps)}` : '',
    io.riops ? `riops=${io.riops}` : '',
    io.wiops ? `wiops=${io.wiops}` : '',
  ].filter(Boolean);
  return [
    { limit: 'Memory max', value: size(l.memory_max) },
    { limit: 'Memory high', value: size(l.memory_high) },
    { limit: 'CPU max', value: l.cpu_max ? cpuMaxCores(l.cpu_max) : '-' },
    { limit: 'I/O max', value: ioParts.join(',') || '-' },
    { limit: 'Pids max', value: l.pids_max ? String(l.pids_max) : '-' },
    { limit: 'RAM volume', value: size(grant.ram_volume?.size) },
  ];
}

bindStepHandler('renderLimitsResult', async ({ output, params }) => {
  const text = requireStepOutput(output, 'repo policy limits');
  if (text === undefined) return;
  const grant = parseCapturedJson<GrantLimits>(text);
  const format = getOutputFormat();
  if (format !== 'table') {
    const limits = { limits: grant.limits ?? {}, ram_volume: grant.ram_volume ?? {} };
    if (params.merge === true) {
      const policy = heldPolicy;
      heldPolicy = undefined;
      if (policy === undefined) {
        throw new Error(t('commands.repo.policy.settingsNotHeld'));
      }
      outputService.print({ ...policy, ...limits }, format);
      return;
    }
    outputService.print(limits, format);
    return;
  }
  outputService.print(await limitRows(grant), 'table');
});

/** Add the size-policy flags to the repository_policy_set params; an absent flag leaves the stored value. */
function addSizeParams(params: Record<string, unknown>, options: PolicySetOptions): void {
  // Tri-state booleans: 'true' | 'false' | absent (leave the stored value).
  const autoGrow = parseBoolOption('--auto-grow', options.autoGrow);
  if (autoGrow) params.auto_grow = autoGrow;
  const autoTrim = parseBoolOption('--auto-trim', options.autoTrim);
  if (autoTrim) params.auto_trim = autoTrim;
  if (options.maxQuota) params.max_quota = options.maxQuota;
  if (options.growThreshold) params.grow_threshold = options.growThreshold;
  if (options.growStep) params.grow_step = options.growStep;
  if (options.trimInterval) params.trim_interval = options.trimInterval;
}

async function handlePolicySet(ref: string | undefined, options: PolicySetOptions): Promise<void> {
  const limitParams = limitParamsOf(options);
  const wantsLimits = Object.keys(limitParams).length > 0;
  // Limits are a per-repository operator grant (Decision 2): the machine-wide form has none to set.
  if (wantsLimits && !ref) {
    throw new ValidationError(t('commands.repo.policy.limitsNeedRef'));
  }
  // set is mutating, so resolve without readOnly (like `repo up`).
  const target = await resolvePolicyTarget(ref, options.machine, 'policy set', false);
  if (wantsLimits && target.repo) assertLimitsChangeAllowed(target.repo);
  addSizeParams(target.params, options);

  if (hasSizeFlags(options) || !wantsLimits) {
    await runPolicyFunction('repository_policy_set', target, options.debug);
  }
  if (wantsLimits && target.repo) {
    await assertMachineExists(target.machineName);
    await runLimitsFunction(
      'repository_limits_set',
      { ...target, repo: target.repo },
      limitParams,
      options.debug
    );
  }
}

/** Register `repo policy set|get`, automatic size management policy
 * (rediacc/renet#76): online auto-grow + scheduled trim, applied by the
 * machine-side storage-maintain timer. There is deliberately no auto-shrink:
 * quota shrink stays the offline, operator-run `repo resize`. */
export function registerRepoPolicyCommand(repo: Command): void {
  const policy = repo
    .command('policy')
    .summary(t('commands.repo.policy.descriptionShort'))
    .description(t('commands.repo.policy.description'));

  policy
    .command('set')
    .summary(t('commands.repo.policy.set.descriptionShort'))
    .description(t('commands.repo.policy.set.description'))
    .argument('[ref]', t('options.repoRef'))
    .addOption(
      new Option('--auto-grow <bool>', t('commands.repo.policy.set.autoGrowOption')).choices([
        'true',
        'false',
      ])
    )
    .option('--max-quota <size>', t('commands.repo.policy.set.maxQuotaOption'))
    .option('--grow-threshold <percent>', t('commands.repo.policy.set.growThresholdOption'))
    .option('--grow-step <step>', t('commands.repo.policy.set.growStepOption'))
    .addOption(
      new Option('--auto-trim <bool>', t('commands.repo.policy.set.autoTrimOption')).choices([
        'true',
        'false',
      ])
    )
    .option('--trim-interval <hours>', t('commands.repo.policy.set.trimIntervalOption'))
    .option('--memory-max <size>', t('commands.repo.policy.set.memoryMaxOption'))
    .option('--memory-high <size>', t('commands.repo.policy.set.memoryHighOption'))
    .option('--cpu-max <cores>', t('commands.repo.policy.set.cpuMaxOption'))
    .option('--io-max <limits>', t('commands.repo.policy.set.ioMaxOption'))
    .option('--pids-max <count>', t('commands.repo.policy.set.pidsMaxOption'))
    .option('--ram-volume <size>', t('commands.repo.policy.set.ramVolumeOption'))
    .option('--clear-limits', t('commands.repo.policy.set.clearLimitsOption'))
    .option('--force', t('commands.repo.policy.set.forceOption'))
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string | undefined, options: PolicySetOptions) => {
      try {
        await handlePolicySet(ref, options);
      } catch (error) {
        handleError(error);
      }
    });

  policy
    .command('get')
    .summary(t('commands.repo.policy.get.descriptionShort'))
    .description(t('commands.repo.policy.get.description'))
    .argument('[ref]', t('options.repoRef'))
    .option('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .action(async (ref: string | undefined, options: { machine?: string; debug?: boolean }) => {
      try {
        // get is read-only: skip the derived-machine remote round-trip.
        const target = await resolvePolicyTarget(ref, options.machine, 'policy get', true);
        // json and yaml print ONE document: the settings merged with the limits, so the limits job folds in the settings the first job held.
        const merge = target.repo !== undefined && getOutputFormat() !== 'table';
        const read = await runPolicyFunction('repository_policy_get', target, options.debug, merge);
        // A single-repo get adds the repository's limits table (Decision 2).
        if (target.repo && (read || !merge)) {
          await runLimitsFunction(
            'repository_limits_show',
            { ...target, repo: target.repo },
            {},
            options.debug,
            merge
          );
        }
      } catch (error) {
        handleError(error);
      }
    });
}

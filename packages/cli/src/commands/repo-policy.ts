import { type Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { outputService } from '../services/core/output.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { getOutputFormat, handleError, ValidationError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
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
  debug?: boolean;
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
  /** `{ name: <guid> }` for a single-repo ref, `{}` for the machine-wide form. */
  params: Record<string, unknown>;
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
      params: { name: repo.repositoryGuid },
    };
  }

  // Machine-wide form: address the machine's default policy on -m (errors when
  // -m is also absent, as before).
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

async function runPolicyFunction(
  functionName: 'repository_policy_set' | 'repository_policy_get',
  target: PolicyTarget,
  debug: boolean | undefined
): Promise<void> {
  await assertMachineExists(target.machineName);

  const result = await getExecutor().execute({
    functionName,
    machineName: target.machineName,
    params: target.params,
    debug,
    captureOutput: true,
  });

  if (!result.success) {
    renderLocalExecutionFailure(result, t('commands.repo.policy.failed'));
    return;
  }

  const parsed = parseDatastorePruneOutput(result.stdout ?? '');
  await renderPolicyResult(parsed);
}

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

async function handlePolicySet(ref: string | undefined, options: PolicySetOptions): Promise<void> {
  // set is mutating, so resolve without readOnly (like `repo up`).
  const target = await resolvePolicyTarget(ref, options.machine, 'policy set', false);
  const params = target.params;

  // Tri-state booleans: 'true' | 'false' | absent (leave the stored value).
  const autoGrow = parseBoolOption('--auto-grow', options.autoGrow);
  if (autoGrow) params.auto_grow = autoGrow;
  const autoTrim = parseBoolOption('--auto-trim', options.autoTrim);
  if (autoTrim) params.auto_trim = autoTrim;
  if (options.maxQuota) params.max_quota = options.maxQuota;
  if (options.growThreshold) params.grow_threshold = options.growThreshold;
  if (options.growStep) params.grow_step = options.growStep;
  if (options.trimInterval) params.trim_interval = options.trimInterval;

  await runPolicyFunction('repository_policy_set', target, options.debug);
}

/** Register `repo policy set|get` — automatic size management policy
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
        await runPolicyFunction('repository_policy_get', target, options.debug);
      } catch (error) {
        handleError(error);
      }
    });
}

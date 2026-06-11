import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { getOutputFormat, handleError } from '../utils/errors.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { assertMachineExists } from './_validate.js';
import { parseDatastorePruneOutput } from './datastore-prune-parser.js';

interface PolicySetOptions {
  machine: string;
  name?: string;
  autoGrow?: string;
  maxQuota?: string;
  growThreshold?: string;
  growStep?: string;
  autoTrim?: string;
  trimInterval?: string;
  debug?: boolean;
}

/** Validate a tri-state boolean option value ('true' | 'false'). */
function parseBoolOption(flag: string, value: string | undefined): string | undefined {
  if (value === undefined) return undefined;
  if (value !== 'true' && value !== 'false') {
    throw new Error(t('commands.repo.policy.invalidBool', { flag, value }));
  }
  return value;
}

/** Resolve an optional repo name to its GUID param. */
async function repoGuidParam(name: string | undefined): Promise<Record<string, unknown>> {
  if (!name) return {};
  const repo = await configService.getRepository(name);
  if (!repo) {
    throw new Error(t('commands.repo.policy.repoNotFound', { name }));
  }
  return { name: repo.repositoryGuid };
}

async function runPolicyFunction(
  functionName: 'repository_policy_set' | 'repository_policy_get',
  machine: string,
  params: Record<string, unknown>,
  debug: boolean | undefined
): Promise<void> {
  await assertMachineExists(machine);

  const result = await localExecutorService.execute({
    functionName,
    machineName: machine,
    params,
    debug,
    captureOutput: true,
  });

  if (!result.success) {
    renderLocalExecutionFailure(result, t('commands.repo.policy.failed'));
    return;
  }

  const parsed = parseDatastorePruneOutput(result.stdout ?? '');
  outputService.print(parsed, getOutputFormat() === 'table' ? 'json' : getOutputFormat());
}

async function handlePolicySet(options: PolicySetOptions): Promise<void> {
  const params = await repoGuidParam(options.name);

  // Tri-state booleans: 'true' | 'false' | absent (leave the stored value).
  const autoGrow = parseBoolOption('--auto-grow', options.autoGrow);
  if (autoGrow) params.auto_grow = autoGrow;
  const autoTrim = parseBoolOption('--auto-trim', options.autoTrim);
  if (autoTrim) params.auto_trim = autoTrim;
  if (options.maxQuota) params.max_quota = options.maxQuota;
  if (options.growThreshold) params.grow_threshold = options.growThreshold;
  if (options.growStep) params.grow_step = options.growStep;
  if (options.trimInterval) params.trim_interval = options.trimInterval;

  await runPolicyFunction('repository_policy_set', options.machine, params, options.debug);
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
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--name <name>', t('commands.repo.policy.nameOption'))
    .option('--auto-grow <bool>', t('commands.repo.policy.set.autoGrowOption'))
    .option('--max-quota <size>', t('commands.repo.policy.set.maxQuotaOption'))
    .option('--grow-threshold <percent>', t('commands.repo.policy.set.growThresholdOption'))
    .option('--grow-step <step>', t('commands.repo.policy.set.growStepOption'))
    .option('--auto-trim <bool>', t('commands.repo.policy.set.autoTrimOption'))
    .option('--trim-interval <hours>', t('commands.repo.policy.set.trimIntervalOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: PolicySetOptions) => {
      try {
        await handlePolicySet(options);
      } catch (error) {
        handleError(error);
      }
    });

  policy
    .command('get')
    .summary(t('commands.repo.policy.get.descriptionShort'))
    .description(t('commands.repo.policy.get.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--name <name>', t('commands.repo.policy.nameOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: { machine: string; name?: string; debug?: boolean }) => {
      try {
        const params = await repoGuidParam(options.name);
        await runPolicyFunction('repository_policy_get', options.machine, params, options.debug);
      } catch (error) {
        handleError(error);
      }
    });
}

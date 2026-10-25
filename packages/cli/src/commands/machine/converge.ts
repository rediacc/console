/**
 * `rdc machine converge <name>`: restart every repo daemon still on an older
 * runtime layout onto the current one (agent/plans/PLAN-renet-runtime-converge.md, D5).
 *
 * The executor runs the same pass on its own after a renet upload; this verb is
 * the manual form: a dry run to see the plan, a resume after a failed pass, or
 * `--policy always` to also restart daemons started by an older renet binary.
 */

import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { type Command, Option } from 'commander';
import { t } from '../../i18n/index.js';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { outputService } from '../../services/core/output.js';
import { setExitCode } from '../../services/core/request-context.js';
import { type ExecuteResult, getExecutor } from '../../services/executor/executor-factory.js';
import { renetProvisioner } from '../../services/renet/renet-provisioner.js';
import {
  buildConvergeParams,
  CONVERGE_FUNCTION,
  type ConvergeOptions,
  type ConvergeReport,
  convergeResumeCommand,
  countConvergeResults,
  isRuntimeConvergeOptedOut,
  parseConvergeReport,
  RUNTIME_POLICIES,
  readRuntimeStatus,
  renderConvergeReport,
  routerRefreshAfterPass,
} from '../../services/renet/runtime-converge.js';
import type { OutputFormat } from '../../types/index.js';
import { getOutputFormat, handleError } from '../../utils/errors.js';
import { renderLocalExecutionFailure } from '../../utils/local-execution-failures.js';
import { assertMachineExists } from '../_validate.js';

interface ConvergeCommandOptions extends ConvergeOptions {
  json?: boolean;
  debug?: boolean;
}

function startingKey(dryRun: boolean | undefined): string {
  return dryRun ? 'commands.machine.converge.startingDryRun' : 'commands.machine.converge.starting';
}

/** Print the report and settle the exit code; true when the pass succeeded. */
function settleConverge(machineName: string, result: ExecuteResult, format: OutputFormat): boolean {
  const report = parseConvergeReport(result.stdout);
  if (report && format === 'table') renderConvergeReport(report, machineName);
  else if (report) outputService.print(report, format);
  if (result.success) return true;
  // Without a report nothing explained the failure yet; with one, its lines named each failed repo.
  if (report) setExitCode(result.exitCode > 0 ? result.exitCode : 1);
  else
    renderLocalExecutionFailure(
      result,
      t('commands.machine.converge.failed', { machine: machineName })
    );
  return false;
}

async function runConverge(machineName: string, options: ConvergeCommandOptions): Promise<void> {
  await assertMachineExists(machineName);
  const format: OutputFormat = options.json ? 'json' : getOutputFormat();
  const table = format === 'table';
  if (table) outputService.info(t(startingKey(options.dryRun), { machine: machineName }));

  const result = await getExecutor().execute({
    functionName: CONVERGE_FUNCTION,
    machineName,
    params: buildConvergeParams(options),
    debug: options.debug,
    captureOutput: true,
  });

  if (settleConverge(machineName, result, format) && table) {
    outputService.success(t('commands.machine.converge.completed', { machine: machineName }));
  }
}

export function registerConvergeCommand(machine: Command): void {
  machine
    .command('converge')
    .argument('<name>', t('options.name'))
    .summary(t('commands.machine.converge.descriptionShort'))
    .description(t('commands.machine.converge.description'))
    .option('--dry-run', t('commands.machine.converge.dryRunOption'))
    .option('--json', t('commands.machine.converge.jsonOption'))
    .option('--include-unknown', t('commands.machine.converge.includeUnknownOption'))
    .addOption(
      new Option('--policy <policy>', t('commands.machine.converge.policyOption'))
        .choices([...RUNTIME_POLICIES])
        .default('epoch')
    )
    .option('--continue-on-error', t('commands.machine.converge.continueOnErrorOption'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: ConvergeCommandOptions) => {
      try {
        await runConverge(name, options);
      } catch (error) {
        handleError(error);
      }
    });
}

/**
 * The converge pass of `machine setup` (D5): after setup, a stale repo daemon
 * is moved onto the current layout, then the router refresh the renet upload
 * owed runs. Unlike the executor's pass this one does not wait for an upload in
 * this run: setup is the explicit place to repair a machine an earlier upload
 * left stale. A failure is a warning naming the resume command; setup itself
 * already succeeded.
 */
export async function convergeAfterSetup(
  machineName: string,
  session: {
    sftp: Pick<SFTPClient, 'exec'>;
    remoteRenetPath: string;
    datastore?: string;
    routerRefreshDue: boolean;
  },
  options: { converge?: boolean; debug?: boolean }
): Promise<void> {
  let report: ConvergeReport | null = null;
  if (options.converge !== false && !isRuntimeConvergeOptedOut()) {
    report = await runSetupPass(machineName, session, options.debug);
  }
  // A pass that moved a repo already refreshed the router (the executor does it after converge).
  const executorRefreshed = report !== null && countConvergeResults(report).converged > 0;
  const refresh = routerRefreshAfterPass({ due: session.routerRefreshDue, summary: null });
  if (refresh && !executorRefreshed) {
    if (await renetProvisioner.refreshRouter(session.sftp, session.remoteRenetPath)) {
      outputService.info(t('commands.machine.converge.routerRefreshed', { machine: machineName }));
    }
  }
}

/** The count of repos still on an older runtime layout, or null (after a warning) when the status cannot be read. */
async function readStaleCount(
  machineName: string,
  session: { sftp: Pick<SFTPClient, 'exec'>; remoteRenetPath: string; datastore?: string }
): Promise<number | null> {
  try {
    const status = await readRuntimeStatus(
      session.sftp,
      session.remoteRenetPath,
      session.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH
    );
    return status.stale;
  } catch (error) {
    outputService.warn(
      t('commands.machine.converge.statusUnreadable', {
        machine: machineName,
        error: error instanceof Error ? error.message : String(error),
      })
    );
    return null;
  }
}

async function runSetupPass(
  machineName: string,
  session: { sftp: Pick<SFTPClient, 'exec'>; remoteRenetPath: string; datastore?: string },
  debug: boolean | undefined
): Promise<ConvergeReport | null> {
  const stale = await readStaleCount(machineName, session);
  if (stale === null || stale === 0) return null;

  outputService.info(t('commands.machine.converge.setupStarting', { machine: machineName, stale }));
  const warnFailed = (error: string) =>
    outputService.warn(
      t('commands.machine.converge.autoFailed', {
        machine: machineName,
        error,
        command: convergeResumeCommand(machineName),
      })
    );
  let result: Awaited<ReturnType<ReturnType<typeof getExecutor>['execute']>>;
  try {
    result = await getExecutor().execute({
      functionName: CONVERGE_FUNCTION,
      machineName,
      params: {},
      debug,
      captureOutput: true,
      quietSpinners: true,
    });
  } catch (error) {
    // Setup already succeeded: a thrown pass still gets the resume command and the router refresh.
    warnFailed(error instanceof Error ? error.message : String(error));
    return null;
  }
  const report = parseConvergeReport(result.stdout);
  if (report) renderConvergeReport(report, machineName);
  else if (!result.success) warnFailed(result.error ?? '');
  return report;
}

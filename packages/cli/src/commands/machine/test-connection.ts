import { Command } from 'commander';
import {
  parseCreateQueueItem,
  parseGetQueueItemTrace,
  parseGetTeamMachines,
} from '@rediacc/shared/api';
import { isValidHost, isValidPort } from '@rediacc/shared/queue-vault';
import type { MachineWithVaultStatus } from '@rediacc/shared/services/machine';
import { parseSshTestResult, unescapeLogOutput } from '@rediacc/shared/utils';
import { t } from '../../i18n/index.js';
import { typedApi } from '../../services/api.js';
import { authService } from '../../services/auth.js';
import { contextService } from '../../services/context.js';
import { outputService } from '../../services/output.js';
import { queueService } from '../../services/queue.js';
import { addCloudOnlyGuard, markCloudOnly } from '../../utils/cloud-guard.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { askPassword } from '../../utils/prompt.js';
import { startSpinner, stopSpinner, withSpinner } from '../../utils/spinner.js';
import type { OutputFormat } from '../../types/index.js';

interface TestConnectionOptions {
  ip: string;
  user: string;
  team?: string;
  bridge?: string;
  port: string;
  password?: string;
  datastore: string;
  machine?: string;
  save?: boolean;
}

type SshTestResult = ReturnType<typeof parseSshTestResult>;

function validateConnectionOptions(options: TestConnectionOptions): void {
  if (!isValidHost(options.ip)) {
    throw new ValidationError(t('errors.invalidHost', { host: options.ip }));
  }
  if (!isValidPort(options.port)) {
    throw new ValidationError(t('errors.invalidPort', { port: options.port }));
  }
}

function buildMachineContext(options: TestConnectionOptions, sshPassword: string) {
  return {
    ip: options.ip,
    user: options.user,
    port: Number.parseInt(options.port, 10),
    datastore: options.datastore,
    ssh_password: sshPassword || undefined,
  };
}

interface TraceData {
  summary?: {
    status?: string | null;
    consoleOutput?: string | null;
    errorMessage?: string | null;
    lastFailureReason?: string | null;
  } | null;
  queueDetails?: { status?: string | null } | null;
  responseVaultContent?: { vaultContent?: string | null } | null;
}

function processTraceForResult(trace: TraceData): SshTestResult {
  const consoleOutput = trace.summary?.consoleOutput
    ? unescapeLogOutput(trace.summary.consoleOutput)
    : null;
  const responseVaultContent = trace.responseVaultContent?.vaultContent ?? null;

  const result = parseSshTestResult({ responseVaultContent, consoleOutput });

  if (!result && consoleOutput) {
    outputService.info(t('commands.machine.testConnection.rawOutput'));
    outputService.info(consoleOutput);
  }

  return result;
}

function displayTraceError(trace: TraceData): void {
  const errorMsg = trace.summary?.errorMessage ?? trace.summary?.lastFailureReason;
  if (errorMsg) {
    outputService.error(t('commands.machine.testConnection.error', { error: errorMsg }));
  }
}

const TERMINAL_STATUSES = ['COMPLETED', 'FAILED', 'CANCELLED'] as const;

function isTerminalStatus(status: string | null | undefined): status is string {
  return status != null && (TERMINAL_STATUSES as readonly string[]).includes(status.toUpperCase());
}

function handleTerminalStatusResult(trace: TraceData, status: string): SshTestResult {
  const success = status.toUpperCase() === 'COMPLETED';
  stopSpinner(
    success,
    t('commands.machine.testConnection.testResult', {
      result: success ? t('common.completed') : t('common.failed'),
    })
  );

  const result = processTraceForResult(trace);
  if (!success) {
    displayTraceError(trace);
  }
  return result;
}

function handlePollTimeout(taskId: string): null {
  stopSpinner(false, t('commands.machine.testConnection.timeout'));
  outputService.error(t('commands.machine.testConnection.timeoutMessage'));
  outputService.info(t('commands.machine.testConnection.taskId', { taskId }));
  return null;
}

async function pollForCompletion(taskId: string): Promise<SshTestResult> {
  const pollInterval = 2000;
  const maxAttempts = 60;
  const spinner = startSpinner(t('commands.machine.testConnection.waiting'));

  for (let attempts = 1; attempts <= maxAttempts; attempts++) {
    await new Promise((resolve) => setTimeout(resolve, pollInterval));

    const traceResponse = await typedApi.GetQueueItemTrace({ taskId });
    const trace = parseGetQueueItemTrace(traceResponse as never);
    const status = trace.summary?.status ?? trace.queueDetails?.status;

    if (isTerminalStatus(status)) {
      return handleTerminalStatusResult(trace, status);
    }

    if (spinner) {
      spinner.text = t('commands.machine.testConnection.waitingTime', { seconds: attempts * 2 });
    }
  }

  return handlePollTimeout(taskId);
}

function displayResultField(
  value: unknown,
  translationKey: string,
  formatValue?: (val: unknown) => unknown
): void {
  if (value === undefined) return;
  const displayValue = formatValue ? formatValue(value) : value;
  outputService.info(t(translationKey, displayValue as Record<string, unknown>));
}

function displayResultDetails(result: NonNullable<SshTestResult>): void {
  outputService.info('');
  outputService.info(t('commands.machine.testConnection.results'));
  outputService.info(
    t('commands.machine.testConnection.statusResult', {
      status: result.status === 'success' ? t('common.success') : t('common.failed'),
    })
  );

  if (result.auth_method) {
    outputService.info(
      t('commands.machine.testConnection.authMethod', { method: result.auth_method })
    );
  }

  displayResultField(
    result.ssh_key_configured,
    'commands.machine.testConnection.sshKeyConfigured',
    (v) => ({ status: v ? t('common.yes') : t('common.no') })
  );

  displayResultField(
    result.public_key_deployed,
    'commands.machine.testConnection.publicKeyDeployed',
    (v) => ({ status: v ? t('common.yes') : t('common.no') })
  );

  if (result.known_hosts) {
    const truncated =
      result.known_hosts.length > 80
        ? `${result.known_hosts.substring(0, 80)}...`
        : result.known_hosts;
    outputService.info(t('commands.machine.testConnection.knownHosts', { entry: truncated }));
  }

  if (result.message && result.status !== 'success') {
    outputService.error(t('commands.machine.testConnection.message', { message: result.message }));
  }
}

function parseVaultContent(vaultContent: string | undefined): Record<string, unknown> {
  if (!vaultContent) return {};
  try {
    return JSON.parse(vaultContent);
  } catch {
    return {};
  }
}

async function saveKnownHostsToVault(
  options: TestConnectionOptions,
  teamName: string,
  knownHosts: string
): Promise<void> {
  const saveMachineName = options.machine!;
  outputService.info('');

  await withSpinner(
    t('commands.machine.testConnection.saving', { machine: saveMachineName }),
    async () => {
      const machinesResponse = await typedApi.GetTeamMachines({ teamName });
      const machines = parseGetTeamMachines(machinesResponse as never);
      const targetMachine = machines.find(
        (m: MachineWithVaultStatus) => m.machineName === saveMachineName
      );

      if (!targetMachine) {
        throw new ValidationError(t('errors.machineNotFound', { name: saveMachineName }));
      }

      const vaultData = parseVaultContent(targetMachine.vaultContent ?? undefined);
      vaultData.known_hosts = knownHosts;
      vaultData.ip = options.ip;
      vaultData.user = options.user;
      vaultData.datastore = options.datastore;
      delete vaultData.ssh_password;

      await typedApi.UpdateMachineVault({
        teamName,
        machineName: saveMachineName,
        vaultContent: JSON.stringify(vaultData),
        vaultVersion: (targetMachine.vaultVersion ?? 0) + 1,
      });
    },
    t('commands.machine.testConnection.saved')
  );
}

function shouldSaveKnownHosts(
  options: TestConnectionOptions,
  result: SshTestResult
): result is NonNullable<SshTestResult> & { known_hosts: string } {
  return !!(options.save && options.machine && result?.known_hosts && result.status === 'success');
}

export function registerTestConnectionCommand(machine: Command, program: Command): void {
  const testConnectionCmd = machine
    .command('test-connection')
    .description(t('commands.machine.testConnection.description'));

  addCloudOnlyGuard(testConnectionCmd);
  markCloudOnly(testConnectionCmd);

  testConnectionCmd
    .requiredOption('--ip <address>', t('options.machineIp'))
    .requiredOption('--user <name>', t('options.sshUser'))
    .option('-t, --team <name>', t('options.team'))
    .option('-b, --bridge <name>', t('options.bridge'))
    .option('--port <number>', t('options.sshPort'), '22')
    .option('--password <pwd>', t('options.sshPassword'))
    .option('--datastore <path>', t('options.datastore'), '/mnt/rediacc')
    .option('-m, --machine <name>', t('options.machineForVault'))
    .option('--save', t('options.saveKnownHosts'))
    .action(async (options: TestConnectionOptions) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }
        if (!opts.bridge) {
          throw new ValidationError(t('errors.bridgeRequired'));
        }

        validateConnectionOptions(options);

        const sshPassword = options.password ?? (await askPassword(t('prompts.sshPassword')));

        outputService.info(
          t('commands.machine.testConnection.testing', {
            user: options.user,
            ip: options.ip,
            port: options.port,
          })
        );

        const machineContext = buildMachineContext(options, sshPassword);
        const teamName = opts.team;
        const bridgeName = opts.bridge;
        const machineName = options.machine ?? '';

        const queueVault = await queueService.buildQueueVault({
          teamName,
          machineName,
          bridgeName,
          functionName: 'machine_ssh_test',
          params: {},
          priority: 1,
          machineContext,
        });

        const createResponse = await withSpinner(
          t('commands.machine.testConnection.creating'),
          () =>
            typedApi.CreateQueueItem({
              teamName,
              machineName,
              bridgeName,
              vaultContent: queueVault,
              priority: 1,
            }),
          t('commands.machine.testConnection.created')
        );

        const { taskId } = parseCreateQueueItem(createResponse as never);
        if (!taskId) {
          throw new ValidationError(t('errors.failedCreateQueueItem'));
        }

        outputService.info(t('commands.machine.testConnection.taskId', { taskId }));

        const result = await pollForCompletion(taskId);
        if (!result) return;

        const format = program.opts().output as OutputFormat;

        if (format === 'json') {
          outputService.print(result, format);
        } else {
          displayResultDetails(result);
        }

        if (shouldSaveKnownHosts(options, result)) {
          await saveKnownHostsToVault(options, teamName, result.known_hosts);
        }
      } catch (error) {
        handleError(error);
      }
    });
}

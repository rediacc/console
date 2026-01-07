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
import { handleError, ValidationError } from '../../utils/errors.js';
import { askPassword } from '../../utils/prompt.js';
import { startSpinner, stopSpinner, withSpinner } from '../../utils/spinner.js';
import type { OutputFormat } from '../../types/index.js';

export function registerTestConnectionCommand(machine: Command, program: Command): void {
  machine
    .command('test-connection')
    .description(t('commands.machine.testConnection.description'))
    .requiredOption('--ip <address>', t('options.machineIp'))
    .requiredOption('--user <name>', t('options.sshUser'))
    .option('-t, --team <name>', t('options.team'))
    .option('-b, --bridge <name>', t('options.bridge'))
    .option('--port <number>', t('options.sshPort'), '22')
    .option('--password <pwd>', t('options.sshPassword'))
    .option('--datastore <path>', t('options.datastore'), '/mnt/rediacc')
    .option('-m, --machine <name>', t('options.machineForVault'))
    .option('--save', t('options.saveKnownHosts'))
    .action(
      async (options: {
        ip: string;
        user: string;
        team?: string;
        bridge?: string;
        port: string;
        password?: string;
        datastore: string;
        machine?: string;
        save?: boolean;
      }) => {
        try {
          await authService.requireAuth();
          const opts = await contextService.applyDefaults(options);

          if (!opts.team) {
            throw new ValidationError(t('errors.teamRequired'));
          }
          if (!opts.bridge) {
            throw new ValidationError(t('errors.bridgeRequired'));
          }

          // Validate IP address or hostname
          if (!isValidHost(options.ip)) {
            throw new ValidationError(t('errors.invalidHost', { host: options.ip }));
          }

          // Validate port number
          if (!isValidPort(options.port)) {
            throw new ValidationError(t('errors.invalidPort', { port: options.port }));
          }

          // Get password - from flag or prompt interactively
          // Only prompt if --password flag was not provided at all (undefined)
          const sshPassword = options.password ?? (await askPassword(t('prompts.sshPassword')));

          outputService.info(
            t('commands.machine.testConnection.testing', {
              user: options.user,
              ip: options.ip,
              port: options.port,
            })
          );

          // Build machine context for ssh_test
          const machineContext = {
            ip: options.ip,
            user: options.user,
            port: parseInt(options.port, 10),
            datastore: options.datastore,
            ssh_password: sshPassword || undefined,
          };

          // Validated values (safe to use without type assertions)
          const teamName = opts.team;
          const bridgeName = opts.bridge;
          const machineName = options.machine ?? '';

          // Build queue vault for ssh_test
          const queueVault = await queueService.buildQueueVault({
            teamName,
            machineName,
            bridgeName,
            functionName: 'machine_ssh_test',
            params: {},
            priority: 1,
            machineContext,
          });

          // Create queue item
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

          // Poll for completion
          const pollInterval = 2000;
          const maxAttempts = 60; // 2 minutes max
          let attempts = 0;
          let isComplete = false;
          let result: ReturnType<typeof parseSshTestResult> = null;

          const spinner = startSpinner(t('commands.machine.testConnection.waiting'));

          while (!isComplete && attempts < maxAttempts) {
            attempts++;
            await new Promise((resolve) => setTimeout(resolve, pollInterval));

            const traceResponse = await typedApi.GetQueueItemTrace({ taskId });
            const trace = parseGetQueueItemTrace(traceResponse as never);

            const status = trace.summary?.status ?? trace.queueDetails?.status;
            const terminalStatuses = ['COMPLETED', 'FAILED', 'CANCELLED'];

            if (status && terminalStatuses.includes(status.toUpperCase())) {
              isComplete = true;
              const success = status.toUpperCase() === 'COMPLETED';
              stopSpinner(
                success,
                t('commands.machine.testConnection.testResult', {
                  result: success ? t('common.completed') : t('common.failed'),
                })
              );

              // Try to parse result from response vault or console output
              const consoleOutput = trace.summary?.consoleOutput
                ? unescapeLogOutput(trace.summary.consoleOutput)
                : null;
              const responseVaultContent = trace.responseVaultContent?.vaultContent ?? null;

              result = parseSshTestResult({
                responseVaultContent,
                consoleOutput,
              });

              if (!result && consoleOutput) {
                outputService.info(t('commands.machine.testConnection.rawOutput'));
                outputService.info(consoleOutput);
              }

              if (!success) {
                const errorMsg = trace.summary?.errorMessage ?? trace.summary?.lastFailureReason;
                if (errorMsg) {
                  outputService.error(
                    t('commands.machine.testConnection.error', { error: errorMsg })
                  );
                }
              }
            } else if (spinner) {
              spinner.text = t('commands.machine.testConnection.waitingTime', {
                seconds: attempts * 2,
              });
            }
          }

          if (!isComplete) {
            stopSpinner(false, t('commands.machine.testConnection.timeout'));
            outputService.error(t('commands.machine.testConnection.timeoutMessage'));
            outputService.info(t('commands.machine.testConnection.taskId', { taskId }));
            return;
          }

          const format = program.opts().output as OutputFormat;

          // Display result
          if (result) {
            if (format === 'json') {
              outputService.print(result, format);
            } else {
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
              if (result.ssh_key_configured !== undefined) {
                outputService.info(
                  t('commands.machine.testConnection.sshKeyConfigured', {
                    status: result.ssh_key_configured ? t('common.yes') : t('common.no'),
                  })
                );
              }
              if (result.public_key_deployed !== undefined) {
                outputService.info(
                  t('commands.machine.testConnection.publicKeyDeployed', {
                    status: result.public_key_deployed ? t('common.yes') : t('common.no'),
                  })
                );
              }
              if (result.known_hosts) {
                const knownHosts = result.known_hosts;
                const truncated =
                  knownHosts.length > 80 ? `${knownHosts.substring(0, 80)}...` : knownHosts;
                outputService.info(
                  t('commands.machine.testConnection.knownHosts', { entry: truncated })
                );
              }
              if (result.message && result.status !== 'success') {
                outputService.error(
                  t('commands.machine.testConnection.message', { message: result.message })
                );
              }
            }

            // Save known_hosts to machine vault if requested
            if (
              options.save &&
              options.machine &&
              result.known_hosts &&
              result.status === 'success'
            ) {
              const saveMachineName = options.machine;
              const knownHosts = result.known_hosts;
              outputService.info('');
              await withSpinner(
                t('commands.machine.testConnection.saving', { machine: saveMachineName }),
                async () => {
                  // First get current vault
                  const machinesResponse = await typedApi.GetTeamMachines({
                    teamName,
                  });
                  const machines = parseGetTeamMachines(machinesResponse as never);
                  const targetMachine = machines.find(
                    (m: MachineWithVaultStatus) => m.machineName === saveMachineName
                  );

                  if (!targetMachine) {
                    throw new ValidationError(
                      t('errors.machineNotFound', { name: saveMachineName })
                    );
                  }

                  // Parse existing vault and add known_hosts
                  let vaultData: Record<string, unknown> = {};
                  if (targetMachine.vaultContent) {
                    try {
                      vaultData = JSON.parse(targetMachine.vaultContent);
                    } catch {
                      // If vault is not JSON, start fresh
                    }
                  }

                  vaultData.known_hosts = knownHosts;
                  vaultData.ip = options.ip;
                  vaultData.user = options.user;
                  vaultData.datastore = options.datastore;
                  // Clear password - it was only for initial connection
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
          }
        } catch (error) {
          handleError(error);
        }
      }
    );
}

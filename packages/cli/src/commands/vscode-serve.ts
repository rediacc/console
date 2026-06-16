/**
 * `rdc vscode serve status|stop` — lifecycle for the in-sandbox browser
 * VS Code server started by `rdc vscode connect --browser`.
 */

import { getServerProvider } from '@rediacc/shared-desktop/vscode-server';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import { deployRepoKeyIfNeeded } from '../services/repo-key-deployment.js';
import { getSSHConnectionDetails } from '../services/ssh-connection.js';
import { serverStatus, stopServer } from '../services/vscode-server-remote.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError } from '../utils/errors.js';

interface VSCodeServeOptions {
  team?: string;
  machine?: string;
  repository?: string;
  serverProvider?: string;
}

async function resolveServeContext(options: VSCodeServeOptions) {
  const opts = await configService.applyDefaults(options);
  if (!opts.machine) throw new Error(t('errors.machineRequired'));
  if (!opts.repository) throw new Error(t('errors.vscode.browserNeedsRepo'));
  await assertCommandPolicy(CMD.VSCODE_REPO, opts.repository);

  const provider = getServerProvider(options.serverProvider);
  const connectionDetails = await getSSHConnectionDetails(
    opts.team ?? '',
    opts.machine,
    opts.repository
  );
  await deployRepoKeyIfNeeded(opts.repository, opts.machine);
  return { provider, connectionDetails };
}

export function registerVSCodeServeCommands(vscode: Command): void {
  const serve = vscode.command('serve').description(t('commands.vscode.serve.description'));

  serve
    .command('status')
    .description(t('commands.vscode.serve.status.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('-r, --repository <name>', t('options.repository'))
    .option('--server-provider <id>', t('options.vscodeServerProvider'))
    .action(async (options: VSCodeServeOptions) => {
      try {
        const { provider, connectionDetails } = await resolveServeContext(options);
        const status = await serverStatus(provider, connectionDetails);
        if (status.running) {
          outputService.print(
            t('commands.vscode.serve.status.running', {
              provider: provider.id,
              port: String(status.remotePort),
              pid: String(status.pid),
            })
          );
        } else {
          outputService.print(t('commands.vscode.serve.status.stopped', { provider: provider.id }));
        }
      } catch (error) {
        handleError(error);
      }
    });

  serve
    .command('stop')
    .description(t('commands.vscode.serve.stop.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('-r, --repository <name>', t('options.repository'))
    .option('--server-provider <id>', t('options.vscodeServerProvider'))
    .action(async (options: VSCodeServeOptions) => {
      try {
        const { provider, connectionDetails } = await resolveServeContext(options);
        const stopped = await stopServer(provider, connectionDetails);
        outputService.print(
          stopped
            ? t('commands.vscode.serve.stop.stopped', { provider: provider.id })
            : t('commands.vscode.serve.stop.notRunning', { provider: provider.id })
        );
      } catch (error) {
        handleError(error);
      }
    });
}

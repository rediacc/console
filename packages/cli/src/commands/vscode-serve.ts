/**
 * `rdc vscode serve status|stop <target>` — lifecycle for the in-sandbox browser
 * VS Code server started by `rdc vscode connect --browser <target>` (spec/03
 * §5.9). The target grammar is `term connect`'s, but only the repo form can
 * carry a server: the browser server runs INSIDE a repo sandbox, so a place
 * (machine or cluster) target is refused, and so is a cluster-placed repo (the
 * browser flow has no kubernetes wiring in v1).
 */

import { type Command, Option } from 'commander';
import { t } from '../i18n/index.js';
import { getServerProvider } from '../remote/vscode-server/index.js';
import { outputService } from '../services/core/output.js';
import { serverStatus, stopServer } from '../services/core/vscode-server-remote.js';
import { getSSHConnectionDetails } from '../services/machine/ssh-connection.js';
import { deployRepoKeyIfNeeded } from '../services/repo/repo-key-deployment.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { resolveConnectTarget } from '../utils/repo-target.js';

interface VSCodeServeOptions {
  serverProvider?: string;
}

async function resolveServeContext(target: string, options: VSCodeServeOptions) {
  const resolved = await resolveConnectTarget(target, { readOnly: true });
  if (resolved.kind !== 'repo') {
    throw new ValidationError(t('errors.vscode.browserNeedsRepo'));
  }
  if (resolved.kubeCluster) {
    throw new ValidationError(
      t('errors.cluster.featureUnsupportedV1', {
        feature: 'vscode serve',
        hint: 'the browser VS Code server runs inside a docker repo sandbox',
      })
    );
  }

  // Same synthetic policy key as `vscode connect`'s repo form (see vscode.ts).
  await assertCommandPolicy(CMD.VSCODE_CONNECT, resolved.repoKey);

  const provider = getServerProvider(options.serverProvider);
  // Teams are retired vocabulary (`-t` is deleted in P4); the SSH-connection
  // layer still takes the segment, so the local adapter's empty team is passed.
  const connectionDetails = await getSSHConnectionDetails(
    '',
    resolved.machineName,
    resolved.repoKey
  );
  await deployRepoKeyIfNeeded(resolved.repoKey, resolved.machineName);
  return { provider, connectionDetails };
}

export function registerVSCodeServeCommands(vscode: Command): void {
  const serve = vscode.command('serve').description(t('commands.vscode.serve.description'));

  serve
    .command('status')
    .description(t('commands.vscode.serve.status.description'))
    .argument('<target>', t('options.repoRef'))
    .addOption(
      new Option('--server-provider <id>', t('options.vscodeServerProvider')).choices([
        'openvscode',
        'code-server',
      ])
    )
    .action(async (target: string, options: VSCodeServeOptions) => {
      try {
        const { provider, connectionDetails } = await resolveServeContext(target, options);
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
    .argument('<target>', t('options.repoRef'))
    .addOption(
      new Option('--server-provider <id>', t('options.vscodeServerProvider')).choices([
        'openvscode',
        'code-server',
      ])
    )
    .action(async (target: string, options: VSCodeServeOptions) => {
      try {
        const { provider, connectionDetails } = await resolveServeContext(target, options);
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

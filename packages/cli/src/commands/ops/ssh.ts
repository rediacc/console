import { spawn } from 'node:child_process';
import { Command } from 'commander';
import { DEFAULTS } from '@rediacc/shared/config';
import { t } from '../../i18n/index.js';
import { opsExecutorService } from '../../services/ops-executor.js';
import { outputService } from '../../services/output.js';
import { handleError } from '../../utils/errors.js';
import type { OpsBackend } from '../../services/ops-executor.js';

interface VMInfo {
  id: number;
  name: string;
  ip: string;
  status: string;
  sshPort?: number;
}

interface OpsStatusResponse {
  vms: VMInfo[];
}

export function registerOpsSSHCommand(ops: Command, _program: Command): void {
  ops
    .command('ssh <vmId> [command...]')
    .description(t('commands.ops.ssh.description'))
    .option('--backend <backend>', t('options.opsBackend'))
    .option('--user <user>', t('options.opsSSHUser'))
    .allowUnknownOption()
    .action(
      async (vmId: string, command: string[], options: { backend?: string; user?: string }) => {
        try {
          const backend = options.backend ? (options.backend as OpsBackend) : undefined;
          const response = await opsExecutorService.runOpsJSON<OpsStatusResponse>('status', [], {
            backend,
          });

          const targetId = Number.parseInt(vmId, 10);
          const vm = response.vms.find((v) => v.id === targetId);

          if (vm?.status !== 'running') {
            outputService.error(t('commands.ops.ssh.vmNotFound', { id: vmId }));
            process.exitCode = 1;
            return;
          }

          const user = options.user ?? process.env.USER ?? DEFAULTS.CLI_TEST.VM_USER;
          const sshArgs = [
            '-o',
            'StrictHostKeyChecking=no',
            '-o',
            'UserKnownHostsFile=/dev/null',
            '-o',
            'LogLevel=ERROR',
          ];

          // If VM has a forwarded SSH port (QEMU user-mode networking), use localhost with port
          if (vm.sshPort) {
            sshArgs.push('-p', String(vm.sshPort));
            sshArgs.push(`${user}@localhost`);
          } else {
            sshArgs.push(`${user}@${vm.ip}`);
          }

          // Append remote command if provided
          if (command.length > 0) {
            sshArgs.push('--', command.join(' '));
          }

          outputService.info(t('commands.ops.ssh.connecting', { id: vmId }));

          const child = spawn('ssh', sshArgs, { stdio: 'inherit' });
          child.on('close', (code) => {
            process.exitCode = code ?? 0;
          });
        } catch (error) {
          handleError(error);
        }
      }
    );
}

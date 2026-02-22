import { spawn } from 'node:child_process';
import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { opsExecutorService } from '../../services/ops-executor.js';
import { outputService } from '../../services/output.js';
import { handleError } from '../../utils/errors.js';

function spawnInteractive(command: string, args: string[]): Promise<number> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: 'inherit' });
    child.on('close', (code) => resolve(code ?? 1));
    child.on('error', reject);
  });
}

export function registerOpsSetupCommand(ops: Command, _program: Command): void {
  ops
    .command('setup')
    .description(t('commands.ops.setup.description'))
    .option('--debug', t('options.debug'))
    .action(async (options: { debug?: boolean }) => {
      try {
        if (process.platform === 'darwin') {
          outputService.info(t('commands.ops.setup.macos'));

          const exitCode = await spawnInteractive('brew', ['install', 'qemu', 'cdrtools']);
          if (exitCode !== 0) {
            outputService.error(t('commands.ops.setup.brewFailed'));
            process.exitCode = exitCode;
            return;
          }

          outputService.success(t('commands.ops.setup.completed'));
        } else if (process.platform === 'win32') {
          outputService.info(t('commands.ops.setup.windows'));

          const flags: string[] = [];
          if (options.debug) flags.push('--debug');

          // Delegate to renet ops host setup (no sudo on Windows — run elevated)
          const renetPath = await opsExecutorService.getRenetPath();
          const exitCode = await spawnInteractive(renetPath, [
            'ops',
            'host',
            'setup',
            ...flags,
          ]);

          if (exitCode !== 0) {
            outputService.error(t('commands.ops.setup.failed'));
            process.exitCode = exitCode;
            return;
          }

          outputService.success(t('commands.ops.setup.completed'));
        } else if (process.platform === 'linux') {
          outputService.info(t('commands.ops.setup.linux'));

          const flags: string[] = [];
          if (options.debug) flags.push('--debug');

          // Delegate to renet ops host setup (requires sudo)
          const renetPath = await opsExecutorService.getRenetPath();
          const exitCode = await spawnInteractive('sudo', [
            renetPath,
            'ops',
            'host',
            'setup',
            ...flags,
          ]);

          if (exitCode !== 0) {
            outputService.error(t('commands.ops.setup.failed'));
            process.exitCode = exitCode;
            return;
          }

          outputService.success(t('commands.ops.setup.completed'));
        } else {
          outputService.error(t('commands.ops.setup.unsupported', { platform: process.platform }));
          process.exitCode = 1;
        }
      } catch (error) {
        handleError(error);
      }
    });
}

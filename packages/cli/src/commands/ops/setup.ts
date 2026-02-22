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

async function setupDarwin(): Promise<number> {
  outputService.info(t('commands.ops.setup.macos'));
  const exitCode = await spawnInteractive('brew', ['install', 'qemu', 'cdrtools']);
  if (exitCode !== 0) {
    outputService.error(t('commands.ops.setup.brewFailed'));
    return exitCode;
  }
  outputService.success(t('commands.ops.setup.completed'));
  return 0;
}

async function setupRenet(options: { debug?: boolean }, useSudo: boolean): Promise<number> {
  const flags: string[] = [];
  if (options.debug) flags.push('--debug');

  const renetPath = await opsExecutorService.getRenetPath();
  const exitCode = useSudo
    ? await spawnInteractive('sudo', [renetPath, 'ops', 'host', 'setup', ...flags])
    : await spawnInteractive(renetPath, ['ops', 'host', 'setup', ...flags]);

  if (exitCode !== 0) {
    outputService.error(t('commands.ops.setup.failed'));
    return exitCode;
  }
  outputService.success(t('commands.ops.setup.completed'));
  return 0;
}

export function registerOpsSetupCommand(ops: Command, _program: Command): void {
  ops
    .command('setup')
    .description(t('commands.ops.setup.description'))
    .option('--debug', t('options.debug'))
    .action(async (options: { debug?: boolean }) => {
      try {
        if (process.platform === 'darwin') {
          process.exitCode = await setupDarwin();
        } else if (process.platform === 'win32') {
          outputService.info(t('commands.ops.setup.windows'));
          process.exitCode = await setupRenet(options, false);
        } else if (process.platform === 'linux') {
          outputService.info(t('commands.ops.setup.linux'));
          process.exitCode = await setupRenet(options, true);
        } else {
          outputService.error(t('commands.ops.setup.unsupported', { platform: process.platform }));
          process.exitCode = 1;
        }
      } catch (error) {
        handleError(error);
      }
    });
}

import { spawn } from 'node:child_process';
import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { outputService } from '../../services/core/output.js';
import { setExitCode, writeStderr } from '../../services/core/request-context.js';
import { opsExecutorService } from '../../services/executor/ops-executor.js';
import { handleError } from '../../utils/errors.js';

function spawnInteractive(
  command: string,
  args: string[],
  env?: Record<string, string>
): Promise<number> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      stdio: 'inherit',
      ...(env ? { env: { ...process.env, ...env } } : {}),
    });
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
  const renetPath = await opsExecutorService.getRenetPath();
  // renet has no --debug flag: rdc consumes it, echoes the argv and sets REDIACC_DEBUG=1 for the child.
  const args = ['ops', 'host', 'setup'];
  if (options.debug)
    writeStderr(`[DEBUG] ${useSudo ? 'sudo ' : ''}${renetPath} ${args.join(' ')}\n`);
  const debugEnv = options.debug ? { REDIACC_DEBUG: '1' } : undefined;
  // sudo resets the environment, so under sudo the variable rides as `env REDIACC_DEBUG=1 <renet>`.
  const exitCode = useSudo
    ? await spawnInteractive(
        'sudo',
        [...(debugEnv ? ['env', 'REDIACC_DEBUG=1'] : []), renetPath, ...args],
        debugEnv
      )
    : await spawnInteractive(renetPath, args, debugEnv);

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
    .summary(t('commands.ops.setup.descriptionShort'))
    .description(t('commands.ops.setup.description'))
    .option('--debug', t('options.debug'))
    .action(async (options: { debug?: boolean }) => {
      try {
        if (process.platform === 'darwin') {
          setExitCode(await setupDarwin());
        } else if (process.platform === 'win32') {
          outputService.info(t('commands.ops.setup.windows'));
          setExitCode(await setupRenet(options, false));
        } else if (process.platform === 'linux') {
          outputService.info(t('commands.ops.setup.linux'));
          setExitCode(await setupRenet(options, true));
        } else {
          outputService.error(t('commands.ops.setup.unsupported', { platform: process.platform }));
          setExitCode(1);
        }
      } catch (error) {
        handleError(error);
      }
    });
}

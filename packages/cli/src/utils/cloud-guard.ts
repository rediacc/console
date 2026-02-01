/**
 * Cloud-only command guard utility.
 * Blocks commands/subcommands from running in non-cloud (s3/local) modes
 * with a clear error message.
 */
import { DEFAULTS } from '@rediacc/shared/config';
import type { Command } from 'commander';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';

/**
 * Add a preAction hook that blocks the command in non-cloud modes.
 * Works for both top-level commands and subcommands.
 */
export function addCloudOnlyGuard(command: Command): void {
  command.hook('preAction', async () => {
    const context = await contextService.getCurrent();
    const mode = context?.mode ?? DEFAULTS.CONTEXT.MODE;
    if (mode !== 'cloud') {
      outputService.error(
        `"${command.name()}" is only available in cloud mode. Current mode: ${mode}`
      );
      process.exit(1);
    }
  });
}

/**
 * Append a `[cloud only]` indicator to a command's description.
 */
export function markCloudOnly(command: Command): void {
  const desc = command.description();
  if (desc && !desc.includes('[cloud only]')) {
    command.description(`${desc} [cloud only]`);
  }
}

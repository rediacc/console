import { Command } from 'commander';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { handleError } from '../utils/errors.js';
import type { OutputFormat } from '../types/index.js';

export function registerContextCommands(program: Command): void {
  const context = program.command('context').description('CLI context management');

  // context show
  context
    .command('show')
    .description('Show current context')
    .action(async () => {
      try {
        const ctx = await contextService.get();
        const format = program.opts().output as OutputFormat;

        if (Object.keys(ctx).length === 0) {
          outputService.info('No context set');
        } else {
          outputService.print(ctx, format);
        }
      } catch (error) {
        handleError(error);
      }
    });

  // context set
  context
    .command('set <key> <value>')
    .description('Set a context value (team, region)')
    .action(async (key, value) => {
      try {
        const validKeys = ['team', 'region'];
        if (!validKeys.includes(key)) {
          outputService.error(`Invalid context key. Valid keys: ${validKeys.join(', ')}`);
          process.exit(1);
        }

        await contextService.set(key as 'team' | 'region', value);
        outputService.success(`Context "${key}" set to "${value}"`);
      } catch (error) {
        handleError(error);
      }
    });

  // context clear
  context
    .command('clear [key]')
    .description('Clear context (all or specific key)')
    .action(async (key) => {
      try {
        if (key) {
          const validKeys = ['team', 'region'];
          if (!validKeys.includes(key)) {
            outputService.error(`Invalid context key. Valid keys: ${validKeys.join(', ')}`);
            process.exit(1);
          }
          await contextService.remove(key as 'team' | 'region');
          outputService.success(`Context "${key}" cleared`);
        } else {
          await contextService.clear();
          outputService.success('All context cleared');
        }
      } catch (error) {
        handleError(error);
      }
    });
}

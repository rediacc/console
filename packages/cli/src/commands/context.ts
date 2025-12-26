import { Command } from 'commander';
import { apiClient } from '../services/api.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { askText } from '../utils/prompt.js';
import type { NamedContext, OutputFormat } from '../types/index.js';

export function registerContextCommands(program: Command): void {
  const context = program
    .command('context')
    .description('Manage CLI contexts (multiple endpoints)');

  // context list - List all contexts
  context
    .command('list')
    .alias('ls')
    .description('List all contexts')
    .action(async () => {
      try {
        const contexts = await contextService.list();
        const currentName = await contextService.getCurrentName();
        const format = program.opts().output as OutputFormat;

        if (contexts.length === 0) {
          outputService.info('No contexts configured. Create one with: rdc context create <name>');
          return;
        }

        // Add 'current' indicator to the output
        const displayData = contexts.map((ctx) => ({
          current: ctx.name === currentName ? '*' : '',
          name: ctx.name,
          apiUrl: ctx.apiUrl,
          userEmail: ctx.userEmail ?? '-',
          team: ctx.team ?? '-',
          region: ctx.region ?? '-',
          bridge: ctx.bridge ?? '-',
          machine: ctx.machine ?? '-',
        }));

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // context use - Switch to a context
  context
    .command('use <name>')
    .description('Switch to a different context')
    .action(async (name) => {
      try {
        await contextService.use(name);
        // Reinitialize API client with new context
        await apiClient.reinitialize();
        outputService.success(`Switched to context "${name}"`);
      } catch (error) {
        handleError(error);
      }
    });

  // context create - Create a new context
  context
    .command('create <name>')
    .description('Create a new context')
    .option('-u, --api-url <url>', 'API endpoint URL')
    .option('-s, --switch', 'Switch to this context after creation')
    .action(async (name, options) => {
      try {
        // If no API URL provided, prompt for it, then normalize
        const rawUrl =
          options.apiUrl ?? (await askText('API URL:', { default: 'https://www.rediacc.com/api' }));
        const apiUrl = apiClient.normalizeApiUrl(rawUrl);

        const newContext: NamedContext = {
          name,
          apiUrl,
        };

        await contextService.create(newContext);
        outputService.success(`Context "${name}" created`);

        // Optionally switch to the new context
        if (options.switch) {
          await contextService.use(name);
          await apiClient.reinitialize();
          outputService.success(`Switched to context "${name}"`);
        }
      } catch (error) {
        handleError(error);
      }
    });

  // context delete - Delete a context
  context
    .command('delete <name>')
    .alias('rm')
    .description('Delete a context')
    .action(async (name) => {
      try {
        await contextService.delete(name);
        outputService.success(`Context "${name}" deleted`);
      } catch (error) {
        handleError(error);
      }
    });

  // context rename - Rename a context
  context
    .command('rename <oldName> <newName>')
    .description('Rename a context')
    .action(async (oldName, newName) => {
      try {
        await contextService.rename(oldName, newName);
        outputService.success(`Context renamed from "${oldName}" to "${newName}"`);
      } catch (error) {
        handleError(error);
      }
    });

  // context current - Show current context name (for scripting)
  context
    .command('current')
    .description('Print current context name')
    .action(async () => {
      try {
        const name = await contextService.getCurrentName();
        if (name) {
          // eslint-disable-next-line no-console -- Raw output for scripting
          console.log(name);
        } else {
          outputService.info('No context selected');
          process.exitCode = 1;
        }
      } catch (error) {
        handleError(error);
      }
    });

  // context show - Show current context details
  context
    .command('show')
    .description('Show current context details')
    .action(async () => {
      try {
        const ctx = await contextService.getCurrent();
        const format = program.opts().output as OutputFormat;

        if (!ctx) {
          outputService.info('No context selected. Create one with: rdc context create <name>');
          return;
        }

        // Don't show sensitive fields
        const display = {
          name: ctx.name,
          apiUrl: ctx.apiUrl,
          userEmail: ctx.userEmail ?? '-',
          team: ctx.team ?? '-',
          region: ctx.region ?? '-',
          bridge: ctx.bridge ?? '-',
          machine: ctx.machine ?? '-',
          authenticated: ctx.token ? 'yes' : 'no',
        };

        outputService.print(display, format);
      } catch (error) {
        handleError(error);
      }
    });

  // context set - Set a default value
  context
    .command('set <key> <value>')
    .description('Set a default value (team, region, bridge, machine)')
    .action(async (key, value) => {
      try {
        const validKeys = ['team', 'region', 'bridge', 'machine'];
        if (!validKeys.includes(key)) {
          throw new ValidationError(`Invalid key. Valid keys: ${validKeys.join(', ')}`);
        }

        await contextService.set(key as 'team' | 'region' | 'bridge' | 'machine', value);
        outputService.success(`Set "${key}" to "${value}"`);
      } catch (error) {
        handleError(error);
      }
    });

  // context clear - Clear defaults
  context
    .command('clear [key]')
    .description('Clear defaults (all or specific key)')
    .action(async (key) => {
      try {
        if (key) {
          const validKeys = ['team', 'region', 'bridge', 'machine'];
          if (!validKeys.includes(key)) {
            throw new ValidationError(`Invalid key. Valid keys: ${validKeys.join(', ')}`);
          }
          await contextService.remove(key as 'team' | 'region' | 'bridge' | 'machine');
          outputService.success(`Cleared "${key}"`);
        } else {
          await contextService.clearDefaults();
          outputService.success('Cleared all defaults');
        }
      } catch (error) {
        handleError(error);
      }
    });
}

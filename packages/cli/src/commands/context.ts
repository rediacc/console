import { Command } from 'commander';
import { DEFAULTS } from '@rediacc/shared/config';
import { registerInfraCommands } from './context-infra.js';
import { registerLocalDataCommands } from './context-local-data.js';
import { registerLocalCommands } from './context-local.js';
import { registerMigrationCommands } from './context-migration.js';
import { t } from '../i18n/index.js';
import { apiClient } from '../services/api.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { askText } from '../utils/prompt.js';
import type { NamedContext, OutputFormat } from '../types/index.js';

export function registerContextCommands(program: Command): void {
  const context = program.command('context').description(t('commands.context.description'));

  // context list - List all contexts
  context
    .command('list')
    .alias('ls')
    .description(t('commands.context.list.description'))
    .action(async () => {
      try {
        const contexts = await contextService.list();
        const format = program.opts().output as OutputFormat;

        if (contexts.length === 0) {
          outputService.info(t('commands.context.list.noContexts'));
          return;
        }

        const displayData = contexts.map((ctx) => {
          const isSelfHosted = (ctx.mode ?? 'cloud') !== 'cloud';
          const apiUrl = isSelfHosted
            ? (ctx.s3?.endpoint ?? '-')
            : ctx.apiUrl;

          return {
            name: ctx.name,
            mode: ctx.mode ?? DEFAULTS.CONTEXT.MODE,
            apiUrl,
            userEmail: ctx.userEmail ?? '-',
            team: ctx.team ?? '-',
            machines: isSelfHosted
              ? Object.keys(ctx.machines ?? {}).length.toString()
              : '-',
          };
        });

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // context create - Create a new context
  context
    .command('create <name>')
    .description(t('commands.context.create.description'))
    .option('-u, --api-url <url>', t('options.apiUrl'))
    .action(async (name, options) => {
      try {
        const rawUrl =
          options.apiUrl ??
          (await askText(t('prompts.apiUrl'), {
            default: 'https://www.rediacc.com/api',
          }));
        const apiUrl = apiClient.normalizeApiUrl(rawUrl);

        const newContext: NamedContext = {
          name,
          apiUrl,
        };

        await contextService.create(newContext);
        outputService.success(t('commands.context.create.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // context delete - Delete a context
  context
    .command('delete <name>')
    .alias('rm')
    .description(t('commands.context.delete.description'))
    .action(async (name) => {
      try {
        await contextService.delete(name);
        outputService.success(t('commands.context.delete.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // context rename - Rename a context
  context
    .command('rename <oldName> <newName>')
    .description(t('commands.context.rename.description'))
    .action(async (oldName, newName) => {
      try {
        await contextService.rename(oldName, newName);
        outputService.success(t('commands.context.rename.success', { oldName, newName }));
      } catch (error) {
        handleError(error);
      }
    });

  // context current - Show current context name (raw output for scripting)
  context
    .command('current')
    .description(t('commands.context.current.description'))
    .action(() => {
      try {
        const name = contextService.getCurrentName();
        process.stdout.write(`${name}\n`);
      } catch (error) {
        handleError(error);
      }
    });

  // context show - Show current context details
  context
    .command('show')
    .description(t('commands.context.show.description'))
    .action(async () => {
      try {
        const ctx = await contextService.getCurrent();
        const format = program.opts().output as OutputFormat;

        if (!ctx) {
          outputService.info(t('commands.context.show.noContext'));
          return;
        }

        let display: Record<string, unknown>;
        if ((ctx.mode ?? 'cloud') !== 'cloud') {
          // Self-hosted mode (local or S3)
          let machineCount = 0;
          let storageCount = 0;
          let repoCount = 0;
          try {
            const state = await contextService.getResourceState();
            machineCount = Object.keys(state.getMachines()).length;
            storageCount = Object.keys(state.getStorages()).length;
            repoCount = Object.keys(state.getRepositories()).length;
          } catch {
            // Fallback to context fields (may be 0 for encrypted/S3)
            machineCount = Object.keys(ctx.machines ?? {}).length;
            storageCount = Object.keys(ctx.storages ?? {}).length;
            repoCount = Object.keys(ctx.repositories ?? {}).length;
          }

          display = {
            name: ctx.name,
            mode: ctx.mode,
            ...(ctx.s3 ? {
              endpoint: ctx.s3.endpoint,
              bucket: ctx.s3.bucket,
              s3Region: ctx.s3.region,
              prefix: ctx.s3.prefix ?? '-',
            } : {}),
            encrypted: ctx.encrypted ? 'yes' : 'no',
            sshKey: ctx.ssh?.privateKeyPath ?? '-',
            renetPath: ctx.renetPath ?? DEFAULTS.CONTEXT.RENET_PATH,
            machines: machineCount,
            storages: storageCount,
            repositories: repoCount,
            defaultMachine: ctx.machine ?? '-',
          };
        } else {
          display = {
            name: ctx.name,
            mode: DEFAULTS.CONTEXT.MODE,
            apiUrl: ctx.apiUrl,
            userEmail: ctx.userEmail ?? '-',
            team: ctx.team ?? '-',
            region: ctx.region ?? '-',
            bridge: ctx.bridge ?? '-',
            machine: ctx.machine ?? '-',
            authenticated: ctx.token ? 'yes' : 'no',
          };
        }

        outputService.print(display, format);
      } catch (error) {
        handleError(error);
      }
    });

  // context set - Set a default value
  context
    .command('set <key> <value>')
    .description(t('commands.context.set.description'))
    .action(async (key, value) => {
      try {
        const validKeys = ['team', 'region', 'bridge', 'machine'];
        if (!validKeys.includes(key)) {
          throw new ValidationError(t('errors.invalidKey', { keys: validKeys.join(', ') }));
        }

        await contextService.set(key as 'team' | 'region' | 'bridge' | 'machine', value);
        outputService.success(t('commands.context.set.success', { key, value }));
      } catch (error) {
        handleError(error);
      }
    });

  // context clear - Clear defaults
  context
    .command('clear [key]')
    .description(t('commands.context.clear.description'))
    .action(async (key) => {
      try {
        if (key) {
          const validKeys = ['team', 'region', 'bridge', 'machine'];
          if (!validKeys.includes(key)) {
            throw new ValidationError(t('errors.invalidKey', { keys: validKeys.join(', ') }));
          }
          await contextService.remove(key as 'team' | 'region' | 'bridge' | 'machine');
          outputService.success(t('commands.context.clear.keyCleared', { key }));
        } else {
          await contextService.clearDefaults();
          outputService.success(t('commands.context.clear.allCleared'));
        }
      } catch (error) {
        handleError(error);
      }
    });

  // Local mode commands (create-local, create-s3, machines, ssh, renet)
  registerLocalCommands(context, program);

  // Local data commands (storage, repository)
  registerLocalDataCommands(context, program);

  // Migration commands (to-s3, to-local)
  registerMigrationCommands(context);

  // Infrastructure commands (set-infra, show-infra, push-infra)
  registerInfraCommands(context, program);
}

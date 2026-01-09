import * as fs from 'fs/promises';
import * as os from 'os';
import * as path from 'path';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { apiClient } from '../services/api.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { askText } from '../utils/prompt.js';
import type { NamedContext, OutputFormat, LocalMachineConfig } from '../types/index.js';

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

        const displayData = contexts.map((ctx) => ({
          name: ctx.name,
          mode: ctx.mode ?? 'cloud',
          apiUrl: ctx.mode === 'local' ? '-' : ctx.apiUrl,
          userEmail: ctx.userEmail ?? '-',
          team: ctx.team ?? '-',
          machines: ctx.mode === 'local' ? Object.keys(ctx.machines ?? {}).length.toString() : '-',
        }));

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
        // If no API URL provided, prompt for it, then normalize
        const rawUrl =
          options.apiUrl ??
          (await askText(t('prompts.apiUrl'), { default: 'https://www.rediacc.com/api' }));
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

  // context current - Show current context name (for scripting)
  // Returns the context that would be used: from --context flag or "default"
  context
    .command('current')
    .description(t('commands.context.current.description'))
    .action(() => {
      try {
        const name = contextService.getCurrentName();
        // eslint-disable-next-line no-console -- Raw output for scripting
        console.log(name);
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

        // Don't show sensitive fields
        const isLocal = ctx.mode === 'local';
        const display = isLocal
          ? {
              name: ctx.name,
              mode: 'local',
              sshKey: ctx.ssh?.privateKeyPath ?? '-',
              renetPath: ctx.renetPath ?? 'renet (in PATH)',
              machines: Object.keys(ctx.machines ?? {}).length,
              defaultMachine: ctx.machine ?? '-',
            }
          : {
              name: ctx.name,
              mode: 'cloud',
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

  // ============================================================================
  // Local Mode Commands
  // ============================================================================

  // context create-local - Create a new local context
  context
    .command('create-local <name>')
    .description(t('commands.context.createLocal.description'))
    .requiredOption('--ssh-key <path>', t('options.sshKey'))
    .option('--renet-path <path>', t('options.renetPath'))
    .action(async (name, options) => {
      try {
        // Expand ~ in path
        const sshKeyPath = options.sshKey.startsWith('~')
          ? path.join(os.homedir(), options.sshKey.slice(1))
          : options.sshKey;

        // Verify SSH key exists
        try {
          await fs.access(sshKeyPath);
        } catch {
          throw new ValidationError(t('errors.sshKeyNotFound', { path: sshKeyPath }));
        }

        await contextService.createLocal(name, options.sshKey, {
          renetPath: options.renetPath,
        });
        outputService.success(t('commands.context.createLocal.success', { name }));
        outputService.info(t('commands.context.createLocal.nextStep'));
      } catch (error) {
        handleError(error);
      }
    });

  // context add-machine - Add a machine to local context
  context
    .command('add-machine <name>')
    .description(t('commands.context.addMachine.description'))
    .requiredOption('--ip <address>', t('options.machineIp'))
    .requiredOption('--user <username>', t('options.sshUser'))
    .option('--port <port>', t('options.sshPort'), '22')
    .option('--datastore <path>', t('options.datastore'), '/mnt/rediacc')
    .action(async (name, options) => {
      try {
        const config: LocalMachineConfig = {
          ip: options.ip,
          user: options.user,
          port: parseInt(options.port, 10),
          datastore: options.datastore,
        };

        await contextService.addLocalMachine(name, config);
        outputService.success(
          t('commands.context.addMachine.success', { name, user: config.user, ip: config.ip })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // context remove-machine - Remove a machine from local context
  context
    .command('remove-machine <name>')
    .description(t('commands.context.removeMachine.description'))
    .action(async (name) => {
      try {
        await contextService.removeLocalMachine(name);
        outputService.success(t('commands.context.removeMachine.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // context machines - List machines in local context
  context
    .command('machines')
    .description(t('commands.context.machines.description'))
    .action(async () => {
      try {
        const machines = await contextService.listLocalMachines();
        const format = program.opts().output as OutputFormat;

        if (machines.length === 0) {
          outputService.info(t('commands.context.machines.noMachines'));
          return;
        }

        const displayData = machines.map((m) => ({
          name: m.name,
          ip: m.config.ip,
          user: m.config.user,
          port: m.config.port ?? 22,
          datastore: m.config.datastore ?? '/mnt/rediacc',
        }));

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // context set-ssh - Update SSH configuration
  context
    .command('set-ssh')
    .description(t('commands.context.setSsh.description'))
    .requiredOption('--private-key <path>', t('options.sshPrivateKey'))
    .option('--public-key <path>', t('options.sshPublicKey'))
    .action(async (options) => {
      try {
        await contextService.setLocalSSH({
          privateKeyPath: options.privateKey,
          publicKeyPath: options.publicKey,
        });
        outputService.success(t('commands.context.setSsh.success'));
      } catch (error) {
        handleError(error);
      }
    });

  // context set-renet - Set renet binary path
  context
    .command('set-renet <path>')
    .description(t('commands.context.setRenet.description'))
    .action(async (renetPath) => {
      try {
        await contextService.setRenetPath(renetPath);
        outputService.success(t('commands.context.setRenet.success', { path: renetPath }));
      } catch (error) {
        handleError(error);
      }
    });
}

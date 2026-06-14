import { readFileSync } from 'node:fs';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { assertCommandPolicy, CMD } from '../utils/command-policy.js';
import { getOutputFormat, handleError } from '../utils/errors.js';
import { createGuidResolver, loadGuidMap } from '../utils/guid-resolver.js';
import { renderLocalExecutionFailure } from '../utils/local-execution-failures.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { assertMachineExists } from './_validate.js';
import { parseDatastorePruneOutput } from './datastore-prune-parser.js';
import { handleForkAction } from './repo-fork.js';
import { registerRepoPolicyCommand } from './repo-policy.js';
import { registerRepoTakeoverCommand } from './repo-takeover.js';
import { registerRepoTrimCommand } from './repo-trim.js';

/** Execute a machine-level function (no repository context needed). */
async function executeMachineFunction(
  functionName: string,
  options: { machine: string; debug?: boolean; skipRouterRestart?: boolean },
  messages: { starting: string; completed: string; failed: string }
): Promise<void> {
  await assertMachineExists(options.machine);
  outputService.info(messages.starting);

  const result = await localExecutorService.execute({
    functionName,
    machineName: options.machine,
    params: {},
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
  });

  if (result.success) {
    outputService.success(messages.completed);
  } else {
    renderLocalExecutionFailure(result, result.error ?? messages.failed);
  }
}

interface AutostartListPayload {
  service_installed?: boolean;
  service_enabled?: boolean;
  repositories?: { name: string; enabled: boolean; on_disk: boolean }[] | null;
}

/** `repo autostart list` — fetch the renet payload and render it. */
async function handleAutostartList(options: {
  machine: string;
  debug?: boolean;
  skipRouterRestart?: boolean;
}): Promise<void> {
  await assertMachineExists(options.machine);
  outputService.info(t('commands.repo.autostart.list.starting', { machine: options.machine }));

  const result = await localExecutorService.execute({
    functionName: 'repository_autostart_list',
    machineName: options.machine,
    params: {},
    debug: options.debug,
    skipRouterRestart: options.skipRouterRestart,
    captureOutput: true,
  });

  if (!result.success) {
    renderLocalExecutionFailure(result, result.error ?? t('commands.repo.autostart.list.failed'));
    return;
  }

  // renet relays a single JSON object with `[repository_autostart_list]`
  // line prefixes — same shape the prune parser extracts.
  const payload = parseDatastorePruneOutput(result.stdout ?? '') as AutostartListPayload;
  const format = getOutputFormat();
  if (format !== 'table') {
    outputService.print(payload, format);
    return;
  }

  const resolve = createGuidResolver(await loadGuidMap());
  const rows = (payload.repositories ?? []).map((r) => ({
    repository: resolve(r.name),
    guid: r.name,
    enabled: r.enabled ? 'yes' : 'no',
    onDisk: r.on_disk ? 'yes' : 'no',
  }));

  if (rows.length === 0) {
    outputService.info(t('commands.repo.autostart.list.empty', { machine: options.machine }));
  } else {
    outputService.print(rows, 'table');
  }
  outputService.info(
    t('commands.repo.autostart.list.service', {
      installed: payload.service_installed ? 'yes' : 'no',
      enabled: payload.service_enabled ? 'yes' : 'no',
    })
  );
}

/**
 * Register extended repo commands: fork, resize, expand, validate,
 * autostart, ownership, and template.
 */
export function registerExtendedRepoCommands(repo: Command): void {
  // repo fork --parent <name> --tag <name>
  const forkCmd = repo
    .command('fork')
    .summary(t('commands.repo.fork.descriptionShort'))
    .description(t('commands.repo.fork.description'))
    .requiredOption('--parent <name>', t('options.name'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--tag <name>', t('commands.repo.fork.tagOption'))
    .option('--checkpoint', t('commands.repo.fork.checkpointOption'))
    .option('--immutable', t('commands.repo.fork.immutableOption'))
    .option('--up', t('commands.repo.fork.upOption'))
    .option('--detach', t('commands.repo.fork.detachOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (options: {
        parent: string;
        machine: string;
        tag: string;
        checkpoint?: boolean;
        immutable?: boolean;
        up?: boolean;
        detach?: boolean;
        debug?: boolean;
        skipRouterRestart?: boolean;
      }) => {
        const parent = options.parent;
        const tagName = options.tag;
        await handleForkAction(parent, tagName, options);
      }
    );
  forkCmd.addHelpText('after', t('commands.repo.fork.examples'));

  registerRepoTakeoverCommand(repo);

  // repo resize --name <name>
  repo
    .command('resize')
    .summary(t('commands.repo.resize.descriptionShort'))
    .description(t('commands.repo.resize.description'))
    .requiredOption('--name <name>', t('options.name'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--size <size>', t('commands.repo.resize.sizeOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (options: {
        name: string;
        machine: string;
        size: string;
        debug?: boolean;
        skipRouterRestart?: boolean;
      }) => {
        try {
          const name = options.name;
          await assertCommandPolicy(CMD.REPO_RESIZE, name);
          await executeRepoFunction(
            'repository_resize',
            name,
            options.machine,
            { size: options.size },
            options,
            {
              starting: t('commands.repo.resize.starting', {
                repository: name,
                size: options.size,
                machine: options.machine,
              }),
              completed: t('commands.repo.resize.completed'),
              failed: t('commands.repo.resize.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo expand --name <name>
  repo
    .command('expand')
    .summary(t('commands.repo.expand.descriptionShort'))
    .description(t('commands.repo.expand.description'))
    .requiredOption('--name <name>', t('options.name'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--size <size>', t('commands.repo.expand.sizeOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (options: {
        name: string;
        machine: string;
        size: string;
        debug?: boolean;
        skipRouterRestart?: boolean;
      }) => {
        try {
          const name = options.name;
          await assertCommandPolicy(CMD.REPO_EXPAND, name);
          await executeRepoFunction(
            'repository_expand',
            name,
            options.machine,
            { size: options.size },
            options,
            {
              starting: t('commands.repo.expand.starting', {
                repository: name,
                size: options.size,
                machine: options.machine,
              }),
              completed: t('commands.repo.expand.completed'),
              failed: t('commands.repo.expand.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo trim [--name <name>] -m <machine>
  registerRepoTrimCommand(repo);

  // repo policy set|get
  registerRepoPolicyCommand(repo);

  // repo validate --name <name>
  repo
    .command('validate')
    .summary(t('commands.repo.validate.descriptionShort'))
    .description(t('commands.repo.validate.description'))
    .requiredOption('--name <name>', t('options.name'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (options: {
        name: string;
        machine: string;
        debug?: boolean;
        skipRouterRestart?: boolean;
      }) => {
        try {
          const name = options.name;
          await executeRepoFunction('repository_validate', name, options.machine, {}, options, {
            starting: t('commands.repo.validate.starting', {
              repository: name,
              machine: options.machine,
            }),
            completed: t('commands.repo.validate.completed'),
            failed: t('commands.repo.validate.failed'),
          });
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo autostart (parent command with subcommands)
  const autostart = repo.command('autostart').description(t('commands.repo.autostart.description'));

  // repo autostart enable [--name <name>] — per-repo if name given, all repos if omitted
  autostart
    .command('enable')
    .description(t('commands.repo.autostart.enable.description'))
    .option('--name <name>', t('options.name'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (options: {
        name?: string;
        machine: string;
        debug?: boolean;
        skipRouterRestart?: boolean;
      }) => {
        try {
          const name = options.name;
          if (name) {
            await assertCommandPolicy(CMD.REPO_AUTOSTART_ENABLE, name);
            await executeRepoFunction(
              'repository_autostart_enable',
              name,
              options.machine,
              {},
              options,
              {
                starting: t('commands.repo.autostart.enable.starting', {
                  repository: name,
                  machine: options.machine,
                }),
                completed: t('commands.repo.autostart.enable.completed'),
                failed: t('commands.repo.autostart.enable.failed'),
              }
            );
          } else {
            await executeMachineFunction('repository_autostart_enable_all', options, {
              starting: t('commands.repo.autostart.enable.startingAll', {
                machine: options.machine,
              }),
              completed: t('commands.repo.autostart.enable.completedAll'),
              failed: t('commands.repo.autostart.enable.failedAll'),
            });
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo autostart disable [--name <name>] — per-repo if name given, all repos if omitted
  autostart
    .command('disable')
    .description(t('commands.repo.autostart.disable.description'))
    .option('--name <name>', t('options.name'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (options: {
        name?: string;
        machine: string;
        debug?: boolean;
        skipRouterRestart?: boolean;
      }) => {
        try {
          const name = options.name;
          if (name) {
            await assertCommandPolicy(CMD.REPO_AUTOSTART_DISABLE, name);
            await executeRepoFunction(
              'repository_autostart_disable',
              name,
              options.machine,
              {},
              options,
              {
                starting: t('commands.repo.autostart.disable.starting', {
                  repository: name,
                  machine: options.machine,
                }),
                completed: t('commands.repo.autostart.disable.completed'),
                failed: t('commands.repo.autostart.disable.failed'),
              }
            );
          } else {
            await executeMachineFunction('repository_autostart_disable_all', options, {
              starting: t('commands.repo.autostart.disable.startingAll', {
                machine: options.machine,
              }),
              completed: t('commands.repo.autostart.disable.completedAll'),
              failed: t('commands.repo.autostart.disable.failedAll'),
            });
          }
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo autostart list
  autostart
    .command('list')
    .description(t('commands.repo.autostart.list.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(async (options: { machine: string; debug?: boolean; skipRouterRestart?: boolean }) => {
      try {
        await handleAutostartList(options);
      } catch (error) {
        handleError(error);
      }
    });

  // repo ownership --name <name>
  repo
    .command('ownership')
    .summary(t('commands.repo.ownership.descriptionShort'))
    .description(t('commands.repo.ownership.description'))
    .requiredOption('--name <name>', t('options.name'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--uid <uid>', t('commands.repo.ownership.uidOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (options: {
        name: string;
        machine: string;
        uid?: string;
        debug?: boolean;
        skipRouterRestart?: boolean;
      }) => {
        try {
          const name = options.name;
          await assertCommandPolicy(CMD.REPO_OWNERSHIP, name);
          const params: Record<string, unknown> = {};
          if (options.uid) params.owner_uid = options.uid;

          await executeRepoFunction(
            'repository_ownership',
            name,
            options.machine,
            params,
            options,
            {
              starting: t('commands.repo.ownership.starting', {
                repository: name,
                machine: options.machine,
              }),
              completed: t('commands.repo.ownership.completed'),
              failed: t('commands.repo.ownership.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo template (parent command with list + apply subcommands)
  const template = repo
    .command('template')
    .summary(t('commands.repo.template.descriptionShort'))
    .description(t('commands.repo.template.description'));

  // repo template list
  template
    .command('list')
    .summary(t('commands.repo.template.list.descriptionShort'))
    .description(t('commands.repo.template.list.description'))
    .action(async () => {
      try {
        const { TEMPLATES } = await import('../templates/embedded.generated.js');
        const entries = Object.values(TEMPLATES);
        if (entries.length === 0) {
          outputService.info(t('commands.repo.template.list.empty'));
          return;
        }
        for (const tmpl of entries) {
          outputService.info(`  ${tmpl.name.padEnd(20)} ${tmpl.description}`);
        }
      } catch (error) {
        handleError(error);
      }
    });

  // repo template apply --name <template> -m <machine> -r <repo>
  template
    .command('apply')
    .summary(t('commands.repo.template.apply.descriptionShort'))
    .description(t('commands.repo.template.apply.description'))
    .requiredOption('--name <name>', t('options.name'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('-r, --repository <name>', t('options.repository'))
    .option('--file <path>', t('commands.repo.template.fileOption'))
    .option('--grand <name>', t('commands.repo.template.grandOption'))
    .option('--debug', t('options.debug'))
    .option('--skip-router-restart', t('options.skipRouterRestart'))
    .action(
      async (options: {
        name: string;
        machine: string;
        repository: string;
        file?: string;
        grand?: string;
        debug?: boolean;
        skipRouterRestart?: boolean;
      }) => {
        try {
          const templateName = options.name;
          await assertCommandPolicy(CMD.REPO_TEMPLATE, options.repository);

          let tmplBase64: string;

          if (options.file) {
            // File mode (backward compat): read local JSON file
            let fileContent: string;
            try {
              fileContent = readFileSync(options.file, 'utf-8');
            } catch {
              throw new Error(t('commands.repo.template.fileNotFound', { path: options.file }));
            }
            tmplBase64 = Buffer.from(fileContent).toString('base64');
          } else {
            // Embedded mode: look up template by name
            const { TEMPLATES } = await import('../templates/embedded.generated.js');
            const embedded = TEMPLATES[templateName] as (typeof TEMPLATES)[string] | undefined;
            if (!embedded) {
              const available = Object.keys(TEMPLATES).join(', ');
              throw new Error(
                t('commands.repo.template.apply.notFound', {
                  name: templateName,
                  available,
                })
              );
            }
            const templateJSON = { version: '2', files: embedded.files };
            tmplBase64 = Buffer.from(JSON.stringify(templateJSON)).toString('base64');
          }

          const params: Record<string, unknown> = { tmpl: tmplBase64 };

          // Resolve grand repo friendly name -> GUID
          if (options.grand) {
            const grandRepo = await configService.getRepository(options.grand);
            params.grand = grandRepo?.repositoryGuid ?? options.grand;
          }

          await executeRepoFunction(
            'repository_template_apply',
            options.repository,
            options.machine,
            params,
            options,
            {
              starting: t('commands.repo.template.starting', {
                repository: options.repository,
                machine: options.machine,
              }),
              completed: t('commands.repo.template.completed'),
              failed: t('commands.repo.template.failed'),
            }
          );
        } catch (error) {
          handleError(error);
        }
      }
    );
}

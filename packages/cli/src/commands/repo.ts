import { randomBytes, randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { contextService } from '../services/context.js';
import { localExecutorService } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { handleError } from '../utils/errors.js';

function generateCredential(): string {
  return randomBytes(24).toString('base64');
}

/**
 * Execute a repository lifecycle function on a remote machine.
 * Validates the repository exists in context and runs the function via localExecutorService.
 */
async function executeRepoFunction(
  functionName: string,
  repoName: string,
  machineName: string,
  params: Record<string, unknown>,
  options: { debug?: boolean },
  messages: { starting: string; completed: string; failed: string }
): Promise<void> {
  // Validate repository exists in context
  const repo = await contextService.getLocalRepository(repoName);
  if (!repo) {
    throw new Error(`Repository "${repoName}" not found in context`);
  }
  if (!repo.credential) {
    outputService.warn(t('commands.repo.noCredential', { name: repoName }));
  }

  // Ensure network_id is assigned (auto-allocates for legacy repos without one)
  await contextService.ensureRepositoryNetworkId(repoName);

  outputService.info(messages.starting);

  const result = await localExecutorService.execute({
    functionName,
    machineName,
    params: { repository: repoName, ...params },
    debug: options.debug,
  });

  if (result.success) {
    outputService.success(messages.completed);
  } else {
    outputService.error(result.error ?? messages.failed);
    process.exitCode = result.exitCode;
  }
}

export function registerRepoCommands(program: Command): void {
  const repo = program.command('repo').description(t('commands.repo.description'));

  // repo create <name>
  repo
    .command('create <name>')
    .description(t('commands.repo.create.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--size <size>', t('commands.repo.create.sizeOption'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: { machine: string; size: string; debug?: boolean }) => {
      try {
        // Validate doesn't already exist
        const existing = await contextService.getLocalRepository(name);
        if (existing) {
          throw new Error(t('commands.repo.create.alreadyExists', { name }));
        }

        // Generate UUID, credential, and allocate networkId
        const repositoryGuid = randomUUID();
        const credential = generateCredential();
        const networkId = await contextService.allocateNetworkId();

        // Register in config.json first (so the executor can find it)
        await contextService.addLocalRepository(name, {
          repositoryGuid,
          tag: 'latest',
          credential,
          networkId,
        });

        outputService.info(
          t('commands.repo.create.registered', {
            repository: name,
            guid: repositoryGuid.slice(0, 8),
            networkId,
          })
        );
        outputService.info(
          t('commands.repo.create.starting', {
            repository: name,
            size: options.size,
            machine: options.machine,
          })
        );

        // Execute on remote
        const result = await localExecutorService.execute({
          functionName: 'repository_create',
          machineName: options.machine,
          params: { repository: name, size: options.size },
          debug: options.debug,
        });

        if (result.success) {
          outputService.success(t('commands.repo.create.completed'));
        } else {
          // Rollback: remove from config.json
          await contextService.removeLocalRepository(name);
          outputService.warn(t('commands.repo.create.rollback', { repository: name }));
          outputService.error(result.error ?? t('commands.repo.create.failed'));
          process.exitCode = result.exitCode;
        }
      } catch (error) {
        // Rollback on unexpected error
        const exists = await contextService.getLocalRepository(name);
        if (exists) {
          await contextService.removeLocalRepository(name);
          outputService.warn(t('commands.repo.create.rollback', { repository: name }));
        }
        handleError(error);
      }
    });

  // repo delete <name>
  repo
    .command('delete <name>')
    .description(t('commands.repo.delete.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: { machine: string; debug?: boolean }) => {
      try {
        // Validate exists
        const repoConfig = await contextService.getLocalRepository(name);
        if (!repoConfig) {
          throw new Error(`Repository "${name}" not found in context`);
        }

        await contextService.ensureRepositoryNetworkId(name);

        outputService.info(
          t('commands.repo.delete.starting', { repository: name, machine: options.machine })
        );

        const result = await localExecutorService.execute({
          functionName: 'repository_delete',
          machineName: options.machine,
          params: { repository: name },
          debug: options.debug,
        });

        if (result.success) {
          await contextService.removeLocalRepository(name);
          outputService.info(t('commands.repo.delete.removed', { repository: name }));
          outputService.success(t('commands.repo.delete.completed'));
        } else {
          outputService.error(result.error ?? t('commands.repo.delete.failed'));
          process.exitCode = result.exitCode;
        }
      } catch (error) {
        handleError(error);
      }
    });

  // repo mount <name>
  repo
    .command('mount <name>')
    .description(t('commands.repo.mount.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--checkpoint', t('commands.repo.mount.checkpointOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (name: string, options: { machine: string; checkpoint?: boolean; debug?: boolean }) => {
        try {
          const params: Record<string, unknown> = {};
          if (options.checkpoint) params.checkpoint = true;

          await executeRepoFunction('repository_mount', name, options.machine, params, options, {
            starting: t('commands.repo.mount.starting', {
              repository: name,
              machine: options.machine,
            }),
            completed: t('commands.repo.mount.completed'),
            failed: t('commands.repo.mount.failed'),
          });
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo unmount <name>
  repo
    .command('unmount <name>')
    .description(t('commands.repo.unmount.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--checkpoint', t('commands.repo.unmount.checkpointOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (name: string, options: { machine: string; checkpoint?: boolean; debug?: boolean }) => {
        try {
          const params: Record<string, unknown> = {};
          if (options.checkpoint) params.checkpoint = true;

          await executeRepoFunction('repository_unmount', name, options.machine, params, options, {
            starting: t('commands.repo.unmount.starting', {
              repository: name,
              machine: options.machine,
            }),
            completed: t('commands.repo.unmount.completed'),
            failed: t('commands.repo.unmount.failed'),
          });
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo up <name>
  repo
    .command('up <name>')
    .description(t('commands.repo.up.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--mount', t('commands.repo.up.mountOption'))
    .option('--prep-only', t('commands.repo.up.prepOnlyOption'))
    .option('--grand <name>', t('commands.repo.up.grandOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        name: string,
        options: {
          machine: string;
          mount?: boolean;
          prepOnly?: boolean;
          grand?: string;
          debug?: boolean;
        }
      ) => {
        try {
          const params: Record<string, unknown> = {};
          if (options.mount) params.mount = true;
          if (options.prepOnly) params.option = 'prep-only';

          // Resolve grand repo friendly name → GUID
          if (options.grand) {
            const grandRepo = await contextService.getLocalRepository(options.grand);
            params.grand = grandRepo?.repositoryGuid ?? options.grand;
          }

          await executeRepoFunction('repository_up', name, options.machine, params, options, {
            starting: t('commands.repo.up.starting', {
              repository: name,
              machine: options.machine,
            }),
            completed: t('commands.repo.up.completed'),
            failed: t('commands.repo.up.failed'),
          });
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo down <name>
  repo
    .command('down <name>')
    .description(t('commands.repo.down.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--unmount', t('commands.repo.down.unmountOption'))
    .option('--grand <name>', t('commands.repo.down.grandOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        name: string,
        options: {
          machine: string;
          unmount?: boolean;
          grand?: string;
          debug?: boolean;
        }
      ) => {
        try {
          const params: Record<string, unknown> = {};
          if (options.unmount) params.option = 'unmount';

          // Resolve grand repo friendly name → GUID
          if (options.grand) {
            const grandRepo = await contextService.getLocalRepository(options.grand);
            params.grand = grandRepo?.repositoryGuid ?? options.grand;
          }

          await executeRepoFunction('repository_down', name, options.machine, params, options, {
            starting: t('commands.repo.down.starting', {
              repository: name,
              machine: options.machine,
            }),
            completed: t('commands.repo.down.completed'),
            failed: t('commands.repo.down.failed'),
          });
        } catch (error) {
          handleError(error);
        }
      }
    );

  // repo status <name>
  repo
    .command('status <name>')
    .description(t('commands.repo.status.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: { machine: string; debug?: boolean }) => {
      try {
        await executeRepoFunction('repository_status', name, options.machine, {}, options, {
          starting: t('commands.repo.status.starting', {
            repository: name,
            machine: options.machine,
          }),
          completed: t('commands.repo.status.completed'),
          failed: t('commands.repo.status.failed'),
        });
      } catch (error) {
        handleError(error);
      }
    });

  // repo list (no positional arg — lists all repos on the machine)
  repo
    .command('list')
    .description(t('commands.repo.list.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: { machine: string; debug?: boolean }) => {
      try {
        outputService.info(t('commands.repo.list.starting', { machine: options.machine }));

        const result = await localExecutorService.execute({
          functionName: 'repository_list',
          machineName: options.machine,
          params: {},
          debug: options.debug,
        });

        if (result.success) {
          outputService.success(t('commands.repo.list.completed'));
        } else {
          outputService.error(t('commands.repo.list.failed', { error: result.error }));
          process.exitCode = result.exitCode;
        }
      } catch (error) {
        handleError(error);
      }
    });

  // repo fork <parent>
  repo
    .command('fork <parent>')
    .description(t('commands.repo.fork.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--tag <name>', t('commands.repo.fork.tagOption'))
    .option('--debug', t('options.debug'))
    .action(async (parent: string, options: { machine: string; tag: string; debug?: boolean }) => {
      const forkName = options.tag;
      try {
        // Validate parent exists
        const parentConfig = await contextService.getLocalRepository(parent);
        if (!parentConfig) {
          throw new Error(`Repository "${parent}" not found in context`);
        }

        // Validate fork doesn't already exist
        const existing = await contextService.getLocalRepository(forkName);
        if (existing) {
          throw new Error(t('commands.repo.fork.alreadyExists', { name: forkName }));
        }

        // Generate new GUID and allocate networkId; reuse parent's credential (same LUKS password)
        const repositoryGuid = randomUUID();
        const networkId = await contextService.allocateNetworkId();

        await contextService.addLocalRepository(forkName, {
          repositoryGuid,
          tag: 'latest',
          credential: parentConfig.credential,
          networkId,
        });

        outputService.info(
          t('commands.repo.fork.registered', {
            repository: forkName,
            guid: repositoryGuid.slice(0, 8),
            networkId,
          })
        );
        outputService.info(
          t('commands.repo.fork.starting', {
            parent,
            repository: forkName,
            machine: options.machine,
          })
        );

        // Execute fork on remote (repository param = parent, tag = fork's GUID)
        const result = await localExecutorService.execute({
          functionName: 'repository_fork',
          machineName: options.machine,
          params: { repository: parent, tag: repositoryGuid },
          debug: options.debug,
        });

        if (result.success) {
          outputService.success(t('commands.repo.fork.completed'));
        } else {
          await contextService.removeLocalRepository(forkName);
          outputService.warn(t('commands.repo.fork.rollback', { repository: forkName }));
          outputService.error(result.error ?? t('commands.repo.fork.failed'));
          process.exitCode = result.exitCode;
        }
      } catch (error) {
        const exists = await contextService.getLocalRepository(forkName);
        if (exists) {
          await contextService.removeLocalRepository(forkName);
          outputService.warn(t('commands.repo.fork.rollback', { repository: forkName }));
        }
        handleError(error);
      }
    });

  // repo resize <name>
  repo
    .command('resize <name>')
    .description(t('commands.repo.resize.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--size <size>', t('commands.repo.resize.sizeOption'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: { machine: string; size: string; debug?: boolean }) => {
      try {
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
    });

  // repo expand <name>
  repo
    .command('expand <name>')
    .description(t('commands.repo.expand.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--size <size>', t('commands.repo.expand.sizeOption'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: { machine: string; size: string; debug?: boolean }) => {
      try {
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
    });

  // repo validate <name>
  repo
    .command('validate <name>')
    .description(t('commands.repo.validate.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: { machine: string; debug?: boolean }) => {
      try {
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
    });

  // repo ownership <name>
  repo
    .command('ownership <name>')
    .description(t('commands.repo.ownership.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .option('--uid <uid>', t('commands.repo.ownership.uidOption'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options: { machine: string; uid?: string; debug?: boolean }) => {
      try {
        const params: Record<string, unknown> = {};
        if (options.uid) params.owner_uid = options.uid;

        await executeRepoFunction('repository_ownership', name, options.machine, params, options, {
          starting: t('commands.repo.ownership.starting', {
            repository: name,
            machine: options.machine,
          }),
          completed: t('commands.repo.ownership.completed'),
          failed: t('commands.repo.ownership.failed'),
        });
      } catch (error) {
        handleError(error);
      }
    });

  // repo template <name>
  repo
    .command('template <name>')
    .description(t('commands.repo.template.description'))
    .requiredOption('-m, --machine <name>', t('commands.repo.machineOption'))
    .requiredOption('--file <path>', t('commands.repo.template.fileOption'))
    .option('--grand <name>', t('commands.repo.template.grandOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (
        name: string,
        options: { machine: string; file: string; grand?: string; debug?: boolean }
      ) => {
        try {
          // Read and base64-encode template file
          let fileContent: string;
          try {
            fileContent = readFileSync(options.file, 'utf-8');
          } catch {
            throw new Error(t('commands.repo.template.fileNotFound', { path: options.file }));
          }
          const tmpl = Buffer.from(fileContent).toString('base64');

          const params: Record<string, unknown> = { tmpl };

          // Resolve grand repo friendly name → GUID
          if (options.grand) {
            const grandRepo = await contextService.getLocalRepository(options.grand);
            params.grand = grandRepo?.repositoryGuid ?? options.grand;
          }

          await executeRepoFunction(
            'repository_template_apply',
            name,
            options.machine,
            params,
            options,
            {
              starting: t('commands.repo.template.starting', {
                repository: name,
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

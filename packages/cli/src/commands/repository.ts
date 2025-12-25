import { Command } from 'commander';
import {
  canDeleteGrandRepo,
  canPromoteToGrand,
  findSiblingClones,
  isCredential,
  type RepositoryWithRelations,
} from '@rediacc/shared/services/repository';
import type { CompanyVaultRecord } from '@rediacc/shared/types';
import { api } from '../services/api.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import type { OutputFormat } from '../types/index.js';

export function registerRepositoryCommands(program: Command): void {
  const repository = program.command('repository').description('Repository management commands');

  // repository list
  repository
    .command('list')
    .description('List repositories')
    .option('-t, --team <name>', 'Team name')
    .action(async (options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError('Team name required. Use --team or set context.');
        }

        const repositories = await withSpinner(
          'Fetching repositories...',
          () => api.repositories.list({ teamName: opts.team as string }),
          'Repositories fetched'
        );

        const format = program.opts().output as OutputFormat;

        outputService.print(repositories, format);
      } catch (error) {
        handleError(error);
      }
    });

  // repository create
  repository
    .command('create <name>')
    .description('Create a new repository')
    .option('-t, --team <name>', 'Team name')
    .option('--tag <tag>', 'Repository tag', 'main')
    .option('--parent <name>', 'Parent repository (for forks)')
    .option('--parent-tag <tag>', 'Parent repository tag')
    .action(async (name, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError('Team name required. Use --team or set context.');
        }

        const createOptions: {
          repositoryTag?: string;
          parentRepositoryName?: string;
          parentRepositoryTag?: string;
        } = {
          repositoryTag: options.tag,
        };
        if (options.parent) {
          createOptions.parentRepositoryName = options.parent;
          createOptions.parentRepositoryTag = options.parentTag ?? 'main';
        }

        await withSpinner(
          `Creating repository "${name}:${options.tag}"...`,
          () => api.repositories.create(opts.team as string, name, createOptions),
          `Repository "${name}:${options.tag}" created`
        );
      } catch (error) {
        handleError(error);
      }
    });

  // repository rename
  repository
    .command('rename <oldName> <newName>')
    .description('Rename a repository')
    .option('-t, --team <name>', 'Team name')
    .option('--tag <tag>', 'Repository tag', 'main')
    .action(async (oldName, newName, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError('Team name required. Use --team or set context.');
        }

        await withSpinner(
          `Renaming repository "${oldName}" to "${newName}"...`,
          () =>
            api.repositories.rename({
              teamName: opts.team as string,
              currentRepositoryName: oldName,
              newRepositoryName: newName,
            }),
          `Repository renamed to "${newName}"`
        );
      } catch (error) {
        handleError(error);
      }
    });

  // repository delete - enhanced with shared orchestration
  repository
    .command('delete <name>')
    .description('Delete a repository')
    .option('-t, --team <name>', 'Team name')
    .option('--tag <tag>', 'Repository tag', 'main')
    .option('-f, --force', 'Skip confirmation')
    .action(async (name, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError('Team name required. Use --team or set context.');
        }

        // Fetch all repositories to validate deletion
        const allRepositories = await withSpinner(
          'Checking repository relationships...',
          () => api.repositories.list({ teamName: opts.team as string }),
          'Repository relationships checked'
        );

        // Find the target repo
        const targetRepository = allRepositories.find(
          (r: RepositoryWithRelations) =>
            r.repositoryName === name && (r.repositoryTag === options.tag || !options.tag)
        );

        if (!targetRepository) {
          throw new ValidationError(`Repository "${name}:${options.tag}" not found`);
        }

        // Use shared orchestration to validate deletion
        if (isCredential(targetRepository)) {
          const validation = canDeleteGrandRepo(targetRepository, allRepositories);

          if (!validation.canDelete) {
            let errorMessage = `Cannot delete grand repository: ${validation.reason}`;

            if (validation.childClones.length > 0) {
              const cloneNames = validation.childClones
                .map(
                  (clone) =>
                    `${clone.repositoryName}${clone.repositoryTag ? `:${clone.repositoryTag}` : ''}`
                )
                .join(', ');
              errorMessage += `. Affected child clones: ${cloneNames}. Delete or promote child clones first.`;
            }
            throw new ValidationError(errorMessage);
          }
        }

        if (!options.force) {
          const { askConfirm } = await import('../utils/prompt.js');

          // Show warning for grand repos
          if (isCredential(targetRepository)) {
            outputService.warn(
              'This is a grand repository (credential). Deleting it is irreversible.'
            );
          }

          const confirm = await askConfirm(
            `Delete repository "${name}:${options.tag}"? This cannot be undone.`
          );
          if (!confirm) {
            outputService.info('Cancelled');
            return;
          }
        }

        await withSpinner(
          `Deleting repository "${name}:${options.tag}"...`,
          () =>
            api.repositories.delete({
              teamName: opts.team as string,
              repositoryName: name,
              repositoryTag: options.tag,
            }),
          `Repository "${name}:${options.tag}" deleted`
        );
      } catch (error) {
        handleError(error);
      }
    });

  // repository promote - enhanced with shared orchestration
  repository
    .command('promote <name>')
    .description('Promote a fork to grand status')
    .option('-t, --team <name>', 'Team name')
    .option('--tag <tag>', 'Repository tag', 'main')
    .option('-f, --force', 'Skip confirmation')
    .action(async (name, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError('Team name required. Use --team or set context.');
        }

        // Fetch all repositories to validate promotion
        const allRepositories = await withSpinner(
          'Checking repository relationships...',
          () => api.repositories.list({ teamName: opts.team as string }),
          'Repository relationships checked'
        );

        // Find the target repo
        const targetRepository = allRepositories.find(
          (r: RepositoryWithRelations) =>
            r.repositoryName === name && (r.repositoryTag === options.tag || !options.tag)
        );

        if (!targetRepository) {
          throw new ValidationError(`Repository "${name}:${options.tag}" not found`);
        }

        // Use shared orchestration to validate promotion
        const validation = canPromoteToGrand(targetRepository);

        if (!validation.canPromote) {
          throw new ValidationError(`Cannot promote: ${validation.reason}`);
        }

        // Find and display affected siblings
        const { siblingClones, currentGrandName } = findSiblingClones(
          targetRepository,
          allRepositories
        );

        if (!options.force && siblingClones.length > 0) {
          outputService.info(
            `\nThis will separate "${name}" from grand repository "${currentGrandName}"`
          );
          outputService.info(
            `\n${siblingClones.length} sibling clone(s) will remain linked to the original grand:`
          );
          siblingClones.forEach((sibling) => {
            outputService.info(
              `  - ${sibling.repositoryName}${sibling.repositoryTag ? `:${sibling.repositoryTag}` : ''}`
            );
          });

          const { askConfirm } = await import('../utils/prompt.js');
          const confirm = await askConfirm('\nProceed with promotion?');
          if (!confirm) {
            outputService.info('Cancelled');
            return;
          }
        }

        await withSpinner(
          `Promoting repository "${name}:${options.tag}"...`,
          () =>
            api.repositories.promoteToGrand({
              teamName: opts.team as string,
              repositoryName: name,
            }),
          `Repository "${name}:${options.tag}" promoted to grand status`
        );
      } catch (error) {
        handleError(error);
      }
    });

  // repository vault subcommand
  const vault = repository.command('vault').description('Repository vault management');

  // repository vault get
  vault
    .command('get <repositoryName>')
    .description('Get repository vault data')
    .option('-t, --team <name>', 'Team name')
    .option('--tag <tag>', 'Repository tag', 'main')
    .action(async (repositoryName, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError('Team name required. Use --team or set context.');
        }

        const vaultsResponse = await withSpinner(
          'Fetching repository vault...',
          () =>
            api.company.getAllVaults({
              teamName: opts.team,
              repositoryName,
              repositoryTag: options.tag,
            }),
          'Vault fetched'
        );

        const repositoryVault = vaultsResponse.vaults.find(
          (vault: CompanyVaultRecord & { vaultType?: string }) => vault.vaultType === 'Repository'
        );
        const format = program.opts().output as OutputFormat;

        if (repositoryVault) {
          outputService.print(repositoryVault, format);
        } else {
          outputService.info('No repository vault found');
        }
      } catch (error) {
        handleError(error);
      }
    });

  // repository vault update
  vault
    .command('update <repositoryName>')
    .description('Update repository vault data')
    .option('-t, --team <name>', 'Team name')
    .option('--tag <tag>', 'Repository tag', 'main')
    .option('--vault <json>', 'Vault data as JSON string')
    .option(
      '--vault-version <n>',
      'Current vault version (required for optimistic concurrency)',
      parseInt
    )
    .action(async (repositoryName, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError('Team name required. Use --team or set context.');
        }

        // Get vault data from --vault flag or stdin
        let vaultData: string = options.vault;
        if (!vaultData && !process.stdin.isTTY) {
          // Read from stdin if not a TTY (piped input)
          const chunks: Buffer[] = [];
          for await (const chunk of process.stdin) {
            chunks.push(chunk);
          }
          vaultData = Buffer.concat(chunks).toString('utf-8').trim();
        }

        if (!vaultData) {
          throw new ValidationError(
            'Vault data required. Use --vault <json> or pipe JSON via stdin.'
          );
        }

        if (options.vaultVersion === undefined || options.vaultVersion === null) {
          throw new ValidationError('Vault version required. Use --vault-version <n>.');
        }

        // Validate JSON
        try {
          JSON.parse(vaultData);
        } catch {
          throw new ValidationError('Invalid JSON vault data.');
        }

        await withSpinner(
          'Updating repository vault...',
          () =>
            api.repositories.updateVault({
              teamName: opts.team as string,
              repositoryName,
              repositoryTag: options.tag,
              vaultContent: vaultData,
              vaultVersion: options.vaultVersion,
            }),
          'Repository vault updated'
        );
      } catch (error) {
        handleError(error);
      }
    });
}

import { parseGetOrganizationVaults, parseGetTeamRepositories } from '@rediacc/shared/api';
import { DEFAULT_REPOSITORY_TAG } from '@rediacc/shared/api/typedApi/defaults';
import {
  canDeleteGrandRepo,
  canPromoteToGrand,
  findSiblingClones,
  isCredential,
  type RepositoryWithRelations,
} from '@rediacc/shared/services/repository';
import type { GetOrganizationVaults_ResultSet1 } from '@rediacc/shared/types';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import type { OutputFormat } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';

function validateGrandRepoDeletion(
  repository: RepositoryWithRelations,
  allRepositories: RepositoryWithRelations[]
): void {
  if (!isCredential(repository)) return;

  const validation = canDeleteGrandRepo(repository, allRepositories);
  if (validation.canDelete) return;

  let errorMessage = t('errors.cannotDeleteGrandRepo', { reason: validation.reason });

  if (validation.childClones.length > 0) {
    const cloneNames = validation.childClones
      .map(
        (clone) => `${clone.repositoryName}${clone.repositoryTag ? `:${clone.repositoryTag}` : ''}`
      )
      .join(', ');
    errorMessage += t('errors.affectedChildClones', { clones: cloneNames });
  }

  throw new ValidationError(errorMessage);
}

async function confirmDeletion(
  repository: RepositoryWithRelations,
  name: string,
  tag: string
): Promise<boolean> {
  const { askConfirm } = await import('../utils/prompt.js');

  if (isCredential(repository)) {
    outputService.warn(t('commands.repository.delete.grandRepoWarning'));
  }

  return askConfirm(t('commands.repository.delete.confirm', { name, tag }));
}

export function registerRepositoryCommands(program: Command): void {
  const repository = program
    .command('repository')
    .description(t('commands.repository.description'));

  // repository list
  repository
    .command('list')
    .description(t('commands.repository.list.description'))
    .option('-t, --team <name>', t('options.team'))
    .action(async (options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const apiResponse = await withSpinner(
          t('commands.repository.list.fetching'),
          () => typedApi.GetTeamRepositories({ teamName: opts.team as string }),
          t('commands.repository.list.success')
        );

        const repositories = parseGetTeamRepositories(apiResponse as never);

        const format = program.opts().output as OutputFormat;

        outputService.print(repositories, format);
      } catch (error) {
        handleError(error);
      }
    });

  // repository create
  repository
    .command('create <name>')
    .description(t('commands.repository.create.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('--tag <tag>', t('options.repositoryTag'), DEFAULT_REPOSITORY_TAG)
    .option('--parent <name>', t('options.parentRepository'))
    .option('--parent-tag <tag>', t('options.parentRepositoryTag'))
    .action(async (name, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const createParams = {
          teamName: opts.team,
          repositoryName: name,
          repositoryTag: options.tag,
          parentRepositoryName: options.parent,
          parentRepositoryTag: options.parent
            ? (options.parentTag ?? DEFAULT_REPOSITORY_TAG)
            : undefined,
        };

        await withSpinner(
          t('commands.repository.create.creating', { name, tag: options.tag }),
          () => typedApi.CreateRepository(createParams as never),
          t('commands.repository.create.success', { name, tag: options.tag })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // repository rename
  repository
    .command('rename <oldName> <newName>')
    .description(t('commands.repository.rename.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('--tag <tag>', t('options.repositoryTag'), DEFAULT_REPOSITORY_TAG)
    .action(async (oldName, newName, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        await withSpinner(
          t('commands.repository.rename.renaming', { oldName, newName }),
          () =>
            typedApi.UpdateRepositoryName({
              teamName: opts.team as string,
              currentRepositoryName: oldName,
              newRepositoryName: newName,
            }),
          t('commands.repository.rename.success', { name: newName })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // repository delete - enhanced with shared orchestration
  repository
    .command('delete <name>')
    .description(t('commands.repository.delete.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('--tag <tag>', t('options.repositoryTag'), DEFAULT_REPOSITORY_TAG)
    .option('-f, --force', t('options.force'))
    .action(async (name, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const apiResponse = await withSpinner(
          t('commands.repository.delete.checkingRelationships'),
          () => typedApi.GetTeamRepositories({ teamName: opts.team as string }),
          t('commands.repository.delete.relationshipsChecked')
        );

        const allRepositories = parseGetTeamRepositories(apiResponse as never);

        const targetRepository = allRepositories.find(
          (r: RepositoryWithRelations) =>
            r.repositoryName === name && (r.repositoryTag === options.tag || !options.tag)
        );

        if (!targetRepository) {
          throw new ValidationError(t('errors.repositoryNotFound', { name, tag: options.tag }));
        }

        validateGrandRepoDeletion(targetRepository, allRepositories);

        if (!options.force) {
          const confirmed = await confirmDeletion(targetRepository, name, options.tag);
          if (!confirmed) {
            outputService.info(t('prompts.cancelled'));
            return;
          }
        }

        await withSpinner(
          t('commands.repository.delete.deleting', { name, tag: options.tag }),
          () =>
            typedApi.DeleteRepository({
              teamName: opts.team as string,
              repositoryName: name,
              repositoryTag: options.tag,
            }),
          t('commands.repository.delete.success', { name, tag: options.tag })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // repository promote - enhanced with shared orchestration
  repository
    .command('promote <name>')
    .description(t('commands.repository.promote.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('--tag <tag>', t('options.repositoryTag'), DEFAULT_REPOSITORY_TAG)
    .option('-f, --force', t('options.force'))
    .action(async (name, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        // Fetch all repositories to validate promotion
        const apiResponse = await withSpinner(
          t('commands.repository.promote.checkingRelationships'),
          () => typedApi.GetTeamRepositories({ teamName: opts.team as string }),
          t('commands.repository.promote.relationshipsChecked')
        );

        const allRepositories = parseGetTeamRepositories(apiResponse as never);

        // Find the target repo
        const targetRepository = allRepositories.find(
          (r: RepositoryWithRelations) =>
            r.repositoryName === name && (r.repositoryTag === options.tag || !options.tag)
        );

        if (!targetRepository) {
          throw new ValidationError(t('errors.repositoryNotFound', { name, tag: options.tag }));
        }

        // Use shared orchestration to validate promotion
        const validation = canPromoteToGrand(targetRepository);

        if (!validation.canPromote) {
          throw new ValidationError(t('errors.cannotPromote', { reason: validation.reason }));
        }

        // Find and display affected siblings
        const { siblingClones, currentGrandName } = findSiblingClones(
          targetRepository,
          allRepositories
        );

        if (!options.force && siblingClones.length > 0) {
          outputService.info(
            t('commands.repository.promote.separateInfo', { name, grandName: currentGrandName })
          );
          outputService.info(
            t('commands.repository.promote.siblingsInfo', { count: siblingClones.length })
          );
          siblingClones.forEach((sibling) => {
            outputService.info(
              `  - ${sibling.repositoryName}${sibling.repositoryTag ? `:${sibling.repositoryTag}` : ''}`
            );
          });

          const { askConfirm } = await import('../utils/prompt.js');
          const confirm = await askConfirm(t('commands.repository.promote.confirmPromote'));
          if (!confirm) {
            outputService.info(t('prompts.cancelled'));
            return;
          }
        }

        await withSpinner(
          t('commands.repository.promote.promoting', { name, tag: options.tag }),
          () =>
            typedApi.PromoteRepositoryToGrand({
              teamName: opts.team as string,
              repositoryName: name,
            }),
          t('commands.repository.promote.success', { name, tag: options.tag })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // repository vault subcommand
  const vault = repository.command('vault').description(t('commands.repository.vault.description'));

  // repository vault get
  vault
    .command('get <repositoryName>')
    .description(t('commands.repository.vault.get.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('--tag <tag>', t('options.repositoryTag'), DEFAULT_REPOSITORY_TAG)
    .action(async (repositoryName, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const response = await withSpinner(
          t('commands.repository.vault.get.fetching'),
          () => typedApi.GetOrganizationVaults({}),
          t('commands.repository.vault.get.success')
        );

        const vaults = parseGetOrganizationVaults(
          response as never
        ) as unknown as (GetOrganizationVaults_ResultSet1 & {
          vaultType?: string;
          teamName?: string;
          repositoryName?: string;
          repositoryTag?: string;
        })[];

        const repositoryVault = vaults.find(
          (vault) =>
            vault.vaultType === 'Repository' &&
            vault.teamName === opts.team &&
            vault.repositoryName === repositoryName &&
            vault.repositoryTag === options.tag
        );
        const format = program.opts().output as OutputFormat;

        if (repositoryVault) {
          outputService.print(repositoryVault, format);
        } else {
          outputService.info(t('commands.repository.vault.get.notFound'));
        }
      } catch (error) {
        handleError(error);
      }
    });

  // repository vault update
  vault
    .command('update <repositoryName>')
    .description(t('commands.repository.vault.update.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('--tag <tag>', t('options.repositoryTag'), DEFAULT_REPOSITORY_TAG)
    .option('--vault <json>', t('options.vaultJson'))
    .option('--vault-version <n>', t('options.vaultVersion'), Number.parseInt)
    .action(async (repositoryName, options) => {
      try {
        await authService.requireAuth();
        const opts = await contextService.applyDefaults(options);

        if (!opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
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
          throw new ValidationError(t('errors.vaultDataRequired'));
        }

        if (options.vaultVersion === undefined || options.vaultVersion === null) {
          throw new ValidationError(t('errors.vaultVersionRequired'));
        }

        // Validate JSON
        try {
          JSON.parse(vaultData);
        } catch {
          throw new ValidationError(t('errors.invalidJsonVault'));
        }

        await withSpinner(
          t('commands.repository.vault.update.updating'),
          () =>
            typedApi.UpdateRepositoryVault({
              teamName: opts.team as string,
              repositoryName,
              repositoryTag: options.tag,
              vaultContent: vaultData,
              vaultVersion: options.vaultVersion,
            }),
          t('commands.repository.vault.update.success')
        );
      } catch (error) {
        handleError(error);
      }
    });
}

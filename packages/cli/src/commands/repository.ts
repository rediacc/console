import { Command } from 'commander';
import { parseGetOrganizationVaults, parseGetTeamRepositories } from '@rediacc/shared/api';
import { DEFAULT_REPOSITORY_TAG } from '@rediacc/shared/api/typedApi/defaults';
import {
  canPromoteToGrand,
  findSiblingClones,
  type RepositoryWithRelations,
} from '@rediacc/shared/services/repository';
import type { GetOrganizationVaults_ResultSet1 } from '@rediacc/shared/types';
import { getOrCreateCommand } from './bridge-utils.js';
import { t } from '../i18n/index.js';
import { typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { addCloudOnlyGuard, markCloudOnly } from '../utils/cloud-guard.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import type { OutputFormat } from '../types/index.js';

export function registerRepositoryMetadataCommands(program: Command): void {
  const repository = getOrCreateCommand(
    program,
    'repository',
    t('commands.repository.description')
  );

  // repository rename (cloud-only)
  const renameCmd = repository
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
  addCloudOnlyGuard(renameCmd);
  markCloudOnly(renameCmd);

  // repository promote (cloud-only)
  const promoteCmd = repository
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
  addCloudOnlyGuard(promoteCmd);
  markCloudOnly(promoteCmd);

  // repository vault subcommand (cloud-only)
  const vault = repository.command('vault').description(t('commands.repository.vault.description'));
  addCloudOnlyGuard(vault);
  markCloudOnly(vault);

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

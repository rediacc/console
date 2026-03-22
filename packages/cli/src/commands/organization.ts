import {
  extractFirstByIndex,
  parseGetOrganizationDashboard,
  parseGetOrganizationVault,
  parseGetOrganizationVaults,
} from '@rediacc/shared/api';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { outputService } from '../services/output.js';
import type { OutputFormat } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
export function registerOrganizationCommands(program: Command): void {
  const organization = program
    .command('organization')
    .description(t('commands.organization.description'));

  // organization info
  organization
    .command('info')
    .description(t('commands.organization.info.description'))
    .action(async () => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          t('commands.organization.info.fetching'),
          () => typedApi.GetUserOrganization({}),
          t('commands.organization.info.success')
        );

        // Extract organization info from first row
        const info = extractFirstByIndex(apiResponse as never, 0);
        const format = program.opts().output as OutputFormat;

        if (info) {
          outputService.print(info, format);
        } else {
          outputService.info(t('commands.organization.info.notFound'));
        }
      } catch (error) {
        handleError(error);
      }
    });

  // organization dashboard
  organization
    .command('dashboard')
    .description(t('commands.organization.dashboard.description'))
    .action(async () => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          t('commands.organization.dashboard.fetching'),
          () => typedApi.GetOrganizationDashboard({}),
          t('commands.organization.dashboard.success')
        );

        const dashboard = parseGetOrganizationDashboard(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(dashboard, format);
      } catch (error) {
        handleError(error);
      }
    });

  // organization vault subcommand
  const vault = organization
    .command('vault')
    .description(t('commands.organization.vault.description'));

  // organization vault get
  vault
    .command('get')
    .description(t('commands.organization.vault.get.description'))
    .action(async () => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          t('commands.organization.vault.get.fetching'),
          () => typedApi.GetOrganizationVault({}),
          t('commands.organization.vault.get.success')
        );

        const vaultData = parseGetOrganizationVault(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        if (vaultData?.vaultContent) {
          outputService.print(vaultData, format);
        } else {
          outputService.info(t('commands.organization.vault.get.notFound'));
        }
      } catch (error) {
        handleError(error);
      }
    });

  // organization vault list
  vault
    .command('list')
    .description(t('commands.organization.vault.list.description'))
    .action(async () => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          t('commands.organization.vault.list.fetching'),
          () => typedApi.GetOrganizationVaults({}),
          t('commands.organization.vault.list.success')
        );

        const vaults = parseGetOrganizationVaults(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(vaults, format);
      } catch (error) {
        handleError(error);
      }
    });

  // organization vault update
  vault
    .command('update')
    .description(t('commands.organization.vault.update.description'))
    .option('--vault <json>', t('options.vaultJson'))
    .option('--vault-version <n>', t('options.vaultVersion'), Number.parseInt)
    .action(async (options: { vault?: string; vaultVersion?: number }) => {
      try {
        await authService.requireAuth();

        // Get vault data from --vault flag or stdin
        let vaultData: string = options.vault ?? '';
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

        if (options.vaultVersion == null) {
          throw new ValidationError(t('errors.vaultVersionRequired'));
        }

        // Validate JSON
        try {
          JSON.parse(vaultData);
        } catch {
          throw new ValidationError(t('errors.invalidJsonVault'));
        }

        await withSpinner(
          t('commands.organization.vault.update.updating'),
          () =>
            typedApi.UpdateOrganizationVault({
              vaultContent: vaultData,
              vaultVersion: options.vaultVersion as number,
            }),
          t('commands.organization.vault.update.success')
        );
      } catch (error) {
        handleError(error);
      }
    });

  // organization export
  organization
    .command('export')
    .description(t('commands.organization.export.description'))
    .option('--path <path>', t('options.outputPath'))
    .action(async (options: { path?: string }) => {
      try {
        await authService.requireAuth();

        const exportData = await withSpinner(
          t('commands.organization.export.exporting'),
          () => typedApi.ExportOrganizationData({}),
          t('commands.organization.export.success')
        );

        if (options.path) {
          const { promises: fs } = await import('node:fs');
          await fs.writeFile(options.path, JSON.stringify(exportData, null, 2));
          outputService.success(t('commands.organization.export.exported', { path: options.path }));
        } else {
          const format = program.opts().output as OutputFormat;
          outputService.print(exportData, format);
        }
      } catch (error) {
        handleError(error);
      }
    });

  // organization import
  organization
    .command('import <path>')
    .description(t('commands.organization.import.description'))
    .option('--mode <mode>', t('options.importMode'), 'merge')
    .action(async (path: string, options: { mode: string }) => {
      try {
        await authService.requireAuth();

        const { promises: fs } = await import('node:fs');
        const content = await fs.readFile(path, 'utf-8');
        try {
          JSON.parse(content);
        } catch {
          throw new Error(t('errors.invalidJsonFile'));
        }

        await withSpinner(
          t('commands.organization.import.importing'),
          () =>
            typedApi.ImportOrganizationData({
              organizationDataJson: content,
              importMode: options.mode,
            }),
          t('commands.organization.import.success')
        );
      } catch (error) {
        handleError(error);
      }
    });

  // organization maintenance
  organization
    .command('maintenance <action>')
    .description(t('commands.organization.maintenance.description'))
    .action(async (action: string) => {
      try {
        await authService.requireAuth();

        const validActions = ['enable', 'disable'];
        if (!validActions.includes(action)) {
          throw new ValidationError(
            t('errors.invalidAction', { action, valid: validActions.join(', ') })
          );
        }

        const enable = action === 'enable';

        await withSpinner(
          enable
            ? t('commands.organization.maintenance.enabling')
            : t('commands.organization.maintenance.disabling'),
          () => typedApi.UpdateOrganizationBlockUserRequests({ blockUserRequests: enable }),
          enable
            ? t('commands.organization.maintenance.enabled')
            : t('commands.organization.maintenance.disabled')
        );
      } catch (error) {
        handleError(error);
      }
    });
}

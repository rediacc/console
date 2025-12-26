import { Command } from 'commander';
import {
  parseGetCompanyVault,
  parseGetCompanyVaults,
  parseGetCompanyDashboardJson,
  extractFirstByIndex,
} from '@rediacc/shared/api';
import { typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import type { OutputFormat } from '../types/index.js';
export function registerCompanyCommands(program: Command): void {
  const company = program.command('company').description('Company management commands');

  // company info
  company
    .command('info')
    .description('Get company information')
    .action(async () => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          'Fetching company info...',
          () => typedApi.GetUserCompany({}),
          'Company info fetched'
        );

        // Extract company info from first row
        const info = extractFirstByIndex(apiResponse as never, 0);
        const format = program.opts().output as OutputFormat;

        if (info) {
          outputService.print(info, format);
        } else {
          outputService.info('No company info found');
        }
      } catch (error) {
        handleError(error);
      }
    });

  // company dashboard
  company
    .command('dashboard')
    .description('Get company dashboard data')
    .action(async () => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          'Fetching dashboard...',
          () => typedApi.GetCompanyDashboardJson({}),
          'Dashboard fetched'
        );

        const dashboard = parseGetCompanyDashboardJson(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(dashboard, format);
      } catch (error) {
        handleError(error);
      }
    });

  // company vault subcommand
  const vault = company.command('vault').description('Company vault management');

  // company vault get
  vault
    .command('get')
    .description('Get company vault data')
    .action(async () => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          'Fetching company vault...',
          () => typedApi.GetCompanyVault({}),
          'Vault fetched'
        );

        const vaultData = parseGetCompanyVault(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        if (vaultData?.vaultContent) {
          outputService.print(vaultData, format);
        } else {
          outputService.info('No company vault found');
        }
      } catch (error) {
        handleError(error);
      }
    });

  // company vault list
  vault
    .command('list')
    .description('List all vault types')
    .action(async () => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          'Fetching vaults...',
          () => typedApi.GetCompanyVaults({}),
          'Vaults fetched'
        );

        const vaults = parseGetCompanyVaults(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        outputService.print(vaults, format);
      } catch (error) {
        handleError(error);
      }
    });

  // company vault update
  vault
    .command('update')
    .description('Update company vault data')
    .option('--vault <json>', 'Vault data as JSON string')
    .option(
      '--vault-version <n>',
      'Current vault version (required for optimistic concurrency)',
      parseInt
    )
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
          throw new ValidationError(
            'Vault data required. Use --vault <json> or pipe JSON via stdin.'
          );
        }

        if (options.vaultVersion == null) {
          throw new ValidationError('Vault version required. Use --vault-version <n>.');
        }

        // Validate JSON
        try {
          JSON.parse(vaultData);
        } catch {
          throw new ValidationError('Invalid JSON vault data.');
        }

        await withSpinner(
          'Updating company vault...',
          () =>
            typedApi.UpdateCompanyVault({
              vaultContent: vaultData,
              vaultVersion: options.vaultVersion as number,
            }),
          'Company vault updated'
        );
      } catch (error) {
        handleError(error);
      }
    });

  // company export
  company
    .command('export')
    .description('Export company data')
    .option('--path <path>', 'Output file path')
    .action(async (options: { path?: string }) => {
      try {
        await authService.requireAuth();

        const exportData = await withSpinner(
          'Exporting company data...',
          () => typedApi.ExportCompanyData({}),
          'Export complete'
        );

        if (options.path) {
          const { promises: fs } = await import('node:fs');
          await fs.writeFile(options.path, JSON.stringify(exportData, null, 2));
          outputService.success(`Exported to ${options.path}`);
        } else {
          const format = program.opts().output as OutputFormat;
          outputService.print(exportData, format);
        }
      } catch (error) {
        handleError(error);
      }
    });

  // company import
  company
    .command('import <path>')
    .description('Import company data')
    .option('--mode <mode>', 'Import mode (merge|replace)', 'merge')
    .action(async (path: string, options: { mode: string }) => {
      try {
        await authService.requireAuth();

        const { promises: fs } = await import('node:fs');
        const content = await fs.readFile(path, 'utf-8');
        try {
          JSON.parse(content);
        } catch {
          throw new Error('The provided file does not contain valid JSON.');
        }

        await withSpinner(
          'Importing company data...',
          () => typedApi.ImportCompanyData({ companyDataJson: content, importMode: options.mode }),
          'Import complete'
        );
      } catch (error) {
        handleError(error);
      }
    });

  // company maintenance
  company
    .command('maintenance <action>')
    .description('Enable or disable maintenance mode (blocks non-admin logins)')
    .action(async (action: string) => {
      try {
        await authService.requireAuth();

        const validActions = ['enable', 'disable'];
        if (!validActions.includes(action)) {
          throw new ValidationError(`Invalid action "${action}". Use "enable" or "disable".`);
        }

        const enable = action === 'enable';

        await withSpinner(
          `${enable ? 'Enabling' : 'Disabling'} maintenance mode...`,
          () => typedApi.UpdateCompanyBlockUserRequests({ blockUserRequests: enable }),
          `Maintenance mode ${enable ? 'enabled' : 'disabled'}`
        );
      } catch (error) {
        handleError(error);
      }
    });
}

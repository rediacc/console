import { Command } from 'commander';
import { api } from '../services/api.js';
import { authService } from '../services/auth.js';
import { outputService } from '../services/output.js';
import { handleError } from '../utils/errors.js';
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

        const info = await withSpinner(
          'Fetching company info...',
          () => api.company.getInfo(),
          'Company info fetched'
        );

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

        const dashboard = await withSpinner(
          'Fetching dashboard...',
          () => api.company.getDashboard(),
          'Dashboard fetched'
        );

        const format = program.opts().output as OutputFormat;

        if (dashboard) {
          outputService.print(dashboard, format);
        } else {
          outputService.info('No dashboard data found');
        }
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

        const vaultData = await withSpinner(
          'Fetching company vault...',
          () => api.company.getVault(),
          'Vault fetched'
        );

        const format = program.opts().output as OutputFormat;

        if (vaultData?.vault) {
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

        const vaults = await withSpinner(
          'Fetching vaults...',
          () => api.company.getAllVaults(),
          'Vaults fetched'
        );

        const format = program.opts().output as OutputFormat;

        outputService.print(vaults.vaults, format);
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
    .action(async (options) => {
      try {
        await authService.requireAuth();

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
          outputService.error('Vault data required. Use --vault <json> or pipe JSON via stdin.');
          process.exit(1);
        }

        if (options.vaultVersion === undefined || options.vaultVersion === null) {
          outputService.error('Vault version required. Use --vault-version <n>.');
          process.exit(1);
        }

        // Validate JSON
        try {
          JSON.parse(vaultData);
        } catch {
          outputService.error('Invalid JSON vault data.');
          process.exit(1);
        }

        await withSpinner(
          'Updating company vault...',
          () =>
            api.company.updateVault({
              vaultContent: vaultData,
              vaultVersion: options.vaultVersion,
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
    .action(async (options) => {
      try {
        await authService.requireAuth();

        const exportData = await withSpinner(
          'Exporting company data...',
          () => api.company.exportData(),
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
    .action(async (path, options) => {
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
          () => api.company.importData({ companyDataJson: content, importMode: options.mode }),
          'Import complete'
        );
      } catch (error) {
        handleError(error);
      }
    });
}

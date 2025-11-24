import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { apiClient } from '../services/api.js'
import { outputService } from '../services/output.js'
import { withSpinner } from '../utils/spinner.js'
import { handleError } from '../utils/errors.js'
import type { OutputFormat } from '../types/index.js'

export function registerCompanyCommands(program: Command): void {
  const company = program
    .command('company')
    .description('Company management commands')

  // company info
  company
    .command('info')
    .description('Get company information')
    .action(async () => {
      try {
        await authService.requireAuth()

        const response = await withSpinner(
          'Fetching company info...',
          () => apiClient.get('/GetUserCompany', {}),
          'Company info fetched'
        )

        const info = response.resultSets?.[0]?.data?.[0]
        const format = program.opts().output as OutputFormat

        if (info) {
          outputService.print(info, format)
        } else {
          outputService.info('No company info found')
        }
      } catch (error) {
        handleError(error)
      }
    })

  // company dashboard
  company
    .command('dashboard')
    .description('Get company dashboard data')
    .action(async () => {
      try {
        await authService.requireAuth()

        const response = await withSpinner(
          'Fetching dashboard...',
          () => apiClient.get('/GetCompanyDashboardJson', {}),
          'Dashboard fetched'
        )

        const dashboard = response.resultSets?.[0]?.data?.[0]
        const format = program.opts().output as OutputFormat

        if (dashboard) {
          outputService.print(dashboard, format)
        } else {
          outputService.info('No dashboard data found')
        }
      } catch (error) {
        handleError(error)
      }
    })

  // company vault subcommand
  const vault = company
    .command('vault')
    .description('Company vault management')

  // company vault get
  vault
    .command('get')
    .description('Get company vault data')
    .action(async () => {
      try {
        await authService.requireAuth()

        const response = await withSpinner(
          'Fetching company vault...',
          () => apiClient.get('/GetCompanyVault', {}),
          'Vault fetched'
        )

        const vaultData = response.resultSets?.[0]?.data?.[0]
        const format = program.opts().output as OutputFormat

        if (vaultData) {
          outputService.print(vaultData, format)
        } else {
          outputService.info('No company vault found')
        }
      } catch (error) {
        handleError(error)
      }
    })

  // company vault list
  vault
    .command('list')
    .description('List all vault types')
    .action(async () => {
      try {
        await authService.requireAuth()

        const response = await withSpinner(
          'Fetching vaults...',
          () => apiClient.get('/GetCompanyVaults', {}),
          'Vaults fetched'
        )

        const vaults = response.resultSets?.[0]?.data || []
        const format = program.opts().output as OutputFormat

        outputService.print(vaults, format)
      } catch (error) {
        handleError(error)
      }
    })

  // company export
  company
    .command('export')
    .description('Export company data')
    .option('--path <path>', 'Output file path')
    .action(async (options) => {
      try {
        await authService.requireAuth()

        const response = await withSpinner(
          'Exporting company data...',
          () => apiClient.get('/ExportCompanyData', {}),
          'Export complete'
        )

        const exportData = response.resultSets?.[0]?.data?.[0]

        if (options.path) {
          const { promises: fs } = await import('node:fs')
          await fs.writeFile(options.path, JSON.stringify(exportData, null, 2))
          outputService.success(`Exported to ${options.path}`)
        } else {
          const format = program.opts().output as OutputFormat
          outputService.print(exportData, format)
        }
      } catch (error) {
        handleError(error)
      }
    })

  // company import
  company
    .command('import <path>')
    .description('Import company data')
    .option('--mode <mode>', 'Import mode (merge|replace)', 'merge')
    .action(async (path, options) => {
      try {
        await authService.requireAuth()

        const { promises: fs } = await import('node:fs')
        const content = await fs.readFile(path, 'utf-8')
        const importData = JSON.parse(content)

        await withSpinner(
          'Importing company data...',
          () => apiClient.post('/ImportCompanyData', {
            data: importData,
            mode: options.mode,
          }),
          'Import complete'
        )
      } catch (error) {
        handleError(error)
      }
    })
}

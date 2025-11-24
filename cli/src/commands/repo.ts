import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { apiClient } from '../services/api.js'
import { contextService } from '../services/context.js'
import { outputService } from '../services/output.js'
import { withSpinner } from '../utils/spinner.js'
import { handleError } from '../utils/errors.js'
import type { OutputFormat } from '../types/index.js'

export function registerRepoCommands(program: Command): void {
  const repo = program
    .command('repo')
    .description('Repository management commands')

  // repo list
  repo
    .command('list')
    .description('List repositories')
    .option('-t, --team <name>', 'Team name')
    .action(async (options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        const response = await withSpinner(
          'Fetching repositories...',
          () => apiClient.get('/GetTeamRepositories', { teamName: opts.team }),
          'Repositories fetched'
        )

        const repos = response.resultSets?.[0]?.data || []
        const format = program.opts().output as OutputFormat

        outputService.print(repos, format)
      } catch (error) {
        handleError(error)
      }
    })

  // repo create
  repo
    .command('create <name>')
    .description('Create a new repository')
    .option('-t, --team <name>', 'Team name')
    .option('--tag <tag>', 'Repository tag', 'main')
    .option('--parent <name>', 'Parent repository (for forks)')
    .option('--parent-tag <tag>', 'Parent repository tag')
    .action(async (name, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        const params: Record<string, string> = {
          repoName: name,
          repoTag: options.tag,
          teamName: opts.team!,
        }

        if (options.parent) {
          params.parentRepoName = options.parent
          params.parentRepoTag = options.parentTag || 'main'
        }

        await withSpinner(
          `Creating repository "${name}:${options.tag}"...`,
          () => apiClient.post('/CreateRepository', params),
          `Repository "${name}:${options.tag}" created`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // repo rename
  repo
    .command('rename <oldName> <newName>')
    .description('Rename a repository')
    .option('-t, --team <name>', 'Team name')
    .option('--tag <tag>', 'Repository tag', 'main')
    .action(async (oldName, newName, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        await withSpinner(
          `Renaming repository "${oldName}" to "${newName}"...`,
          () => apiClient.post('/UpdateRepositoryName', {
            currentRepoName: oldName,
            newRepoName: newName,
            repoTag: options.tag,
            teamName: opts.team,
          }),
          `Repository renamed to "${newName}"`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // repo delete
  repo
    .command('delete <name>')
    .description('Delete a repository')
    .option('-t, --team <name>', 'Team name')
    .option('--tag <tag>', 'Repository tag', 'main')
    .option('-f, --force', 'Skip confirmation')
    .action(async (name, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        if (!options.force) {
          const { askConfirm } = await import('../utils/prompt.js')
          const confirm = await askConfirm(`Delete repository "${name}:${options.tag}"? This cannot be undone.`)
          if (!confirm) {
            outputService.info('Cancelled')
            return
          }
        }

        await withSpinner(
          `Deleting repository "${name}:${options.tag}"...`,
          () => apiClient.post('/DeleteRepository', {
            repoName: name,
            repoTag: options.tag,
            teamName: opts.team,
          }),
          `Repository "${name}:${options.tag}" deleted`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // repo promote
  repo
    .command('promote <name>')
    .description('Promote a fork to grand status')
    .option('-t, --team <name>', 'Team name')
    .option('--tag <tag>', 'Repository tag', 'main')
    .action(async (name, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        await withSpinner(
          `Promoting repository "${name}:${options.tag}"...`,
          () => apiClient.post('/PromoteRepositoryToGrand', {
            repoName: name,
            repoTag: options.tag,
            teamName: opts.team,
          }),
          `Repository "${name}:${options.tag}" promoted`
        )
      } catch (error) {
        handleError(error)
      }
    })

  // repo vault subcommand
  const vault = repo
    .command('vault')
    .description('Repository vault management')

  // repo vault get
  vault
    .command('get <repoName>')
    .description('Get repository vault data')
    .option('-t, --team <name>', 'Team name')
    .option('--tag <tag>', 'Repository tag', 'main')
    .action(async (repoName, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        const response = await withSpinner(
          'Fetching repository vault...',
          () => apiClient.get('/GetCompanyVaults', {
            teamName: opts.team,
            repositoryName: repoName,
            repoTag: options.tag,
          }),
          'Vault fetched'
        )

        const vaults = response.resultSets?.[0]?.data || []
        const repoVault = vaults.find((v: any) => v.vaultType === 'Repository')
        const format = program.opts().output as OutputFormat

        if (repoVault) {
          outputService.print(repoVault, format)
        } else {
          outputService.info('No repository vault found')
        }
      } catch (error) {
        handleError(error)
      }
    })
}

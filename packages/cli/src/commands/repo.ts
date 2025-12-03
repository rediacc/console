import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { api } from '../services/api.js'
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

        const repos = await withSpinner(
          'Fetching repositories...',
          () => api.repos.list(opts.team as string),
          'Repositories fetched'
        )

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

        const createOptions: {
          repoTag?: string
          parentRepoName?: string
          parentRepoTag?: string
        } = {
          repoTag: options.tag,
        }
        if (options.parent) {
          createOptions.parentRepoName = options.parent
          createOptions.parentRepoTag = options.parentTag || 'main'
        }

        await withSpinner(
          `Creating repository "${name}:${options.tag}"...`,
          () => api.repos.create(opts.team as string, name, createOptions),
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
          () => api.repos.rename(opts.team as string, oldName, newName),
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
          () => api.repos.delete(opts.team as string, name, options.tag),
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
          () => api.repos.promoteToGrand(opts.team as string, name),
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

        const vaultsResponse = await withSpinner(
          'Fetching repository vault...',
          () => api.company.getAllVaults({
            teamName: opts.team,
            repoName,
            repoTag: options.tag,
          }),
          'Vault fetched'
        )

        const repoVault = vaultsResponse.vaults.find((v: any) => v.vaultType === 'Repository')
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

  // repo vault update
  vault
    .command('update <repoName>')
    .description('Update repository vault data')
    .option('-t, --team <name>', 'Team name')
    .option('--tag <tag>', 'Repository tag', 'main')
    .option('--vault <json>', 'Vault data as JSON string')
    .option('--vault-version <n>', 'Current vault version (required for optimistic concurrency)', parseInt)
    .action(async (repoName, options) => {
      try {
        await authService.requireAuth()
        const opts = await contextService.applyDefaults(options)

        if (!opts.team) {
          outputService.error('Team name required. Use --team or set context.')
          process.exit(1)
        }

        // Get vault data from --vault flag or stdin
        let vaultData: string = options.vault
        if (!vaultData && !process.stdin.isTTY) {
          // Read from stdin if not a TTY (piped input)
          const chunks: Buffer[] = []
          for await (const chunk of process.stdin) {
            chunks.push(chunk)
          }
          vaultData = Buffer.concat(chunks).toString('utf-8').trim()
        }

        if (!vaultData) {
          outputService.error('Vault data required. Use --vault <json> or pipe JSON via stdin.')
          process.exit(1)
        }

        if (options.vaultVersion === undefined || options.vaultVersion === null) {
          outputService.error('Vault version required. Use --vault-version <n>.')
          process.exit(1)
        }

        // Validate JSON
        try {
          JSON.parse(vaultData)
        } catch {
          outputService.error('Invalid JSON vault data.')
          process.exit(1)
        }

        await withSpinner(
          'Updating repository vault...',
          () => api.repos.updateVault(
            opts.team as string,
            repoName,
            vaultData,
            options.vaultVersion,
          ),
          'Repository vault updated'
        )
      } catch (error) {
        handleError(error)
      }
    })
}




import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { api } from '../services/api.js'
import { outputService } from '../services/output.js'
import { withSpinner } from '../utils/spinner.js'
import { handleError } from '../utils/errors.js'
import type { OutputFormat } from '../types/index.js'
export function registerUserCommands(program: Command): void {
  const user = program
    .command('user')
    .description('User management commands')

  // user list
  user
    .command('list')
    .description('List all users')
    .action(async () => {
      try {
        await authService.requireAuth()

        const users = await withSpinner(
          'Fetching users...',
          () => api.users.list(),
          'Users fetched'
        )

        const format = program.opts().output as OutputFormat

        outputService.print(users, format)
      } catch (error) {
        handleError(error)
      }
    })

  // user create
  user
    .command('create <email>')
    .description('Create a new user')
    .option('-n, --name <name>', 'User full name')
    .action(async (email, options) => {
      try {
        await authService.requireAuth()

        const result = await withSpinner(
          `Creating user "${email}"...`,
          () => api.users.create(
            email,
            undefined,
            { fullName: options.name || email.split('@')[0] },
          ),
          'User created'
        )

        if (result.activationCode) {
          outputService.success(`Activation code: ${result.activationCode}`)
        }
      } catch (error) {
        handleError(error)
      }
    })

  // user activate
  user
    .command('activate <email> <activationCode>')
    .description('Activate a user account')
    .action(async (email, activationCode) => {
      try {
        const { askPassword } = await import('../utils/prompt.js')
        const password = await askPassword('Set password for user:')
        const confirmPassword = await askPassword('Confirm password:')

        if (password !== confirmPassword) {
          outputService.error('Passwords do not match')
          process.exit(1)
        }

        const { nodeCryptoProvider } = await import('../adapters/crypto.js')
        const passwordHash = await nodeCryptoProvider.generateHash(password)

        await withSpinner(
          `Activating user "${email}"...`,
          () => api.auth.activateAccount(email, activationCode, passwordHash),
          'User activated'
        )
      } catch (error) {
        handleError(error)
      }
    })

  // user deactivate
  user
    .command('deactivate <email>')
    .description('Deactivate a user account')
    .option('-f, --force', 'Skip confirmation')
    .action(async (email, options) => {
      try {
        await authService.requireAuth()

        if (!options.force) {
          const { askConfirm } = await import('../utils/prompt.js')
          const confirm = await askConfirm(`Deactivate user "${email}"?`)
          if (!confirm) {
            outputService.info('Cancelled')
            return
          }
        }

        await withSpinner(
          `Deactivating user "${email}"...`,
          () => api.users.deactivate(email),
          'User deactivated'
        )
      } catch (error) {
        handleError(error)
      }
    })

  // user exists
  user
    .command('exists <email>')
    .description('Check if a user exists')
    .action(async (email) => {
      try {
        const status = await api.auth.checkRegistration(email)

        if (status.isRegistered) {
          outputService.success(`User "${email}" exists`)
        } else {
          outputService.info(`User "${email}" does not exist`)
        }
      } catch (error) {
        handleError(error)
      }
    })

  // user vault subcommand
  const vault = user
    .command('vault')
    .description('User vault management')

  // user vault get
  vault
    .command('get')
    .description('Get current user vault data')
    .action(async () => {
      try {
        await authService.requireAuth()

        const vaultData = await withSpinner(
          'Fetching user vault...',
          () => api.users.getVault(),
          'Vault fetched'
        )

        const format = program.opts().output as OutputFormat

        if (vaultData) {
          outputService.print(vaultData, format)
        } else {
          outputService.info('No user vault found')
        }
      } catch (error) {
        handleError(error)
      }
    })

  // user vault update
  vault
    .command('update')
    .description('Update current user vault data')
    .option('--vault <json>', 'Vault data as JSON string')
    .option('--vault-version <n>', 'Current vault version (required for optimistic concurrency)', parseInt)
    .action(async (options) => {
      try {
        await authService.requireAuth()

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
          'Updating user vault...',
          () => api.users.updateVault(vaultData, options.vaultVersion),
          'User vault updated'
        )
      } catch (error) {
        handleError(error)
      }
    })

  // user permission subcommand
  const permission = user
    .command('permission')
    .description('User permission management')

  // user permission assign
  permission
    .command('assign <userEmail> <groupName>')
    .description('Assign a permission group to a user')
    .action(async (userEmail, groupName) => {
      try {
        await authService.requireAuth()

        await withSpinner(
          `Assigning "${groupName}" to user "${userEmail}"...`,
          () => api.users.assignPermissions(userEmail, groupName),
          'Permission assigned'
        )
      } catch (error) {
        handleError(error)
      }
    })
}

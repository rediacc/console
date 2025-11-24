import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { apiClient } from '../services/api.js'
import { outputService } from '../services/output.js'
import { withSpinner } from '../utils/spinner.js'
import { handleError } from '../utils/errors.js'
import type { OutputFormat } from '../types/index.js'
import { getFirstRow, type UserResponse } from '../types/api-responses.js'

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

        const response = await withSpinner(
          'Fetching users...',
          () => apiClient.get('/GetCompanyUsers', {}),
          'Users fetched'
        )

        const users = response.resultSets?.[0]?.data || []
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

        const response = await withSpinner(
          `Creating user "${email}"...`,
          () => apiClient.post('/CreateNewUser', {
            userEmail: email,
            fullName: options.name || email.split('@')[0],
          }),
          'User created'
        )

        const data = getFirstRow<UserResponse>(response.resultSets)
        if (data?.activationCode) {
          outputService.success(`Activation code: ${data.activationCode}`)
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
          () => apiClient.activateUser(email, activationCode, passwordHash),
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
          () => apiClient.post('/UpdateUserToDeactivated', { userEmail: email }),
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
        const response = await apiClient.get('/IsRegistered', { userEmail: email })
        const data = getFirstRow<UserResponse>(response.resultSets)

        if (data?.isRegistered) {
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

        const response = await withSpinner(
          'Fetching user vault...',
          () => apiClient.get('/GetUserVault', {}),
          'Vault fetched'
        )

        const vaultData = response.resultSets?.[0]?.data?.[0]
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
          () => apiClient.post('/UpdateUserAssignedPermissions', {
            userEmail,
            permissionGroupName: groupName,
          }),
          'Permission assigned'
        )
      } catch (error) {
        handleError(error)
      }
    })
}

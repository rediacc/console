import { Command } from 'commander'
import { authService } from '../services/auth.js'
import { apiClient } from '../services/api.js'
import { outputService } from '../services/output.js'
import { askText, askPassword, askConfirm } from '../utils/prompt.js'
import { withSpinner } from '../utils/spinner.js'
import { handleError, exitWithSuccess } from '../utils/errors.js'
import type { OutputFormat } from '../types/index.js'
import { getFirstRow, type TokenForkResponse, type TFAResponse } from '../types/api-responses.js'

export function registerAuthCommands(program: Command): void {
  const auth = program
    .command('auth')
    .description('Authentication commands')

  // auth login
  auth
    .command('login')
    .description('Authenticate with Rediacc')
    .option('-e, --email <email>', 'Email address')
    .option('-n, --name <name>', 'Session name')
    .action(async (options) => {
      try {
        // Get email
        const email = options.email || await askText('Email:', {
          validate: (input) => input.includes('@') || 'Please enter a valid email',
        })

        // Get password
        const password = await askPassword('Password:')

        // Attempt login
        const result = await withSpinner(
          'Authenticating...',
          () => authService.login(email, password, { sessionName: options.name }),
          'Authenticated successfully'
        )

        // Handle 2FA if required
        if (result.isTFAEnabled) {
          const tfaCode = await askText('Enter 2FA code:')
          await withSpinner(
            'Verifying 2FA...',
            () => authService.privilegeWithTFA(tfaCode),
            '2FA verified successfully'
          )
        }

        if (!result.success && !result.isTFAEnabled) {
          outputService.error(result.message || 'Authentication failed')
          process.exit(1)
        }

        outputService.success('Login successful!')
      } catch (error) {
        handleError(error)
      }
    })

  // auth logout
  auth
    .command('logout')
    .description('Clear stored credentials')
    .action(async () => {
      try {
        await withSpinner(
          'Logging out...',
          () => authService.logout(),
          'Logged out successfully'
        )
      } catch (error) {
        handleError(error)
      }
    })

  // auth status
  auth
    .command('status')
    .description('Check current authentication status')
    .action(async () => {
      try {
        const isAuth = await authService.isAuthenticated()
        const email = await authService.getStoredEmail()

        if (isAuth) {
          outputService.success(`Authenticated as: ${email || 'unknown'}`)
        } else {
          outputService.warn('Not authenticated. Run: rediacc login')
        }
      } catch (error) {
        handleError(error)
      }
    })

  // auth token subcommand
  const token = auth
    .command('token')
    .description('Token management')

  // auth token list
  token
    .command('list')
    .description('List active tokens/sessions')
    .action(async () => {
      try {
        await authService.requireAuth()
        const response = await withSpinner(
          'Fetching tokens...',
          () => apiClient.get('/GetUserRequests', {}),
          'Tokens fetched'
        )

        const tokens = response.resultSets?.[0]?.data || []
        const format = program.opts().output as OutputFormat

        if (tokens.length === 0) {
          outputService.info('No active tokens')
          return
        }

        outputService.print(tokens, format)
      } catch (error) {
        handleError(error)
      }
    })

  // auth token fork
  token
    .command('fork')
    .description('Create a forked token for another application')
    .option('-n, --name <name>', 'Token name', 'CLI Fork')
    .option('-e, --expires <hours>', 'Expiration in hours', '24')
    .action(async (options) => {
      try {
        await authService.requireAuth()

        const response = await withSpinner(
          'Creating forked token...',
          () => apiClient.post('/ForkAuthenticationRequest', {
            name: options.name,
            expiresInHours: parseInt(options.expires, 10),
          }),
          'Token created'
        )

        // The forked token is in the second result set
        const tokenData = getFirstRow<TokenForkResponse>(response.resultSets, 1)
        if (tokenData?.requestToken) {
          outputService.success(`Token: ${tokenData.requestToken}`)
        } else {
          outputService.info('Token created successfully')
        }
      } catch (error) {
        handleError(error)
      }
    })

  // auth token revoke
  token
    .command('revoke <requestId>')
    .description('Revoke a specific token')
    .action(async (requestId) => {
      try {
        await authService.requireAuth()

        await withSpinner(
          'Revoking token...',
          () => apiClient.post('/DeleteUserRequest', { requestId }),
          'Token revoked'
        )
      } catch (error) {
        handleError(error)
      }
    })

  // auth tfa subcommand
  const tfa = auth
    .command('tfa')
    .description('Two-factor authentication management')

  // auth tfa status
  tfa
    .command('status')
    .description('Check TFA status')
    .action(async () => {
      try {
        await authService.requireAuth()

        const response = await apiClient.post('/UpdateUserTFA', { action: 'status' })
        const data = getFirstRow<TFAResponse>(response.resultSets)

        if (data?.isTFAEnabled) {
          outputService.success('TFA is enabled')
        } else {
          outputService.info('TFA is not enabled')
        }
      } catch (error) {
        handleError(error)
      }
    })

  // auth tfa enable
  tfa
    .command('enable')
    .description('Enable two-factor authentication')
    .action(async () => {
      try {
        await authService.requireAuth()

        const response = await withSpinner(
          'Enabling TFA...',
          () => apiClient.post('/UpdateUserTFA', { action: 'enable' }),
          'TFA setup initiated'
        )

        const data = getFirstRow<TFAResponse>(response.resultSets)
        if (data?.secret) {
          outputService.info(`Setup key: ${data.secret}`)
          outputService.info('Add this to your authenticator app')
        }
      } catch (error) {
        handleError(error)
      }
    })

  // auth tfa disable
  tfa
    .command('disable')
    .description('Disable two-factor authentication')
    .action(async () => {
      try {
        await authService.requireAuth()

        const confirm = await askConfirm('Are you sure you want to disable TFA?')
        if (!confirm) {
          outputService.info('Cancelled')
          return
        }

        await withSpinner(
          'Disabling TFA...',
          () => apiClient.post('/UpdateUserTFA', { action: 'disable' }),
          'TFA disabled'
        )
      } catch (error) {
        handleError(error)
      }
    })

  // Top-level shortcuts
  program
    .command('login')
    .description('Authenticate with Rediacc (shortcut for: auth login)')
    .option('-e, --email <email>', 'Email address')
    .option('-n, --name <name>', 'Session name')
    .action(async (options) => {
      // Forward to auth login
      await auth.commands.find(c => c.name() === 'login')?.parseAsync([
        'node', 'rediacc',
        ...(options.email ? ['-e', options.email] : []),
        ...(options.name ? ['-n', options.name] : []),
      ])
    })

  program
    .command('logout')
    .description('Clear stored credentials (shortcut for: auth logout)')
    .action(async () => {
      // Forward to auth logout
      await auth.commands.find(c => c.name() === 'logout')?.parseAsync(['node', 'rediacc'])
    })
}

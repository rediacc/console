import { Command } from 'commander';
import { api, apiClient } from '../services/api.js';
import { authService } from '../services/auth.js';
import { outputService } from '../services/output.js';
import type { OutputFormat } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { askConfirm, askPassword, askText } from '../utils/prompt.js';
import { withSpinner } from '../utils/spinner.js';
export function registerAuthCommands(program: Command): void {
  const auth = program.command('auth').description('Authentication commands');

  // auth login
  auth
    .command('login')
    .description('Authenticate with Rediacc')
    .option('-e, --email <email>', 'Email address')
    .option('-p, --password <password>', 'Password (for non-interactive login)')
    .option('-n, --name <name>', 'Session name')
    .option('--endpoint <url>', 'API endpoint URL (overrides REDIACC_API_URL)')
    .action(async (options) => {
      try {
        // Set API endpoint if provided
        if (options.endpoint) {
          await apiClient.setApiUrl(options.endpoint);
        }

        // Get email
        const email =
          options.email ??
          (await askText('Email:', {
            validate: (input) => input.includes('@') || 'Please enter a valid email',
          }));

        // Get password (use provided or prompt interactively)
        const password = options.password ?? (await askPassword('Password:'));

        // Attempt login
        const result = await withSpinner(
          'Authenticating...',
          () => authService.login(email, password, { sessionName: options.name }),
          'Authenticated successfully'
        );

        // Handle 2FA if required
        if (result.isTFAEnabled) {
          const tfaCode = await askText('Enter 2FA code:');
          await withSpinner(
            'Verifying 2FA...',
            () => authService.privilegeWithTFA(tfaCode),
            '2FA verified successfully'
          );
        }

        if (!result.success && !result.isTFAEnabled) {
          throw new ValidationError(result.message ?? 'Authentication failed');
        }

        outputService.success('Login successful!');
      } catch (error) {
        handleError(error);
      }
    });

  // auth logout
  auth
    .command('logout')
    .description('Clear stored credentials')
    .action(async () => {
      try {
        await withSpinner('Logging out...', () => authService.logout(), 'Logged out successfully');
      } catch (error) {
        handleError(error);
      }
    });

  // auth status
  auth
    .command('status')
    .description('Check current authentication status')
    .action(async () => {
      try {
        const isAuth = await authService.isAuthenticated();
        const email = await authService.getStoredEmail();

        if (isAuth) {
          outputService.success(`Authenticated as: ${email ?? 'unknown'}`);
        } else {
          outputService.warn('Not authenticated. Run: rediacc login');
        }
      } catch (error) {
        handleError(error);
      }
    });

  // auth register
  auth
    .command('register')
    .description('Register a new company and user account')
    .requiredOption('--company <name>', 'Company name')
    .requiredOption('-e, --email <email>', 'Email address')
    .requiredOption('-p, --password <password>', 'Password')
    .option('--endpoint <url>', 'API endpoint URL (overrides REDIACC_API_URL)')
    .action(async (options) => {
      try {
        // Set API endpoint if provided
        if (options.endpoint) {
          await apiClient.setApiUrl(options.endpoint);
        }

        const result = await withSpinner(
          'Registering account...',
          () => authService.register(options.company, options.email, options.password),
          'Registration submitted'
        );

        if (!result.success) {
          throw new ValidationError(result.message ?? 'Registration failed');
        }

        outputService.success('Registration successful! Check your email for the activation code.');
        outputService.info('Then run: rdc auth activate -e <email> -p <password> --code <code>');
      } catch (error) {
        handleError(error);
      }
    });

  // auth activate
  auth
    .command('activate')
    .description('Activate account with verification code')
    .requiredOption('-e, --email <email>', 'Email address')
    .requiredOption('-p, --password <password>', 'Password')
    .requiredOption('--code <code>', 'Activation code from email')
    .option('--endpoint <url>', 'API endpoint URL (overrides REDIACC_API_URL)')
    .action(async (options) => {
      try {
        // Set API endpoint if provided
        if (options.endpoint) {
          await apiClient.setApiUrl(options.endpoint);
        }

        const result = await withSpinner(
          'Activating account...',
          () => authService.activate(options.email, options.password, options.code),
          'Account activated'
        );

        if (!result.success) {
          throw new ValidationError(result.message ?? 'Activation failed');
        }

        outputService.success('Account activated! You can now login with: rdc login');
      } catch (error) {
        handleError(error);
      }
    });

  // auth token subcommand
  const token = auth.command('token').description('Token management');

  // auth token list
  token
    .command('list')
    .description('List active tokens/sessions')
    .action(async () => {
      try {
        await authService.requireAuth();
        const tokens = await withSpinner(
          'Fetching tokens...',
          () => api.auth.getSessions(),
          'Tokens fetched'
        );

        const format = program.opts().output as OutputFormat;

        if (tokens.length === 0) {
          outputService.info('No active tokens');
          return;
        }

        outputService.print(tokens, format);
      } catch (error) {
        handleError(error);
      }
    });

  // auth token fork
  token
    .command('fork')
    .description('Create a forked token for another application')
    .option('-n, --name <name>', 'Token name', 'CLI Fork')
    .option('-e, --expires <hours>', 'Expiration in hours', '24')
    .action(async (options) => {
      try {
        await authService.requireAuth();

        const credentials = await withSpinner(
          'Creating forked token...',
          () =>
            api.auth.forkSession(options.name, {
              expiresInHours: parseInt(options.expires, 10),
            }),
          'Token created'
        );

        const token = credentials.requestToken ?? credentials.nextRequestToken;
        if (token) {
          outputService.success(`Token: ${token}`);
        } else {
          outputService.info('Token created successfully');
        }
      } catch (error) {
        handleError(error);
      }
    });

  // auth token revoke
  token
    .command('revoke <requestId>')
    .description('Revoke a specific token')
    .action(async (requestId) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          'Revoking token...',
          () => api.auth.terminateSession(requestId),
          'Token revoked'
        );
      } catch (error) {
        handleError(error);
      }
    });

  // auth tfa subcommand
  const tfa = auth.command('tfa').description('Two-factor authentication management');

  // auth tfa status
  tfa
    .command('status')
    .description('Check TFA status')
    .action(async () => {
      try {
        await authService.requireAuth();

        const status = await api.auth.getTfaStatus();

        if (status.isTFAEnabled) {
          outputService.success('TFA is enabled');
        } else {
          outputService.info('TFA is not enabled');
        }
      } catch (error) {
        handleError(error);
      }
    });

  // auth tfa enable
  tfa
    .command('enable')
    .description('Enable two-factor authentication')
    .action(async () => {
      try {
        await authService.requireAuth();

        const tfaSetup = await withSpinner(
          'Enabling TFA...',
          () => api.auth.enableTfa(),
          'TFA setup initiated'
        );

        if (tfaSetup?.secret) {
          outputService.info(`Setup key: ${tfaSetup.secret}`);
          outputService.info('Add this to your authenticator app');
        }
      } catch (error) {
        handleError(error);
      }
    });

  // auth tfa disable
  tfa
    .command('disable')
    .description('Disable two-factor authentication')
    .option('--code <code>', 'Current TFA code for verification')
    .option('-y, --yes', 'Skip confirmation prompt')
    .action(async (options) => {
      try {
        await authService.requireAuth();

        if (!options.yes) {
          const confirm = await askConfirm('Are you sure you want to disable TFA?');
          if (!confirm) {
            outputService.info('Cancelled');
            return;
          }
        }

        // If code provided, pass it; otherwise use default flow
        const code = options.code ?? undefined;
        await withSpinner(
          'Disabling TFA...',
          () => api.auth.disableTfa(undefined, code),
          'TFA disabled'
        );
      } catch (error) {
        handleError(error);
      }
    });

  // Top-level shortcuts
  program
    .command('login')
    .description('Authenticate with Rediacc (shortcut for: auth login)')
    .option('-e, --email <email>', 'Email address')
    .option('-p, --password <password>', 'Password (for non-interactive login)')
    .option('-n, --name <name>', 'Session name')
    .option('--endpoint <url>', 'API endpoint URL (overrides REDIACC_API_URL)')
    .action(async (options) => {
      // Forward to auth login
      await auth.commands
        .find((c) => c.name() === 'login')
        ?.parseAsync([
          'node',
          'rediacc',
          ...(options.email ? ['-e', options.email] : []),
          ...(options.password ? ['-p', options.password] : []),
          ...(options.name ? ['-n', options.name] : []),
          ...(options.endpoint ? ['--endpoint', options.endpoint] : []),
        ]);
    });

  program
    .command('logout')
    .description('Clear stored credentials (shortcut for: auth logout)')
    .action(async () => {
      // Forward to auth logout
      await auth.commands.find((c) => c.name() === 'logout')?.parseAsync(['node', 'rediacc']);
    });
}

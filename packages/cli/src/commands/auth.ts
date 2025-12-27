import { Command } from 'commander';
import {
  parseGetUserRequests,
  parseForkAuthenticationRequest,
  parseUpdateUserTFA,
  parseGetRequestAuthenticationStatus,
} from '@rediacc/shared/api';
import { typedApi, apiClient } from '../services/api.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { askConfirm, askPassword, askText } from '../utils/prompt.js';
import { withSpinner } from '../utils/spinner.js';
import type { OutputFormat } from '../types/index.js';

export function registerAuthCommands(program: Command): void {
  const auth = program.command('auth').description('Authentication commands');

  // auth login
  auth
    .command('login')
    .description('Authenticate with Rediacc')
    .option('-e, --email <email>', 'Email address')
    .option('-p, --password <password>', 'Password (for non-interactive login)')
    .option('-n, --name <name>', 'Session name')
    .option('--endpoint <url>', 'API endpoint URL')
    .option('--save-as <context>', 'Save credentials to a named context')
    .action(async (options) => {
      try {
        // Determine context name (--save-as overrides current context)
        const contextName = options.saveAs ?? (await contextService.getCurrentName());

        // Determine API URL
        let apiUrl: string;
        if (options.endpoint) {
          apiUrl = apiClient.normalizeApiUrl(options.endpoint);
        } else if (contextName) {
          const existingContext = await contextService.get(contextName);
          apiUrl = existingContext?.apiUrl ?? (await contextService.getApiUrl());
        } else {
          apiUrl = await contextService.getApiUrl();
        }

        // Temporarily set API URL for this request
        const originalUrl = apiClient.getApiUrl();
        if (apiUrl !== originalUrl) {
          await apiClient.reinitialize();
        }

        // Get email
        const email =
          options.email ??
          (await askText('Email:', {
            validate: (input) => input.includes('@') || 'Please enter a valid email',
          }));

        // Get password
        const password = options.password ?? (await askPassword('Password:'));

        // Attempt login with context info
        const result = await withSpinner(
          'Authenticating...',
          () =>
            authService.login(email, password, {
              sessionName: options.name,
              contextName: contextName ?? 'default',
              apiUrl,
            }),
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

        const savedTo = contextName ?? 'default';
        outputService.success(`Login successful! Saved to context "${savedTo}"`);
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
        const apiResponse = await withSpinner(
          'Fetching tokens...',
          () => typedApi.GetUserRequests({}),
          'Tokens fetched'
        );

        const tokens = parseGetUserRequests(apiResponse as never);
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
    .option('-e, --expires <hours>', 'Expiration in hours (1-720)', '24')
    .action(async (options: { name: string; expires: string }) => {
      try {
        await authService.requireAuth();

        // Validate expiration hours (must be between 1 and 720)
        const expiresHours = parseInt(options.expires, 10);
        if (isNaN(expiresHours) || expiresHours < 1 || expiresHours > 720) {
          throw new ValidationError('Token expiration must be between 1 and 720 hours');
        }

        const apiResponse = await withSpinner(
          'Creating forked token...',
          () =>
            typedApi.ForkAuthenticationRequest({
              childName: options.name,
              tokenExpirationHours: expiresHours,
            }),
          'Token created'
        );

        const credentials = parseForkAuthenticationRequest(apiResponse as never);

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
    .action(async (requestId: string) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          'Revoking token...',
          () => typedApi.DeleteUserRequest({ targetRequestId: parseInt(requestId, 10) }),
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

        const apiResponse = await typedApi.GetRequestAuthenticationStatus({});
        const status = parseGetRequestAuthenticationStatus(apiResponse as never);

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

        const apiResponse = await withSpinner(
          'Enabling TFA...',
          () => typedApi.UpdateUserTFA({ enable: true }),
          'TFA setup initiated'
        );

        const tfaSetup = parseUpdateUserTFA(apiResponse as never);

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
    .action(async (options: { code?: string; yes?: boolean }) => {
      try {
        await authService.requireAuth();

        if (!options.yes) {
          const confirm = await askConfirm('Are you sure you want to disable TFA?');
          if (!confirm) {
            outputService.info('Cancelled');
            return;
          }
        }

        // Build payload
        const payload: { enable: boolean; currentCode?: string } = { enable: false };
        if (options.code) {
          payload.currentCode = options.code;
        }

        await withSpinner(
          'Disabling TFA...',
          () => typedApi.UpdateUserTFA(payload),
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

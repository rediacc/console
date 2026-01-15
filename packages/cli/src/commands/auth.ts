import {
  parseForkAuthenticationRequest,
  parseGetRequestAuthenticationStatus,
  parseGetUserRequests,
  parseUpdateUserTFA,
} from '@rediacc/shared/api';
import { DEFAULTS } from '@rediacc/shared/config';
import { isValidEmail } from '@rediacc/shared/validation';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { apiClient, typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { contextService } from '../services/context.js';
import { outputService } from '../services/output.js';
import type { OutputFormat } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { askConfirm, askPassword, askText } from '../utils/prompt.js';
import { withSpinner } from '../utils/spinner.js';

export function registerAuthCommands(program: Command): void {
  const auth = program.command('auth').description(t('commands.auth.description'));

  // auth login
  auth
    .command('login')
    .description(t('commands.auth.login.description'))
    .option('-e, --email <email>', t('options.email'))
    .option('-p, --password <password>', t('options.password'))
    .option('-m, --master-password <password>', t('options.masterPassword'))
    .option('-n, --name <name>', t('options.sessionName'))
    .option('--endpoint <url>', t('options.endpoint'))
    .option('--save-as <context>', t('options.saveAs'))
    .action(async (options) => {
      try {
        // Determine context name (--save-as overrides current context)
        const contextName = options.saveAs ?? contextService.getCurrentName();

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

        // Set API URL for this login request
        apiClient.setApiUrl(apiUrl);

        // Get email
        const email =
          options.email ??
          (await askText(t('prompts.email'), {
            validate: (input) => isValidEmail(input) || t('errors.invalidEmail'),
          }));

        // Get password
        const password = options.password ?? (await askPassword(t('prompts.password')));

        // Attempt login with context info
        const result = await withSpinner(
          t('commands.auth.login.authenticating'),
          () =>
            authService.login(email, password, {
              sessionName: options.name,
              contextName: contextName ?? 'default',
              apiUrl,
              masterPassword: options.masterPassword,
            }),
          t('status.success')
        );

        // Handle 2FA if required
        if (result.isTFAEnabled) {
          const tfaCode = await askText(t('commands.auth.login.tfaPrompt'));
          await withSpinner(
            t('commands.auth.login.verifyingTfa'),
            () => authService.privilegeWithTFA(tfaCode),
            t('commands.auth.login.tfaVerified')
          );
        }

        if (!result.success && !result.isTFAEnabled) {
          throw new ValidationError(result.message ?? t('errors.authFailed'));
        }

        const savedTo = contextName ?? 'default';
        outputService.success(t('commands.auth.login.success', { context: savedTo }));
      } catch (error) {
        handleError(error);
      }
    });

  // auth logout
  auth
    .command('logout')
    .description(t('commands.auth.logout.description'))
    .action(async () => {
      try {
        await withSpinner(
          t('commands.auth.logout.loggingOut'),
          () => authService.logout(),
          t('commands.auth.logout.success')
        );
      } catch (error) {
        handleError(error);
      }
    });

  // auth status
  auth
    .command('status')
    .description(t('commands.auth.status.description'))
    .action(async () => {
      try {
        const isAuth = await authService.isAuthenticated();
        const email = await authService.getStoredEmail();

        if (isAuth) {
          outputService.success(
            t('commands.auth.status.authenticated', { email: email ?? DEFAULTS.TELEMETRY.UNKNOWN })
          );
        } else {
          outputService.warn(t('commands.auth.status.notAuthenticated'));
        }
      } catch (error) {
        handleError(error);
      }
    });

  // auth register
  auth
    .command('register')
    .description(t('commands.auth.register.description'))
    .requiredOption('--organization <name>', t('options.organization'))
    .requiredOption('-e, --email <email>', t('options.email'))
    .requiredOption('-p, --password <password>', t('options.password'))
    .option('-m, --master-password <password>', t('options.masterPassword'))
    .option('--endpoint <url>', t('options.endpoint'))
    .option('--plan <plan>', t('options.subscriptionPlan'), 'COMMUNITY')
    .action(async (options) => {
      try {
        // Set API endpoint if provided
        if (options.endpoint) {
          apiClient.setApiUrl(options.endpoint);
        }

        const result = await withSpinner(
          t('commands.auth.register.registering'),
          () =>
            authService.register(
              options.organization,
              options.email,
              options.password,
              options.plan,
              options.masterPassword
            ),
          t('commands.auth.register.submitted')
        );

        if (!result.success) {
          throw new ValidationError(result.message ?? t('errors.registrationFailed'));
        }

        outputService.success(t('commands.auth.register.success'));
        outputService.info(t('commands.auth.register.nextStep'));
      } catch (error) {
        handleError(error);
      }
    });

  // auth activate
  auth
    .command('activate')
    .description(t('commands.auth.activate.description'))
    .requiredOption('-e, --email <email>', t('options.email'))
    .requiredOption('-p, --password <password>', t('options.password'))
    .requiredOption('--code <code>', t('options.activationCode'))
    .option('--endpoint <url>', t('options.endpoint'))
    .action(async (options) => {
      try {
        // Set API endpoint if provided
        if (options.endpoint) {
          apiClient.setApiUrl(options.endpoint);
        }

        const result = await withSpinner(
          t('commands.auth.activate.activating'),
          () => authService.activate(options.email, options.password, options.code),
          t('commands.auth.activate.activated')
        );

        if (!result.success) {
          throw new ValidationError(result.message ?? t('errors.activationFailed'));
        }

        outputService.success(t('commands.auth.activate.success'));
      } catch (error) {
        handleError(error);
      }
    });

  // auth token subcommand
  const token = auth.command('token').description(t('commands.auth.token.description'));

  // auth token list
  token
    .command('list')
    .description(t('commands.auth.token.list.description'))
    .action(async () => {
      try {
        await authService.requireAuth();
        const apiResponse = await withSpinner(
          t('commands.auth.token.list.fetching'),
          () => typedApi.GetUserRequests({}),
          t('status.success')
        );

        const tokens = parseGetUserRequests(apiResponse as never);
        const format = program.opts().output as OutputFormat;

        if (tokens.length === 0) {
          outputService.info(t('commands.auth.token.list.noTokens'));
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
    .description(t('commands.auth.token.fork.description'))
    .option('-n, --name <name>', t('options.tokenName'), 'CLI Fork')
    .option('-e, --expires <hours>', t('options.expires'), '24')
    .action(async (options: { name: string; expires: string }) => {
      try {
        await authService.requireAuth();

        // Validate expiration hours (must be between 1 and 720)
        const expiresHours = Number.parseInt(options.expires, 10);
        if (Number.isNaN(expiresHours) || expiresHours < 1 || expiresHours > 720) {
          throw new ValidationError(t('errors.invalidExpiration'));
        }

        const apiResponse = await withSpinner(
          t('commands.auth.token.fork.creating'),
          () =>
            typedApi.ForkAuthenticationRequest({
              childName: options.name,
              tokenExpirationHours: expiresHours,
            }),
          t('commands.auth.token.fork.success')
        );

        const credentials = parseForkAuthenticationRequest(apiResponse as never);

        const tokenValue = credentials.requestToken ?? credentials.nextRequestToken;
        if (tokenValue) {
          outputService.success(t('commands.auth.token.fork.tokenValue', { token: tokenValue }));
        } else {
          outputService.info(t('commands.auth.token.fork.success'));
        }
      } catch (error) {
        handleError(error);
      }
    });

  // auth token revoke
  token
    .command('revoke <requestId>')
    .description(t('commands.auth.token.revoke.description'))
    .action(async (requestId: string) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          t('commands.auth.token.revoke.revoking'),
          () => typedApi.DeleteUserRequest({ targetRequestId: Number.parseInt(requestId, 10) }),
          t('commands.auth.token.revoke.success')
        );
      } catch (error) {
        handleError(error);
      }
    });

  // auth tfa subcommand
  const tfa = auth.command('tfa').description(t('commands.auth.tfa.description'));

  // auth tfa status
  tfa
    .command('status')
    .description(t('commands.auth.tfa.status.description'))
    .action(async () => {
      try {
        await authService.requireAuth();

        const apiResponse = await typedApi.GetRequestAuthenticationStatus({});
        const status = parseGetRequestAuthenticationStatus(apiResponse as never);

        if (status.isTFAEnabled) {
          outputService.success(t('commands.auth.tfa.status.enabled'));
        } else {
          outputService.info(t('commands.auth.tfa.status.disabled'));
        }
      } catch (error) {
        handleError(error);
      }
    });

  // auth tfa enable
  tfa
    .command('enable')
    .description(t('commands.auth.tfa.enable.description'))
    .action(async () => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          t('commands.auth.tfa.enable.enabling'),
          () => typedApi.UpdateUserTFA({ enable: true }),
          t('commands.auth.tfa.enable.initiated')
        );

        const tfaSetup = parseUpdateUserTFA(apiResponse as never);

        if (tfaSetup?.secret) {
          outputService.info(t('commands.auth.tfa.enable.setupKey', { key: tfaSetup.secret }));
          outputService.info(t('commands.auth.tfa.enable.addToApp'));
        }
      } catch (error) {
        handleError(error);
      }
    });

  // auth tfa disable
  tfa
    .command('disable')
    .description(t('commands.auth.tfa.disable.description'))
    .option('--code <code>', t('options.tfaCode'))
    .option('-y, --yes', t('options.yes'))
    .action(async (options: { code?: string; yes?: boolean }) => {
      try {
        await authService.requireAuth();

        if (!options.yes) {
          const confirmResult = await askConfirm(t('commands.auth.tfa.disable.confirm'));
          if (!confirmResult) {
            outputService.info(t('prompts.cancelled'));
            return;
          }
        }

        // Build payload
        const payload: { enable: boolean; currentCode?: string } = { enable: false };
        if (options.code) {
          payload.currentCode = options.code;
        }

        await withSpinner(
          t('commands.auth.tfa.disable.disabling'),
          () => typedApi.UpdateUserTFA(payload),
          t('commands.auth.tfa.disable.success')
        );
      } catch (error) {
        handleError(error);
      }
    });

  // Top-level shortcuts
  program
    .command('login')
    .description(t('commands.auth.login.shortcut'))
    .option('-e, --email <email>', t('options.email'))
    .option('-p, --password <password>', t('options.password'))
    .option('-m, --master-password <password>', t('options.masterPassword'))
    .option('-n, --name <name>', t('options.sessionName'))
    .option('--endpoint <url>', t('options.endpoint'))
    .action(async (options) => {
      // Forward to auth login
      await auth.commands
        .find((c) => c.name() === 'login')
        ?.parseAsync([
          'node',
          'rediacc',
          ...(options.email ? ['-e', options.email] : []),
          ...(options.password ? ['-p', options.password] : []),
          ...(options.masterPassword ? ['-m', options.masterPassword] : []),
          ...(options.name ? ['-n', options.name] : []),
          ...(options.endpoint ? ['--endpoint', options.endpoint] : []),
        ]);
    });

  program
    .command('logout')
    .description(t('commands.auth.logout.shortcut'))
    .action(async () => {
      // Forward to auth logout
      await auth.commands.find((c) => c.name() === 'logout')?.parseAsync(['node', 'rediacc']);
    });
}

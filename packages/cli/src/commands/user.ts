import { Command } from 'commander';
import { parseGetCompanyUsers, parseCreateUser, parseIsRegistered } from '@rediacc/shared/api';
import { apiClient, typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import type { OutputFormat } from '../types/index.js';
export function registerUserCommands(program: Command): void {
  const user = program.command('user').description('User management commands');

  // user list
  user
    .command('list')
    .description('List all users')
    .action(async () => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          'Fetching users...',
          () => typedApi.GetCompanyUsers({}),
          'Users fetched'
        );

        const users = parseGetCompanyUsers(apiResponse as never);

        const format = program.opts().output as OutputFormat;

        outputService.print(users, format);
      } catch (error) {
        handleError(error);
      }
    });

  // user create
  user
    .command('create <email>')
    .description('Create a new user')
    .option('-p, --password <password>', 'Password for the new user')
    .action(async (email, options) => {
      try {
        await authService.requireAuth();

        // Get password - either from option or prompt
        let password: string;
        if (options.password) {
          password = options.password;
        } else {
          const { askPassword } = await import('../utils/prompt.js');
          password = await askPassword('Password for new user:');
          const confirmPassword = await askPassword('Confirm password:');

          if (password !== confirmPassword) {
            throw new ValidationError('Passwords do not match');
          }
        }

        const { nodeCryptoProvider } = await import('../adapters/crypto.js');
        const passwordHash = await nodeCryptoProvider.generateHash(password);

        // Server generates secure activation code - do not send one from client
        // Middleware rejects requests that include activationCode, so we omit it
        const response = await withSpinner(
          `Creating user "${email}"...`,
          () =>
            typedApi.CreateNewUser({
              newUserEmail: email,
              newUserHash: passwordHash,
            } as Parameters<typeof typedApi.CreateNewUser>[0]),
          'User created'
        );

        // Extract server-generated activation code from response
        const result = parseCreateUser(response as never);
        if (result?.activationCode) {
          outputService.success(`Activation code: ${result.activationCode}`);
        }
      } catch (error) {
        handleError(error);
      }
    });

  // user activate
  user
    .command('activate <email> <activationCode>')
    .description('Activate a user account')
    .action(async (email, activationCode) => {
      try {
        const { askPassword } = await import('../utils/prompt.js');
        const password = await askPassword('Set password for user:');
        const confirmPassword = await askPassword('Confirm password:');

        if (password !== confirmPassword) {
          throw new ValidationError('Passwords do not match');
        }

        const { nodeCryptoProvider } = await import('../adapters/crypto.js');
        const passwordHash = await nodeCryptoProvider.generateHash(password);

        await withSpinner(
          `Activating user "${email}"...`,
          () => apiClient.activateUser(email, activationCode, passwordHash),
          'User activated'
        );
      } catch (error) {
        handleError(error);
      }
    });

  // user deactivate
  user
    .command('deactivate <email>')
    .description('Deactivate a user account')
    .option('-f, --force', 'Skip confirmation')
    .action(async (email, options) => {
      try {
        await authService.requireAuth();

        if (!options.force) {
          const { askConfirm } = await import('../utils/prompt.js');
          const confirm = await askConfirm(`Deactivate user "${email}"?`);
          if (!confirm) {
            outputService.info('Cancelled');
            return;
          }
        }

        await withSpinner(
          `Deactivating user "${email}"...`,
          () => typedApi.UpdateUserToDeactivated({ userEmail: email }),
          'User deactivated'
        );
      } catch (error) {
        handleError(error);
      }
    });

  // user reactivate
  user
    .command('reactivate <email>')
    .description('Reactivate a deactivated user account')
    .action(async (email) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          `Reactivating user "${email}"...`,
          () => typedApi.UpdateUserToActivated({ userEmail: email }),
          'User reactivated'
        );
      } catch (error) {
        handleError(error);
      }
    });

  // user update-email
  user
    .command('update-email <currentEmail> <newEmail>')
    .description("Change a user's email address")
    .action(async (currentEmail, newEmail) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          `Updating email for "${currentEmail}"...`,
          () => typedApi.UpdateUserEmail({ currentUserEmail: currentEmail, newUserEmail: newEmail }),
          `Email updated to "${newEmail}"`
        );
      } catch (error) {
        handleError(error);
      }
    });

  // user update-password
  user
    .command('update-password')
    .description('Change your password')
    .option('--password <password>', 'New password (non-interactive mode)')
    .option('--confirm <confirm>', 'Confirm password (non-interactive mode)')
    .action(async (options) => {
      try {
        await authService.requireAuth();

        let newPassword: string;
        let confirmPassword: string;

        if (options.password) {
          // Non-interactive mode
          newPassword = options.password;
          confirmPassword = options.confirm ?? options.password;
        } else {
          // Interactive mode
          const { askPassword } = await import('../utils/prompt.js');
          newPassword = await askPassword('New password:');
          confirmPassword = await askPassword('Confirm new password:');
        }

        if (newPassword !== confirmPassword) {
          throw new ValidationError('Passwords do not match');
        }

        const { nodeCryptoProvider } = await import('../adapters/crypto.js');
        const passwordHash = await nodeCryptoProvider.generateHash(newPassword);

        await withSpinner(
          'Updating password...',
          () => typedApi.UpdateUserPassword({ userNewPass: passwordHash }),
          'Password updated'
        );
      } catch (error) {
        handleError(error);
      }
    });

  // user update-language
  user
    .command('update-language <language>')
    .description("Set current user's preferred language")
    .action(async (language) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          `Updating language preference...`,
          () => typedApi.UpdateUserLanguage({ preferredLanguage: language }),
          `Language updated to "${language}"`
        );
      } catch (error) {
        handleError(error);
      }
    });

  // user exists
  user
    .command('exists <email>')
    .description('Check if a user exists')
    .action(async (email) => {
      try {
        const apiResponse = await typedApi.IsRegistered({ userName: email });
        const status = parseIsRegistered(apiResponse as never);

        if (status.isRegistered) {
          outputService.success(`User "${email}" exists`);
        } else {
          outputService.info(`User "${email}" does not exist`);
        }
      } catch (error) {
        handleError(error);
      }
    });

  // user vault subcommand
  const vault = user.command('vault').description('User vault management');

  // user vault get
  vault
    .command('get')
    .description('Get current user vault data')
    .action(async () => {
      try {
        await authService.requireAuth();

        const response = await withSpinner(
          'Fetching user vault...',
          () => typedApi.GetUserVault({}),
          'Vault fetched'
        );

        const format = program.opts().output as OutputFormat;

        // GetUserVault returns the vault data directly in first result set
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- results may be empty at runtime
        const vaultData = response.results[0]?.[0] ?? {};
        outputService.print(vaultData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // user vault update
  vault
    .command('update')
    .description('Update current user vault data')
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
          throw new ValidationError(
            'Vault data required. Use --vault <json> or pipe JSON via stdin.'
          );
        }

        if (options.vaultVersion === undefined || options.vaultVersion === null) {
          throw new ValidationError('Vault version required. Use --vault-version <n>.');
        }

        // Validate JSON
        try {
          JSON.parse(vaultData);
        } catch {
          throw new ValidationError('Invalid JSON vault data.');
        }

        await withSpinner(
          'Updating user vault...',
          () =>
            typedApi.UpdateUserVault({
              vaultContent: vaultData,
              vaultVersion: options.vaultVersion,
            }),
          'User vault updated'
        );
      } catch (error) {
        handleError(error);
      }
    });

  // user permission subcommand
  const permission = user.command('permission').description('User permission management');

  // user permission assign
  permission
    .command('assign <userEmail> <groupName>')
    .description('Assign a permission group to a user')
    .action(async (userEmail, groupName) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          `Assigning "${groupName}" to user "${userEmail}"...`,
          () =>
            typedApi.UpdateUserAssignedPermissions({ userEmail, permissionGroupName: groupName }),
          'Permission assigned'
        );
      } catch (error) {
        handleError(error);
      }
    });
}

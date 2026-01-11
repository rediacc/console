import { Command } from 'commander';
import { parseGetOrganizationUsers, parseCreateUser, parseIsRegistered } from '@rediacc/shared/api';
import { t } from '../i18n/index.js';
import { apiClient, typedApi } from '../services/api.js';
import { authService } from '../services/auth.js';
import { outputService } from '../services/output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { withSpinner } from '../utils/spinner.js';
import type { OutputFormat } from '../types/index.js';
export function registerUserCommands(program: Command): void {
  const user = program.command('user').description(t('commands.user.description'));

  // user list
  user
    .command('list')
    .description(t('commands.user.list.description'))
    .action(async () => {
      try {
        await authService.requireAuth();

        const apiResponse = await withSpinner(
          t('commands.user.list.fetching'),
          () => typedApi.GetOrganizationUsers({}),
          t('commands.user.list.success')
        );

        const users = parseGetOrganizationUsers(apiResponse as never);

        const format = program.opts().output as OutputFormat;

        outputService.print(users, format);
      } catch (error) {
        handleError(error);
      }
    });

  // user create
  user
    .command('create <email>')
    .description(t('commands.user.create.description'))
    .option('-p, --password <password>', t('options.userPassword'))
    .action(async (email, options) => {
      try {
        await authService.requireAuth();

        // Get password - either from option or prompt
        let password: string;
        if (options.password) {
          password = options.password;
        } else {
          const { askPassword } = await import('../utils/prompt.js');
          password = await askPassword(t('prompts.passwordForUser'));
          const confirmPassword = await askPassword(t('prompts.confirmPassword'));

          if (password !== confirmPassword) {
            throw new ValidationError(t('errors.passwordsMismatch'));
          }
        }

        const { nodeCryptoProvider } = await import('../adapters/crypto.js');
        const passwordHash = await nodeCryptoProvider.generateHash(password);

        // Server generates secure activation code - do not send one from client
        // Middleware rejects requests that include activationCode, so we omit it
        const response = await withSpinner(
          t('commands.user.create.creating', { email }),
          () =>
            typedApi.CreateNewUser({
              newUserEmail: email,
              newUserHash: passwordHash,
            } as Parameters<typeof typedApi.CreateNewUser>[0]),
          t('commands.user.create.success')
        );

        // Extract server-generated activation code from response
        const result = parseCreateUser(response as never);
        if (result?.activationCode) {
          outputService.success(
            t('commands.user.create.activationCode', { code: result.activationCode })
          );
        }
      } catch (error) {
        handleError(error);
      }
    });

  // user activate
  user
    .command('activate <email> <activationCode>')
    .description(t('commands.user.activate.description'))
    .action(async (email, activationCode) => {
      try {
        const { askPassword } = await import('../utils/prompt.js');
        const password = await askPassword(t('prompts.setPassword'));
        const confirmPassword = await askPassword(t('prompts.confirmPassword'));

        if (password !== confirmPassword) {
          throw new ValidationError(t('errors.passwordsMismatch'));
        }

        const { nodeCryptoProvider } = await import('../adapters/crypto.js');
        const passwordHash = await nodeCryptoProvider.generateHash(password);

        await withSpinner(
          t('commands.user.activate.activating', { email }),
          () => apiClient.activateUser(email, activationCode, passwordHash),
          t('commands.user.activate.success')
        );
      } catch (error) {
        handleError(error);
      }
    });

  // user deactivate
  user
    .command('deactivate <email>')
    .description(t('commands.user.deactivate.description'))
    .option('-f, --force', t('options.force'))
    .action(async (email, options) => {
      try {
        await authService.requireAuth();

        if (!options.force) {
          const { askConfirm } = await import('../utils/prompt.js');
          const confirm = await askConfirm(t('commands.user.deactivate.confirm', { email }));
          if (!confirm) {
            outputService.info(t('prompts.cancelled'));
            return;
          }
        }

        await withSpinner(
          t('commands.user.deactivate.deactivating', { email }),
          () => typedApi.UpdateUserToDeactivated({ userEmail: email }),
          t('commands.user.deactivate.success')
        );
      } catch (error) {
        handleError(error);
      }
    });

  // user reactivate
  user
    .command('reactivate <email>')
    .description(t('commands.user.reactivate.description'))
    .action(async (email) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          t('commands.user.reactivate.reactivating', { email }),
          () => typedApi.UpdateUserToActivated({ userEmail: email }),
          t('commands.user.reactivate.success')
        );
      } catch (error) {
        handleError(error);
      }
    });

  // user update-email
  user
    .command('update-email <currentEmail> <newEmail>')
    .description(t('commands.user.updateEmail.description'))
    .action(async (currentEmail, newEmail) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          t('commands.user.updateEmail.updating', { email: currentEmail }),
          () =>
            typedApi.UpdateUserEmail({ currentUserEmail: currentEmail, newUserEmail: newEmail }),
          t('commands.user.updateEmail.success', { email: newEmail })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // user update-password
  user
    .command('update-password')
    .description(t('commands.user.updatePassword.description'))
    .option('--password <password>', t('options.newPasswordNonInteractive'))
    .option('--confirm <confirm>', t('options.confirmPasswordNonInteractive'))
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
          newPassword = await askPassword(t('prompts.newPassword'));
          confirmPassword = await askPassword(t('prompts.confirmNewPassword'));
        }

        if (newPassword !== confirmPassword) {
          throw new ValidationError(t('errors.passwordsMismatch'));
        }

        const { nodeCryptoProvider } = await import('../adapters/crypto.js');
        const passwordHash = await nodeCryptoProvider.generateHash(newPassword);

        await withSpinner(
          t('commands.user.updatePassword.updating'),
          () => typedApi.UpdateUserPassword({ userNewPass: passwordHash }),
          t('commands.user.updatePassword.success')
        );
      } catch (error) {
        handleError(error);
      }
    });

  // user update-language
  user
    .command('update-language <language>')
    .description(t('commands.user.updateLanguage.description'))
    .action(async (language) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          t('commands.user.updateLanguage.updating'),
          () => typedApi.UpdateUserLanguage({ preferredLanguage: language }),
          t('commands.user.updateLanguage.success', { language })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // user exists
  user
    .command('exists <email>')
    .description(t('commands.user.exists.description'))
    .action(async (email) => {
      try {
        const apiResponse = await typedApi.IsRegistered({ userName: email });
        const status = parseIsRegistered(apiResponse as never);

        if (status.isRegistered) {
          outputService.success(t('commands.user.exists.exists', { email }));
        } else {
          outputService.info(t('commands.user.exists.notExists', { email }));
        }
      } catch (error) {
        handleError(error);
      }
    });

  // user vault subcommand
  const vault = user.command('vault').description(t('commands.user.vault.description'));

  // user vault get
  vault
    .command('get')
    .description(t('commands.user.vault.get.description'))
    .action(async () => {
      try {
        await authService.requireAuth();

        const response = await withSpinner(
          t('commands.user.vault.get.fetching'),
          () => typedApi.GetUserVault({}),
          t('commands.user.vault.get.success')
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
    .description(t('commands.user.vault.update.description'))
    .option('--vault <json>', t('options.vaultJson'))
    .option('--vault-version <n>', t('options.vaultVersion'), Number.parseInt)
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
          throw new ValidationError(t('errors.vaultDataRequired'));
        }

        if (options.vaultVersion === undefined || options.vaultVersion === null) {
          throw new ValidationError(t('errors.vaultVersionRequired'));
        }

        // Validate JSON
        try {
          JSON.parse(vaultData);
        } catch {
          throw new ValidationError(t('errors.invalidJsonVault'));
        }

        await withSpinner(
          t('commands.user.vault.update.updating'),
          () =>
            typedApi.UpdateUserVault({
              vaultContent: vaultData,
              vaultVersion: options.vaultVersion,
            }),
          t('commands.user.vault.update.success')
        );
      } catch (error) {
        handleError(error);
      }
    });

  // user permission subcommand
  const permission = user
    .command('permission')
    .description(t('commands.user.permission.description'));

  // user permission assign
  permission
    .command('assign <userEmail> <groupName>')
    .description(t('commands.user.permission.assign.description'))
    .action(async (userEmail, groupName) => {
      try {
        await authService.requireAuth();

        await withSpinner(
          t('commands.user.permission.assign.assigning', { group: groupName, email: userEmail }),
          () =>
            typedApi.UpdateUserAssignedPermissions({ userEmail, permissionGroupName: groupName }),
          t('commands.user.permission.assign.success')
        );
      } catch (error) {
        handleError(error);
      }
    });
}

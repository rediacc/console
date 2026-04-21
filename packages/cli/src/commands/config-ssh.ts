import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import type { OutputFormat } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';

/**
 * SSH key management. In v2, SSH always persists as inline content under
 * `config.credentials.ssh`. Path-only storage is no longer supported —
 * `--key <path>` reads the file and inlines the content on save.
 */
export function registerSSHCommands(config: Command, program: Command): void {
  const ssh = config.command('ssh').description(t('commands.config.ssh.description'));

  ssh
    .command('set')
    .description(t('commands.config.ssh.set.description'))
    .requiredOption('--key <path>', t('commands.config.ssh.set.optionKey'))
    .option('--embed', t('commands.config.ssh.set.optionEmbed'))
    .action(async (options) => {
      try {
        const keyPath: string = options.key;
        const { readSSHKey, readOptionalSSHKey } = await import('../services/renet-execution.js');

        let privateKey: string;
        try {
          privateKey = await readSSHKey(keyPath);
        } catch {
          throw new ValidationError(t('commands.config.ssh.set.keyNotFound', { path: keyPath }));
        }

        const { isValidSSHKey } = await import('@rediacc/shared-desktop/ssh');
        if (!isValidSSHKey(privateKey)) {
          throw new ValidationError(t('commands.config.ssh.set.invalidKey'));
        }

        const publicKey = (await readOptionalSSHKey(`${keyPath}.pub`)).trim() || undefined;

        const state = await configService.getResourceState();
        await state.setSSH({
          privateKey: privateKey.trim(),
          publicKey,
        });

        outputService.success(t('commands.config.ssh.set.success'));
      } catch (error) {
        handleError(error);
      }
    });

  ssh
    .command('show')
    .description(t('commands.config.ssh.show.description'))
    .action(async () => {
      try {
        const cfg = await configService.getCurrent();
        const format = program.opts().output as OutputFormat;

        if (!cfg) {
          outputService.info(t('commands.config.ssh.show.noKey'));
          return;
        }

        let hasEmbedded = false;
        try {
          const state = await configService.getResourceState();
          hasEmbedded = state.getSSH()?.privateKey != null;
        } catch {
          // No resource state available
        }

        if (!hasEmbedded) {
          outputService.info(t('commands.config.ssh.show.noKey'));
          return;
        }

        outputService.print({ embedded: 'yes' }, format);
      } catch (error) {
        handleError(error);
      }
    });

  ssh
    .command('remove')
    .description(t('commands.config.ssh.remove.description'))
    .action(async () => {
      try {
        const cfg = await configService.getCurrent();
        if (!cfg) {
          outputService.info(t('commands.config.ssh.remove.noKey'));
          return;
        }

        let hasEmbedded = false;
        try {
          const state = await configService.getResourceState();
          hasEmbedded = state.getSSH()?.privateKey != null;
        } catch {
          // No resource state available
        }

        if (!hasEmbedded) {
          outputService.info(t('commands.config.ssh.remove.noKey'));
          return;
        }

        const state = await configService.getResourceState();
        await state.setSSH({ privateKey: '', publicKey: undefined });

        outputService.success(t('commands.config.ssh.remove.success'));
      } catch (error) {
        handleError(error);
      }
    });
}

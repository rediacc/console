import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import type { OutputFormat } from '../types/index.js';
import { handleError, ValidationError } from '../utils/errors.js';

export function registerSSHCommands(config: Command, program: Command): void {
  const ssh = config.command('ssh').description(t('commands.config.ssh.description'));

  // config ssh set
  ssh
    .command('set')
    .description(t('commands.config.ssh.set.description'))
    .requiredOption('--key <path>', t('commands.config.ssh.set.optionKey'))
    .option('--embed', t('commands.config.ssh.set.optionEmbed'))
    .action(async (options) => {
      try {
        const keyPath: string = options.key;
        const embed: boolean = options.embed ?? false;

        const { readSSHKey, readOptionalSSHKey } = await import('../services/renet-execution.js');

        // Validate the key file exists and is readable
        let privateKey: string;
        try {
          privateKey = await readSSHKey(keyPath);
        } catch {
          throw new ValidationError(t('commands.config.ssh.set.keyNotFound', { path: keyPath }));
        }

        // Validate key format
        const { isValidSSHKey } = await import('@rediacc/shared-desktop/ssh');
        if (!isValidSSHKey(privateKey)) {
          throw new ValidationError(t('commands.config.ssh.set.invalidKey'));
        }

        const configName = configService.getCurrentName();

        if (embed) {
          outputService.warn(t('commands.config.ssh.set.embedWarning'));

          // Read optional public key
          const publicKey = (await readOptionalSSHKey(`${keyPath}.pub`)).trim() || undefined;

          const state = await configService.getResourceState();
          await state.setSSH({
            privateKey: privateKey.trim(),
            publicKey,
          });
        } else {
          // Store path reference only
          const pubKeyPath = `${keyPath}.pub`;
          let publicKeyPath: string | undefined;
          try {
            const fs = await import('node:fs/promises');
            const os = await import('node:os');
            const path = await import('node:path');
            const expandedPub = pubKeyPath.startsWith('~')
              ? path.join(os.homedir(), pubKeyPath.slice(1))
              : pubKeyPath;
            await fs.access(expandedPub);
            publicKeyPath = pubKeyPath;
          } catch {
            // No public key file — that's fine
          }

          await configService.update(configName, {
            ssh: { privateKeyPath: keyPath, publicKeyPath },
          });
        }

        outputService.success(t('commands.config.ssh.set.success'));
      } catch (error) {
        handleError(error);
      }
    });

  // config ssh show
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

        const hasPath = cfg.ssh?.privateKeyPath;
        let hasEmbedded = false;

        try {
          const state = await configService.getResourceState();
          hasEmbedded = state.getSSH()?.privateKey != null;
        } catch {
          // No resource state available
        }

        if (!hasPath && !hasEmbedded) {
          outputService.info(t('commands.config.ssh.show.noKey'));
          return;
        }

        const display: Record<string, string> = {};

        if (hasPath) {
          display.keyPath = cfg.ssh!.privateKeyPath;
          if (cfg.ssh!.publicKeyPath) {
            display.publicKeyPath = cfg.ssh!.publicKeyPath;
          }
        }

        display.embedded = hasEmbedded ? 'yes' : 'no';

        outputService.print(display, format);
      } catch (error) {
        handleError(error);
      }
    });

  // config ssh remove
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

        const hasPath = cfg.ssh?.privateKeyPath;
        let hasEmbedded = false;

        try {
          const state = await configService.getResourceState();
          hasEmbedded = state.getSSH()?.privateKey != null;
        } catch {
          // No resource state available
        }

        if (!hasPath && !hasEmbedded) {
          outputService.info(t('commands.config.ssh.remove.noKey'));
          return;
        }

        const configName = configService.getCurrentName();

        // Clear path-based SSH config
        if (hasPath) {
          await configService.update(configName, { ssh: undefined });
        }

        // Clear embedded SSH content
        if (hasEmbedded) {
          const state = await configService.getResourceState();
          await state.setSSH({ privateKey: '', publicKey: undefined });
          // Also clear sshContent from config directly for unencrypted configs
          await configService.update(configName, { sshContent: undefined });
        }

        outputService.success(t('commands.config.ssh.remove.success'));
      } catch (error) {
        handleError(error);
      }
    });
}

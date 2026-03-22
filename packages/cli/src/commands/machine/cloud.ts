import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { createCloudMachine, destroyCloudMachine } from '../../services/tofu/index.js';
import { handleError } from '../../utils/errors.js';

export function registerCloudCommands(machine: Command, _program: Command): void {
  // machine provision <name>
  machine
    .command('provision <name>')
    .description(t('commands.machine.provision.description'))
    .requiredOption('--provider <name>', t('commands.machine.provision.optionProvider'))
    .option('--region <region>', t('commands.machine.provision.optionRegion'))
    .option('--type <type>', t('commands.machine.provision.optionType'))
    .option('--image <image>', t('commands.machine.provision.optionImage'))
    .option('--ssh-user <user>', t('commands.machine.provision.optionSshUser'))
    .option('--base-domain <domain>', t('commands.machine.provision.optionBaseDomain'))
    .option('--no-infra', t('commands.machine.provision.optionNoInfra'))
    .option('--debug', t('options.debug'))
    .action(async (name, options) => {
      try {
        await createCloudMachine(name, options.provider, {
          region: options.region,
          instanceType: options.type,
          image: options.image,
          sshUser: options.sshUser,
          baseDomain: options.baseDomain,
          noInfra: options.noInfra,
          debug: options.debug,
        });
      } catch (error) {
        handleError(error);
      }
    });

  // machine deprovision <name>
  machine
    .command('deprovision <name>')
    .description(t('commands.machine.deprovision.description'))
    .option('--force', t('commands.machine.deprovision.optionForce'))
    .option('--debug', t('options.debug'))
    .action(async (name, options) => {
      try {
        if (!options.force) {
          const { createInterface } = await import('node:readline');
          const rl = createInterface({ input: process.stdin, output: process.stdout });
          const answer = await new Promise<string>((resolve) => {
            rl.question(`${t('commands.machine.deprovision.confirm', { name })} (y/N) `, resolve);
          });
          rl.close();
          if (answer.toLowerCase() !== 'y') {
            return;
          }
        }

        await destroyCloudMachine(name, {
          force: options.force,
          debug: options.debug,
        });
      } catch (error) {
        handleError(error);
      }
    });
}

import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { createCloudMachine, destroyCloudMachine } from '../../services/tofu/index.js';
import { handleError } from '../../utils/errors.js';

/** The repository keys placed on `machine` (#80f7476a). */
async function reposOn(machine: string): Promise<string[]> {
  const { configService } = await import('../../services/config/config-resources.js');
  const { repoKeysPlacedOn } = await import('../../services/config/machine-gone-repos.js');
  const config = await configService.getCurrent();
  return config ? repoKeysPlacedOn(config, machine) : [];
}

/**
 * The repos of a deprovisioned machine: archived with `--archive-repos` (credential kept,
 * restorable), otherwise named with the commands that archive them, never left unsaid.
 */
export async function settleMachineRepos(
  machine: string,
  repoKeys: string[],
  archive: boolean
): Promise<void> {
  if (repoKeys.length === 0) return;
  const { outputService } = await import('../../services/core/output.js');
  if (archive) {
    const { configService } = await import('../../services/config/config-resources.js');
    const archived = await configService.archiveRepositories(repoKeys);
    outputService.info(
      t('commands.machine.deprovision.reposArchived', {
        machine,
        count: archived.length,
        repos: archived.join(', '),
      })
    );
    return;
  }
  outputService.warn(
    t('commands.machine.deprovision.reposLeft', {
      machine,
      count: repoKeys.length,
      repos: repoKeys.join(', '),
    })
  );
  outputService.info(t('commands.machine.deprovision.reposLeftHint'));
}

export function registerCloudCommands(machine: Command, _program: Command): void {
  // machine provision
  machine
    .command('provision')
    .description(t('commands.machine.provision.description'))
    .argument('<name>', t('options.name'))
    .requiredOption('--provider <name>', t('commands.machine.provision.optionProvider'))
    .option('--region <region>', t('commands.machine.provision.optionRegion'))
    .option('--type <type>', t('commands.machine.provision.optionType'))
    .option('--image <image>', t('commands.machine.provision.optionImage'))
    .option('--ssh-user <user>', t('commands.machine.provision.optionSshUser'))
    .option('--base-domain <domain>', t('commands.machine.provision.optionBaseDomain'))
    .option('--no-infra', t('commands.machine.provision.optionNoInfra'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options) => {
      try {
        await createCloudMachine(name, options.provider, {
          region: options.region,
          instanceType: options.type,
          image: options.image,
          sshUser: options.sshUser,
          baseDomain: options.baseDomain,
          // Commander stores `--no-infra` as `infra: false`; `noInfra` is never set.
          noInfra: options.infra === false,
          debug: options.debug,
        });
      } catch (error) {
        handleError(error);
      }
    });

  // machine deprovision
  machine
    .command('deprovision')
    .description(t('commands.machine.deprovision.description'))
    .argument('<name>', t('options.name'))
    .option('--force', t('commands.machine.deprovision.optionForce'))
    .option('--archive-repos', t('commands.machine.deprovision.optionArchiveRepos'))
    .option('--debug', t('options.debug'))
    .action(async (name: string, options) => {
      try {
        // Read before the machine leaves the config: afterwards its repos still name it, and nothing else can.
        const repoKeys = await reposOn(name);
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
        await settleMachineRepos(name, repoKeys, options.archiveRepos === true);
      } catch (error) {
        handleError(error);
      }
    });
}

import { DEFAULTS } from '@rediacc/shared/config';
import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import type { CloudProviderConfig, OutputFormat, ProviderSSHKeyConfig } from '../../types/index.js';
import { assertResourceName } from '../../utils/config-schema.js';
import { handleError } from '../../utils/errors.js';

/** Apply custom provider fields from CLI options to a config object. */
function applyCustomProviderFields(
  config: CloudProviderConfig,
  options: Record<string, string | undefined>
): void {
  if (options.resource) config.resource = options.resource;
  if (options.labelAttr) config.labelAttr = options.labelAttr;
  if (options.regionAttr) config.regionAttr = options.regionAttr;
  if (options.sizeAttr) config.sizeAttr = options.sizeAttr;
  if (options.imageAttr) config.imageAttr = options.imageAttr;
  if (options.ipv4Output) config.ipv4Output = options.ipv4Output;
  if (options.ipv6Output) config.ipv6Output = options.ipv6Output;
  if (options.sshKeyAttr) {
    config.sshKey = {
      attr: options.sshKeyAttr,
      format:
        (options.sshKeyFormat as ProviderSSHKeyConfig['format'] | undefined) ??
        DEFAULTS.CLOUD.SSH_KEY_FORMAT,
      keyResource: options.sshKeyResource,
    };
  }
}

/** Build a CloudProviderConfig from CLI options. */
function buildProviderConfig(options: Record<string, string | undefined>): CloudProviderConfig {
  const config: CloudProviderConfig = { apiToken: options.token! };

  if (options.provider) config.provider = options.provider;
  if (options.source) config.source = options.source;
  if (options.region) config.region = options.region;
  if (options.type) config.instanceType = options.type;
  if (options.image) config.image = options.image;
  if (options.sshUser) config.sshUser = options.sshUser;

  applyCustomProviderFields(config, options);
  return config;
}

/** Register `machine provider add/remove/list`. */
export function registerProviderCommands(machine: Command, program: Command): void {
  const provider = machine
    .command('provider')
    .description(t('commands.machine.provider.description'));

  provider
    .command('add')
    .argument('<name>', t('options.name'))
    .description(t('commands.machine.provider.add.description'))
    .option('--provider <source>', t('commands.machine.provider.add.optionProvider'))
    .option('--source <source>', t('commands.machine.provider.add.optionSource'))
    .requiredOption('--token <token>', t('commands.machine.provider.add.optionToken'))
    .option('--region <region>', t('commands.machine.provider.add.optionRegion'))
    .option('--type <type>', t('commands.machine.provider.add.optionInstanceType'))
    .option('--image <image>', t('commands.machine.provider.add.optionImage'))
    .option('--ssh-user <user>', t('commands.machine.provider.add.optionSshUser'))
    .option('--resource <type>', t('commands.machine.provider.add.optionResource'))
    .option('--label-attr <attr>', t('commands.machine.provider.add.optionLabelAttr'))
    .option('--region-attr <attr>', t('commands.machine.provider.add.optionRegionAttr'))
    .option('--size-attr <attr>', t('commands.machine.provider.add.optionSizeAttr'))
    .option('--image-attr <attr>', t('commands.machine.provider.add.optionImageAttr'))
    .option('--ipv4-output <attr>', t('commands.machine.provider.add.optionIpv4Output'))
    .option('--ipv6-output <attr>', t('commands.machine.provider.add.optionIpv6Output'))
    .option('--ssh-key-attr <attr>', t('commands.machine.provider.add.optionSshKeyAttr'))
    .option('--ssh-key-format <format>', t('commands.machine.provider.add.optionSshKeyFormat'))
    .option('--ssh-key-resource <type>', t('commands.machine.provider.add.optionSshKeyResource'))
    .action(async (name: string, options) => {
      try {
        assertResourceName(name);

        if (!options.provider && !options.source) {
          throw new Error(
            'Either --provider (known provider) or --source (custom provider) is required'
          );
        }

        const providerConfig = buildProviderConfig(options);
        await configService.addCloudProvider(name, providerConfig);
        outputService.success(
          t('commands.machine.provider.add.success', {
            name,
            provider: options.provider ?? options.source,
          })
        );
      } catch (error) {
        handleError(error);
      }
    });

  provider
    .command('remove')
    .argument('<name>', t('options.name'))
    .description(t('commands.machine.provider.remove.description'))
    .action(async (name: string) => {
      try {
        await configService.removeCloudProvider(name);
        outputService.success(t('commands.machine.provider.remove.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  provider
    .command('list')
    .description(t('commands.machine.provider.list.description'))
    .action(async () => {
      try {
        const providers = await configService.listCloudProviders();
        const format = program.opts().output as OutputFormat;

        if (providers.length === 0) {
          outputService.info(t('commands.machine.provider.list.noProviders'));
          return;
        }

        const displayData = providers.map((p) => ({
          name: p.name,
          provider: p.config.provider ?? p.config.source ?? DEFAULTS.CLOUD.DISPLAY_PLACEHOLDER,
          region: p.config.region ?? DEFAULTS.CLOUD.DISPLAY_PLACEHOLDER,
          instanceType: p.config.instanceType ?? DEFAULTS.CLOUD.DISPLAY_PLACEHOLDER,
          sshUser: p.config.sshUser ?? DEFAULTS.CLOUD.SSH_USER,
        }));

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });
}

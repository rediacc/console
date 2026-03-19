import { execFileSync } from 'node:child_process';
import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { pushInfraConfig } from '../services/infra-provision.js';
import { outputService } from '../services/output.js';
import { provisionRenetToRemote, readSSHKey } from '../services/renet-execution.js';
import { deployAllRepoKeys } from '../services/repo-key-deployment.js';
import type {
  CloudProviderConfig,
  MachineConfig,
  OutputFormat,
  ProviderSSHKeyConfig,
} from '../types/index.js';
import { assertResourceName, MachineConfigSchema, parseConfig } from '../utils/config-schema.js';
import { handleError } from '../utils/errors.js';

async function postSetupMachineTasks(name: string, debug?: boolean): Promise<void> {
  // Deploy all per-repo SSH keys to the newly set up machine
  try {
    const deployed = await deployAllRepoKeys(name);
    if (deployed > 0) {
      outputService.info(`Deployed ${deployed} repo SSH keys to ${name}`);
    }
  } catch {
    // non-fatal
  }

  // Auto push-infra if machine has infra configured
  try {
    const postSetupConfig = await configService.getLocalConfig();
    const postSetupMachine = postSetupConfig.machines[name];
    if (postSetupMachine?.infra?.baseDomain) {
      outputService.info(t('commands.machine.provision.configuringInfra', { name }));
      await pushInfraConfig(name, { debug });
    }
  } catch {
    // push-infra failure is non-fatal during setup
  }
}

/**
 * Apply custom provider fields from CLI options to a config object.
 */
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

/**
 * Build a CloudProviderConfig from CLI options.
 */
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

function scanHostKeys(ip: string, port: number): string {
  try {
    const result = execFileSync('ssh-keyscan', ['-p', String(port), ip], {
      encoding: 'utf-8',
      timeout: 10_000,
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    return result.trim();
  } catch {
    return '';
  }
}

async function scanSingleMachine(machineName: string): Promise<void> {
  const machine = await configService.getLocalMachine(machineName);
  const keyscan = scanHostKeys(machine.ip, machine.port ?? DEFAULTS.SSH.PORT);
  if (keyscan) {
    await configService.updateMachine(machineName, {
      knownHosts: keyscan,
    });
    outputService.success(t('commands.config.machine.scanKeys.keysScanned', { name: machineName }));
  } else {
    outputService.warn(t('commands.config.machine.scanKeys.noKeys', { name: machineName }));
  }
}

async function scanAllMachines(): Promise<void> {
  const machines = await configService.listMachines();
  let scanned = 0;
  for (const m of machines) {
    try {
      const keyscan = scanHostKeys(m.config.ip, m.config.port ?? DEFAULTS.SSH.PORT);
      if (keyscan) {
        await configService.updateMachine(m.name, {
          knownHosts: keyscan,
        });
        outputService.info(t('commands.config.machine.scanKeys.keysScanned', { name: m.name }));
        scanned++;
      }
    } catch {
      outputService.warn(t('commands.config.machine.scanKeys.noKeys', { name: m.name }));
    }
  }
  outputService.success(
    t('commands.config.machine.scanKeys.completed', {
      count: scanned,
      total: machines.length,
    })
  );
}

export function registerMachineCommands(config: Command, program: Command): void {
  const machine = config.command('machine').description(t('commands.config.machine.description'));

  // config machine add
  machine
    .command('add <name>')
    .summary(t('commands.config.machine.add.descriptionShort'))
    .description(t('commands.config.machine.add.description'))
    .requiredOption('--ip <address>', t('options.machineIp'))
    .requiredOption('--user <username>', t('options.sshUser'))
    .option('--port <port>', t('options.sshPort'), '22')
    .option('--datastore <path>', t('options.datastore'), '/mnt/rediacc')
    .action(async (name, options) => {
      try {
        assertResourceName(name);
        const machineConfig = parseConfig(
          MachineConfigSchema,
          {
            ip: options.ip.trim(),
            user: options.user.trim(),
            port: Number.parseInt(options.port, 10),
            datastore: options.datastore?.trim(),
          },
          'machine config'
        ) as MachineConfig;

        await configService.addMachine(name, machineConfig);
        outputService.success(
          t('commands.config.machine.add.success', {
            name,
            user: machineConfig.user,
            ip: machineConfig.ip,
          })
        );

        try {
          const keyscan = scanHostKeys(machineConfig.ip, machineConfig.port ?? DEFAULTS.SSH.PORT);
          if (keyscan) {
            await configService.updateMachine(name, {
              knownHosts: keyscan,
            });
            outputService.info(t('commands.config.machine.scanKeys.keysScanned', { name }));
          }
        } catch {
          /* non-fatal */
        }
      } catch (error) {
        handleError(error);
      }
    });

  // config machine remove
  machine
    .command('remove <name>')
    .description(t('commands.config.machine.remove.description'))
    .action(async (name) => {
      try {
        await configService.removeMachine(name);
        outputService.success(t('commands.config.machine.remove.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // config machine list
  machine
    .command('list')
    .description(t('commands.config.machine.list.description'))
    .action(async () => {
      try {
        const machines = await configService.listMachines();
        const format = program.opts().output as OutputFormat;

        if (machines.length === 0) {
          outputService.info(t('commands.config.machine.list.noMachines'));
          return;
        }

        const displayData = machines.map((m) => ({
          name: m.name,
          ip: m.config.ip,
          user: m.config.user,
          port: m.config.port ?? DEFAULTS.SSH.PORT,
          datastore: m.config.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH,
        }));

        outputService.print(displayData, format);
      } catch (error) {
        handleError(error);
      }
    });

  // config machine scan-keys
  machine
    .command('scan-keys [machine]')
    .description(t('commands.config.machine.scanKeys.description'))
    .action(async (machineName?: string) => {
      try {
        if (machineName) {
          await scanSingleMachine(machineName);
        } else {
          await scanAllMachines();
        }
      } catch (error) {
        handleError(error);
      }
    });

  // config machine setup
  machine
    .command('setup <name>')
    .summary(t('commands.config.machine.setup.descriptionShort'))
    .description(t('commands.config.machine.setup.description'))
    .option(
      '--datastore <path>',
      t('commands.config.machine.setup.datastoreOption'),
      '/mnt/rediacc'
    )
    .option(
      '--datastore-size <size>',
      t('commands.config.machine.setup.datastoreSizeOption'),
      '95%'
    )
    .option('--debug', t('options.debug'))
    .action(async (name, options) => {
      try {
        const localConfig = await configService.getLocalConfig();
        const machineObj = await configService.getLocalMachine(name);
        const sshPrivateKey =
          localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

        outputService.info(t('commands.config.machine.setup.starting', { machine: name }));

        const { remotePath: remoteRenetPath } = await provisionRenetToRemote(
          localConfig,
          machineObj,
          sshPrivateKey,
          {
            debug: options.debug,
          }
        );

        const sftp = new SFTPClient({
          host: machineObj.ip,
          port: machineObj.port ?? DEFAULTS.SSH.PORT,
          username: machineObj.user,
          privateKey: sshPrivateKey,
        });
        await sftp.connect();

        try {
          const datastoreSize =
            options.datastoreSize === NETWORK_DEFAULTS.DATASTORE_SIZE
              ? (localConfig.datastoreSize ?? NETWORK_DEFAULTS.DATASTORE_SIZE)
              : options.datastoreSize;
          const cmd = `sudo ${remoteRenetPath} setup --auto --datastore ${options.datastore} --datastore-size ${datastoreSize}`;

          if (options.debug) {
            outputService.info(`[setup] Running: ${cmd}`);
          }

          const exitCode = await sftp.execStreaming(cmd, {
            onStdout: (data) => process.stdout.write(data),
            onStderr: (data) => process.stderr.write(data),
          });

          if (exitCode === 0) {
            outputService.success(t('commands.config.machine.setup.completed', { machine: name }));
            await postSetupMachineTasks(name, options.debug);
          } else {
            outputService.error(
              t('commands.config.machine.setup.failed', {
                machine: name,
                error: `exit code ${exitCode}`,
              })
            );
            process.exitCode = exitCode;
          }
        } finally {
          sftp.close();
        }
      } catch (error) {
        handleError(error);
      }
    });

  // config machine set-ceph
  machine
    .command('set-ceph')
    .description(t('commands.config.machine.setCeph.description'))
    .requiredOption('-m, --machine <name>', t('options.machine'))
    .requiredOption('--pool <name>', t('commands.config.machine.setCeph.optionPool'))
    .requiredOption('--image <name>', t('commands.config.machine.setCeph.optionImage'))
    .option('--cluster <name>', t('commands.config.machine.setCeph.optionCluster'), 'ceph')
    .action(async (options: { machine: string; pool: string; image: string; cluster: string }) => {
      try {
        await configService.updateMachine(options.machine, {
          ceph: {
            pool: options.pool,
            image: options.image,
            clusterName: options.cluster === 'ceph' ? undefined : options.cluster,
          },
        });
        outputService.success(
          t('commands.config.machine.setCeph.success', {
            name: options.machine,
            pool: options.pool,
            image: options.image,
          })
        );
      } catch (error) {
        handleError(error);
      }
    });
}

export function registerProviderCommands(config: Command, program: Command): void {
  const provider = config
    .command('provider')
    .description(t('commands.config.provider.description'));

  // config provider add
  provider
    .command('add <name>')
    .description(t('commands.config.provider.add.description'))
    .option('--provider <source>', t('commands.config.provider.add.optionProvider'))
    .option('--source <source>', t('commands.config.provider.add.optionSource'))
    .requiredOption('--token <token>', t('commands.config.provider.add.optionToken'))
    .option('--region <region>', t('commands.config.provider.add.optionRegion'))
    .option('--type <type>', t('commands.config.provider.add.optionInstanceType'))
    .option('--image <image>', t('commands.config.provider.add.optionImage'))
    .option('--ssh-user <user>', t('commands.config.provider.add.optionSshUser'))
    .option('--resource <type>', t('commands.config.provider.add.optionResource'))
    .option('--label-attr <attr>', t('commands.config.provider.add.optionLabelAttr'))
    .option('--region-attr <attr>', t('commands.config.provider.add.optionRegionAttr'))
    .option('--size-attr <attr>', t('commands.config.provider.add.optionSizeAttr'))
    .option('--image-attr <attr>', t('commands.config.provider.add.optionImageAttr'))
    .option('--ipv4-output <attr>', t('commands.config.provider.add.optionIpv4Output'))
    .option('--ipv6-output <attr>', t('commands.config.provider.add.optionIpv6Output'))
    .option('--ssh-key-attr <attr>', t('commands.config.provider.add.optionSshKeyAttr'))
    .option('--ssh-key-format <format>', t('commands.config.provider.add.optionSshKeyFormat'))
    .option('--ssh-key-resource <type>', t('commands.config.provider.add.optionSshKeyResource'))
    .action(async (name, options) => {
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
          t('commands.config.provider.add.success', {
            name,
            provider: options.provider ?? options.source,
          })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // config provider remove
  provider
    .command('remove <name>')
    .description(t('commands.config.provider.remove.description'))
    .action(async (name) => {
      try {
        await configService.removeCloudProvider(name);
        outputService.success(t('commands.config.provider.remove.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });

  // config provider list
  provider
    .command('list')
    .description(t('commands.config.provider.list.description'))
    .action(async () => {
      try {
        const providers = await configService.listCloudProviders();
        const format = program.opts().output as OutputFormat;

        if (providers.length === 0) {
          outputService.info(t('commands.config.provider.list.noProviders'));
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

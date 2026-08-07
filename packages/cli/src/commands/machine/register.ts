import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { type Command, Option } from 'commander';
import { t } from '../../i18n/index.js';
import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import { machineConnections } from '../../services/machine/machine-connection.js';
import { guardMachineRemoval } from '../../services/machine/machine-remove-guard.js';
import { pushInfraConfig } from '../../services/provision/infra-provision.js';
import { provisionRenetToRemote, readSSHKey } from '../../services/renet/renet-execution.js';
import { deployAllRepoKeys } from '../../services/repo/repo-key-deployment.js';
import type { MachineConfig, OutputFormat } from '../../types/index.js';
import { assertResourceName, MachineConfigSchema, parseConfig } from '../../utils/config-schema.js';
import { handleError } from '../../utils/errors.js';
import { classifyKeyChange, scanHostKeys, shortFingerprint } from '../../utils/host-keys.js';

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
 * Report what a scan did to each pinned algorithm.
 *
 * Replacing an existing pin and pinning a key for the first time are very
 * different acts, and printing one line for both hides the security-relevant
 * case. Only prints per-key detail when something was actually replaced, so the
 * ordinary re-scan stays quiet.
 */
function reportKeyChanges(machineName: string, previous: string, scanned: string): void {
  const changes = classifyKeyChange(previous, scanned);
  const replaced = changes.filter((c) => c.kind === 'replaced');

  if (replaced.length === 0) {
    outputService.success(t('commands.machine.scanKeys.keysScanned', { name: machineName }));
    return;
  }

  outputService.warn(
    t('commands.machine.scanKeys.replaced', { name: machineName, count: replaced.length })
  );
  for (const c of changes) {
    if (c.kind === 'replaced' && c.oldKey) {
      outputService.print(
        `  ${c.type.padEnd(22)} REPLACED  ${shortFingerprint(c.oldKey)} -> ${shortFingerprint(c.newKey)}`
      );
    } else {
      outputService.print(
        `  ${c.type.padEnd(22)} ${c.kind === 'pinned' ? 'pinned (new)' : 'unchanged'}`
      );
    }
  }
}

async function scanSingleMachine(machineName: string): Promise<void> {
  const machine = await configService.getLocalMachine(machineName);
  const previous = machine.knownHosts ?? '';
  const keyscan = scanHostKeys(machine.ip, machine.port ?? DEFAULTS.SSH.PORT);
  if (keyscan) {
    await configService.updateMachine(machineName, { knownHosts: keyscan });
    reportKeyChanges(machineName, previous, keyscan);
  } else {
    outputService.warn(t('commands.machine.scanKeys.noKeys', { name: machineName }));
  }
}

async function scanAllMachines(): Promise<void> {
  const machines = await configService.listMachines();
  let scanned = 0;
  for (const m of machines) {
    try {
      const previous = m.config.knownHosts ?? '';
      const keyscan = scanHostKeys(m.config.ip, m.config.port ?? DEFAULTS.SSH.PORT);
      if (keyscan) {
        await configService.updateMachine(m.name, { knownHosts: keyscan });
        // Stay one line per machine in the bulk case unless a pin was actually
        // replaced, which is worth interrupting the summary for.
        if (classifyKeyChange(previous, keyscan).some((c) => c.kind === 'replaced')) {
          reportKeyChanges(m.name, previous, keyscan);
        } else {
          outputService.info(t('commands.machine.scanKeys.keysScanned', { name: m.name }));
        }
        scanned++;
      }
    } catch {
      outputService.warn(t('commands.machine.scanKeys.noKeys', { name: m.name }));
    }
  }
  outputService.success(
    t('commands.machine.scanKeys.completed', { count: scanned, total: machines.length })
  );
}

/** `machine add <name>` — register an existing SSH-reachable machine. */
function registerAdd(machine: Command): void {
  machine
    .command('add')
    .argument('<name>', t('options.name'))
    .summary(t('commands.machine.add.descriptionShort'))
    .description(t('commands.machine.add.description'))
    .requiredOption('--ip <address>', t('options.machineIp'))
    .requiredOption('--user <username>', t('options.sshUser'))
    .option('--port <port>', t('options.sshPort'), '22')
    .action(async (name: string, options) => {
      try {
        assertResourceName(name);
        const machineConfig = parseConfig(
          MachineConfigSchema,
          {
            ip: options.ip.trim(),
            user: options.user.trim(),
            port: Number.parseInt(options.port, 10),
          },
          'machine config'
        ) as MachineConfig;

        await configService.addMachine(name, machineConfig);
        outputService.success(
          t('commands.machine.add.success', {
            name,
            user: machineConfig.user,
            ip: machineConfig.ip,
          })
        );

        try {
          const keyscan = scanHostKeys(machineConfig.ip, machineConfig.port ?? DEFAULTS.SSH.PORT);
          if (keyscan) {
            await configService.updateMachine(name, { knownHosts: keyscan });
            outputService.info(t('commands.machine.scanKeys.keysScanned', { name }));
          }
        } catch {
          /* non-fatal */
        }
      } catch (error) {
        handleError(error);
      }
    });
}

/** `machine remove <name>` — deregister a machine from the config. */
function registerRemove(machine: Command): void {
  machine
    .command('remove')
    .argument('<name>', t('options.name'))
    .description(t('commands.machine.remove.description'))
    .option('-y, --yes', t('options.yes'))
    .option('--force', t('commands.machine.remove.forceOption'))
    .action(async (name: string, options: { yes?: boolean; force?: boolean }) => {
      try {
        // Refuse (exit 12) if repositories are still placed on this machine,
        // unless --force. Runs before the confirm so we fail fast and teaching.
        await guardMachineRemoval(name, options.force);
        if (!options.yes) {
          const { askConfirm } = await import('../../utils/prompt.js');
          const confirmed = await askConfirm(t('commands.machine.remove.confirm', { name }));
          if (!confirmed) {
            outputService.info(t('status.cancelled'));
            return;
          }
        }
        await configService.removeMachine(name);
        outputService.success(t('commands.machine.remove.success', { name }));
      } catch (error) {
        handleError(error);
      }
    });
}

/** `machine list` — list registered machines. */
function registerList(machine: Command, program: Command): void {
  machine
    .command('list')
    .description(t('commands.machine.list.description'))
    .option('--search <text>', t('options.searchInField', { field: 'name' }))
    // Closed set: --sort keys are exactly the columns of the output rows below.
    .addOption(
      new Option('--sort <field>', t('options.sortByField')).choices([
        'name',
        'ip',
        'user',
        'port',
        'datastore',
      ])
    )
    .option('--desc', t('options.sortDescending'))
    .action(async (options: { search?: string; sort?: string; desc?: boolean }) => {
      try {
        const machines = await configService.listMachines();
        const format = program.opts().output as OutputFormat;

        // The hint is a table-mode courtesy. Every machine-readable format falls
        // through to print() so a consumer gets {"success":true,"data":[]} rather
        // than zero bytes on stdout.
        if (machines.length === 0 && format === 'table') {
          outputService.info(t('commands.machine.list.noMachines'));
          return;
        }

        let rows = machines.map((m) => ({
          name: m.name,
          ip: m.config.ip,
          user: m.config.user,
          port: m.config.port ?? DEFAULTS.SSH.PORT,
          datastore: m.config.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH,
        }));

        if (options.search) {
          const term = options.search.toLowerCase();
          rows = rows.filter((r) => r.name.toLowerCase().includes(term));
        }
        if (options.sort) {
          const key = options.sort as keyof (typeof rows)[number];
          rows.sort((a, b) => String(a[key]).localeCompare(String(b[key])));
          if (options.desc) rows.reverse();
        }

        outputService.print(rows, format);
      } catch (error) {
        handleError(error);
      }
    });
}

/** `machine scan-keys [name]` — pin SSH host keys for one or all machines. */
function registerScanKeys(machine: Command): void {
  machine
    .command('scan-keys')
    .argument('[name]', t('options.name'))
    .description(t('commands.machine.scanKeys.description'))
    .action(async (name: string | undefined) => {
      try {
        if (name) {
          await scanSingleMachine(name);
        } else {
          await scanAllMachines();
        }
      } catch (error) {
        handleError(error);
      }
    });
}

/** `machine setup <name>` — install renet and prepare the machine. */
function registerSetup(machine: Command): void {
  machine
    .command('setup')
    .argument('<name>', t('options.name'))
    .summary(t('commands.machine.setup.descriptionShort'))
    .description(t('commands.machine.setup.description'))
    .option('--datastore-path <path>', t('commands.machine.setup.datastoreOption'), '/mnt/rediacc')
    .option('--datastore-size <size>', t('commands.machine.setup.datastoreSizeOption'), '95%')
    .option('--debug', t('options.debug'))
    .action(async (name: string, options) => {
      try {
        const localConfig = await configService.getLocalConfig();
        const machineObj = await configService.getLocalMachine(name);
        const sshPrivateKey =
          localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

        outputService.info(t('commands.machine.setup.starting', { machine: name }));

        const { remotePath: remoteRenetPath } = await provisionRenetToRemote(
          localConfig,
          machineObj,
          sshPrivateKey,
          { debug: options.debug }
        );

        const lease = await machineConnections.acquireFor(machineObj, sshPrivateKey);

        try {
          const datastoreSize =
            options.datastoreSize === NETWORK_DEFAULTS.DATASTORE_SIZE
              ? (localConfig.datastoreSize ?? NETWORK_DEFAULTS.DATASTORE_SIZE)
              : options.datastoreSize;
          const cmd = `sudo ${remoteRenetPath} setup --auto --datastore ${options.datastorePath} --datastore-size ${datastoreSize}`;

          if (options.debug) {
            outputService.info(`[setup] Running: ${cmd}`);
          }

          const exitCode = await lease.sftp.execStreaming(cmd, {
            onStdout: (data) => process.stdout.write(data),
            onStderr: (data) => process.stderr.write(data),
          });

          if (exitCode === 0) {
            outputService.success(t('commands.machine.setup.completed', { machine: name }));
            await postSetupMachineTasks(name, options.debug);
          } else {
            outputService.error(
              t('commands.machine.setup.failed', { machine: name, error: `exit code ${exitCode}` })
            );
            process.exitCode = exitCode;
          }
        } finally {
          lease.release();
        }
      } catch (error) {
        handleError(error);
      }
    });
}

/** Register `machine add/remove/list/scan-keys/setup` on the machine noun. */
export function registerMachineRegistrationCommands(machine: Command, program: Command): void {
  registerAdd(machine);
  registerRemove(machine);
  registerList(machine, program);
  registerScanKeys(machine);
  registerSetup(machine);
}

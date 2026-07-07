/**
 * Cloud Machine Provisioning
 *
 * Orchestrates the full create/destroy lifecycle for cloud-provisioned machines.
 * Uses OpenTofu for VM provisioning, then chains into the existing machine
 * bootstrap pipeline (add-machine → scan-keys → setup-machine → push-infra).
 */

import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { DEFAULTS } from '@rediacc/shared/config';
import { t } from '../../i18n/index.js';
import { configService } from '../config/config-resources.js';
import { pushInfraConfig, removeMachineDnsRecords } from '../provision/infra-provision.js';
import { outputService } from '../core/output.js';
import { bootstrapMachine, scanHostKeys, waitForSSH } from '../renet/machine-bootstrap.js';
import { TofuExecutor } from './executor.js';
import { resolveProviderMapping } from './provider-resolver.js';
import { generateTfJson } from './tf-generator.js';

const TOFU_BASE_DIR = join(homedir(), '.config', 'rediacc', 'tofu');

interface CreateOptions {
  region?: string;
  instanceType?: string;
  image?: string;
  sshUser?: string;
  baseDomain?: string;
  /** Full infra config to inherit (from source machine during backup push auto-provision). Overrides baseDomain. */
  inheritInfra?: import('../../types/index.js').InfraConfig;
  /** Skip infra configuration entirely. */
  noInfra?: boolean;
  debug?: boolean;
}

interface DestroyOptions {
  force?: boolean;
  debug?: boolean;
}

function getTofuDir(machineName: string): string {
  return join(TOFU_BASE_DIR, machineName);
}

/**
 * Resolve infrastructure source from options or sibling machines.
 */
async function resolveInfraSource(
  machineName: string,
  options: CreateOptions
): Promise<Partial<import('../../types/index.js').InfraConfig> | undefined> {
  if (options.inheritInfra) return options.inheritInfra;
  if (options.baseDomain) return { baseDomain: options.baseDomain };

  const latestConfig = await configService.getLocalConfig();
  const sibling = Object.entries(latestConfig.machines).find(
    ([name, m]) => name !== machineName && m?.infra?.baseDomain
  );
  if (sibling?.[1]?.infra?.baseDomain) {
    outputService.info(t('commands.machine.provision.infraInherited', { source: sibling[0] }));
    return { baseDomain: sibling[1].infra.baseDomain };
  }
  return undefined;
}

/**
 * Load the SSH public key from config, reading from file if needed.
 */
async function loadSSHPublicKey(): Promise<{
  localConfig: Awaited<ReturnType<typeof configService.getLocalConfig>>;
  sshPublicKey: string;
}> {
  const localConfig = await configService.getLocalConfig();
  let sshPublicKey = localConfig.sshPublicKey;
  if (!sshPublicKey && localConfig.ssh.publicKeyPath) {
    const { readFile } = await import('node:fs/promises');
    sshPublicKey = (await readFile(localConfig.ssh.publicKeyPath, 'utf-8')).trim();
  }
  if (!sshPublicKey) {
    throw new Error(
      'SSH public key required for cloud provisioning. Set with: rdc config init --name <name> --ssh-key <path>'
    );
  }
  return { localConfig, sshPublicKey };
}

/**
 * Create a cloud machine via OpenTofu and bootstrap it.
 *
 * Flow: tofu apply → wait SSH → add-machine → scan-keys → setup-machine → [push-infra]
 */
export async function createCloudMachine(
  machineName: string,
  providerName: string,
  options: CreateOptions = {}
): Promise<void> {
  const config = await configService.getCurrent();
  if (!config) throw new Error('No active config');

  const providerConfig = config.resources?.cloudProviders?.[providerName];
  if (!providerConfig) {
    throw new Error(t('commands.machine.provision.providerRequired', { name: providerName }));
  }

  const mapping = resolveProviderMapping(providerConfig);
  const { sshPublicKey } = await loadSSHPublicKey();

  await TofuExecutor.resolveBinary();

  const tfConfig = generateTfJson({
    machineName,
    mapping,
    apiToken: providerConfig.apiToken,
    sshPublicKey,
    overrides: { region: options.region, instanceType: options.instanceType, image: options.image },
  });

  const executor = new TofuExecutor(getTofuDir(machineName));
  await executor.writeConfig(tfConfig);

  const providerLabel =
    providerConfig.provider ?? providerConfig.source ?? DEFAULTS.CLOUD.UNKNOWN_PROVIDER;
  const regionLabel = options.region ?? mapping.defaults?.[mapping.regionAttr] ?? '';
  outputService.info(
    t('commands.machine.provision.provisioning', {
      name: machineName,
      provider: providerLabel,
      region: regionLabel,
    })
  );

  await executor.init({ debug: options.debug });
  await executor.apply({ debug: options.debug });

  const outputs: Partial<Record<string, { value: unknown }>> = await executor.getOutputs();
  const ipv4 = String(outputs.ipv4?.value ?? '');
  const ipv6Raw = outputs.ipv6?.value ? String(outputs.ipv6.value) : undefined;
  const ipv6 = ipv6Raw?.split('/')[0];

  if (!ipv4) throw new Error('OpenTofu apply succeeded but no IPv4 address in outputs');

  outputService.info(t('commands.machine.provision.waitingSSH'));
  const sshUser = options.sshUser ?? providerConfig.sshUser ?? DEFAULTS.CLOUD.SSH_USER;
  const sshPort = DEFAULTS.SSH.PORT;
  await waitForSSH(ipv4, sshPort);
  outputService.info(t('commands.machine.provision.sshReady'));

  await configService.addMachine(machineName, { ip: ipv4, user: sshUser, port: sshPort });
  const keyscan = scanHostKeys(ipv4, sshPort);
  if (keyscan) await configService.updateMachine(machineName, { knownHosts: keyscan });

  outputService.info(t('commands.machine.provision.settingUp'));
  await bootstrapMachine(machineName, options);

  // set-infra + push-infra
  if (!options.noInfra) {
    const infraSource = await resolveInfraSource(machineName, options);
    if (infraSource?.baseDomain) {
      outputService.info(t('commands.machine.provision.configuringInfra', { name: machineName }));
      await configService.setMachineInfra(machineName, {
        ...infraSource,
        publicIPv4: ipv4,
        publicIPv6: ipv6,
      });
      await pushInfraConfig(machineName, { debug: options.debug });
    } else {
      outputService.info(t('commands.machine.provision.noInfraHint'));
    }
  }

  outputService.success(t('commands.machine.provision.completed', { name: machineName, ip: ipv4 }));
}

/**
 * Clean up DNS records and remove machine from config.
 * Best-effort: failures don't block the deprovision flow.
 */
async function cleanupMachineResources(machineName: string): Promise<void> {
  try {
    const localConfig = await configService.getLocalConfig();
    const machine = localConfig.machines[machineName];
    if (machine?.infra) {
      const deleted = await removeMachineDnsRecords(machineName, machine.infra, localConfig);
      if (deleted > 0) {
        outputService.info(t('commands.machine.deprovision.dnsCleanedUp', { count: deleted }));
      }
    }
  } catch {
    // DNS cleanup is best-effort
  }

  try {
    await configService.removeMachine(machineName);
  } catch {
    // Machine may not exist in config if only partially created
  }
}

/**
 * Destroy a cloud-provisioned machine via OpenTofu and remove from config.
 */
export async function destroyCloudMachine(
  machineName: string,
  options: DestroyOptions = {}
): Promise<void> {
  const tofuDir = getTofuDir(machineName);

  if (!existsSync(tofuDir)) {
    throw new Error(t('commands.machine.deprovision.noState', { name: machineName }));
  }

  outputService.info(t('commands.machine.deprovision.destroying', { name: machineName }));

  const executor = new TofuExecutor(tofuDir);

  try {
    await executor.destroy({ debug: options.debug });
  } catch (error) {
    if (!options.force) throw error;
    // --force: warn but continue with config removal and cleanup
    outputService.warn(
      t('commands.machine.deprovision.destroyFailed', {
        name: machineName,
        error: error instanceof Error ? error.message : String(error),
      })
    );
  }

  await cleanupMachineResources(machineName);

  // Clean up tofu state
  await executor.cleanup();

  outputService.success(t('commands.machine.deprovision.completed', { name: machineName }));
}

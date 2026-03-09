/**
 * Cloud Machine Provisioning
 *
 * Orchestrates the full create/destroy lifecycle for cloud-provisioned machines.
 * Uses OpenTofu for VM provisioning, then chains into the existing machine
 * bootstrap pipeline (add-machine → scan-keys → setup-machine → push-infra).
 */

import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { DEFAULTS } from '@rediacc/shared/config';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { t } from '../../i18n/index.js';
import { configService } from '../config-resources.js';
import { pushInfraConfig, removeMachineDnsRecords } from '../infra-provision.js';
import { outputService } from '../output.js';
import { provisionRenetToRemote, readSSHKey } from '../renet-execution.js';
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

function scanHostKeys(ip: string, port: number): string {
  try {
    return execFileSync('ssh-keyscan', ['-p', String(port), ip], {
      encoding: 'utf-8',
      timeout: 10_000,
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    return '';
  }
}

async function waitForSSH(ip: string, port: number, timeoutMs = 120_000): Promise<void> {
  const start = Date.now();
  const interval = 5_000;

  while (Date.now() - start < timeoutMs) {
    try {
      const keys = scanHostKeys(ip, port);
      if (keys) return;
    } catch {
      // ignore
    }
    await sleep(interval);
  }

  throw new Error(`SSH not reachable at ${ip}:${port} after ${timeoutMs / 1000}s`);
}

/**
 * Bootstrap a machine via SSH: provision renet, run setup.
 */
async function bootstrapMachine(machineName: string, options: { debug?: boolean }): Promise<void> {
  const updatedConfig = await configService.getLocalConfig();
  const machine = updatedConfig.machines[machineName]!;
  const sshPrivateKey =
    updatedConfig.sshPrivateKey ?? (await readSSHKey(updatedConfig.ssh.privateKeyPath));

  await provisionRenetToRemote(updatedConfig, machine, sshPrivateKey, { debug: options.debug });

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });
  await sftp.connect();

  try {
    const cmd = 'sudo renet setup --auto --datastore /mnt/rediacc --datastore-size 95%';
    const exitCode = await sftp.execStreaming(cmd, {
      onStdout: (data) => {
        if (options.debug) process.stdout.write(data);
      },
      onStderr: (data) => process.stderr.write(data),
    });
    if (exitCode !== 0) {
      outputService.warn(`Machine setup exited with code ${exitCode}`);
    }
  } finally {
    sftp.close();
  }
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
      'SSH public key required for cloud provisioning. Set with: rdc config set-ssh --private-key <path> --public-key <path>'
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

  const providerConfig = config.cloudProviders?.[providerName];
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

/**
 * Infrastructure Provisioning Service
 *
 * Pushes machine infrastructure configuration to remote machines via SSH.
 * Calls `sudo renet proxy configure` which generates config.env,
 * router.env, and docker-compose.override.yml on the remote machine.
 * Also ensures Cloudflare DNS records for the machine subdomain.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { t } from '../i18n/index.js';
import type { InfraConfig } from '../types/index.js';
import { CloudflareDnsClient, type DnsAction } from './cloudflare-dns.js';
import { configService } from './config-resources.js';
import { outputService } from './output.js';
import { provisionRenetToRemote, readSSHKey } from './renet-execution.js';

interface PushInfraOptions {
  debug?: boolean;
}

/**
 * Build snake_case JSON payload for Go consumption.
 * Machine-level infra fields + config-level shared fields + machine name.
 */
function buildInfraPayload(
  machineName: string,
  infra: InfraConfig,
  configLevel: { cfDnsApiToken?: string; certEmail?: string }
): string {
  const payload: Record<string, unknown> = {};
  payload.machine_name = machineName;
  if (infra.publicIPv4) payload.public_ipv4 = infra.publicIPv4;
  if (infra.publicIPv6) payload.public_ipv6 = infra.publicIPv6;
  if (infra.baseDomain) payload.base_domain = infra.baseDomain;
  if (configLevel.certEmail) payload.cert_email = configLevel.certEmail;
  if (configLevel.cfDnsApiToken) payload.cf_dns_api_token = configLevel.cfDnsApiToken;
  if (infra.tcpPorts && infra.tcpPorts.length > 0) payload.tcp_ports = infra.tcpPorts;
  if (infra.udpPorts && infra.udpPorts.length > 0) payload.udp_ports = infra.udpPorts;
  return JSON.stringify(payload);
}

function logDnsAction(action: DnsAction, type: string, name: string, content: string): void {
  const key =
    `commands.config.infra.push.dns${action.charAt(0).toUpperCase() + action.slice(1)}` as const;
  outputService.info(t(key, { type, name, content }));
}

/**
 * Resolve the Cloudflare zone ID for the given base domain.
 * Uses cached cfDnsZoneId if available, otherwise queries the API and caches.
 */
async function resolveZoneId(
  client: CloudflareDnsClient,
  baseDomain: string,
  cachedZoneId?: string
): Promise<string> {
  if (cachedZoneId) return cachedZoneId;

  outputService.info(t('commands.config.infra.push.dnsResolvingZone', { domain: baseDomain }));
  const zoneId = await client.getZoneId(baseDomain);
  await configService.updateConfigFields({ cfDnsZoneId: zoneId });
  return zoneId;
}

/**
 * Check if DNS operations should be skipped for this infra config.
 * Returns true if DNS should be skipped.
 */
function shouldSkipDns(
  infra: InfraConfig,
  cfDnsApiToken: string | undefined,
  debug: boolean | undefined
): boolean {
  if (!cfDnsApiToken) {
    if (debug) outputService.warn(t('commands.config.infra.push.dnsSkipNoToken'));
    return true;
  }
  if (!infra.baseDomain || infra.baseDomain.endsWith('.local')) {
    if (debug) outputService.info(t('commands.config.infra.push.dnsSkipLocal'));
    return true;
  }
  return !infra.publicIPv4;
}

/**
 * Build DNS record list for a machine subdomain.
 */
function buildMachineDnsRecords(
  machineName: string,
  infra: InfraConfig
): { type: string; name: string; content: string }[] {
  const baseName = `${machineName}.${infra.baseDomain}`;
  const wildcardName = `*.${machineName}.${infra.baseDomain}`;

  const records: { type: string; name: string; content: string }[] = [
    { type: 'A', name: baseName, content: infra.publicIPv4! },
    { type: 'A', name: wildcardName, content: infra.publicIPv4! },
  ];
  if (infra.publicIPv6) {
    records.push(
      { type: 'AAAA', name: baseName, content: infra.publicIPv6 },
      { type: 'AAAA', name: wildcardName, content: infra.publicIPv6 }
    );
  }
  return records;
}

/**
 * Ensure Cloudflare DNS records exist for the machine subdomain.
 * Creates/updates: {machineName}.{baseDomain} and *.{machineName}.{baseDomain}
 */
async function ensureMachineDnsRecords(
  machineName: string,
  infra: InfraConfig,
  config: { cfDnsApiToken?: string; cfDnsZoneId?: string },
  options: PushInfraOptions
): Promise<void> {
  if (shouldSkipDns(infra, config.cfDnsApiToken, options.debug)) return;

  const client = new CloudflareDnsClient(config.cfDnsApiToken!);

  try {
    const zoneId = await resolveZoneId(client, infra.baseDomain!, config.cfDnsZoneId);
    const records = buildMachineDnsRecords(machineName, infra);

    for (const { type, name, content } of records) {
      const action = await client.ensureRecord(zoneId, type, name, content);
      logDnsAction(action, type, name, content);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    outputService.warn(t('commands.config.infra.push.dnsError', { message }));
  }
}

/**
 * Ensure Cloudflare DNS wildcard records for a repo subdomain.
 * Creates: *.{repoName}.{machineName}.{baseDomain} A/AAAA records.
 * Called after `repo up` to enable auto-route DNS resolution.
 */
export async function ensureRepoDnsRecords(
  machineName: string,
  repoName: string,
  infra: InfraConfig,
  config: { cfDnsApiToken?: string; cfDnsZoneId?: string }
): Promise<void> {
  if (!config.cfDnsApiToken) return;
  if (!infra.baseDomain || infra.baseDomain.endsWith('.local')) return;
  if (!infra.publicIPv4) return;

  const client = new CloudflareDnsClient(config.cfDnsApiToken);

  try {
    const zoneId = await resolveZoneId(client, infra.baseDomain, config.cfDnsZoneId);
    const wildcardName = `*.${repoName}.${machineName}.${infra.baseDomain}`;

    const action = await client.ensureRecord(zoneId, 'A', wildcardName, infra.publicIPv4);
    logDnsAction(action, 'A', wildcardName, infra.publicIPv4);

    if (infra.publicIPv6) {
      const action6 = await client.ensureRecord(zoneId, 'AAAA', wildcardName, infra.publicIPv6);
      logDnsAction(action6, 'AAAA', wildcardName, infra.publicIPv6);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    outputService.warn(t('commands.config.infra.push.dnsError', { message }));
  }
}

/**
 * Remove all Cloudflare DNS records for a machine subdomain.
 * Deletes: {machineName}.{baseDomain}, *.{machineName}.{baseDomain},
 * and any repo-level wildcards (*.{repo}.{machineName}.{baseDomain}).
 * Returns the number of records deleted.
 */
export async function removeMachineDnsRecords(
  machineName: string,
  infra: InfraConfig,
  config: { cfDnsApiToken?: string; cfDnsZoneId?: string }
): Promise<number> {
  if (!config.cfDnsApiToken) return 0;
  if (!infra.baseDomain || infra.baseDomain.endsWith('.local')) return 0;

  const client = new CloudflareDnsClient(config.cfDnsApiToken);
  const zoneId = await resolveZoneId(client, infra.baseDomain, config.cfDnsZoneId);
  const suffix = `${machineName}.${infra.baseDomain}`;

  const records = await client.searchRecordsBySuffix(zoneId, suffix);
  for (const record of records) {
    await client.deleteRecord(zoneId, record.id);
    outputService.info(
      t('commands.machine.deprovision.dnsDeleted', { type: record.type, name: record.name })
    );
  }

  return records.length;
}

/**
 * Execute proxy configure + install commands on the remote machine via SSH.
 */
async function executeProxySetup(
  sftp: SFTPClient,
  infraJSON: string,
  baseDomain: string | undefined,
  remoteRenetPath: string,
  options: PushInfraOptions
): Promise<void> {
  const configExitCode = await sftp.execStreaming(`sudo ${remoteRenetPath} proxy configure`, {
    stdin: infraJSON,
    onStdout: (data) => {
      if (options.debug) process.stdout.write(data);
    },
    onStderr: (data) => {
      process.stderr.write(data);
    },
  });

  if (configExitCode !== 0) {
    throw new Error(`renet proxy configure exited with code ${configExitCode}`);
  }

  // Upload cached acme.json before proxy starts (avoids re-requesting certs)
  if (baseDomain) {
    try {
      const { uploadCertCacheViaConnection } = await import('./cert-cache.js');
      const uploaded = await uploadCertCacheViaConnection(sftp, baseDomain, {
        debug: options.debug,
      });
      if (uploaded && options.debug) {
        outputService.info(t('commands.config.infra.push.certCacheUploaded'));
      }
    } catch {
      // Non-fatal: cert cache upload failure should not block push-infra
    }
  }

  if (options.debug) {
    outputService.info(t('commands.context.pushInfra.installingProxy'));
  }

  const installExitCode = await sftp.execStreaming(`sudo ${remoteRenetPath} proxy install`, {
    onStdout: (data) => {
      if (options.debug) process.stdout.write(data);
    },
    onStderr: (data) => {
      process.stderr.write(data);
    },
  });

  if (installExitCode !== 0) {
    outputService.warn(
      `Proxy install exited with code ${installExitCode} (proxy may need manual start)`
    );
  }
}

/**
 * Push infrastructure configuration to a remote machine.
 *
 * Flow:
 * 1. Load machine config + SSH keys from context
 * 2. Provision renet binary to remote
 * 3. Build infra JSON (snake_case keys for Go)
 * 4. SSH: pipe JSON to `sudo renet proxy configure`
 * 5. SSH: run `sudo renet proxy install` (installs systemd service + starts proxy)
 * 6. Ensure Cloudflare DNS records for machine subdomain
 */
export async function pushInfraConfig(
  machineName: string,
  options: PushInfraOptions = {}
): Promise<void> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    const available = Object.keys(localConfig.machines).join(', ');
    throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
  }

  if (!machine.infra) {
    throw new Error(
      `Machine "${machineName}" has no infrastructure config. Set it with: rdc config infra set ${machineName}`
    );
  }

  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  const { remotePath: remoteRenetPath } = await provisionRenetToRemote(
    { renetPath: localConfig.renetPath },
    machine,
    sshPrivateKey,
    {
      debug: options.debug,
      restartServices: false,
    }
  );

  const infraJSON = buildInfraPayload(machineName, machine.infra, {
    cfDnsApiToken: localConfig.cfDnsApiToken,
    certEmail: localConfig.certEmail,
  });

  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });
  await sftp.connect();

  try {
    await executeProxySetup(sftp, infraJSON, machine.infra.baseDomain, remoteRenetPath, options);
  } finally {
    sftp.close();
  }

  await ensureMachineDnsRecords(machineName, machine.infra, localConfig, options);
}

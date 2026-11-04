/**
 * Infrastructure Provisioning Service
 *
 * Pushes machine infrastructure configuration to remote machines via SSH.
 * Calls `sudo renet proxy configure` which generates config.env,
 * router.env, and docker-compose.override.yml on the remote machine.
 * Also ensures Cloudflare DNS records for the machine subdomain.
 */

import { t } from '../../i18n/index.js';
import { parentRepoName } from '../../remote/repository/index.js';
import type { InfraConfig } from '../../types/index.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { setExitCode } from '../core/request-context.js';
import { pendingExitCode, runCommandJob } from '../jobs/command-job.js';
import { bindStepHandler, planStep } from '../jobs/steps.js';
import { machineConnections } from '../machine/machine-connection.js';
import { readSSHKey } from '../renet/renet-execution.js';
import { CloudflareDnsClient, type DnsAction } from './cloudflare-dns.js';

interface PushInfraOptions {
  debug?: boolean;
}

/**
 * Build snake_case JSON payload for Go consumption.
 * Machine-level infra fields + config-level shared fields + machine name.
 */
export function buildInfraPayload(
  machineName: string,
  infra: InfraConfig,
  configLevel: { cfDnsApiToken?: string; certEmail?: string; team?: string }
): string {
  const payload: Record<string, unknown> = {};
  payload.machine_name = machineName;
  payload.team_name = configLevel.team ?? '';
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
    const wildcardName = `*.${parentRepoName(repoName)}.${machineName}.${infra.baseDomain}`;

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
 * Ensure Cloudflare DNS records for a cluster subdomain.
 * Creates: {clusterName}.{machineName}.{baseDomain} and
 * *.{clusterName}.{machineName}.{baseDomain} A/AAAA records, so the flat k8s
 * hostname scheme ({svc}--{ns}.{cluster}.{machine}.{baseDomain}) resolves under
 * one per-cluster wildcard (new cert/DNS only per cluster, never per namespace
 * or fork). Additive analog of ensureRepoDnsRecords; called after cluster create.
 */
export async function ensureClusterDnsRecords(
  machineName: string,
  clusterName: string,
  infra: InfraConfig,
  config: { cfDnsApiToken?: string; cfDnsZoneId?: string }
): Promise<void> {
  if (!config.cfDnsApiToken) return;
  if (!infra.baseDomain || infra.baseDomain.endsWith('.local')) return;
  if (!infra.publicIPv4) return;

  const client = new CloudflareDnsClient(config.cfDnsApiToken);

  try {
    const zoneId = await resolveZoneId(client, infra.baseDomain, config.cfDnsZoneId);
    const clusterBase = `${clusterName}.${machineName}.${infra.baseDomain}`;
    const records: { type: string; name: string; content: string }[] = [
      { type: 'A', name: clusterBase, content: infra.publicIPv4 },
      { type: 'A', name: `*.${clusterBase}`, content: infra.publicIPv4 },
    ];
    if (infra.publicIPv6) {
      records.push(
        { type: 'AAAA', name: clusterBase, content: infra.publicIPv6 },
        { type: 'AAAA', name: `*.${clusterBase}`, content: infra.publicIPv6 }
      );
    }

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
 * Remove all Cloudflare DNS records for a cluster subdomain.
 * Deletes {clusterName}.{machineName}.{baseDomain},
 * *.{clusterName}.{machineName}.{baseDomain}, and any namespace/fork wildcards
 * under it (suffix match). Additive analog of removeMachineDnsRecords; called on
 * cluster destroy. Returns the number of records deleted.
 */
export async function removeClusterDnsRecords(
  machineName: string,
  clusterName: string,
  infra: InfraConfig,
  config: { cfDnsApiToken?: string; cfDnsZoneId?: string }
): Promise<number> {
  if (!config.cfDnsApiToken) return 0;
  if (!infra.baseDomain || infra.baseDomain.endsWith('.local')) return 0;

  const client = new CloudflareDnsClient(config.cfDnsApiToken);
  const zoneId = await resolveZoneId(client, infra.baseDomain, config.cfDnsZoneId);
  const suffix = `${clusterName}.${machineName}.${infra.baseDomain}`;

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
 * Upload the cached acme.json before the proxy starts (avoids re-requesting certs). The upload is a plain SSH write, so it runs on the client before the `infra-push` job starts; a failure never blocks the push.
 */
async function uploadCachedCerts(
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
  sshPrivateKey: string,
  baseDomain: string,
  debug: boolean | undefined
): Promise<void> {
  try {
    const lease = await machineConnections.acquireFor(machine, sshPrivateKey);
    try {
      const { uploadCertCacheViaConnection } = await import('../account/cert-cache.js');
      const uploaded = await uploadCertCacheViaConnection(lease.sftp, baseDomain, { debug });
      if (uploaded && debug) outputService.info(t('commands.config.infra.push.certCacheUploaded'));
    } finally {
      lease.release();
    }
  } catch {
    // Non-fatal: cert cache upload failure should not block push-infra
  }
}

/** The success step of an infra push: the machine's Cloudflare DNS records, read from the config when the job finishes. */
async function ensureMachineDns(machineName: string): Promise<void> {
  const localConfig = await configService.getLocalConfig();
  const infra = localConfig.machines[machineName]?.infra;
  if (!infra) return;
  await ensureMachineDnsRecords(machineName, infra, localConfig, {});
}

bindStepHandler('ensureMachineDns', ({ machine }) => ensureMachineDns(machine));

/** The success step of a provision's setup job: push the infra config the previous step recorded. A failed push is non-fatal, as it was inline. */
bindStepHandler('pushProvisionedInfra', async ({ machine, params }) => {
  try {
    await pushInfraConfig(machine, { debug: params.debug === true });
  } catch (error) {
    outputService.warn(
      `Infra push to ${machine} failed: ${error instanceof Error ? error.message : String(error)}`
    );
  }
});

/**
 * Push infrastructure configuration to a remote machine.
 *
 * Flow:
 * 1. Load machine config + SSH keys from context
 * 2. Build infra JSON (snake_case keys for Go)
 * 3. Upload the cached acme.json over SSH (before the job)
 * 4. One `infra-push` job: `renet proxy configure` with the JSON as its payload, then `renet proxy install`
 * 5. Step on success: ensure Cloudflare DNS records for the machine subdomain
 *
 * Resolves true when the job finished here, false when it was handed back still running (its step runs when `rdc job wait` or the finished notice sees it finish).
 */
export async function pushInfraConfig(
  machineName: string,
  options: PushInfraOptions = {}
): Promise<boolean> {
  const localConfig = await configService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    const available = Object.keys(localConfig.machines).join(', ');
    throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
  }

  if (!machine.infra) {
    throw new Error(
      `Machine "${machineName}" has no infrastructure config. Set it with: rdc machine infra set ${machineName}`
    );
  }

  const sshPrivateKey =
    localConfig.sshPrivateKey ?? (await readSSHKey(localConfig.ssh.privateKeyPath));

  const team = (await configService.applyDefaults({})).team ?? '';
  const infraJSON = buildInfraPayload(machineName, machine.infra, {
    cfDnsApiToken: localConfig.cfDnsApiToken,
    certEmail: localConfig.certEmail,
    team,
  });

  if (machine.infra.baseDomain) {
    await uploadCachedCerts(machine, sshPrivateKey, machine.infra.baseDomain, options.debug);
  }

  const outcome = await runCommandJob(
    'machine infra push',
    {
      functionName: 'infra-push',
      machineName,
      params: {},
      commandKind: { name: 'infra-push', payload: infraJSON },
      debug: options.debug,
    },
    [planStep('ensureMachineDns', { machine: machineName })]
  );
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return false;
  }
  if (!outcome.result.success) {
    throw new Error(
      outcome.result.error ?? `infra push exited with code ${outcome.result.exitCode}`
    );
  }
  return true;
}

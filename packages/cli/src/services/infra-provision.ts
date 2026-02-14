/**
 * Infrastructure Provisioning Service
 *
 * Pushes machine infrastructure configuration to remote machines via SSH.
 * Calls `sudo renet proxy configure` which generates config.env,
 * router.env, and docker-compose.override.yml on the remote machine.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { SFTPClient } from '@rediacc/shared-desktop/sftp';
import { contextService } from './context.js';
import { outputService } from './output.js';
import { provisionRenetToRemote, readSSHKey, readOptionalSSHKey } from './renet-execution.js';
import type { InfraConfig } from '../types/index.js';

interface PushInfraOptions {
  debug?: boolean;
}

/**
 * Convert InfraConfig (camelCase) to snake_case JSON for Go consumption.
 */
function buildInfraPayload(infra: InfraConfig): string {
  const payload: Record<string, unknown> = {};
  if (infra.publicIPv4) payload.public_ipv4 = infra.publicIPv4;
  if (infra.publicIPv6) payload.public_ipv6 = infra.publicIPv6;
  if (infra.baseDomain) payload.base_domain = infra.baseDomain;
  if (infra.certEmail) payload.cert_email = infra.certEmail;
  if (infra.cfDnsApiToken) payload.cf_dns_api_token = infra.cfDnsApiToken;
  if (infra.tcpPorts && infra.tcpPorts.length > 0) payload.tcp_ports = infra.tcpPorts;
  if (infra.udpPorts && infra.udpPorts.length > 0) payload.udp_ports = infra.udpPorts;
  return JSON.stringify(payload);
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
 */
export async function pushInfraConfig(
  machineName: string,
  options: PushInfraOptions = {}
): Promise<void> {
  const localConfig = await contextService.getLocalConfig();
  const machine = localConfig.machines[machineName];
  if (!machine) {
    const available = Object.keys(localConfig.machines).join(', ');
    throw new Error(`Machine "${machineName}" not found. Available: ${available}`);
  }

  if (!machine.infra) {
    throw new Error(
      `Machine "${machineName}" has no infrastructure config. Set it with: rdc context set-infra ${machineName}`
    );
  }

  // Read SSH keys
  const sshPrivateKey = localConfig.sshPrivateKey ?? await readSSHKey(localConfig.ssh.privateKeyPath);
  const sshPublicKey = localConfig.sshPublicKey ?? await readOptionalSSHKey(localConfig.ssh.publicKeyPath);

  // Provision renet binary to remote
  if (options.debug) {
    outputService.info(`Provisioning renet to ${machine.ip}...`);
  }
  await provisionRenetToRemote(
    { renetPath: localConfig.renetPath },
    machine,
    sshPrivateKey,
    { debug: options.debug }
  );

  // Build infra payload
  const infraJSON = buildInfraPayload(machine.infra);

  if (options.debug) {
    outputService.info(`Pushing infra config to ${machine.ip}...`);
  }

  // Connect and execute
  const sftp = new SFTPClient({
    host: machine.ip,
    port: machine.port ?? DEFAULTS.SSH.PORT,
    username: machine.user,
    privateKey: sshPrivateKey,
  });
  await sftp.connect();

  try {
    // Step 1: Configure proxy (generates config.env, router.env, docker-compose.override.yml)
    const configExitCode = await sftp.execStreaming('sudo renet proxy configure', {
      stdin: infraJSON,
      onStdout: (data) => {
        if (options.debug) {
          process.stdout.write(data);
        }
      },
      onStderr: (data) => {
        process.stderr.write(data);
      },
    });

    if (configExitCode !== 0) {
      throw new Error(`renet proxy configure exited with code ${configExitCode}`);
    }

    // Step 2: Install and start proxy (idempotent — safe to run multiple times)
    // Creates systemd service for rediacc-router, copies renet binary, starts everything
    if (options.debug) {
      outputService.info('Installing and starting proxy...');
    }

    const installExitCode = await sftp.execStreaming('sudo renet proxy install', {
      onStdout: (data) => {
        if (options.debug) {
          process.stdout.write(data);
        }
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
  } finally {
    sftp.close();
  }
}

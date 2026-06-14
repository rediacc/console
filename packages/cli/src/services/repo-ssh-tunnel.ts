/**
 * Shared SSH -L tunnel primitives over a repo's sandbox-gateway key.
 *
 * Used by `repo tunnel` (forward a container port) and `vscode connect
 * --browser` (forward the in-sandbox VS Code server port). The repo key's
 * authorized_keys entry forces `renet sandbox-gateway`, which permits
 * port-forward channels — sessions stay sandboxed, forwarding works.
 */

import net from 'node:net';
import type { ChildProcess } from 'node:child_process';
import { SSHConnection, spawnSSH } from '@rediacc/shared-desktop/ssh';
import { TIMEOUT_DEFAULTS } from '@rediacc/shared/config/defaults';
import { t } from '../i18n/index.js';
import type { ConnectionDetails } from './ssh-connection.js';
import { ValidationError } from '../types/errors.js';

export interface TunnelSpec {
  connectionDetails: ConnectionDetails;
  localPort: number;
  /** Remote address as seen from the machine (container service IP or 127.0.0.1). */
  remoteIP: string;
  remotePort: number;
  /** Milliseconds to wait for the local forward to accept connections. */
  readyTimeoutMs?: number;
}

export interface TunnelHandle {
  child: ChildProcess;
  localPort: number;
  /** Resolves when the ssh process exits cleanly (0/null/130), rejects otherwise. */
  waitUntilExit(): Promise<void>;
  /** SIGTERM the ssh process and release the connection resources. */
  close(): Promise<void>;
}

/** Reject early when another process already listens on the local port. */
export async function assertLocalPortFree(port: number): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const srv = net.createServer();
    srv.once('error', () => {
      reject(new ValidationError(t('commands.repo.tunnel.portInUse', { port: String(port) })));
    });
    srv.listen({ port, host: '127.0.0.1' }, () => srv.close(() => resolve()));
  });
}

/** Poll until the forwarded local port accepts TCP connections. */
export async function waitForLocalPort(port: number, timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const connected = await new Promise<boolean>((resolve) => {
      const sock = net.connect({ port, host: '127.0.0.1' });
      sock.once('connect', () => {
        sock.destroy();
        resolve(true);
      });
      sock.once('error', () => resolve(false));
    });
    if (connected) return true;
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
}

/** Find a free local TCP port. */
export async function findFreeLocalPort(): Promise<number> {
  return await new Promise<number>((resolve, reject) => {
    const srv = net.createServer();
    srv.once('error', reject);
    srv.listen({ port: 0, host: '127.0.0.1' }, () => {
      const address = srv.address();
      if (address && typeof address === 'object') {
        const { port } = address;
        srv.close(() => resolve(port));
      } else {
        srv.close(() => reject(new Error('could not allocate a local port')));
      }
    });
  });
}

/**
 * Open an SSH -L tunnel and wait for the local forward to become ready.
 * Throws (after killing the ssh child) when the port never starts accepting.
 */
export async function openRepoTunnel(spec: TunnelSpec): Promise<TunnelHandle> {
  const { connectionDetails, localPort, remoteIP, remotePort } = spec;

  // Fail fast if the local port is taken — otherwise ssh would print
  // "Address already in use" yet keep running, and we would wrongly
  // report the tunnel as active.
  await assertLocalPortFree(localPort);

  const sshConnection = new SSHConnection(
    connectionDetails.privateKey,
    connectionDetails.known_hosts,
    {
      port: connectionDetails.port,
      forceTTY: false,
    }
  );
  await sshConnection.setup();

  const destination = `${connectionDetails.user}@${connectionDetails.host}`;
  const forwardSpec = `${localPort}:${remoteIP}:${remotePort}`;

  const child = spawnSSH(
    destination,
    [...sshConnection.sshOptions, '-N', '-L', forwardSpec],
    undefined,
    {
      env: { ...process.env, ...connectionDetails.environment },
      stdio: 'inherit',
      agentSocketPath: sshConnection.agentSocketPath,
    }
  );

  const ready = await waitForLocalPort(
    localPort,
    spec.readyTimeoutMs ?? TIMEOUT_DEFAULTS.TUNNEL_READY
  );
  if (!ready) {
    child.kill('SIGTERM');
    await sshConnection.cleanup();
    throw new ValidationError(t('commands.repo.tunnel.notReady', { localPort: String(localPort) }));
  }

  return {
    child,
    localPort,
    waitUntilExit: () =>
      new Promise<void>((resolve, reject) => {
        child.on('exit', (code: number | null) => {
          // Exit code 130 = SIGINT (128+2), treat as normal
          if (code === 0 || code === null || code === 130) {
            resolve();
          } else {
            reject(new Error(t('errors.term.sshExitCode', { code })));
          }
        });
        child.on('error', reject);
      }),
    close: async () => {
      child.kill('SIGTERM');
      await sshConnection.cleanup();
    },
  };
}

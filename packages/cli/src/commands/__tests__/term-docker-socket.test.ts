/**
 * A `term connect` session reaches the repo's daemon on either socket layout. The CLI derives
 * `net-<N>/docker-<N>.sock`, but a read-only connection runs the machine's renet as-is, and a daemon started before
 * renet moved keeps serving the flat `docker-<N>.sock` until its next start. The session prefix carries a test that
 * picks the flat socket only when the derived one is absent.
 *
 * The prefix is run for real under sh against real unix sockets, with the runtime root re-pointed at a temp
 * directory, so the test proves the remote end, not only the string.
 */

import { execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync } from 'node:fs';
import { createServer, type Server } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { repoDockerHost, repoDockerSocketPath } from '@rediacc/shared/config/runtime-paths';
import { WK_DATASTORE_PATH, WK_RUNTIME_DIR } from '@rediacc/shared/config/well-known.generated';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import type { ConnectionDetails } from '../../services/machine/ssh-connection.js';
import { buildEnvPrefix } from '../term.js';

const NETWORK_ID = '3136';

function details(environment: Record<string, string>): ConnectionDetails {
  return {
    host: 'h',
    user: 'repo',
    port: 22,
    privateKey: 'k',
    known_hosts: 'kh',
    datastore: WK_DATASTORE_PATH,
    universalUser: 'u',
    environment,
  };
}

const derived = {
  REDIACC_REPOSITORY: 'observability',
  REDIACC_NETWORK_ID: NETWORK_ID,
  DOCKER_SOCKET: repoDockerSocketPath(NETWORK_ID),
  DOCKER_HOST: repoDockerHost(NETWORK_ID),
};

describe('term connect Docker socket on either layout', () => {
  let root: string;
  const servers: Server[] = [];

  beforeAll(() => {
    root = mkdtempSync(join(tmpdir(), 'term-sock-'));
  });

  afterEach(async () => {
    await Promise.all(servers.splice(0).map((s) => new Promise((r) => s.close(r))));
    rmSync(join(root, 'run'), { recursive: true, force: true });
  });

  afterAll(() => {
    rmSync(root, { recursive: true, force: true });
  });

  /** Listens on a unix socket at `path`, creating its parent. */
  async function listen(path: string): Promise<void> {
    mkdirSync(join(path, '..'), { recursive: true });
    const server = createServer();
    servers.push(server);
    await new Promise<void>((resolve) => server.listen(path, resolve));
  }

  /** Runs the session prefix under sh with the runtime root moved under `root`; prints the resolved pair. */
  function resolvedDockerEnv(prefix: string): string {
    const relocated = prefix.replaceAll(WK_RUNTIME_DIR, join(root, 'run'));
    return execFileSync('sh', [
      '-c',
      `${prefix ? relocated : ''}echo "$DOCKER_SOCKET|$DOCKER_HOST"`,
    ])
      .toString()
      .trim();
  }

  const moved = join('run', `net-${NETWORK_ID}`, `docker-${NETWORK_ID}.sock`);
  const flat = join('run', `docker-${NETWORK_ID}.sock`);

  it('keeps the net-<N> socket when the daemon serves it', async () => {
    await listen(join(root, moved));
    await listen(join(root, flat));
    const path = join(root, moved);
    expect(resolvedDockerEnv(buildEnvPrefix(details(derived)))).toBe(`${path}|unix://${path}`);
  });

  it('switches to the flat socket a daemon on the old layout serves', async () => {
    await listen(join(root, flat));
    const path = join(root, flat);
    expect(resolvedDockerEnv(buildEnvPrefix(details(derived)))).toBe(`${path}|unix://${path}`);
  });

  it('keeps the net-<N> socket when neither exists, so the error names the current layout', () => {
    const path = join(root, moved);
    expect(resolvedDockerEnv(buildEnvPrefix(details(derived)))).toBe(`${path}|unix://${path}`);
  });

  it('adds no test for a socket the vault names', () => {
    const prefix = buildEnvPrefix(
      details({ ...derived, DOCKER_SOCKET: '/srv/d.sock', DOCKER_HOST: 'unix:///srv/d.sock' })
    );
    expect(prefix).not.toContain('[ -S');
  });
});

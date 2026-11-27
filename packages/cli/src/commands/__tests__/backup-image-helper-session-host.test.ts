/**
 * The helper session `rdc backup download` and `upload` open rides the address the pooled SSH
 * session reached. After an IPv6 fallback that is not the machine's configured address, and the
 * rsync destination and the known_hosts file it reads must both name the address ssh dials.
 */

import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const CONFIGURED = '203.0.113.7';
const REACHED = '2001:db8::7';

const mocks = vi.hoisted(() => ({
  createKnownHosts: vi.fn(() => Promise.resolve('/tmp/known_hosts_x')),
  startExportSession: vi.fn((input: unknown) => Promise.resolve(input)),
}));

vi.mock('../../remote/ssh/index.js', () => ({
  createTempKnownHostsFile: mocks.createKnownHosts,
  createTempSSHKeyFile: vi.fn(() => Promise.resolve('/tmp/key_x')),
  removeTempKnownHostsFile: vi.fn(() => Promise.resolve()),
  removeTempSSHKeyFile: vi.fn(() => Promise.resolve()),
}));
vi.mock('../../services/backup-image/session.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/backup-image/session.js')>()),
  startExportSession: mocks.startExportSession,
}));
vi.mock('../../remote/sync/rsync.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../remote/sync/rsync.js')>()),
  getRsyncSSHCommand: vi.fn((opts: string) => Promise.resolve(`ssh ${opts}`)),
}));
vi.mock('../../services/machine/machine-connection.js', () => ({
  machineConnections: {
    acquire: vi.fn(() =>
      Promise.resolve({
        ensure: () =>
          Promise.resolve({
            dialedHost: REACHED,
            execSession: () => Promise.resolve({}),
          }),
        machine: { ip: CONFIGURED, user: 'muhammed', knownHosts: `${CONFIGURED} ssh-ed25519 AAAA` },
        sshPrivateKey: 'KEY',
        release: vi.fn(),
      })
    ),
  },
}));

beforeEach(() => {
  mocks.createKnownHosts.mockClear();
  mocks.startExportSession.mockClear();
});

describe('openHelperSession dials the address the pooled session reached', () => {
  it('pins known_hosts and aims rsync at the reached address, not the configured one', async () => {
    const { realDownloadDeps } = await import('../backup-image-deps.js');
    const deps = realDownloadDeps(new AbortController().signal, { json: true });
    await deps.openSession({
      machine: 'hostinger',
      guid: 'aaaaaaaa-0000-4000-8000-000000000001',
      datastore: WK_DATASTORE_PATH,
    } as Parameters<typeof deps.openSession>[0]);
    expect(mocks.createKnownHosts).toHaveBeenCalledWith(expect.any(String), {
      host: REACHED,
      port: 22,
    });
    const input = mocks.startExportSession.mock.calls[0]?.[0] as {
      transport: { userHost: string };
    };
    expect(input.transport.userHost).toBe(`muhammed@[${REACHED}]`);
    expect(input.transport.userHost).not.toContain(CONFIGURED);
  });
});

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { execCalls } = vi.hoisted(() => ({ execCalls: [] as string[] }));

vi.mock('../config/config-resources.js', () => ({
  configService: {
    getLocalConfig: vi.fn().mockResolvedValue({
      sshPrivateKey: 'key',
      ssh: { privateKeyPath: '/k' },
      machines: { m1: { datastore: "/mnt/my data/o'x;y" } },
    }),
  },
}));
vi.mock('../core/output.js', () => ({ outputService: { warn: vi.fn(), info: vi.fn() } }));
vi.mock('../core/request-context.js', () => ({ writeStdout: vi.fn() }));
vi.mock('../renet/renet-execution.js', () => ({
  acquireRemoteRenet: vi.fn().mockResolvedValue({
    remotePath: "/opt/my renet/o'brien;rm -rf x/renet",
    uploaded: false,
  }),
  readSSHKey: vi.fn(),
}));
vi.mock('../machine/machine-connection.js', () => ({
  machineConnections: {
    acquireFor: vi.fn().mockResolvedValue({
      release: vi.fn(),
      sftp: {
        execStreaming: vi.fn((cmd: string) => {
          execCalls.push(cmd);
          return Promise.resolve(0);
        }),
      },
    }),
  },
}));

import { bootstrapMachine } from '../renet/machine-bootstrap.js';

describe('bootstrapMachine setup command', () => {
  beforeEach(() => {
    execCalls.length = 0;
  });

  it('quotes the renet path and the datastore path', async () => {
    await bootstrapMachine('m1', {});
    expect(execCalls).toHaveLength(1);
    expect(execCalls[0]).toMatch(
      /^sudo '\/opt\/my renet\/o'\\''brien;rm -rf x\/renet' setup --auto --datastore '\/mnt\/my data\/o'\\''x;y' --datastore-size /
    );
  });
});

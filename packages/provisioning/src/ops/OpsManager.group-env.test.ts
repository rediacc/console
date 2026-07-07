import { EventEmitter } from 'node:events';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildGroupEnv } from '../factories';
import type { ProvisioningConfig, VMNetworkConfig } from '../types';
import { OpsManager } from './OpsManager';

// Capture every child_process.spawn call so we can assert the environment each
// ops subprocess actually receives. This is the env-bleed guard for driving two
// concurrent KVM groups from one harness process (wave 8): a group's up/down
// must carry its own VM_NET / DOCKER_REGISTRY and never the ambient group's.
const { spawnCalls } = vi.hoisted(() => ({
  spawnCalls: [] as { command: string; args: string[]; env: NodeJS.ProcessEnv }[],
}));

vi.mock('node:child_process', async (importOriginal) => {
  const actual = await importOriginal<typeof import('node:child_process')>();
  return {
    ...actual,
    spawn: (command: string, args: string[], opts: { env: NodeJS.ProcessEnv }) => {
      spawnCalls.push({ command, args, env: opts.env });
      const child = new EventEmitter() as EventEmitter & {
        stdout: EventEmitter;
        stderr: EventEmitter;
        kill: () => void;
      };
      child.stdout = new EventEmitter();
      child.stderr = new EventEmitter();
      child.kill = () => undefined;
      // Resolve the command promise on the next tick with a clean exit.
      setImmediate(() => child.emit('close', 0));
      return child;
    },
  };
});

const GROUP_A: VMNetworkConfig = {
  netBase: '192.168.111',
  netOffset: 0,
  bridgeId: 1,
  workerIds: [11, 12],
  cephIds: [21, 22, 23],
};

const GROUP_B: VMNetworkConfig = {
  netBase: '192.168.112',
  netOffset: 0,
  bridgeId: 5,
  workerIds: [51],
  cephIds: [],
  netName: 'renet12',
  dockerRegistry: '192.168.112.5:5000',
};

function managerFor(network: VMNetworkConfig, groupEnv?: Record<string, string>): OpsManager {
  const config: ProvisioningConfig = {
    network,
    renet: { binaryPath: '/fake/renet', rootPath: '/fake/root' },
    groupEnv,
  };
  return new OpsManager(config);
}

const lastSpawn = () => spawnCalls[spawnCalls.length - 1];

afterEach(() => {
  spawnCalls.length = 0;
});

describe('buildGroupEnv', () => {
  it('emits the group network vars, incl. VM_NET/DOCKER_REGISTRY when present', () => {
    expect(buildGroupEnv(GROUP_B)).toEqual({
      VM_NET_BASE: '192.168.112',
      VM_NET_OFFSET: '0',
      VM_CONTROL: '5',
      VM_BRIDGE: '5',
      VM_WORKERS: '51',
      VM_CEPH_NODES: '',
      VM_NET: 'renet12',
      DOCKER_REGISTRY: '192.168.112.5:5000',
    });
  });

  it('omits VM_NET/DOCKER_REGISTRY for a group that does not pin them', () => {
    const env = buildGroupEnv(GROUP_A);
    expect(env.VM_NET).toBeUndefined();
    expect(env.DOCKER_REGISTRY).toBeUndefined();
    expect(env.VM_WORKERS).toBe('11 12');
    expect(env.VM_CEPH_NODES).toBe('21 22 23');
  });
});

describe('OpsManager threads groupEnv into ops subprocesses', () => {
  it('startVMs for group B spawns with the group B env', async () => {
    const mgr = managerFor(GROUP_B, buildGroupEnv(GROUP_B));
    await mgr.startVMs({ basic: true });

    const call = lastSpawn();
    expect(call.args.slice(0, 2)).toEqual(['ops', 'up']);
    expect(call.env.VM_NET).toBe('renet12');
    expect(call.env.VM_NET_BASE).toBe('192.168.112');
    expect(call.env.VM_CONTROL).toBe('5');
    expect(call.env.VM_BRIDGE).toBe('5');
    expect(call.env.VM_WORKERS).toBe('51');
    expect(call.env.DOCKER_REGISTRY).toBe('192.168.112.5:5000');
  });

  it('stopVMs for group B spawns `ops down` with the group B env (disjoint IDs)', async () => {
    const mgr = managerFor(GROUP_B, buildGroupEnv(GROUP_B));
    await mgr.stopVMs();

    const call = lastSpawn();
    expect(call.args.slice(0, 2)).toEqual(['ops', 'down']);
    // `ops down` keys VM destruction off VM_WORKERS/VM_BRIDGE — group B's must
    // be its own disjoint IDs so it never tears down group A's VMs.
    expect(call.env.VM_WORKERS).toBe('51');
    expect(call.env.VM_BRIDGE).toBe('5');
    expect(call.env.VM_NET).toBe('renet12');
  });

  it('a groupEnv-less manager leaves VM_NET at ambient (single-group unchanged)', async () => {
    const mgr = managerFor(GROUP_A);
    await mgr.startVMs({ basic: true });

    const call = lastSpawn();
    // No injected override: whatever the ambient process carries is what ships.
    expect(call.env.VM_NET).toBe(process.env.VM_NET);
  });

  it('no env-bleed: group A and group B managers spawn with distinct envs', async () => {
    const a = managerFor(GROUP_A, buildGroupEnv(GROUP_A));
    const b = managerFor(GROUP_B, buildGroupEnv(GROUP_B));

    await a.startVMs({ basic: true });
    const aCall = lastSpawn();
    await b.startVMs({ basic: true });
    const bCall = lastSpawn();

    // Group A never inherits group B's network, and vice versa.
    expect(aCall.env.VM_NET_BASE).toBe('192.168.111');
    expect(aCall.env.VM_NET).not.toBe('renet12');
    expect(bCall.env.VM_NET_BASE).toBe('192.168.112');
    expect(bCall.env.VM_NET).toBe('renet12');
  });

  it('runOpsCommandWithEnv merges group env first, caller override wins', async () => {
    const mgr = managerFor(GROUP_B, buildGroupEnv(GROUP_B));
    await mgr.runOpsCommandWithEnv(['status'], [], { DOCKER_REGISTRY: 'override:9000' });

    const call = lastSpawn();
    expect(call.env.VM_NET).toBe('renet12'); // from group env
    expect(call.env.DOCKER_REGISTRY).toBe('override:9000'); // caller override wins
  });
});

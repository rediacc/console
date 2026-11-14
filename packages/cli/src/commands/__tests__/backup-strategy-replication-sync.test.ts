/**
 * The server-side replication rules follow `backup strategy set`: a replicate destination whose --target moves loses the
 * rules at the old store, switching a whole strategy off drops every rule and switching it on registers them again, and
 * a --replicate-from that equals the resulting target is refused before anything is written.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key} ${JSON.stringify(params)}` : key,
}));

type Dest = { name: string; target?: string; mode?: string; from?: string; enabled?: boolean };
const store = vi.hoisted(() => ({
  strategy: undefined as { schedule: string; enabled?: boolean; destinations: Dest[] } | undefined,
}));
const rules = vi.hoisted(() => ({
  remove: vi.fn(),
  register: vi.fn(),
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getBackupStrategy: () => Promise.resolve(store.strategy),
    setBackupStrategy: (_name: string, update: Record<string, unknown>) => {
      store.strategy = { ...(store.strategy as NonNullable<typeof store.strategy>), ...update };
      return Promise.resolve();
    },
    addBackupDestination: (_name: string, dest: Dest) => {
      const strategy = store.strategy as NonNullable<typeof store.strategy>;
      const others = strategy.destinations.filter((d) => d.name !== dest.name);
      const existing = strategy.destinations.find((d) => d.name === dest.name);
      store.strategy = { ...strategy, destinations: [...others, { ...existing, ...dest }] };
      return Promise.resolve();
    },
    getRepository: () => Promise.resolve({}),
  },
}));
vi.mock('../../services/backup/backup-retention.js', async () => ({
  ...(await vi.importActual<object>('../../services/backup/backup-retention.js')),
  hasAccountToken: () => true,
}));
vi.mock('../../services/backup/backup-replication.js', async () => ({
  ...(await vi.importActual<object>('../../services/backup/backup-replication.js')),
  removeReplicationRulesFor: rules.remove,
  registerStrategyReplication: rules.register,
}));
vi.mock('../../services/config/config-strategy-binding.js', async () => ({
  ...(await vi.importActual<object>('../../services/config/config-strategy-binding.js')),
  machinesBoundToStrategy: () => Promise.resolve(['m1']),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn() },
}));

const { applyBackupStrategyOptions } = await import('../backup-strategy.js');

const upload: Dest = { name: 'primary' };
const replica: Dest = { name: 'copy', mode: 'replicate', target: 'eu-west', from: 'home' };
const done = { done: 1, unsupported: false, failures: [] };

beforeEach(() => {
  store.strategy = { schedule: '0 3 * * *', destinations: [upload, replica] };
  rules.remove.mockReset().mockResolvedValue(done);
  rules.register.mockReset().mockResolvedValue(done);
});

const removedTargets = (): string[] =>
  rules.remove.mock.calls.flatMap((c) => (c[1] as Dest[]).map((d) => d.target ?? 'home'));

describe('a replicate destination whose target moves', () => {
  it('drops the rules at the old target and registers the new ones', async () => {
    await applyBackupStrategyOptions('s', { destination: 'copy', target: 'us-east' });
    expect(removedTargets()).toEqual(['eu-west']);
    const registered = rules.register.mock.calls[0][0] as { destinations: Dest[] };
    expect(registered.destinations.find((d) => d.name === 'copy')?.target).toBe('us-east');
    expect(rules.register).toHaveBeenCalledWith(expect.anything(), 'm1');
  });

  it('leaves the old rules alone when --target repeats the stored one (control)', async () => {
    await applyBackupStrategyOptions('s', { destination: 'copy', target: 'eu-west' });
    expect(removedTargets()).toEqual([]);
  });
});

describe('switching a whole strategy off and on', () => {
  it('drops every replicate destination rule on --disable', async () => {
    await applyBackupStrategyOptions('s', { disable: true });
    expect(removedTargets()).toEqual(['eu-west']);
    expect(rules.register).not.toHaveBeenCalled();
  });

  it('registers the rules again on --enable', async () => {
    await applyBackupStrategyOptions('s', { enable: true });
    expect(rules.register).toHaveBeenCalledWith(expect.anything(), 'm1');
    expect(rules.remove).not.toHaveBeenCalled();
  });

  it('touches no rules when the strategy has no replicate destination (control)', async () => {
    store.strategy = { schedule: '0 3 * * *', destinations: [upload] };
    await applyBackupStrategyOptions('s', { disable: true });
    expect(rules.remove).not.toHaveBeenCalled();
  });

  it('keeps --disable with --destination scoped to that destination', async () => {
    await applyBackupStrategyOptions('s', { destination: 'copy', disable: true });
    expect(store.strategy?.enabled).toBeUndefined();
    expect(removedTargets()).toEqual(['eu-west']);
  });
});

describe('--replicate-from that equals the resulting target', () => {
  it('refuses a self-copy with no --target (an absent target is home) and writes nothing', async () => {
    store.strategy = { schedule: '0 3 * * *', destinations: [upload] };
    await expect(
      applyBackupStrategyOptions('s', { destination: 'copy', replicateFrom: 'home' })
    ).rejects.toThrow(/into itself/);
    expect(store.strategy?.destinations).toEqual([upload]);
  });

  it('refuses when the stored destination already targets the source', async () => {
    await expect(
      applyBackupStrategyOptions('s', { destination: 'copy', replicateFrom: 'eu-west' })
    ).rejects.toThrow(/into itself/);
  });

  it('refuses when --target names the source', async () => {
    await expect(
      applyBackupStrategyOptions('s', {
        destination: 'copy',
        target: 'eu-west',
        replicateFrom: 'eu-west',
      })
    ).rejects.toThrow(/into itself/);
  });

  it('refuses a new --target equal to the stored source when --replicate-from is absent', async () => {
    store.strategy = { schedule: '0 3 * * *', destinations: [upload, replica] };
    await expect(
      applyBackupStrategyOptions('s', { destination: 'copy', target: 'home' })
    ).rejects.toThrow(/into itself/);
    expect(store.strategy?.destinations.find((d) => d.name === 'copy')).toMatchObject({
      target: 'eu-west',
      from: 'home',
    });
  });

  it('admits a new --target that differs from the stored source (control)', async () => {
    store.strategy = { schedule: '0 3 * * *', destinations: [upload, replica] };
    await applyBackupStrategyOptions('s', { destination: 'copy', target: 'us-east' });
    expect(store.strategy?.destinations.find((d) => d.name === 'copy')).toMatchObject({
      target: 'us-east',
      from: 'home',
    });
  });

  it('admits a source that differs from the target (control)', async () => {
    await applyBackupStrategyOptions('s', {
      destination: 'copy',
      target: 'us-east',
      replicateFrom: 'home',
    });
    expect(store.strategy?.destinations.find((d) => d.name === 'copy')).toMatchObject({
      target: 'us-east',
      from: 'home',
    });
  });
});

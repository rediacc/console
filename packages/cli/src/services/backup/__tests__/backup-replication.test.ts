/**
 * Replication rules against a mocked HTTP layer (the server routes land separately): the paths and bodies the CLI
 * sends, one rule per (covered lineage, enabled replicate destination), and a 404 from an older account server
 * reported as data rather than thrown.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock('../../account/account-client.js', () => ({ accountServerFetch: fetchMock }));
const config = vi.hoisted(() => ({
  resources: {
    repositories: {
      mail: { tags: { latest: { repositoryGuid: 'r1', grandGuid: 'G1' } } },
      docs: { tags: { latest: { repositoryGuid: 'r2', grandGuid: 'G2' } } },
    },
  },
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: { getCurrent: () => Promise.resolve(config) },
}));

const {
  desiredRules,
  dropReplicationRules,
  pushReplicationRules,
  registerStrategyReplication,
  removeReplicationRulesFor,
} = await import('../backup-replication.js');

const upload = { name: 'primary' };
const replica = { name: 'copy', mode: 'replicate', target: 'eu-west', from: 'home' };
const strategy = { destinations: [upload, replica] };

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockResolvedValue({});
});

describe('desiredRules', () => {
  it('has one rule per covered lineage and enabled replicate destination', () => {
    expect(desiredRules(strategy, config as never)).toEqual([
      { lineageGuid: 'G1', targetId: 'eu-west', from: 'home' },
      { lineageGuid: 'G2', targetId: 'eu-west', from: 'home' },
    ]);
  });

  it('skips a disabled replicate destination and ignores upload destinations', () => {
    const off = { destinations: [upload, { ...replica, enabled: false }] };
    expect(desiredRules(off, config as never)).toEqual([]);
  });

  it('honours include', () => {
    const only = { ...strategy, include: ['mail'] };
    expect(desiredRules(only, config as never).map((r) => r.lineageGuid)).toEqual(['G1']);
  });
});

describe('registerStrategyReplication', () => {
  it('PUTs {lineageGuid, from} to the target store route', async () => {
    const result = await registerStrategyReplication({ ...strategy, include: ['mail'] }, 'm1');
    expect(fetchMock).toHaveBeenCalledWith('/account/api/v1/backups/stores/eu-west/replication', {
      method: 'PUT',
      body: { lineageGuid: 'G1', from: 'home' },
    });
    expect(result).toEqual({ done: 1, unsupported: false, failures: [] });
  });
});

describe('removal', () => {
  it('DELETEs the rule of each lineage on the target route', async () => {
    const result = await removeReplicationRulesFor({ ...strategy, include: ['docs'] }, [replica]);
    expect(fetchMock).toHaveBeenCalledWith(
      '/account/api/v1/backups/stores/eu-west/replication?lineage=G2',
      { method: 'DELETE' }
    );
    expect(result.done).toBe(1);
  });

  it('does nothing for no destinations', async () => {
    expect((await removeReplicationRulesFor(strategy, [])).done).toBe(0);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('server answers', () => {
  it('reports a 404 as unsupported and stops, never throwing', async () => {
    fetchMock.mockRejectedValue(Object.assign(new Error('Not Found'), { status: 404 }));
    const rules = [
      { lineageGuid: 'G1', targetId: 'eu-west', from: 'home' },
      { lineageGuid: 'G2', targetId: 'eu-west', from: 'home' },
    ];
    const result = await pushReplicationRules(rules);
    expect(result).toEqual({ done: 0, unsupported: true, failures: [] });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect((await dropReplicationRules([{ lineageGuid: 'G1', targetId: 'x' }])).unsupported).toBe(
      true
    );
  });

  it('drops past a rule the server does not hold, so one missing rule never strands the rest', async () => {
    fetchMock
      .mockRejectedValueOnce(
        Object.assign(new Error('no such rule'), {
          status: 404,
          code: 'BACKUP_REPLICATE_RULE_UNKNOWN',
        })
      )
      .mockResolvedValueOnce({});
    const result = await dropReplicationRules([
      { lineageGuid: 'G1', targetId: 'eu-west' },
      { lineageGuid: 'G2', targetId: 'eu-west' },
    ]);
    expect(result).toEqual({ done: 2, unsupported: false, failures: [] });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('does not count a RULE_UNKNOWN 404 on a push as done', async () => {
    fetchMock.mockRejectedValueOnce(
      Object.assign(new Error('no such rule'), {
        status: 404,
        code: 'BACKUP_REPLICATE_RULE_UNKNOWN',
      })
    );
    const result = await pushReplicationRules([
      { lineageGuid: 'G1', targetId: 'eu-west', from: 'home' },
    ]);
    expect(result.done).toBe(0);
    expect(result.unsupported).toBe(false);
    expect(result.failures).toHaveLength(1);
    expect(result.failures[0]).toMatchObject({ lineageGuid: 'G1', target: 'eu-west' });
  });

  it('collects a refusal per rule and goes on with the next', async () => {
    fetchMock
      .mockRejectedValueOnce(Object.assign(new Error('source store retired'), { status: 400 }))
      .mockResolvedValueOnce({});
    const result = await pushReplicationRules([
      { lineageGuid: 'G1', targetId: 'eu-west', from: 'home' },
      { lineageGuid: 'G2', targetId: 'eu-west', from: 'home' },
    ]);
    expect(result.done).toBe(1);
    expect(result.failures).toEqual([
      { lineageGuid: 'G1', target: 'eu-west', reason: 'source store retired' },
    ]);
  });
});

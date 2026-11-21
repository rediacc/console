/**
 * `state.replicaSets[*].phase` and `refreshing`: both are optional, so a set
 * recorded before they existed still parses with neither. The readers treat an
 * absent phase as `ready` (repo-replicate-ops.test.ts drives that); this pins the
 * half the schema owns.
 */

import { describe, expect, it } from 'vitest';
import { StateSchema } from '../state-schema.js';

const SET = {
  repo: 'sqldb',
  datastore: 'ds-data',
  cluster: 'prod',
  replicas: [{ index: 1, fork: 'ds-data:r1', node: 'n1' }],
  createdAt: '2026-07-11T00:00:00Z',
};

function parseSet(extra: Record<string, unknown>) {
  return StateSchema.safeParse({ replicaSets: { 'sqldb-replicas': { ...SET, ...extra } } });
}

describe('ReplicaSetSchema phase and refreshing', () => {
  it('a set recorded before the fields existed parses with neither', () => {
    const parsed = parseSet({});
    expect(parsed.success).toBe(true);
    const set = parsed.data?.replicaSets?.['sqldb-replicas'];
    expect(set?.phase).toBeUndefined();
    expect(set?.refreshing).toBeUndefined();
  });

  it('keeps both phases and the snapshot being rolled to', () => {
    for (const phase of ['placing', 'ready']) {
      const parsed = parseSet({ phase, refreshing: 'replicate-next' });
      const set = parsed.data?.replicaSets?.['sqldb-replicas'];
      expect(set?.phase).toBe(phase);
      expect(set?.refreshing).toBe('replicate-next');
    }
  });

  it('refuses a phase it does not know', () => {
    expect(parseSet({ phase: 'done' }).success).toBe(false);
  });
});

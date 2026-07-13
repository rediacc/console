/**
 * removeClusterFromStore hygiene (BUG #22).
 *
 * `cluster destroy` must clear BOTH halves of a cluster's config: the
 * `resources.clusters` declaration AND the `state.clusters` observation. B1
 * live-witnessed the orphan twice (b1src/rdst still in state after destroy), and
 * a same-name recreate would otherwise inherit the stale memberIds ledger and
 * renumber onto the wrong VM ids.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import { describe, expect, it, vi } from 'vitest';

// Capture the mutator so we can run it against a fixture and assert the result.
const update = vi.fn<(name: string, fn: (cfg: RdcConfig) => RdcConfig) => Promise<void>>();
vi.mock('../../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    update: (name: string, fn: (cfg: RdcConfig) => RdcConfig) => update(name, fn),
  },
}));

import { removeClusterFromStore } from '../config-cluster-logic.js';

function configWith(name: string): RdcConfig {
  return {
    resources: { clusters: { [name]: { pools: [] }, other: { pools: [] } } },
    state: { clusters: { [name]: { memberIds: { cp: [1] } }, other: { memberIds: { cp: [2] } } } },
  } as unknown as RdcConfig;
}

describe('removeClusterFromStore (#22)', () => {
  it('clears both resources.clusters AND state.clusters for the named cluster', async () => {
    let mutated: RdcConfig | undefined;
    update.mockImplementation(async (_name, fn) => {
      mutated = fn(configWith('b1src'));
    });

    await removeClusterFromStore('cfg', 'b1src');

    expect(mutated?.resources?.clusters).not.toHaveProperty('b1src');
    // BUG #22: the state half must go too, or a same-name recreate inherits it.
    expect(mutated?.state?.clusters).not.toHaveProperty('b1src');
    // Sibling clusters are untouched in BOTH halves.
    expect(mutated?.resources?.clusters).toHaveProperty('other');
    expect(mutated?.state?.clusters).toHaveProperty('other');
  });

  it('throws when the cluster is not declared', async () => {
    update.mockImplementation(async (_name, fn) => {
      fn(configWith('b1src'));
    });
    await expect(removeClusterFromStore('cfg', 'ghost')).rejects.toThrow(/not found/);
  });
});

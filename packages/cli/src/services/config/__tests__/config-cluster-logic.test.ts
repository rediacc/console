/**
 * removeClusterFromStore hygiene (BUG #22, and its unswept siblings: BUG #89).
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

/**
 * A cluster that OWNS a datastore, which in turn holds a repo — plus a sibling
 * cluster with the same shape, which must survive untouched.
 */
function configWithDatastores(name: string): RdcConfig {
  return {
    resources: {
      clusters: { [name]: { pools: [] }, other: { pools: [] } },
      datastores: {
        dscp: { cluster: name, backend: { kind: 'rbd', pool: 'rbd', image: 'dscp' } },
        dsother: { cluster: 'other', backend: { kind: 'rbd', pool: 'rbd', image: 'dsother' } },
        dsdocker: { backend: { kind: 'local', machine: 'm1', path: '/mnt/x' } },
      },
      repositories: {
        shop: { placement: { datastore: 'dscp' }, grand: 'latest', tags: { latest: {} } },
        keep: { placement: { datastore: 'dsother' }, grand: 'latest', tags: { latest: {} } },
        docker: { placement: { datastore: 'dsdocker' }, grand: 'latest', tags: { latest: {} } },
      },
    },
    state: {
      clusters: { [name]: { memberIds: { cp: [1] } }, other: { memberIds: { cp: [2] } } },
      datastores: {
        dscp: { attachedTo: `${name}-cp-1`, mounted: true },
        dsother: { attachedTo: 'other-cp-1', mounted: true },
        dsdocker: { attachedTo: 'm1', mounted: true },
      },
      repos: {
        shop: { latest: { networkId: 42 } },
        keep: { latest: { networkId: 43 } },
        docker: { latest: { networkId: 44 } },
      },
    },
  } as unknown as RdcConfig;
}

describe('removeClusterFromStore (#22)', () => {
  it('clears both resources.clusters AND state.clusters for the named cluster', async () => {
    let mutated: RdcConfig | undefined;
    update.mockImplementation((_name, fn) => {
      mutated = fn(configWith('b1src'));
      return Promise.resolve();
    });

    await removeClusterFromStore('cfg', 'b1src');

    expect(mutated?.resources?.clusters).not.toHaveProperty('b1src');
    // BUG #22: the state half must go too, or a same-name recreate inherits it.
    expect(mutated?.state?.clusters).not.toHaveProperty('b1src');
    // Sibling clusters are untouched in BOTH halves.
    expect(mutated?.resources?.clusters).toHaveProperty('other');
    expect(mutated?.state?.clusters).toHaveProperty('other');
  });

  it('clears the OBSERVATIONS of everything the cluster owned, keeps the DECLARATIONS (#89)', async () => {
    let mutated: RdcConfig | undefined;
    update.mockImplementation((_name, fn) => {
      mutated = fn(configWithDatastores('b1src'));
      return Promise.resolve();
    });

    await removeClusterFromStore('cfg', 'b1src');

    // #89: state.datastores[dscp].attachedTo named `b1src-cp-1`. Machine names are
    // DETERMINISTIC, so a same-name recreate re-mints that machine — and the stale hint
    // re-aims derived-machine routing at a brand-new machine that has no such datastore.
    // #22's own failure mode, arriving through the field #22 did not clear.
    expect(mutated?.state?.datastores).not.toHaveProperty('dscp');
    expect(mutated?.state?.repos).not.toHaveProperty('shop');

    // The DECLARATION survives: the operator may intend to recreate. A spec outliving its
    // cluster is defensible; an observation of a world that is gone is a lie by construction.
    expect(mutated?.resources?.datastores).toHaveProperty('dscp');
    expect(mutated?.resources?.repositories).toHaveProperty('shop');

    // Another cluster's datastore, and a plain docker datastore, are untouched in BOTH halves.
    expect(mutated?.state?.datastores).toHaveProperty('dsother');
    expect(mutated?.state?.datastores).toHaveProperty('dsdocker');
    expect(mutated?.state?.repos).toHaveProperty('keep');
    expect(mutated?.state?.repos).toHaveProperty('docker');
  });

  it('throws when the cluster is not declared', async () => {
    update.mockImplementation((_name, fn) => {
      fn(configWith('b1src'));
      return Promise.resolve();
    });
    await expect(removeClusterFromStore('cfg', 'ghost')).rejects.toThrow(/not found/);
  });
});

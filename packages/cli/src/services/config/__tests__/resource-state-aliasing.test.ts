/**
 * A resource state owns its copy of the config. configFileStorage.load() hands out its in-process cache, and a
 * state that aliased it made `delete machines[name]` delete from the cache as well. pushOnce reads that cache
 * as the push base, so the base no longer held the machine, no tombstone was built, and the server refused
 * every remote machine removal as anti-downgrade (eu live test, 2026-09-26).
 */

import { describe, expect, it } from 'vitest';
import type { RemoteConfigAdapter } from '../../../adapters/remote-config-adapter.js';
import type { RdcConfig } from '../../../types/index.js';
import { LocalResourceState, RemoteResourceState } from '../resource-state.js';

function config(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '0b7e4f2a-1c3d-4e5f-8a9b-0c1d2e3f4a5b',
    version: 2,
    resources: {
      machines: {
        keep: { ip: '192.0.2.1', user: 'root' },
        gone: { ip: '192.0.2.2', user: 'root' },
      },
      storages: { s3: { provider: 's3' } },
    },
  } as unknown as RdcConfig;
}

describe('a resource state never edits the config it was loaded from', () => {
  it('remote: removing a machine from the state leaves the loaded document holding it', () => {
    const loaded = config();
    const state = RemoteResourceState.load(loaded, 'c', {} as RemoteConfigAdapter, 2, 0);
    const machines = state.getMachines();
    delete machines.gone;
    delete state.getStorages().s3;

    expect(Object.keys(loaded.resources?.machines ?? {})).toEqual(['keep', 'gone']);
    expect(loaded.resources?.storages?.s3).toBeDefined();
  });

  it('local: the same holds', () => {
    const loaded = config();
    const state = LocalResourceState.load(loaded, 'c');
    delete state.getMachines().gone;

    expect(loaded.resources?.machines?.gone).toBeDefined();
  });
});

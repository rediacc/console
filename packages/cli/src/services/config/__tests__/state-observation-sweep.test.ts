/**
 * BUG #89, swept across its class.
 *
 * #22 established the principle — "state is observation; when the thing is gone, its state
 * goes with it" — and applied it to ONE field. #89 found the same hole in
 * `removeClusterFromStore`. These are its SIBLINGS: every other remover that drops a
 * `resources.*` declaration must drop the matching `state.*` observation too.
 *
 * It matters because `state.datastores[*].attachedTo` IS the derived-machine routing hint,
 * and `resolve-machine` throws only when the hint is ABSENT — a hint that is merely WRONG is
 * followed. Machine names are deterministic, so a stale hint does not dangle: it re-aims at
 * a brand-new, same-named machine.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const update = vi.fn<(name: string, fn: (cfg: RdcConfig) => RdcConfig) => Promise<void>>();
const updateState = vi.fn<(name: string, fn: (cfg: RdcConfig) => RdcConfig) => Promise<void>>();
vi.mock('../../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    update: (name: string, fn: (cfg: RdcConfig) => RdcConfig) => update(name, fn),
    updateState: (name: string, fn: (cfg: RdcConfig) => RdcConfig) => updateState(name, fn),
  },
}));
vi.mock('../config-resources.js', () => ({
  configService: { getEffectiveConfigName: () => 'cfg' },
}));

import { dropMachineObservations } from '../config-cluster-logic.js';
import { forgetDatastore } from '../config-datastores.js';

function cfgWith(): RdcConfig {
  return {
    resources: {
      datastores: {
        ds1: { backend: { kind: 'local', machine: 'm1', path: '/mnt/x' } },
        ds2: { backend: { kind: 'local', machine: 'm1', path: '/mnt/y' } },
      },
    },
    state: {
      datastores: {
        ds1: { attachedTo: 'm1', mounted: true },
        ds2: { attachedTo: 'm1', mounted: true },
      },
    },
  } as unknown as RdcConfig;
}

describe('forgetDatastore drops the observation with the declaration (#89 class)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('clears state.datastores for the forgotten datastore, and leaves its siblings alone', async () => {
    let mutated: RdcConfig | undefined;
    update.mockImplementation((_name, fn) => {
      mutated = fn(cfgWith());
      return Promise.resolve();
    });

    await forgetDatastore('ds1');

    // The declaration goes (that is what "forget" means) …
    expect(mutated?.resources?.datastores).not.toHaveProperty('ds1');
    // … and so must the routing hint, or `attachedTo: m1` outlives the datastore itself.
    expect(mutated?.state?.datastores).not.toHaveProperty('ds1');

    expect(mutated?.resources?.datastores).toHaveProperty('ds2');
    expect(mutated?.state?.datastores).toHaveProperty('ds2');
  });
});

describe('dropMachineObservations: `machine remove` (#89 class, third site)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('clears state.machines AND every datastore hint that named the removed machine', async () => {
    let mutated: RdcConfig | undefined;
    updateState.mockImplementation((_name, fn) => {
      mutated = fn({
        resources: {
          datastores: {
            onM1: { backend: { kind: 'local', machine: 'm1', path: '/x' } },
            onM2: { backend: { kind: 'local', machine: 'm2', path: '/y' } },
          },
        },
        state: {
          machines: { m1: { lastSeenAt: 'now' }, m2: { lastSeenAt: 'now' } },
          datastores: {
            onM1: { attachedTo: 'm1', mounted: true },
            onM2: { attachedTo: 'm2', mounted: true },
          },
        },
      } as unknown as RdcConfig);
      return Promise.resolve();
    });

    await dropMachineObservations('cfg', 'm1');

    expect(mutated?.state?.machines).not.toHaveProperty('m1');
    // The hazard: a hint naming a machine that is gone. resolve-machine FOLLOWS a wrong
    // hint (it only throws on a missing one), and machine names are deterministic.
    expect(mutated?.state?.datastores).not.toHaveProperty('onM1');

    // The other machine, and both DECLARATIONS, are untouched.
    expect(mutated?.state?.machines).toHaveProperty('m2');
    expect(mutated?.state?.datastores).toHaveProperty('onM2');
    expect(mutated?.resources?.datastores).toHaveProperty('onM1');
  });
});

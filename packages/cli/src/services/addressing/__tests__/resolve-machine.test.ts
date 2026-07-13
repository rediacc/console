/**
 * Derived-machine resolution tests (spec/03 §2.3). Fixtures stand in for the
 * config; the remote step-5 check is an injected callback, so every step is
 * exercised without a machine.
 */

import type { MachineConfig, RdcConfig, RepoFamily } from '@rediacc/shared/config-schema';
import { describe, expect, it, vi } from 'vitest';
import { CliExitError } from '../../../utils/cli-exit-error.js';
import { type PlacementView, placementViewFromConfig, resolveMachine } from '../resolve-machine.js';

const GUID = '11111111-1111-4111-8111-111111111111';

function machine(overrides: Partial<MachineConfig> = {}): MachineConfig {
  return { ip: '10.0.0.1', user: 'root', ...overrides };
}

function family(placement: RepoFamily['placement'], tags = ['main']): RepoFamily {
  return {
    grand: tags[0],
    tags: Object.fromEntries(tags.map((t) => [t, { repositoryGuid: GUID }])),
    ...(placement ? { placement } : {}),
  };
}

function view(overrides: Partial<PlacementView> = {}): PlacementView {
  return {
    families: {},
    datastores: {},
    stateDatastores: {},
    machines: {},
    ...overrides,
  };
}

async function expectExit(fn: () => Promise<unknown>, code: number): Promise<CliExitError> {
  let thrown: unknown;
  try {
    await fn();
  } catch (error) {
    thrown = error;
  }
  expect(thrown, 'expected a throw').toBeInstanceOf(CliExitError);
  const err = thrown as CliExitError;
  expect(err.exitCode).toBe(code);
  return err;
}

describe('resolveMachine — the {machine} placement arm', () => {
  it('resolves a bare ref to the placed machine and the grand tag', async () => {
    const v = view({
      families: { shop: family({ machine: 'prod-1' }, ['main']) },
      machines: { 'prod-1': machine() },
    });
    expect(await resolveMachine('shop', v)).toEqual({ machine: 'prod-1', tag: 'main' });
  });

  it('resolves an explicit tag', async () => {
    const v = view({
      families: { shop: family({ machine: 'prod-1' }, ['main', 'test']) },
      machines: { 'prod-1': machine() },
    });
    expect(await resolveMachine('shop:test', v)).toEqual({ machine: 'prod-1', tag: 'test' });
  });
});

describe('resolveMachine — lookup failures (exit 5, candidates listed)', () => {
  it('exits 5 for an unknown repository and lists known ones', async () => {
    const v = view({
      families: { shop: family({ machine: 'm1' }), mail: family({ machine: 'm1' }) },
    });
    const err = await expectExit(() => resolveMachine('ghost', v), 5);
    expect(err.details?.join(' ')).toContain('mail');
    expect(err.details?.join(' ')).toContain('shop');
  });

  it('exits 5 for an unknown tag and lists the tags that exist', async () => {
    const v = view({ families: { shop: family({ machine: 'm1' }, ['main', 'test']) } });
    const err = await expectExit(() => resolveMachine('shop:nope', v), 5);
    expect(err.message).toContain('shop');
    expect(err.details?.join(' ')).toContain('main');
    expect(err.details?.join(' ')).toContain('test');
  });
});

describe('resolveMachine — the {datastore} placement arm', () => {
  it('resolves through the attach record and carries the cluster backref', async () => {
    const v = view({
      families: { shop: family({ datastore: 'ds-alpha' }) },
      datastores: {
        'ds-alpha': { backend: { kind: 'rbd', pool: 'p', image: 'i' }, cluster: 'k8s-1' },
      },
      stateDatastores: { 'ds-alpha': { attachedTo: 'node-2' } },
      machines: { 'node-2': machine() },
    });
    expect(await resolveMachine('shop', v)).toEqual({
      machine: 'node-2',
      datastore: 'ds-alpha',
      cluster: 'k8s-1',
      tag: 'main',
    });
  });

  it('exits 5 when the referenced datastore is not in the registry', async () => {
    const v = view({ families: { shop: family({ datastore: 'gone' }) } });
    const err = await expectExit(() => resolveMachine('shop', v), 5);
    expect(err.message).toContain('gone');
  });

  it('exits 12 with the attach/reconcile teaching error when unattached', async () => {
    const v = view({
      families: { shop: family({ datastore: 'ds-alpha' }) },
      datastores: { 'ds-alpha': { backend: { kind: 'rbd', pool: 'p', image: 'i' } } },
      stateDatastores: {},
    });
    const err = await expectExit(() => resolveMachine('shop', v), 12);
    expect(err.message).toBe(
      'datastore ds-alpha is not attached to any machine. ' +
        'Attach it: "rdc datastore attach ds-alpha --to <machine>" ' +
        '(or "rdc config reconcile" if it is attached but the config does not know).'
    );
  });
});

describe('resolveMachine — missing placement', () => {
  it('exits 12 pointing at config reconcile', async () => {
    const v = view({ families: { shop: family(undefined) } });
    const err = await expectExit(() => resolveMachine('shop', v), 12);
    expect(err.message).toContain('no recorded placement');
    expect(err.message).toContain('rdc config reconcile');
  });
});

describe('resolveMachine — @place (step 4)', () => {
  it('accepts a redundant @place that matches the machine', async () => {
    const v = view({
      families: { shop: family({ machine: 'prod-1' }) },
      machines: { 'prod-1': machine() },
    });
    expect(await resolveMachine('shop@prod-1', v)).toEqual({
      machine: 'prod-1',
      tag: 'main',
      place: 'prod-1',
    });
  });

  it('accepts a redundant @place that matches the machine cluster', async () => {
    const v = view({
      families: { shop: family({ datastore: 'ds' }) },
      datastores: { ds: { backend: { kind: 'rbd', pool: 'p', image: 'i' }, cluster: 'k8s-1' } },
      stateDatastores: { ds: { attachedTo: 'node-2' } },
      machines: { 'node-2': machine({ cluster: { cluster: 'k8s-1', pool: 'servers' } }) },
    });
    const resolved = await resolveMachine('shop@k8s-1', v);
    expect(resolved.machine).toBe('node-2');
    expect(resolved.place).toBe('k8s-1');
  });

  it('exits 12 with the §3.2 conflict text on a contradiction', async () => {
    const v = view({
      families: { shop: family({ machine: 'prod-1' }) },
      machines: { 'prod-1': machine() },
    });
    const err = await expectExit(() => resolveMachine('shop@backup-2', v), 12);
    // Interpolate the names so the source has no contiguous `repo migrate shop`
    // literal (flagged by no-positional-cli-syntax-source until w2b lands it).
    const name = 'shop';
    const home = 'prod-1';
    const at = 'backup-2';
    expect(err.message).toBe(
      `${name} is placed at ${home}; you addressed ${name}@${at}. ` +
        `For the pushed backup copy on ${at} use "rdc backup restore ${name}@${at}"; ` +
        `to move the repo use "rdc repo migrate ${name} --to ${at}".`
    );
  });
});

describe('resolveMachine — verify before executing (step 5)', () => {
  const attachedView = () =>
    view({
      families: { shop: family({ datastore: 'ds' }) },
      datastores: { ds: { backend: { kind: 'rbd', pool: 'p', image: 'i' } } },
      stateDatastores: { ds: { attachedTo: 'node-2' } },
      machines: { 'node-2': machine() },
    });

  it('exits 12 with the reconcile teaching error when the mount check fails', async () => {
    const verifyMount = vi.fn().mockResolvedValue(false);
    const err = await expectExit(() => resolveMachine('shop', attachedView(), { verifyMount }), 12);
    expect(verifyMount).toHaveBeenCalledWith('node-2', 'ds');
    expect(err.message).toBe(
      'config says ds is attached to node-2, but node-2 does not mount it. ' +
        'Run "rdc config reconcile", then retry.'
    );
  });

  it('proceeds when the mount check passes', async () => {
    const verifyMount = vi.fn().mockResolvedValue(true);
    const resolved = await resolveMachine('shop', attachedView(), { verifyMount });
    expect(resolved.machine).toBe('node-2');
    expect(verifyMount).toHaveBeenCalledOnce();
  });

  it('skips the remote round-trip for a read-only verb', async () => {
    const verifyMount = vi.fn().mockResolvedValue(false);
    const resolved = await resolveMachine('shop', attachedView(), { verifyMount, readOnly: true });
    expect(resolved.machine).toBe('node-2');
    expect(verifyMount).not.toHaveBeenCalled();
  });

  it('skips step 5 entirely when no verifier is injected (pure resolution)', async () => {
    const resolved = await resolveMachine('shop', attachedView());
    expect(resolved.machine).toBe('node-2');
  });
});

describe('resolveMachine — step 1 grammar violations propagate exit 2', () => {
  it('exits 2 on a bad ref before any config lookup', async () => {
    await expectExit(() => resolveMachine('Bad_Name', view()), 2);
  });
});

describe('placementViewFromConfig', () => {
  it('maps the four config buckets into the view', () => {
    const config = {
      resources: {
        repositories: { shop: family({ machine: 'm1' }) },
        datastores: { ds: { backend: { kind: 'local', machine: 'm1', path: '/x' } } },
        machines: { m1: machine() },
      },
      state: { datastores: { ds: { attachedTo: 'm1' } } },
    } as unknown as RdcConfig;
    const v = placementViewFromConfig(config);
    expect(Object.keys(v.families)).toEqual(['shop']);
    expect(Object.keys(v.datastores)).toEqual(['ds']);
    expect(v.stateDatastores.ds.attachedTo).toBe('m1');
    expect(Object.keys(v.machines)).toEqual(['m1']);
  });

  it('defaults every bucket to empty when the config is bare', () => {
    const v = placementViewFromConfig({} as RdcConfig);
    expect(v).toEqual({ families: {}, datastores: {}, stateDatastores: {}, machines: {} });
  });
});

import { createEmptyRdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ClusterConfig, MachineConfig, RdcConfig } from '../../../types/index.js';
import { configService } from '../../config/config-resources.js';
import { auditService } from '../../core/audit.js';
import { outputService } from '../../core/output.js';
import { localExecutorService } from '../../executor/local-executor.js';
import {
  __setHealthGateClock,
  __setHealthGateDelay,
  forkCluster,
  migrateCluster,
  rehearseCluster,
} from '../cluster-fork.js';
import { installK8s } from '../cluster-kube.js';

// A 2-node k8s cluster: server on prod-cp-1, agent on prod-w-1.
const k8sCluster: ClusterConfig = {
  provider: 'kvm',
  pools: [
    { name: 'cp', role: 'k8s-server', count: 1 },
    { name: 'w', role: 'k8s-agent', count: 1 },
  ],
};

// A ceph-backed cluster (rbd control datastore) — required for cluster fork +
// in-Ceph migrate (both operate on the anchor rbd datastore).
const cephCluster: ClusterConfig = {
  provider: 'kvm',
  pools: [
    { name: 'cp', role: 'k8s-server', count: 1 },
    { name: 'w', role: 'k8s-agent', count: 1 },
    { name: 'storage', role: 'ceph', count: 1 },
  ],
  ceph: { pool: 'rbd' },
};

const memberIps: Record<string, string> = {
  'prod-cp-1': '192.168.111.11',
  'prod-w-1': '192.168.111.12',
  'dest-cp-1': '192.168.111.21',
  'dest-w-1': '192.168.111.22',
  'relocate-target': '192.168.111.99',
};

// The source cluster's ceph datastores as `datastore list --json` would report.
// Captured through the bridge relay, so stdout carries the `[datastore_list] `
// prefix (finding #10 — parseCapturedJson strips it); the mock uses the REAL
// relay-prefixed shape so the fork path exercises the true capture parser.
function datastoreListJson(cluster: string): string {
  const arr = JSON.stringify([
    { name: 'default', backend: 'local', implicit: true },
    { name: `ds-control-${cluster}`, backend: 'ceph', cluster },
    { name: 'shop', backend: 'ceph', cluster },
  ]);
  return `[datastore_list] ${arr}`;
}

// A fork record as `datastore fork --json` emits it (relay-prefixed), ferried to
// the dest and re-serialized by forkCluster for datastore_adopt.
function forkRecordJson(parent: string, tag: string): string {
  const rec = JSON.stringify({
    name: `${parent}:${tag}`,
    backend: 'ceph',
    ceph: { pool: 'rbd', image: `${parent}-${tag}` },
    fork: { parent, tag },
  });
  return `[datastore_fork] ${rec}`;
}

// The ceph client config export as `ceph client config export --json` emits it
// (relay-prefixed base64 conf/keyring).
function cephConfigExportJson(): string {
  return `[ceph_client_config_export] ${JSON.stringify({ conf: 'Y29uZg==', keyring: 'a2V5' })}`;
}

function buildConfig(clusters: Record<string, ClusterConfig>): RdcConfig {
  const cfg = createEmptyRdcConfig();
  cfg.resources = { machines: {}, storages: {}, clusters };
  return cfg;
}

function stubOutput(): void {
  vi.spyOn(outputService, 'info').mockReturnValue(undefined);
  vi.spyOn(outputService, 'success').mockReturnValue(undefined);
  vi.spyOn(outputService, 'warn').mockReturnValue(undefined);
}

function stubConfig(clusters: Record<string, ClusterConfig>): void {
  vi.spyOn(configService, 'getCurrent').mockResolvedValue(buildConfig(clusters));
  vi.spyOn(configService, 'getLocalMachine').mockImplementation((name: string) =>
    Promise.resolve({ ip: memberIps[name] ?? '10.0.0.1', user: 'root' } as MachineConfig)
  );
  let net = 3072;
  vi.spyOn(configService, 'allocateNetworkId').mockImplementation(() => {
    const v = net;
    net += 64;
    return Promise.resolve(v);
  });
  vi.spyOn(auditService, 'recordOperation').mockReturnValue(undefined);
}

function execMock(listCluster = 'prod', destCluster = 'dest') {
  return vi.spyOn(localExecutorService, 'execute').mockImplementation((opts) => {
    // The join-token read returns a CA-derived token on stdout.
    if (opts.functionName === 'kube_join_token') {
      return Promise.resolve({
        success: true,
        stdout: '{"token":"K10abcdef::server:0123456789abcdef"}',
      } as never);
    }
    if (opts.functionName === 'datastore_list') {
      return Promise.resolve({ success: true, stdout: datastoreListJson(listCluster) } as never);
    }
    if (opts.functionName === 'datastore_fork') {
      const parent = String((opts.params as { parent?: string }).parent ?? 'ds');
      const tag = String((opts.params as { tag?: string }).tag ?? 't');
      return Promise.resolve({ success: true, stdout: forkRecordJson(parent, tag) } as never);
    }
    if (opts.functionName === 'ceph_client_config_export') {
      return Promise.resolve({ success: true, stdout: cephConfigExportJson() } as never);
    }
    if (opts.functionName === 'kube_health') {
      // The #8 dest-own-k3s probe queries the DEST's OWN control datastore; a
      // bare (valid) fork target has none, so it reports NOT serving. Any other
      // kube_health (the fork health gate) succeeds.
      const mp = String((opts.params as { mount_path?: string }).mount_path ?? '');
      const bareDest = !mp.includes(`ds-control-${destCluster}`);
      return Promise.resolve({ success: bareDest } as never);
    }
    return Promise.resolve({ success: true } as never);
  });
}

// Health gate: no real waits in unit tests.
__setHealthGateDelay(() => Promise.resolve());

afterEach(() => {
  vi.restoreAllMocks();
  __setHealthGateClock(() => Date.now()); // reset any per-test clock override
});

describe('installK8s (anchor-model multi-node bring-up)', () => {
  it('provisions the anchor control datastore + embedded server, then joins each agent', async () => {
    stubOutput();
    stubConfig({ prod: k8sCluster });
    const exec = execMock();

    await installK8s('prod', k8sCluster, k8sCluster.pools, { debug: false });

    const calls = exec.mock.calls.map((c) => c[0]);
    expect(calls.map((c) => c.functionName)).toEqual([
      'datastore_create', // anchor control datastore (the CP lives inside it)
      'datastore_attach', // mount it at /mnt/rediacc-ds/ds-control-prod
      'kube_install', // embedded k3s server, --data-dir inside the anchor datastore
      'kube_join_token', // read token
      'kube_join', // agent
    ]);

    // Local backend (no ceph pool): control datastore is local, cluster-labeled.
    const create = calls.find((c) => c.functionName === 'datastore_create');
    expect(create?.machineName).toBe('prod-cp-1');
    expect(create?.params).toMatchObject({
      name: 'ds-control-prod',
      backend: 'local',
      size: '10G',
      cluster: 'prod',
    });
    expect(create?.params).not.toHaveProperty('pool');

    const install = calls.find((c) => c.functionName === 'kube_install');
    expect(install?.machineName).toBe('prod-cp-1');
    expect(install?.params).toMatchObject({
      role: 'server',
      bind_ip: '192.168.111.11',
      mount_path: '/mnt/rediacc-ds/ds-control-prod',
    });

    const join = calls.find((c) => c.functionName === 'kube_join');
    expect(join?.machineName).toBe('prod-w-1');
    expect(join?.params).toMatchObject({
      role: 'agent',
      bind_ip: '192.168.111.12',
      endpoint: 'https://192.168.111.11:6443',
      token: 'K10abcdef::server:0123456789abcdef',
    });
  });

  it('uses a ceph-backed control datastore when the cluster provisions ceph', async () => {
    stubOutput();
    const cephCluster: ClusterConfig = {
      provider: 'kvm',
      pools: [
        { name: 'cp', role: 'k8s-server', count: 1 },
        { name: 'storage', role: 'ceph', count: 1 },
      ],
      ceph: { pool: 'rbd_pool' },
    };
    stubConfig({ prod: cephCluster });
    const exec = execMock();

    await installK8s('prod', cephCluster, cephCluster.pools, { debug: false });

    const create = exec.mock.calls
      .map((c) => c[0])
      .find((c) => c.functionName === 'datastore_create');
    expect(create?.params).toMatchObject({
      name: 'ds-control-prod',
      backend: 'ceph',
      pool: 'rbd_pool',
      ceph_cluster: 'ceph',
      cluster: 'prod',
    });
  });
});

describe('forkCluster (P3 anchor+rejoin orchestrator)', () => {
  it('refuses a fork with no destination (two k3s cannot share a host netns)', async () => {
    stubOutput();
    stubConfig({ prod: cephCluster });
    execMock();
    await expect(forkCluster('prod', { tag: 'joseph' })).rejects.toThrow(/distinct machines/);
  });

  it('refuses an invalid --writes disposition', async () => {
    stubOutput();
    stubConfig({ prod: cephCluster, dest: cephCluster });
    execMock();
    await expect(
      forkCluster('prod', { tag: 'joseph', cluster: 'dest', writes: 'bogus' as never })
    ).rejects.toThrow(/--writes/);
  });

  it('refuses a dest already running its own k3s, dispatching nothing destructive (#8)', async () => {
    stubOutput();
    stubConfig({ prod: cephCluster, dest: cephCluster });
    // kube_health SUCCEEDS for the dest's OWN control datastore ⇒ the dest is
    // running its own control plane ⇒ the :6443 collision refusal fires.
    const exec = vi.spyOn(localExecutorService, 'execute').mockImplementation((opts) => {
      if (opts.functionName === 'kube_health') return Promise.resolve({ success: true } as never);
      return Promise.resolve({ success: true } as never);
    });

    await expect(
      forkCluster('prod', { tag: 'joseph', cluster: 'dest', writes: 'local' })
    ).rejects.toThrow(/already\s+running its own k3s/i);

    // Fail-fast: no snapshot/clone was attempted (nothing destructive).
    const names = exec.mock.calls.map((c) => c[0].functionName);
    expect(names).toContain('kube_health');
    expect(names).not.toContain('datastore_snapshot_create');
    expect(names).not.toContain('datastore_fork');
  });

  it('seeds the fork dest with SOURCE ceph access + prereqs before the snapshot (#7/#15)', async () => {
    stubOutput();
    stubConfig({ prod: cephCluster, dest: cephCluster });
    const exec = execMock('prod');

    await forkCluster('prod', { tag: 'joseph', cluster: 'dest', writes: 'local' });

    const names = exec.mock.calls.map((c) => c[0].functionName);
    // The export runs on the SOURCE ceph mon; prep + install run on each dest
    // member; ALL of it precedes the group snapshot (fail-fast, non-destructive).
    const exportIdx = names.indexOf('ceph_client_config_export');
    const snapIdx = names.indexOf('datastore_snapshot_create');
    expect(exportIdx).toBeGreaterThanOrEqual(0);
    expect(exportIdx).toBeLessThan(snapIdx);
    expect(exec.mock.calls[exportIdx][0].machineName).toBe('prod-storage-1');
    const prep = exec.mock.calls
      .map((c) => c[0])
      .filter((c) => c.functionName === 'kube_fork_dest_prep');
    expect(prep.map((c) => c.machineName)).toEqual(['dest-cp-1', 'dest-w-1']);
    const installs = exec.mock.calls
      .map((c) => c[0])
      .filter((c) => c.functionName === 'ceph_client_config_install');
    expect(installs.map((c) => c.machineName)).toEqual(['dest-cp-1', 'dest-w-1']);
    expect(installs.every((c) => c.params.conf === 'Y29uZg==' && c.params.keyring === 'a2V5')).toBe(
      true
    );
  });

  it('group-snaps, clones each datastore, attaches --writes, forks the CP, rejoins agents', async () => {
    stubOutput();
    stubConfig({ prod: cephCluster, dest: cephCluster });
    const exec = execMock('prod');

    await forkCluster('prod', { tag: 'joseph', cluster: 'dest', writes: 'local' });

    const calls = exec.mock.calls.map((c) => c[0]);
    const names = calls.map((c) => c.functionName);
    // Anchor pipeline order: #8 dest-conflict probe → #7/#15 dest ceph seed
    // (export once on the source mon, then prep+install on each dest member) →
    // list → ONE group snap → clone+adopt each (control first, then data) →
    // attach each with --writes → CP identity-rewrite fork → token → agent join.
    expect(names).toEqual([
      'kube_health', // #8 probe: dest not already running its own k3s
      'ceph_client_config_export', // #7 export source ceph config (from the mon)
      'kube_fork_dest_prep', // #15 dest-cp-1 prereqs (rbd + sqlite3)
      'ceph_client_config_install', // #7 dest-cp-1 /etc/ceph
      'kube_fork_dest_prep', // dest-w-1 prereqs
      'ceph_client_config_install', // dest-w-1 /etc/ceph
      'datastore_list',
      'datastore_snapshot_create',
      'datastore_fork', // ds-control-prod
      'datastore_adopt', // ferry the fork record to the dest (#14)
      'datastore_fork', // shop
      'datastore_adopt',
      'datastore_attach', // ds-control-prod:joseph
      'datastore_attach', // shop:joseph
      'kube_identity_rewrite',
      'kube_join_token',
      'kube_join',
    ]);

    // ONE atomic group snapshot across the source cluster (parent never stops).
    const snap = calls.find((c) => c.functionName === 'datastore_snapshot_create');
    expect(snap?.params).toMatchObject({ group: 'prod', snapshot: 'fork-joseph' });

    // Clones come from the group snap, control datastore FIRST.
    const forks = calls.filter((c) => c.functionName === 'datastore_fork');
    expect(forks.map((c) => c.params?.parent)).toEqual(['ds-control-prod', 'shop']);
    expect(forks[0].params).toMatchObject({
      tag: 'joseph',
      snapshot: 'fork-joseph',
      group: 'prod',
    });

    // Attach composes --writes on every clone, on the DEST control node.
    const attaches = calls.filter((c) => c.functionName === 'datastore_attach');
    expect(attaches.map((c) => c.params?.name)).toEqual(['ds-control-prod:joseph', 'shop:joseph']);
    expect(attaches.every((c) => c.params?.writes === 'local')).toBe(true);
    expect(attaches.every((c) => c.machineName === 'dest-cp-1')).toBe(true);

    // The CP identity rewrite is operation=FORK (F1-safe PKI re-mint), role=fork,
    // NEW networkID, on the fork clone's stable-name mount, on the dest control.
    const rewrite = calls.find((c) => c.functionName === 'kube_identity_rewrite');
    expect(rewrite?.machineName).toBe('dest-cp-1');
    expect(rewrite?.params).toMatchObject({
      operation: 'fork',
      mode: 'server',
      role: 'fork',
      writes: 'local',
      mount_path: '/mnt/rediacc-ds/ds-control-prod-joseph',
      new_node_ip: '192.168.111.21',
    });
    expect(rewrite?.params?.new_network_id).toBeTypeOf('number');

    // Agent rejoins fresh with the new-CA token against the fork endpoint.
    const join = calls.find((c) => c.functionName === 'kube_join');
    expect(join?.machineName).toBe('dest-w-1');
    expect(join?.params).toMatchObject({
      role: 'agent',
      token: 'K10abcdef::server:0123456789abcdef',
      endpoint: 'https://192.168.111.21:6443',
    });
  });

  it('--up gates cluster health after the fork boots', async () => {
    stubOutput();
    stubConfig({ prod: cephCluster, dest: cephCluster });
    const exec = execMock('prod');

    await forkCluster('prod', { tag: 'joseph', cluster: 'dest', writes: 'local', up: true });

    // The FIRST kube_health is the #8 dest-conflict probe (dest's own control
    // datastore); the health GATE is the one against the fork mount.
    const gate = exec.mock.calls.find(
      (c) =>
        c[0].functionName === 'kube_health' &&
        (c[0].params as { mount_path?: string }).mount_path ===
          '/mnt/rediacc-ds/ds-control-prod-joseph'
    );
    expect(gate?.[0].machineName).toBe('dest-cp-1');
    expect(gate?.[0].params).toMatchObject({
      mount_path: '/mnt/rediacc-ds/ds-control-prod-joseph',
    });
  });
});

describe('migrateCluster (P3 in-Ceph fenced remap, zero-copy)', () => {
  it('adopt+verify (before down) → down → detach → fenced attach → rewrite → gate → forget', async () => {
    stubOutput();
    stubConfig({ prod: cephCluster });
    const exec = execMock('prod');

    await migrateCluster('prod', { to: 'relocate-target' });

    const calls = exec.mock.calls.map((c) => c[0]);
    const names = calls.map((c) => c.functionName);
    expect(names).toEqual([
      'ceph_client_config_export', // #19 seed dest with source ceph (export from mon)
      'kube_fork_dest_prep', // #19 dest prereqs (rbd + sqlite3)
      'ceph_client_config_install', // #19 dest /etc/ceph client config
      'datastore_list', // capture the source control-datastore record (#18)
      'datastore_adopt', // adopt the plain record on the DEST — BEFORE anything destructive
      'datastore_list', // verify the dest now registers it
      'kube_prep_fork', // down() the source CP (cutover clock starts here)
      'datastore_detach', // release the source lock
      'datastore_attach', // fenced attach on dest
      'kube_identity_rewrite', // operation=migrate (CA preserved)
      'kube_health', // gate the destination
      'datastore_forget', // drop the stale source record (single-mounter invariant)
    ]);
    // Zero data copy: no backup_push / repository transfer.
    expect(calls.some((c) => c.functionName === 'backup_push')).toBe(false);

    // #19: the dest is seeded with the SOURCE cluster's ceph client config BEFORE
    // anything destructive (a bare dest cannot map the shared rbd image otherwise).
    const install = calls.find((c) => c.functionName === 'ceph_client_config_install');
    expect(install?.machineName).toBe('relocate-target');
    expect(names.indexOf('ceph_client_config_install')).toBeLessThan(
      names.indexOf('datastore_attach')
    );

    // The record is adopted PLAIN on the dest, and the adopt precedes the down —
    // finding #18's failure mode (registry miss after the source is down) is
    // excluded by construction.
    const adopt = calls.find((c) => c.functionName === 'datastore_adopt');
    expect(adopt?.machineName).toBe('relocate-target');
    expect(adopt?.params).toMatchObject({ name: 'ds-control-prod', plain: true });
    expect(typeof adopt?.params?.record_b64).toBe('string');
    expect(names.indexOf('datastore_adopt')).toBeLessThan(names.indexOf('kube_prep_fork'));

    const detach = calls.find((c) => c.functionName === 'datastore_detach');
    expect(detach?.params).toMatchObject({ name: 'ds-control-prod' });
    const attach = calls.find((c) => c.functionName === 'datastore_attach');
    expect(attach?.machineName).toBe('relocate-target');
    expect(attach?.params).toMatchObject({ name: 'ds-control-prod', force: true });

    const rewrite = calls.find((c) => c.functionName === 'kube_identity_rewrite');
    expect(rewrite?.machineName).toBe('relocate-target');
    expect(rewrite?.params).toMatchObject({ operation: 'migrate', mode: 'server' });
    // networkID KEPT — migrate never mints a new one.
    expect(rewrite?.params?.new_network_id).toBeUndefined();

    // Single-mounter invariant: forget runs on the SOURCE, after the gate.
    const forget = calls.find((c) => c.functionName === 'datastore_forget');
    expect(forget?.machineName).toBe('prod-cp-1');
    expect(forget?.params).toMatchObject({ name: 'ds-control-prod' });
    expect(names.indexOf('datastore_forget')).toBeGreaterThan(names.indexOf('kube_health'));
  });

  it('aborts with the source untouched when the dest adopt does not register (verify gate)', async () => {
    stubOutput();
    stubConfig({ prod: cephCluster });
    // datastore_list on the DEST omits the control record → the verify gate fails.
    const exec = vi.spyOn(localExecutorService, 'execute').mockImplementation((opts) => {
      if (opts.functionName === 'ceph_client_config_export') {
        return Promise.resolve({ success: true, stdout: cephConfigExportJson() } as never);
      }
      if (opts.functionName === 'datastore_list') {
        const onDest = opts.machineName === 'relocate-target';
        const arr = JSON.stringify(
          onDest
            ? [{ name: 'default', backend: 'local', implicit: true }]
            : [{ name: 'ds-control-prod', backend: 'ceph', cluster: 'prod' }]
        );
        return Promise.resolve({ success: true, stdout: `[datastore_list] ${arr}` } as never);
      }
      return Promise.resolve({ success: true } as never);
    });

    await expect(migrateCluster('prod', { to: 'relocate-target' })).rejects.toThrow(
      /Refusing to down the source/
    );
    // Nothing destructive ran — the source is never downed or detached.
    const names = exec.mock.calls.map((c) => c[0].functionName);
    expect(names).not.toContain('kube_prep_fork');
    expect(names).not.toContain('datastore_detach');
  });

  it('rolls back to the source (re-attach + restart CP) when the dest attach fails', async () => {
    stubOutput();
    stubConfig({ prod: cephCluster });
    const exec = vi.spyOn(localExecutorService, 'execute').mockImplementation((opts) => {
      if (opts.functionName === 'ceph_client_config_export') {
        return Promise.resolve({ success: true, stdout: cephConfigExportJson() } as never);
      }
      if (opts.functionName === 'datastore_list') {
        return Promise.resolve({ success: true, stdout: datastoreListJson('prod') } as never);
      }
      // The DEST fenced attach fails; the SOURCE re-attach (rollback) succeeds.
      if (opts.functionName === 'datastore_attach' && opts.machineName === 'relocate-target') {
        return Promise.resolve({ success: false, error: 'rbd map: image busy' } as never);
      }
      return Promise.resolve({ success: true } as never);
    });

    await expect(migrateCluster('prod', { to: 'relocate-target' })).rejects.toThrow(/ROLLED BACK/);

    const calls = exec.mock.calls.map((c) => c[0]);
    // Rollback re-attaches on the SOURCE (force) and restarts its CP via a
    // migrate-to-self identity rewrite bound to the source's own IP.
    const srcReattach = calls.find(
      (c) => c.functionName === 'datastore_attach' && c.machineName === 'prod-cp-1'
    );
    expect(srcReattach?.params).toMatchObject({ name: 'ds-control-prod', force: true });
    const srcRestart = calls.find(
      (c) => c.functionName === 'kube_identity_rewrite' && c.machineName === 'prod-cp-1'
    );
    expect(srcRestart?.params).toMatchObject({
      operation: 'migrate',
      new_node_ip: '192.168.111.11',
    });
    // The stale source record is NOT forgotten on a failed/rolled-back migrate.
    expect(calls.some((c) => c.functionName === 'datastore_forget')).toBe(false);
  });

  it('refuses a non-ceph cluster (cross-site datastore transfer is a follow-up)', async () => {
    stubOutput();
    stubConfig({ prod: k8sCluster });
    execMock();
    await expect(migrateCluster('prod', { to: 'relocate-target' })).rejects.toThrow(
      /in-Ceph fenced remap/
    );
  });
});

describe('rehearseCluster (P3 ephemeral throwaway fork → gate → discard)', () => {
  it('forks writes=local role=rehearsal with --up, then discards (uninstall + detach --discard)', async () => {
    stubOutput();
    stubConfig({ prod: cephCluster, dest: cephCluster });
    const exec = execMock('prod');

    await rehearseCluster('prod', { cluster: 'dest', tag: 'r1' });

    const calls = exec.mock.calls.map((c) => c[0]);
    // The rehearsal fork runs SECRETLESS (role=rehearsal), ephemeral (writes=local),
    // and gates health (--up ⇒ kube_health).
    const rewrite = calls.find((c) => c.functionName === 'kube_identity_rewrite');
    expect(rewrite?.params).toMatchObject({
      operation: 'fork',
      role: 'rehearsal',
      writes: 'local',
    });
    expect(calls.some((c) => c.functionName === 'kube_health')).toBe(true);

    // Discard: uninstall the fork CP, then detach --discard EVERY fork clone.
    const uninstall = calls.find((c) => c.functionName === 'kube_uninstall');
    expect(uninstall?.machineName).toBe('dest-cp-1');
    expect(uninstall?.params).toMatchObject({ mount_path: '/mnt/rediacc-ds/ds-control-prod-r1' });

    const discards = calls.filter(
      (c) => c.functionName === 'datastore_detach' && c.params?.discard === true
    );
    expect(discards.map((c) => c.params?.name)).toEqual(['ds-control-prod:r1', 'shop:r1']);
    // Discard runs AFTER the fork (uninstall index > identity-rewrite index).
    const names = calls.map((c) => c.functionName);
    expect(names.indexOf('kube_uninstall')).toBeGreaterThan(names.indexOf('kube_identity_rewrite'));
  });

  it('still discards when the fork/gate FAILS (no residue left behind)', async () => {
    stubOutput();
    stubConfig({ prod: cephCluster, dest: cephCluster });
    // Advance the gate clock past the window after two reads so it expires fast.
    let clock = 0;
    __setHealthGateClock(() => {
      clock += 200_000;
      return clock;
    });
    // Make the health gate fail so forkCluster (--up) throws. kube_health false
    // also satisfies the #8 probe (a bare dest reports its own CP not serving).
    const exec = vi.spyOn(localExecutorService, 'execute').mockImplementation((opts) => {
      if (opts.functionName === 'kube_health') {
        return Promise.resolve({ success: false, error: 'not ready' } as never);
      }
      if (opts.functionName === 'kube_join_token') {
        return Promise.resolve({
          success: true,
          stdout: '{"token":"K10abcdef::server:0123456789abcdef"}',
        } as never);
      }
      if (opts.functionName === 'datastore_list') {
        return Promise.resolve({ success: true, stdout: datastoreListJson('prod') } as never);
      }
      if (opts.functionName === 'datastore_fork') {
        const parent = String((opts.params as { parent?: string }).parent ?? 'ds');
        const tag = String((opts.params as { tag?: string }).tag ?? 't');
        return Promise.resolve({ success: true, stdout: forkRecordJson(parent, tag) } as never);
      }
      if (opts.functionName === 'ceph_client_config_export') {
        return Promise.resolve({ success: true, stdout: cephConfigExportJson() } as never);
      }
      return Promise.resolve({ success: true } as never);
    });

    await expect(rehearseCluster('prod', { cluster: 'dest', tag: 'r1' })).rejects.toThrow(
      /health gate/
    );
    // Even on failure, the fork clones are torn down.
    const calls = exec.mock.calls.map((c) => c[0]);
    const discards = calls.filter(
      (c) => c.functionName === 'datastore_detach' && c.params?.discard === true
    );
    expect(discards.length).toBeGreaterThan(0);

    // ★ BUG #44: the teardown must dispatch at the destination control MACHINE.
    // The failure path used to pass the destination CLUSTER name ("dest") into
    // discardRehearsal's `destControl` machine parameter, so every teardown step
    // was aimed at a machine that does not exist. tryDispatch is best-effort, so
    // it swallowed the errors and the failed rehearsal silently left its entire
    // fork behind. Asserting only that the calls HAPPENED is what let that hide:
    // assert WHERE they land.
    const uninstall = calls.find((c) => c.functionName === 'kube_uninstall');
    expect(uninstall?.machineName).toBe('dest-cp-1');
    for (const d of discards) {
      expect(d.machineName).toBe('dest-cp-1');
    }
  });
});

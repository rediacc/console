import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../../src/utils/bridge/BridgeTestRunner';

// The zot pull-through cache E2E is validated in wave 5+ (k8s repo suite),
// where the control node runs `renet kube registry up|wire` and workers pull
// images through it. Until then this suite is gated OFF everywhere: it is a
// coverage anchor for the kube_registry_* bridge functions, not a live run.
// Set RUN_KUBE_REGISTRY_SUITE=1 (with a worker VM present) to enable it.
const enabled = process.env.RUN_KUBE_REGISTRY_SUITE === '1';
const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
const canRun = enabled && workers.length >= 1;

/**
 * zot pull-through registry cache (kube_registry_up / kube_registry_wire).
 *
 * Coverage:
 *   - kube_registry_up: extract the embedded zot binary, render its config with
 *     sync.onDemand upstreams, install + start the rediacc-zot systemd service.
 *   - kube_registry_wire: write containerd certs.d hosts.toml + k3s
 *     registries.yaml so pulls resolve through the local zot cache.
 */
test.describe
  .serial('zot pull-through registry cache @bridge @kube @registry', () => {
    test.skip(!canRun, 'Requires RUN_KUBE_REGISTRY_SUITE=1 and a worker VM (wave 5+)');

    let control: BridgeTestRunner;

    test.beforeAll(() => {
      control = BridgeTestRunner.forWorker(1);
    });

    test('1. kube_registry_up brings the zot cache online', async () => {
      const result = await control.kubeRegistryUp({
        upstreams: 'docker.io,ghcr.io,quay.io',
        scope: 'machine',
      });
      expect(control.isSuccess(result)).toBe(true);
    });

    test('2. kube_registry_wire points containerd + k3s at the cache', async () => {
      const result = await control.kubeRegistryWire({ endpoint: '127.0.0.1:5000' });
      expect(control.isSuccess(result)).toBe(true);
    });
  });

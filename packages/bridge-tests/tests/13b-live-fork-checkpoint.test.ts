import { expect, test } from '@playwright/test';
import {
  DEFAULT_DATASTORE_PATH,
  DEFAULT_NETWORK_ID,
  FORK_NETWORK_ID_A,
  TEST_PASSWORD,
} from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Live Fork with CRIU Checkpoint (console#440)
 *
 * Forks a RUNNING repository with `repository fork --checkpoint` and brings
 * the fork up while the parent keeps running. Asserts the checkpointed
 * process resumes from its dump-time state instead of starting fresh.
 *
 * This guards both halves of the console#440 fix:
 *  - cow_sync parent-mount flush: without it the CRIU dump written moments
 *    before the reflink never reaches the fork's image, the fork's checkpoint
 *    dir is an empty skeleton, and restore is silently skipped (counter
 *    restarts at ~1).
 *  - eBPF alias-subnet remap: without it CRIU's restore fails on the dump's
 *    parent-subnet socket addresses (EPERM from the cross-repo connect filter
 *    or EADDRINUSE against the still-running parent) and the orchestration
 *    falls back to a fresh container.
 *
 * The proof is a monotonic in-memory counter: the fork's counter must be at
 * or above the parent's pre-checkpoint value immediately after `up`, which a
 * fresh container (restarting from 1) cannot reach.
 */

const COUNTER_COMPOSE = (containerName: string) => `services:
  counter:
    image: alpine:3.20
    container_name: ${containerName}
    network_mode: host
    labels:
      - "rediacc.checkpoint=true"
    command: sh -c 'i=0; while true; do i=$$((i+1)); echo "count=$$i"; sleep 1; done'
`;

const COUNTER_REDIACCFILE = `up() {
    renet compose -- up -d
}

down() {
    renet compose -- down
}
`;

test.describe
  .serial('Live Fork Checkpoint Restore @bridge @integration', () => {
    let runner: BridgeTestRunner;
    const timestamp = Date.now();
    const parentRepoName = `cp-livefork-${timestamp}`;
    const forkTag = `cpfork-${timestamp}`;
    const parentContainerName = `cp-counter-${timestamp}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const parentNetworkId = DEFAULT_NETWORK_ID;
    const forkNetworkId = FORK_NETWORK_ID_A;
    let criuAvailable = false;
    let preForkCount = 0;

    /** Last logged counter value of the counter container on a daemon. */
    const counterValue = async (networkId: string | number): Promise<number> => {
      const result = await runner.executeViaBridge(
        `sudo docker -H unix:///var/run/rediacc/docker-${networkId}.sock logs --tail 5 ${parentContainerName} 2>/dev/null | grep -o "count=[0-9]*" | tail -1 | cut -d= -f2`
      );
      return Number.parseInt(result.stdout.trim(), 10) || 0;
    };

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      const criuCheck = await runner.checkCriu();
      criuAvailable = runner.isSuccess(criuCheck);
      if (!criuAvailable) return;

      await runner.resetWorkerState();
      await runner.datastoreInit('10G', datastorePath, true);
      for (const netId of [parentNetworkId, forkNetworkId]) {
        const setupResult = await runner.daemonSetup(netId);
        if (!runner.isSuccess(setupResult)) {
          throw new Error(
            `daemon_setup(${netId}) failed: ${runner.getCombinedOutput(setupResult)}`
          );
        }
      }
    });

    test.afterAll(async () => {
      for (const [name, netId] of [
        [`${parentRepoName}:${forkTag}`, forkNetworkId],
        [parentRepoName, parentNetworkId],
      ] as const) {
        try {
          await runner.repositoryDown(name, datastorePath, String(netId));
        } catch {
          /* ignore */
        }
        try {
          await runner.repositoryUnmount(name, datastorePath);
        } catch {
          /* ignore */
        }
        try {
          await runner.repositoryRm(name, datastorePath);
        } catch {
          /* ignore */
        }
      }
      try {
        await runner.daemonTeardown(forkNetworkId);
        await runner.daemonTeardown(parentNetworkId);
      } catch {
        /* ignore */
      }
    });

    test('1. create and mount parent repository', async () => {
      test.skip(!criuAvailable, 'CRIU not available on worker');
      const result = await runner.repositoryNew(parentRepoName, '1G', TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
      const mountResult = await runner.repositoryMount(
        parentRepoName,
        TEST_PASSWORD,
        datastorePath
      );
      expect(runner.isSuccess(mountResult)).toBe(true);
    });

    test('2. write checkpoint counter compose + Rediaccfile', async () => {
      test.skip(!criuAvailable, 'CRIU not available on worker');
      const composeResult = await runner.writeFileToRepository(
        parentRepoName,
        'docker-compose.yml',
        COUNTER_COMPOSE(parentContainerName),
        datastorePath
      );
      expect(composeResult.code).toBe(0);
      const rediaccfileResult = await runner.writeFileToRepository(
        parentRepoName,
        'Rediaccfile',
        COUNTER_REDIACCFILE,
        datastorePath
      );
      expect(rediaccfileResult.code).toBe(0);
    });

    test('3. start parent counter', async () => {
      test.skip(!criuAvailable, 'CRIU not available on worker');
      const result = await runner.repositoryUp(
        parentRepoName,
        datastorePath,
        String(parentNetworkId)
      );
      expect(runner.isSuccess(result)).toBe(true);
      expect(await runner.isContainerRunning(parentContainerName, String(parentNetworkId))).toBe(
        true
      );
    });

    test('4. wait for parent counter to accumulate state', async () => {
      test.skip(!criuAvailable, 'CRIU not available on worker');
      // 15 ticks gives a restore-vs-fresh margin: a fresh container cannot
      // reach 15 in the few seconds between fork-up and the read in step 6.
      for (let attempt = 0; attempt < 30 && preForkCount < 15; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        preForkCount = await counterValue(parentNetworkId);
      }
      expect(preForkCount).toBeGreaterThanOrEqual(15);
    });

    test('5. fork the RUNNING parent with --checkpoint', async () => {
      test.skip(!criuAvailable, 'CRIU not available on worker');
      const result = await runner.executeViaBridge(
        `sudo renet repository fork --name "${parentRepoName}" --tag "${forkTag}" --datastore "${datastorePath}" --checkpoint --network-id ${parentNetworkId}`
      );
      expect(result.code).toBe(0);
      // The cow_sync fix is what makes this dump land inside the fork's
      // image: verify the fork's checkpoint manifest exists once mounted.
      const mountResult = await runner.repositoryMount(
        `${parentRepoName}:${forkTag}`,
        TEST_PASSWORD,
        datastorePath
      );
      expect(runner.isSuccess(mountResult)).toBe(true);
      const manifestCheck = await runner.executeViaBridge(
        `sudo test -f "${datastorePath}/mounts/${parentRepoName}:${forkTag}/.rediacc/checkpoint/default/manifest.json" && echo present || echo missing`
      );
      expect(manifestCheck.stdout.trim()).toBe('present');
    });

    test('6. fork up restores the checkpointed process (parent still running)', async () => {
      test.skip(!criuAvailable, 'CRIU not available on worker');
      const result = await runner.repositoryUp(
        `${parentRepoName}:${forkTag}`,
        datastorePath,
        String(forkNetworkId)
      );
      expect(runner.isSuccess(result)).toBe(true);

      const forkCount = await counterValue(forkNetworkId);
      expect(
        forkCount,
        `fork counter ${forkCount} < pre-checkpoint ${preForkCount} — CRIU state not restored (fresh start fallback)`
      ).toBeGreaterThanOrEqual(preForkCount);
    });

    test('7. parent kept running through fork + restore', async () => {
      test.skip(!criuAvailable, 'CRIU not available on worker');
      const before = await counterValue(parentNetworkId);
      await new Promise((resolve) => setTimeout(resolve, 3000));
      const after = await counterValue(parentNetworkId);
      expect(after, `parent counter stalled (${before} -> ${after})`).toBeGreaterThan(before);
    });
  });

import { expect, test } from '@playwright/test';
import { DEFAULT_DATASTORE_PATH, TEST_PASSWORD } from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Multi-Machine Integration Workflow
 *
 * Tests operations across multiple VMs.
 * VMs are automatically started via global-setup.ts.
 */
test.describe
  .serial('Multi-Machine Integration @bridge @multi-machine @integration', () => {
    let runner: BridgeTestRunner;
    const repositoryName = `multi-integration-${Date.now()}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const initializedVMs: string[] = [];
    let crossVMSSHAvailable = false;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      // Create the repository before attempting to deploy/push
      await runner.repositoryNew(repositoryName, '500M', TEST_PASSWORD, datastorePath);

      // Check if SSH from VM1 to VM2 is working (required for deploy/push)
      try {
        const sshCheck = await runner.executeOnWorker(
          `ssh -o BatchMode=yes -o ConnectTimeout=5 ${runner.getWorkerVM2()} echo ok 2>/dev/null`
        );
        crossVMSSHAvailable = runner.isSuccess(sshCheck) && sshCheck.stdout.includes('ok');
      } catch {
        crossVMSSHAvailable = false;
      }
    });

    test.afterAll(async () => {
      // Cleanup: ensure repository is unmounted and deleted even if tests fail
      try {
        await runner.repositoryUnmount(repositoryName, datastorePath);
      } catch {
        /* ignore */
      }
      try {
        await runner.repositoryRm(repositoryName, datastorePath);
      } catch {
        /* ignore */
      }
    });

    test('1. verify all machines reachable', async () => {
      const workers = runner.getWorkerVMs();

      for (const vm of workers) {
        const reachable = await runner.isVMReachable(vm);
        expect(reachable).toBe(true);
      }
    });

    test('2. check setup on all machines', async () => {
      const results = await runner.executeOnAllWorkers(
        'renet bridge once --test-mode --function machine_check_setup'
      );

      for (const [, result] of results) {
        expect(runner.isSuccess(result)).toBe(true);
      }
    });

    test('3. check datastores on all machines', async () => {
      const workers = runner.getWorkerVMs();

      for (const vm of workers) {
        // Check if datastore exists and is initialized
        const result = await runner.testFunctionOnMachine(vm, {
          function: 'datastore_status',
          datastorePath: DEFAULT_DATASTORE_PATH,
        });

        if (runner.isSuccess(result)) {
          initializedVMs.push(vm);
        } else {
          // Try to initialize the datastore if not initialized
          // eslint-disable-next-line no-console
          console.log(`Datastore not initialized on ${vm}, attempting to initialize...`);
          const initResult = await runner.testFunctionOnMachine(vm, {
            function: 'datastore_init',
            datastorePath: DEFAULT_DATASTORE_PATH,
            size: '5G',
            force: true,
          });

          if (runner.isSuccess(initResult)) {
            initializedVMs.push(vm);
            // eslint-disable-next-line no-console
            console.log(`Datastore initialized on ${vm}`);
          } else {
            console.warn(`Failed to initialize datastore on ${vm}, skipping this VM`);
          }
        }
      }

      // At least one VM must have initialized datastore for tests to continue
      expect(initializedVMs.length).toBeGreaterThan(0);
    });

    test('4. deploy repository to all machines', async () => {
      test.skip(!crossVMSSHAvailable, 'Cross-VM SSH not available - skipping deploy test');
      const workers = runner.getWorkerVMs();

      for (const vm of workers) {
        const result = await runner.deploy(repositoryName, vm, DEFAULT_DATASTORE_PATH);
        expect(runner.isSuccess(result)).toBe(true);
      }
    });

    test('5. push from VM1 to VM2', async () => {
      test.skip(!crossVMSSHAvailable, 'Cross-VM SSH not available - skipping push test');
      const result = await runner.push(
        repositoryName,
        runner.getWorkerVM2(),
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

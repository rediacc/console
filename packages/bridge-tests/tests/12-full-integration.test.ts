import { expect, test } from "@playwright/test";
import { DEFAULT_DATASTORE_PATH, DEFAULT_NETWORK_ID, TEST_PASSWORD } from "../src/constants";
import { BridgeTestRunner } from "../src/utils/bridge/BridgeTestRunner";

// Check if Ceph is configured - skip Ceph tests if not
const cephNodes = (process.env.VM_CEPH_NODES ?? "").trim().toLowerCase();
const hasCeph = cephNodes.length > 0 && cephNodes !== "none";

/**
 * Full Integration Tests
 *
 * Tests complete workflows that span multiple function categories.
 * These tests validate end-to-end scenarios from setup to cleanup.
 *
 * Scenarios tested:
 * 1. Basic workflow: setup -> create repo -> mount -> up -> down -> unmount -> rm
 * 2. Ceph workflow: pool -> image -> snapshot -> clone -> mount/unmount
 * 3. Multi-machine workflow: setup machines -> deploy -> push/pull
 * 4. Checkpoint workflow: create -> work -> checkpoint -> restore
 */

/**
 * Basic Repository Workflow
 *
 * Tests a complete repository lifecycle from creation to deletion.
 */
test.describe
  .serial("Full Repository Workflow @bridge @integration", () => {
    let runner: BridgeTestRunner;
    const repositoryName = `full-workflow-${Date.now()}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
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

    // Phase 1: System Checks
    test("1.1 ping: verify system connectivity", async () => {
      const result = await runner.ping();
      expect(result.code).toBe(0);
      expect(runner.getCombinedOutput(result)).toContain("pong");
    });

    test("1.2 check_system: verify system requirements", async () => {
      const result = await runner.checkSystem();
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("1.3 check_datastore: verify datastore available", async () => {
      const result = await runner.checkDatastore(datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Phase 2: Repository Creation
    test("2.1 new: create repository", async () => {
      const result = await runner.repositoryNew(repositoryName, "500M", TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("2.2 list: verify repository created", async () => {
      const result = await runner.repositoryList(datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("2.3 info: get repository info", async () => {
      const result = await runner.repositoryInfo(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Phase 3: Mount and Use
    test("3.1 mount: mount repository", async () => {
      const result = await runner.repositoryMount(repositoryName, TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("3.2 status: check mounted status", async () => {
      const result = await runner.repositoryStatus(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("3.3 validate: validate mounted repository", async () => {
      const result = await runner.repositoryValidate(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Phase 4: Rediaccfile Operations
    test("4.1 up: start repository services", async () => {
      const result = await runner.repositoryUp(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("4.2 status: verify services running", async () => {
      const result = await runner.repositoryStatus(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("4.3 down: stop repository services", async () => {
      const result = await runner.repositoryDown(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Phase 5: Resize (requires unmounted repo)
    test("5.1 unmount: unmount for resize", async () => {
      const result = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("5.2 resize: expand repository", async () => {
      const result = await runner.repositoryResize(repositoryName, "1G", TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Phase 6: Cleanup (already unmounted from resize)
    test("6.1 rm: delete repository", async () => {
      const result = await runner.repositoryRm(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Checkpoint Workflow
 *
 * Tests creating checkpoints, making changes, and restoring.
 * Note: checkpoint_list and checkpoint_delete are not implemented in Go.
 */
test.describe
  .serial("Checkpoint Workflow @bridge @integration", () => {
    let runner: BridgeTestRunner;
    const repositoryName = `checkpoint-workflow-${Date.now()}`;
    const checkpoint1 = "initial-state";
    const checkpoint2 = "after-changes";
    const datastorePath = DEFAULT_DATASTORE_PATH;
    let criuAvailable = false;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      // Check if CRIU is available - checkpoint tests require it
      const criuCheck = await runner.checkCriu();
      criuAvailable = runner.isSuccess(criuCheck);
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

    // Setup
    test("1. create repository", async () => {
      const result = await runner.repositoryNew(repositoryName, "500M", TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("2. mount repository", async () => {
      const result = await runner.repositoryMount(repositoryName, TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Daemon setup - required for checkpoint operations (creates Docker socket)
    test("2a. daemon_setup: set up daemon service", async () => {
      if (!criuAvailable) {
        test.skip();
        return;
      }
      const result = await runner.daemonSetup(DEFAULT_NETWORK_ID.toString());
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("2b. daemon_start: start daemon service", async () => {
      if (!criuAvailable) {
        test.skip();
        return;
      }
      const result = await runner.daemonStart(
        repositoryName,
        datastorePath,
        DEFAULT_NETWORK_ID.toString(),
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Checkpoint workflow - requires CRIU
    test("3. create initial checkpoint", async () => {
      if (!criuAvailable) {
        test.skip();
        return;
      }
      const result = await runner.checkpointCreate(
        repositoryName,
        checkpoint1,
        datastorePath,
        DEFAULT_NETWORK_ID,
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("4. start services (make changes)", async () => {
      if (!criuAvailable) {
        test.skip();
        return;
      }
      const result = await runner.repositoryUp(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("5. create checkpoint after changes", async () => {
      if (!criuAvailable) {
        test.skip();
        return;
      }
      const result = await runner.checkpointCreate(
        repositoryName,
        checkpoint2,
        datastorePath,
        DEFAULT_NETWORK_ID,
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("6. stop services", async () => {
      if (!criuAvailable) {
        test.skip();
        return;
      }
      const result = await runner.repositoryDown(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("7. restore to initial checkpoint", async () => {
      if (!criuAvailable) {
        test.skip();
        return;
      }
      const result = await runner.checkpointRestore(
        repositoryName,
        checkpoint1,
        datastorePath,
        DEFAULT_NETWORK_ID,
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Cleanup - always run even if CRIU tests were skipped
    test("8. unmount repository", async () => {
      const result = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("9. delete repository", async () => {
      const result = await runner.repositoryRm(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Ceph Full Stack Workflow
 *
 * Tests the complete Ceph workflow including COW clone mounting.
 */
test.describe
  .serial("Ceph Full Stack Workflow @bridge @ceph @integration", () => {
    test.skip(!hasCeph, "Ceph not configured (VM_CEPH_NODES empty)");
    let runner: BridgeTestRunner;
    const pool = `integration-pool-${Date.now()}`;
    const image = `integration-image-${Date.now()}`;
    const snapshot = `integration-snap-${Date.now()}`;
    const clone = `integration-clone-${Date.now()}`;
    const mountPoint = `/mnt/integration-${Date.now()}`;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forCeph();
    });

    // Health check
    test("1. check Ceph cluster health", async () => {
      const result = await runner.cephHealth();
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Create stack
    test("2. create pool", async () => {
      const result = await runner.cephPoolCreate(pool);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("3. create image in pool", async () => {
      const result = await runner.cephImageCreate(pool, image, "1G");
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("3a. format image with btrfs", async () => {
      const result = await runner.cephImageFormat(
        pool,
        image,
        "btrfs",
        `integration-${Date.now()}`,
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("4. create snapshot of image", async () => {
      const result = await runner.cephSnapshotCreate(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("5. protect snapshot", async () => {
      const result = await runner.cephSnapshotProtect(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("6. create clone from snapshot", async () => {
      const result = await runner.cephCloneCreate(pool, image, snapshot, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // COW Mount (the CORE use case)
    test("7. mount clone with COW overlay", async () => {
      const result = await runner.cephCloneMount(clone, mountPoint, "10G", pool);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Teardown in EXACT order
    test("8. unmount clone (exact teardown order)", async () => {
      const result = await runner.cephCloneUnmount(clone, false, pool);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("9. delete clone", async () => {
      const result = await runner.cephCloneDelete(pool, clone);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("10. unprotect snapshot", async () => {
      const result = await runner.cephSnapshotUnprotect(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("11. delete snapshot", async () => {
      const result = await runner.cephSnapshotDelete(pool, image, snapshot);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("12. delete image", async () => {
      const result = await runner.cephImageDelete(pool, image);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("13. delete pool", async () => {
      const result = await runner.cephPoolDelete(pool);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Multi-Machine Integration Workflow
 *
 * Tests operations across multiple VMs.
 * VMs are automatically started via global-setup.ts.
 */
test.describe
  .serial("Multi-Machine Integration @bridge @multi-machine @integration", () => {
    let runner: BridgeTestRunner;
    const repositoryName = `multi-integration-${Date.now()}`;
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const initializedVMs: string[] = [];
    let crossVMSSHAvailable = false;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      // Create the repository before attempting to deploy/push
      await runner.repositoryNew(repositoryName, "500M", TEST_PASSWORD, datastorePath);

      // Check if SSH from VM1 to VM2 is working (required for deploy/push)
      try {
        const sshCheck = await runner.executeOnWorker(
          `ssh -o BatchMode=yes -o ConnectTimeout=5 ${runner.getWorkerVM2()} echo ok 2>/dev/null`,
        );
        crossVMSSHAvailable = runner.isSuccess(sshCheck) && sshCheck.stdout.includes("ok");
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

    test("1. verify all machines reachable", async () => {
      const workers = runner.getWorkerVMs();

      for (const vm of workers) {
        const reachable = await runner.isVMReachable(vm);
        expect(reachable).toBe(true);
      }
    });

    test("2. check setup on all machines", async () => {
      const results = await runner.executeOnAllWorkers(
        "renet bridge once --test-mode --function machine_check_setup",
      );

      for (const [, result] of results) {
        expect(runner.isSuccess(result)).toBe(true);
      }
    });

    test("3. check datastores on all machines", async () => {
      const workers = runner.getWorkerVMs();

      for (const vm of workers) {
        // Check if datastore exists and is initialized
        const result = await runner.testFunctionOnMachine(vm, {
          function: "datastore_status",
          datastorePath: DEFAULT_DATASTORE_PATH,
        });

        if (runner.isSuccess(result)) {
          initializedVMs.push(vm);
        } else {
          // Try to initialize the datastore if not initialized
          console.log(`Datastore not initialized on ${vm}, attempting to initialize...`);
          const initResult = await runner.testFunctionOnMachine(vm, {
            function: "datastore_init",
            datastorePath: DEFAULT_DATASTORE_PATH,
            size: "5G",
            force: true,
          });

          if (runner.isSuccess(initResult)) {
            initializedVMs.push(vm);
            console.log(`Datastore initialized on ${vm}`);
          } else {
            console.warn(`Failed to initialize datastore on ${vm}, skipping this VM`);
          }
        }
      }

      // At least one VM must have initialized datastore for tests to continue
      expect(initializedVMs.length).toBeGreaterThan(0);
    });

    test("4. deploy repository to all machines", async () => {
      test.skip(!crossVMSSHAvailable, "Cross-VM SSH not available - skipping deploy test");
      const workers = runner.getWorkerVMs();

      for (const vm of workers) {
        const result = await runner.deploy(repositoryName, vm, DEFAULT_DATASTORE_PATH);
        expect(runner.isSuccess(result)).toBe(true);
      }
    });

    test("5. push from VM1 to VM2", async () => {
      test.skip(!crossVMSSHAvailable, "Cross-VM SSH not available - skipping push test");
      const result = await runner.push(repositoryName, runner.getWorkerVM2(), DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Container + Repository Integration
 *
 * Tests containers within the repository context.
 */
test.describe
  .serial("Container Repository Integration @bridge @integration", () => {
    let runner: BridgeTestRunner;
    const repositoryName = `container-integration-${Date.now()}`;
    const containerName = "test-nginx";
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const networkId = DEFAULT_NETWORK_ID;

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
    });

    test.afterAll(async () => {
      // Cleanup: ensure repository is unmounted and deleted even if tests fail
      try {
        await runner.repositoryDown(repositoryName, datastorePath, networkId);
      } catch {
        /* ignore */
      }
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

    // Setup repository
    test("1. create repository", async () => {
      const result = await runner.repositoryNew(repositoryName, "500M", TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("2. mount repository", async () => {
      const result = await runner.repositoryMount(repositoryName, TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Write Rediaccfile and docker-compose.yaml for container setup
    test("2.1 write Rediaccfile", async () => {
      const rediaccfileContent = runner.readFixture("bridge/Rediaccfile.nginx");
      await runner.writeFileToRepository(
        repositoryName,
        "Rediaccfile",
        rediaccfileContent,
        datastorePath,
      );
    });

    test("2.2 write docker-compose.yaml", async () => {
      const dockerComposeContent = runner
        .readFixture("bridge/docker-compose.nginx.yaml")
        .replace(/\$\{CONTAINER_NAME\}/g, containerName);
      await runner.writeFileToRepository(
        repositoryName,
        "docker-compose.yaml",
        dockerComposeContent,
        datastorePath,
      );
    });

    // Setup and start daemon first (required for container operations)
    test("2a. daemon_setup: set up daemon service", async () => {
      // daemonSetup only takes networkId as parameter
      const result = await runner.daemonSetup(networkId.toString());
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("2b. daemon_start: start daemon service", async () => {
      // daemonStart takes (repository, datastorePath, networkId)
      const result = await runner.daemonStart(repositoryName, datastorePath, networkId.toString());
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Start services (which starts containers)
    test("3. up: start repository services", async () => {
      const result = await runner.repositoryUp(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Container operations
    test("4. list containers", async () => {
      const result = await runner.containerList(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("5. start container", async () => {
      const result = await runner.containerStart(containerName, repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("6. inspect container", async () => {
      const result = await runner.containerInspect(
        containerName,
        repositoryName,
        datastorePath,
        networkId,
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("7. get container logs", async () => {
      const result = await runner.containerLogs(containerName, repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("8. stop container", async () => {
      const result = await runner.containerStop(containerName, repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Cleanup
    test("9. down: stop repository services", async () => {
      const result = await runner.repositoryDown(repositoryName, datastorePath, networkId);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("10. unmount repository", async () => {
      const result = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test("11. delete repository", async () => {
      const result = await runner.repositoryRm(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Error Recovery Integration
 *
 * Tests graceful error handling and recovery.
 */
test.describe("Error Recovery Integration @bridge @integration", () => {
  let runner: BridgeTestRunner;

  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test("should handle sequential operations on nonexistent resources", async () => {
    const nonexistent = "nonexistent-resource-xyz";

    // Run operations on nonexistent resources - they should fail gracefully (no crashes/syntax errors)
    // Some operations are strict (fail if resource doesn't exist), others are tolerant (succeed as no-op)
    const [info, mount, up, down, unmount, rm] = await Promise.all([
      runner.repositoryInfo(nonexistent, DEFAULT_DATASTORE_PATH),
      runner.repositoryMount(nonexistent, TEST_PASSWORD, DEFAULT_DATASTORE_PATH),
      runner.repositoryUp(nonexistent, DEFAULT_DATASTORE_PATH),
      runner.repositoryDown(nonexistent, DEFAULT_DATASTORE_PATH),
      runner.repositoryUnmount(nonexistent, DEFAULT_DATASTORE_PATH),
      runner.repositoryRm(nonexistent, DEFAULT_DATASTORE_PATH),
    ]);

    // Strict operations - should fail because resource doesn't exist
    expect(runner.isSuccess(info)).toBe(false); // Can't get info on nonexistent
    expect(runner.isSuccess(mount)).toBe(false); // Can't mount nonexistent
    expect(runner.isSuccess(rm)).toBe(false); // Can't delete nonexistent

    // Tolerant operations - succeed as no-op (nothing to do)
    expect(runner.isSuccess(up)).toBe(true); // No Rediaccfile, skips gracefully
    expect(runner.isSuccess(down)).toBe(true); // Nothing to stop, succeeds
    expect(runner.isSuccess(unmount)).toBe(true); // Already unmounted, succeeds
  });

  test("should recover from failed operation", async () => {
    // Attempt an operation that will fail (mounting nonexistent repository)
    const failResult = await runner.repositoryMount(
      "likely-nonexistent",
      TEST_PASSWORD,
      DEFAULT_DATASTORE_PATH,
    );
    expect(runner.isSuccess(failResult)).toBe(false); // Mount should fail

    // System should still be responsive after the failed operation
    const pingResult = await runner.ping();
    expect(pingResult.code).toBe(0);
    expect(runner.getCombinedOutput(pingResult)).toContain("pong");
  });
});

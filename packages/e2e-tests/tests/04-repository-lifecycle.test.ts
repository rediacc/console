import { expect, test } from '@playwright/test';
import { repoDockerHost, repoDockerSocketPath } from '@rediacc/shared/config/runtime-paths';
import { DEFAULT_DATASTORE_PATH, DEFAULT_NETWORK_ID, TEST_PASSWORD } from '../src/constants';
import { e2eRepoGuid } from '../src/utils/licence';
import { RenetFunctionsTestRunner } from '../src/utils/renet-functions/RenetFunctionsTestRunner';

// renet licenses a repository by its name and the account server signs UUIDs only, so every repository this suite creates is named by a GUID (src/utils/licence.ts).
const TEST_REPOSITORY_NAME = e2eRepoGuid();
const ENCRYPTED_REPO = e2eRepoGuid();
const SPECIAL_REPO = e2eRepoGuid();
const SIZE_TEST_REPO = e2eRepoGuid();
const INVALID_SIZE_REPO = e2eRepoGuid();

/**
 * Repository Lifecycle Tests (12 functions)
 *
 * Tests repository management functions in proper lifecycle order.
 * These are LEVEL 3 functions - require datastore setup first.
 *
 * Functions tested:
 * - new (create repository)
 * - list
 * - info
 * - status
 * - mount
 * - validate
 * - resize / grow
 * - unmount
 * - rm (delete)
 *
 * Lifecycle order (STRICT):
 * 1. new (create)
 * 2. list (verify exists)
 * 3. mount
 * 4. validate
 * 5. resize/grow
 * 6. unmount
 * 7. rm (cleanup)
 */
test.describe
  .serial('Repository Lifecycle @bridge', () => {
    let runner: RenetFunctionsTestRunner;

    test.beforeAll(async () => {
      runner = RenetFunctionsTestRunner.forWorker();
      await runner.resetWorkerState();

      // Initialize and mount datastore (LEVEL 2 prerequisite for repository operations)
      const initResult = await runner.datastoreInitPool('10G', DEFAULT_DATASTORE_PATH, true);
      if (!runner.isSuccess(initResult)) {
        console.error('[Setup] Datastore init failed:', runner.getCombinedOutput(initResult));
      }
    });

    // ===========================================================================
    // Individual Function Syntax Tests
    // ===========================================================================

    test('repository new should not have shell syntax errors', async () => {
      const result = await runner.repositoryNew(
        TEST_REPOSITORY_NAME,
        '1G',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository list should not have shell syntax errors', async () => {
      const result = await runner.repositoryList(DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository info should not have shell syntax errors', async () => {
      const result = await runner.repositoryInfo(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository status should not have shell syntax errors', async () => {
      const result = await runner.repositoryStatus(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Note: repository_create leaves repo mounted, so unmount first before testing mount
    test('repository unmount should not have shell syntax errors', async () => {
      const result = await runner.repositoryUnmount(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository mount should not have shell syntax errors', async () => {
      const result = await runner.repositoryMount(
        TEST_REPOSITORY_NAME,
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository validate should not have shell syntax errors', async () => {
      const result = await runner.repositoryValidate(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Note: resize/expand require unmounted repo - unmount first
    test('repository resize should not have shell syntax errors', async () => {
      await runner.repositoryUnmount(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
      const result = await runner.repositoryResize(
        TEST_REPOSITORY_NAME,
        '2G',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Note: expand (grow) requires mounted repo - mount first after resize
    test('repository grow should not have shell syntax errors', async () => {
      await runner.repositoryMount(TEST_REPOSITORY_NAME, TEST_PASSWORD, DEFAULT_DATASTORE_PATH);
      const result = await runner.repositoryGrow(
        TEST_REPOSITORY_NAME,
        '3G',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository rm should not have shell syntax errors', async () => {
      await runner.repositoryUnmount(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
      const result = await runner.repositoryRm(TEST_REPOSITORY_NAME, DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Repository with Password Tests
 *
 * Tests repository operations with encryption password.
 */
test.describe
  .serial('Repository with Password @bridge', () => {
    let runner: RenetFunctionsTestRunner;

    test.beforeAll(async () => {
      runner = RenetFunctionsTestRunner.forWorker();
      await runner.resetWorkerState();

      // Initialize datastore (LEVEL 2 prerequisite)
      await runner.datastoreInitPool('10G', DEFAULT_DATASTORE_PATH, true);
    });

    test('repository new with password should not have syntax errors', async () => {
      const result = await runner.repositoryNew(
        ENCRYPTED_REPO,
        '1G',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Note: repository_create leaves repo mounted, unmount first
    test('repository unmount with password should work', async () => {
      const result = await runner.repositoryUnmount(ENCRYPTED_REPO, DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository mount with password should not have syntax errors', async () => {
      const result = await runner.repositoryMount(
        ENCRYPTED_REPO,
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository with special characters in password should handle correctly', async () => {
      // encrypted-repo (still mounted from the previous test) auto-detects the SAME default network id that special-repo below is about to create on. Its state mirror keeps claiming that id for as long as its repository image exists (netid_guard.go), regardless of mount state, so special-repo's create was refused with "network ID ... already in use (holder: repo, encrypted-repo)" until this unmount+rm freed it first.
      await runner.repositoryUnmount(ENCRYPTED_REPO, DEFAULT_DATASTORE_PATH);
      await runner.repositoryRm(ENCRYPTED_REPO, DEFAULT_DATASTORE_PATH);

      // Test with special characters that might need escaping
      const result = await runner.repositoryNew(
        SPECIAL_REPO,
        '1G',
        'p@$$w0rd!#$%',
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test.afterAll(async () => {
      await runner.repositoryUnmount(SPECIAL_REPO, DEFAULT_DATASTORE_PATH).catch(() => undefined);
      await runner.repositoryRm(SPECIAL_REPO, DEFAULT_DATASTORE_PATH).catch(() => undefined);
    });
  });

/**
 * Repository Size Operations Tests
 *
 * Tests repository size management functions.
 */
test.describe
  .serial('Repository Size Operations @bridge', () => {
    let runner: RenetFunctionsTestRunner;

    test.beforeAll(async () => {
      runner = RenetFunctionsTestRunner.forWorker();
      await runner.resetWorkerState();

      // Initialize datastore (LEVEL 2 prerequisite)
      await runner.datastoreInitPool('10G', DEFAULT_DATASTORE_PATH, true);
    });

    test('repository new with various sizes should work', async () => {
      // Create a smaller repo for subsequent resize tests
      const result = await runner.repositoryNew(
        SIZE_TEST_REPO,
        '500M',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository unmount before resize', async () => {
      const result = await runner.repositoryUnmount(SIZE_TEST_REPO, DEFAULT_DATASTORE_PATH);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('repository resize to larger size should work', async () => {
      const result = await runner.repositoryResize(
        SIZE_TEST_REPO,
        '1G',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Note: expand (grow) requires mounted repo - mount first after resize
    test('repository grow should work', async () => {
      await runner.repositoryMount(SIZE_TEST_REPO, TEST_PASSWORD, DEFAULT_DATASTORE_PATH);
      const result = await runner.repositoryGrow(
        SIZE_TEST_REPO,
        '2G',
        TEST_PASSWORD,
        DEFAULT_DATASTORE_PATH
      );
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Repository Full Lifecycle Test
 *
 * Tests the complete repository lifecycle in strict order.
 * This validates the correct command sequence.
 */
test.describe
  .serial('Repository Full Lifecycle @bridge @lifecycle', () => {
    let runner: RenetFunctionsTestRunner;
    const repositoryName = e2eRepoGuid();
    const datastorePath = DEFAULT_DATASTORE_PATH;

    test.beforeAll(async () => {
      runner = RenetFunctionsTestRunner.forWorker();
      await runner.resetWorkerState();

      // Initialize datastore (LEVEL 2 prerequisite)
      await runner.datastoreInitPool('10G', datastorePath, true);
    });

    test('1. new: create repository', async () => {
      const result = await runner.repositoryNew(repositoryName, '1G', TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('2. list: verify repository exists', async () => {
      const result = await runner.repositoryList(datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('3. info: get repository details', async () => {
      const result = await runner.repositoryInfo(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    // Note: repository_create leaves repo mounted, unmount first to test mount
    test('4a. unmount: unmount for mount test', async () => {
      const result = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('4b. mount: mount repository', async () => {
      const result = await runner.repositoryMount(repositoryName, TEST_PASSWORD, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('5. status: check mounted repository status', async () => {
      const result = await runner.repositoryStatus(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('6. validate: validate mounted repository', async () => {
      const result = await runner.repositoryValidate(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('7a. unmount: unmount before resize', async () => {
      const result = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('7b. resize: resize repository', async () => {
      const result = await runner.repositoryResize(
        repositoryName,
        '2G',
        TEST_PASSWORD,
        datastorePath
      );
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('8. unmount: unmount repository', async () => {
      const result = await runner.repositoryUnmount(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });

    test('9. rm: delete repository', async () => {
      const result = await runner.repositoryRm(repositoryName, datastorePath);
      expect(runner.isSuccess(result)).toBe(true);
    });
  });

/**
 * Repository Error Handling Tests
 *
 * Tests error handling for invalid operations.
 */
test.describe('Repository Error Handling @bridge', () => {
  let runner: RenetFunctionsTestRunner;

  test.beforeAll(async () => {
    runner = RenetFunctionsTestRunner.forWorker();
    await runner.resetWorkerState();

    // Initialize datastore (LEVEL 2 prerequisite)
    await runner.datastoreInitPool('10G', DEFAULT_DATASTORE_PATH, true);
  });

  test('operations on nonexistent repository should handle gracefully', async () => {
    const nonexistent = 'nonexistent-repo-xyz';

    // These should fail but NOT have shell syntax errors
    const infoResult = await runner.repositoryInfo(nonexistent, DEFAULT_DATASTORE_PATH);
    expect(infoResult.stderr).not.toContain('syntax error');
    expect(infoResult.stderr).not.toContain('unexpected token');

    const mountResult = await runner.repositoryMount(
      nonexistent,
      TEST_PASSWORD,
      DEFAULT_DATASTORE_PATH
    );
    expect(mountResult.stderr).not.toContain('syntax error');
    expect(mountResult.stderr).not.toContain('unexpected token');
  });

  test('repository with invalid name should handle gracefully', async () => {
    // Names with spaces may be rejected, but should not cause syntax errors
    const result = await runner.repositoryNew(
      'invalid name',
      '1G',
      TEST_PASSWORD,
      DEFAULT_DATASTORE_PATH
    );
    expect(result.stderr).not.toContain('syntax error');
    expect(result.stderr).not.toContain('unexpected token');
  });

  test('repository with invalid size should handle gracefully', async () => {
    // Invalid size should be rejected, but should not cause syntax errors
    const result = await runner.repositoryNew(
      INVALID_SIZE_REPO,
      'invalid',
      TEST_PASSWORD,
      DEFAULT_DATASTORE_PATH
    );
    expect(result.stderr).not.toContain('syntax error');
    expect(result.stderr).not.toContain('unexpected token');
  });
});

/**
 * Repository Size Policy + Trim + Maintain Timer (renet#76)
 *
 * B4 of the CI-strengthening wave: repository_policy_set / repository_policy_get
 * and repository_trim ship but were never e2e-tested (they sit on the coverage
 * gate's legacy allowlist). datastore_status rounds out the storage-health
 * surface. A per-network daemon is started so the storage-maintain timer
 * self-installs (it arms from the daemon's StartForeground, not plain machine
 * setup — see private/renet CLAUDE.md "Autostart & auto-recovery").
 */
const DOCKER_PRUNE_CLASSES = ['A', 'B', 'C', 'D', 'G', 'E', 'F1', 'F2', 'L', 'Q'] as const;

interface DockerPruneRecord {
  network_id: number;
  mode: string;
  classes: Record<string, unknown>;
  errors: string[] | null;
  refused?: string;
}

/**
 * Pull the docker-prune record out of a run's output. `functions once` may
 * re-emit the verb's stdout inside msg="[verb] {\"...\"}", so each line is tried
 * bare and then unescaped. Raw stdout and stderr are used: the record has capitals.
 */
function tryParseRecord(candidate: string): DockerPruneRecord | undefined {
  try {
    const parsed = JSON.parse(candidate) as DockerPruneRecord | null;
    return parsed?.classes ? parsed : undefined;
  } catch {
    return undefined;
  }
}

function parseDockerPruneRecord(stdout: string, stderr: string): DockerPruneRecord {
  for (const line of `${stdout}\n${stderr}`.split('\n')) {
    const body = line.slice(line.indexOf('{'), line.lastIndexOf('}') + 1);
    const found =
      tryParseRecord(body) ?? tryParseRecord(body.replace(/\\"/g, '"').replace(/\\\\/g, '\\'));
    if (found) return found;
  }
  throw new Error(`no docker-prune record in output:\n${stdout}\n${stderr}`);
}

test.describe
  .serial('Repository size policy, trim, and maintain timer @bridge @lifecycle', () => {
    let runner: RenetFunctionsTestRunner;
    const repositoryName = e2eRepoGuid();
    const datastorePath = DEFAULT_DATASTORE_PATH;

    test.beforeAll(async () => {
      runner = RenetFunctionsTestRunner.forWorker();
      await runner.resetWorkerState();
      await runner.datastoreInitPool('10G', datastorePath, true);
      // A mounted repo gives trim something to report; a started per-network
      // daemon is what self-installs the storage-maintain timer.
      const created = await runner.repositoryNew(
        repositoryName,
        '1G',
        TEST_PASSWORD,
        datastorePath
      );
      expect(runner.isSuccess(created)).toBe(true);
      await runner.daemonSetup(DEFAULT_NETWORK_ID);
    });

    test.afterAll(async () => {
      await runner.repositoryUnmount(repositoryName, datastorePath).catch(() => undefined);
      await runner.repositoryRm(repositoryName, datastorePath).catch(() => undefined);
    });

    test('1. policy set → get round-trips the machine-wide auto-trim policy', async () => {
      const set = await runner.repositoryPolicySet({
        autoTrim: true,
        trimInterval: '24',
        datastorePath,
      });
      expect(runner.isSuccess(set), `policy set: ${runner.getCombinedOutput(set)}`).toBe(true);
      // Round-trip, NOT a blind success: the interval we just set is read back.
      const get = await runner.repositoryPolicyGet({ datastorePath });
      expect(runner.isSuccess(get), `policy get: ${runner.getCombinedOutput(get)}`).toBe(true);
      const out = runner.getCombinedOutput(get);
      expect(out.toLowerCase()).toContain('trim');
      expect(out, 'policy get did not reflect the 24h interval just set').toContain('24');
    });

    test('2. trim --report-only returns a structured JSON reclaim report', async () => {
      const trim = await runner.repositoryTrim({ reportOnly: true, datastorePath });
      expect(runner.isSuccess(trim), `trim: ${runner.getCombinedOutput(trim)}`).toBe(true);
      // The command emits --output json; a real report has an object payload.
      expect(runner.getCombinedOutput(trim)).toContain('{');
    });

    test('3. datastore_status reports datastore health', async () => {
      const status = await runner.checkDatastore(datastorePath);
      expect(
        runner.isSuccess(status),
        `datastore_status: ${runner.getCombinedOutput(status)}`
      ).toBe(true);
    });

    test('4. the storage-maintain timer self-installed and is enabled after daemon start', async () => {
      // A conditional skip that can silently become permanent is the disease this wave targets, so this asserts (not skips): the timer must be armed.
      const enabled = await runner.executeViaBridge(
        'systemctl is-enabled rediacc-storage-maintain.timer 2>/dev/null || true'
      );
      expect(enabled.stdout.trim(), 'storage-maintain timer not enabled').toMatch(/enabled|static/);
    });

    test('5. docker-prune dry run returns a JSON record with every class key', async () => {
      const run = await runner.repositoryDockerPrune({ name: repositoryName, datastorePath });
      expect(runner.isSuccess(run), `docker-prune: ${runner.getCombinedOutput(run)}`).toBe(true);
      const record = parseDockerPruneRecord(run.stdout, run.stderr);
      expect(record.mode).toBe('dry-run');
      for (const key of DOCKER_PRUNE_CLASSES) {
        expect(Object.keys(record.classes), `class ${key} missing from the record`).toContain(key);
      }
    });

    test('6. docker-prune --apply online finishes with no errors', async () => {
      const run = await runner.repositoryDockerPrune({
        name: repositoryName,
        datastorePath,
        apply: true,
      });
      expect(runner.isSuccess(run), `docker-prune --apply: ${runner.getCombinedOutput(run)}`).toBe(
        true
      );
      const record = parseDockerPruneRecord(run.stdout, run.stderr);
      expect(record.mode).toBe('online');
      expect(record.refused ?? '').toBe('');
      expect(record.errors ?? []).toEqual([]);
    });

    test('7. docker-prune --apply --offline stops the daemon and brings it back', async () => {
      // The socket's change time (fractional seconds, so a restart inside the same second still reads newer) is when the daemon bound it. An offline window that stopped and restarted the daemon leaves a newer one, so an answering daemon alone (which a never-stopped daemon also gives) is not taken as the proof.
      // The repository's own daemon socket lives under its net-<id> directory (runtime-paths.ts), not at the runtime root.
      const socket = repoDockerSocketPath(DEFAULT_NETWORK_ID);
      const boundAt = async (): Promise<number> => {
        const res = await runner.executeViaBridge(`sudo stat -c %.9Z ${socket}`);
        expect(res.code, `stat ${socket}: ${res.stderr}`).toBe(0);
        return Number(res.stdout.trim());
      };
      const boundBefore = await boundAt();
      expect(boundBefore, 'the daemon socket has no change time').toBeGreaterThan(0);
      const run = await runner.repositoryDockerPrune({
        name: repositoryName,
        datastorePath,
        apply: true,
        offline: true,
      });
      expect(
        runner.isSuccess(run),
        `docker-prune --apply --offline: ${runner.getCombinedOutput(run)}`
      ).toBe(true);
      const record = parseDockerPruneRecord(run.stdout, run.stderr);
      expect(record.mode).toBe('offline');
      expect(record.errors ?? []).toEqual([]);
      // The daemon must answer again on the repository's own socket.
      const info = await runner.executeViaBridge(
        `sudo docker -H ${repoDockerHost(record.network_id)} info --format '{{.ServerVersion}}'`
      );
      expect(info.code, `docker info after offline prune: ${info.stderr}`).toBe(0);
      expect(record.network_id, 'the prune ran against another daemon than the one measured').toBe(
        Number(DEFAULT_NETWORK_ID)
      );
      expect(
        await boundAt(),
        'the daemon socket was not re-bound, so the offline window never restarted the daemon'
      ).toBeGreaterThan(boundBefore);
    });
  });

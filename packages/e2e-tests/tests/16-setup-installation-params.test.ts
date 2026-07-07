import { expect, test } from '@playwright/test';
import { DEFAULT_DATASTORE_PATH, DEFAULT_UID } from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Setup Command Installation Parameters Tests
 *
 * Tests the 5 new installation parameters added to the setup command:
 * - from (installation source)
 * - docker_source
 * - install_amd_driver
 * - install_nvidia_driver
 * - install_criu
 *
 * These tests verify the vault parameter fixes are working end-to-end.
 */
test.describe('Setup Installation Parameters @bridge @setup', () => {
  let runner: BridgeTestRunner;

  // eslint-disable-next-line @typescript-eslint/require-await
  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test('setup with default installation params should succeed', async () => {
    const result = await runner.setupWithOptions({
      datastorePath: DEFAULT_DATASTORE_PATH,
      uid: DEFAULT_UID,
    });
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('setup with from=apt-repo should pass parameter to CLI', async () => {
    const result = await runner.setupWithOptions({
      datastorePath: DEFAULT_DATASTORE_PATH,
      uid: DEFAULT_UID,
      from: 'apt-repo',
    });
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('setup with docker_source=docker-repo should succeed', async () => {
    const result = await runner.setupWithOptions({
      datastorePath: DEFAULT_DATASTORE_PATH,
      uid: DEFAULT_UID,
      dockerSource: 'docker-repo',
    });
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('setup with GPU driver options should succeed', async () => {
    const result = await runner.setupWithOptions({
      datastorePath: DEFAULT_DATASTORE_PATH,
      uid: DEFAULT_UID,
      installAmdDriver: 'auto',
      installNvidiaDriver: 'auto',
    });
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('setup with install_criu=auto should succeed', async () => {
    const result = await runner.setupWithOptions({
      datastorePath: DEFAULT_DATASTORE_PATH,
      uid: DEFAULT_UID,
      installCriu: 'auto',
    });
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('setup with all installation params should succeed', async () => {
    const result = await runner.setupWithOptions({
      datastorePath: DEFAULT_DATASTORE_PATH,
      uid: DEFAULT_UID,
      from: 'apt-repo',
      dockerSource: 'docker-repo',
      installAmdDriver: 'auto',
      installNvidiaDriver: 'auto',
      installCriu: 'auto',
    });
    expect(runner.isSuccess(result)).toBe(true);
  });
});

/**
 * Setup Installation Parameters - Edge Cases
 */
test.describe('Setup Installation Parameters Edge Cases @bridge @setup', () => {
  let runner: BridgeTestRunner;

  // eslint-disable-next-line @typescript-eslint/require-await
  test.beforeAll(async () => {
    runner = BridgeTestRunner.forWorker();
  });

  test('setup with manual docker_source should succeed', async () => {
    const result = await runner.setupWithOptions({
      datastorePath: DEFAULT_DATASTORE_PATH,
      uid: DEFAULT_UID,
      dockerSource: 'manual',
    });
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('setup with install_criu=manual should succeed', async () => {
    const result = await runner.setupWithOptions({
      datastorePath: DEFAULT_DATASTORE_PATH,
      uid: DEFAULT_UID,
      installCriu: 'manual',
    });
    expect(runner.isSuccess(result)).toBe(true);
  });

  test('setup with GPU drivers disabled should succeed', async () => {
    const result = await runner.setupWithOptions({
      datastorePath: DEFAULT_DATASTORE_PATH,
      uid: DEFAULT_UID,
      installAmdDriver: 'false',
      installNvidiaDriver: 'false',
    });
    expect(runner.isSuccess(result)).toBe(true);
  });
});

import { randomBytes } from 'node:crypto';
import { expect, test } from '@playwright/test';
import { DEFAULT_DATASTORE_PATH, DEFAULT_NETWORK_ID, DEFAULT_WORKER_2_IP } from '../src/constants';
import { assertLandlockSelected } from '../src/utils/landlock';
import { e2eRepoGuid } from '../src/utils/licence';
import { peerKnownHostsArg } from '../src/utils/renet-functions/peerKnownHosts';
import { RenetFunctionsTestRunner } from '../src/utils/renet-functions/RenetFunctionsTestRunner';

/**
 * The push bandwidth cap on a real transfer (PLAN-jobs-backup-real-machine-tests E4). renet's unit tests pin the argv (`rsync --bwlimit`); only a timed push shows the cap holds on the wire. 64 MiB of incompressible data at 2 MB/s needs about 33 s, so a push under 25 s means the cap was dropped. The unlimited push of the same image is the control: without it a slow fleet would pass the test on its own speed.
 */
test.describe
  .serial('Push bandwidth cap on a real transfer @bridge @storage @landlock', () => {
    test.setTimeout(900_000);
    const FILL_MIB = 64;
    const CAP_FLOOR_S = 25;
    const guid = e2eRepoGuid();
    const password = randomBytes(16).toString('hex');
    let runner: RenetFunctionsTestRunner;
    let controlSeconds = 0;

    // A distinct destination per push keeps the second push a full transfer, never an incremental one.
    const cappedDest = e2eRepoGuid();

    const timedPush = async (
      extra: string,
      dest = guid
    ): Promise<{ seconds: number; code: number; out: string }> => {
      const pin = await peerKnownHostsArg(
        (command, timeout) => runner.executeViaBridge(command, timeout),
        'dest-known-hosts',
        DEFAULT_WORKER_2_IP
      );
      const started = Date.now();
      const result = await runner.executeViaBridge(
        `sudo renet backup push --name "${guid}" --datastore "${DEFAULT_DATASTORE_PATH}"` +
          ` --target machine --dest-host "${DEFAULT_WORKER_2_IP}" --dest-path "${DEFAULT_DATASTORE_PATH}"` +
          ` --dest "${dest}" --force${pin}${extra}`,
        600_000
      );
      return {
        seconds: (Date.now() - started) / 1000,
        code: result.code,
        out: runner.getCombinedOutput(result).slice(-800),
      };
    };

    test.beforeAll(async () => {
      runner = RenetFunctionsTestRunner.forWorker();
      await assertLandlockSelected(runner);
      await runner.ensureDatastoreReady(DEFAULT_DATASTORE_PATH);
      const created = await runner.repositoryNew(guid, '256M', password, DEFAULT_DATASTORE_PATH);
      expect(
        created.code,
        `repository_create: ${runner.getCombinedOutput(created).slice(-600)}`
      ).toBe(0);
      const mounted = await runner.repositoryMount(guid, password, DEFAULT_DATASTORE_PATH);
      expect(
        mounted.code,
        `repository_mount: ${runner.getCombinedOutput(mounted).slice(-600)}`
      ).toBe(0);
      const fill = await runner.executeViaBridge(
        `sudo dd if=/dev/urandom of="${DEFAULT_DATASTORE_PATH}/mounts/${guid}/fill.bin" bs=1M count=${FILL_MIB} conv=fsync status=none`
      );
      expect(fill.code, `fill: ${runner.getCombinedOutput(fill)}`).toBe(0);
      const unmounted = await runner.repositoryUnmount(
        guid,
        DEFAULT_DATASTORE_PATH,
        DEFAULT_NETWORK_ID
      );
      expect(
        unmounted.code,
        `repository_unmount: ${runner.getCombinedOutput(unmounted).slice(-600)}`
      ).toBe(0);
    });

    test.afterAll(async () => {
      await runner.repositoryRm(guid, DEFAULT_DATASTORE_PATH).catch(() => undefined);
      await RenetFunctionsTestRunner.forWorker(2)
        .repositoryRm(guid, DEFAULT_DATASTORE_PATH)
        .catch(() => undefined);
      await RenetFunctionsTestRunner.forWorker(2)
        .repositoryRm(cappedDest, DEFAULT_DATASTORE_PATH)
        .catch(() => undefined);
    });

    test('control: the unlimited push finishes, and is timed', async () => {
      const r = await timedPush('');
      expect(r.code, `unlimited push: ${r.out}`).toBe(0);
      controlSeconds = r.seconds;
    });

    test('--bwlimit 2M stretches the same push to at least 25 s, and past the control', async () => {
      const r = await timedPush(' --bwlimit 2M', cappedDest);
      expect(r.code, `capped push: ${r.out}`).toBe(0);
      expect(r.seconds, `capped push took ${r.seconds}s`).toBeGreaterThanOrEqual(CAP_FLOOR_S);
      expect(r.seconds, `capped ${r.seconds}s vs control ${controlSeconds}s`).toBeGreaterThan(
        controlSeconds
      );
    });
  });

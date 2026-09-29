import * as fs from 'node:fs';
import * as path from 'node:path';
import { FullConfig } from '@playwright/test';
import {
  CEPH_HEALTH_RETRY_MS,
  CEPH_HEALTH_TIMEOUT_MS,
  DEFAULT_DATASTORE_PATH,
  RENET_SETUP_TIMEOUT_MS,
} from '../constants';
import { getOpsManager } from '../utils/bridge/OpsManager';
import { InfrastructureManager } from '../utils/infrastructure/InfrastructureManager';

/**
 * One named unit of global setup that may run beside others.
 */
export interface SetupStep {
  name: string;
  run: () => Promise<void>;
}

/**
 * Run independent setup steps at once, and fail naming EVERY step that failed.
 * Promise.allSettled rather than Promise.all: Promise.all rejects on the first failure while the other steps keep running unobserved, so a second failure does not reach the log and the teardown can start under a step still in flight.
 * Each failure is prefixed with its step's name, and the first one is kept as the thrown error's cause.
 */
export async function runSetupStepsConcurrently(steps: readonly SetupStep[]): Promise<void> {
  const results = await Promise.allSettled(steps.map((step) => step.run()));
  const failures: { name: string; reason: unknown }[] = [];
  results.forEach((result, index) => {
    if (result.status === 'rejected') {
      failures.push({ name: steps[index].name, reason: result.reason });
    }
  });
  if (failures.length === 0) {
    return;
  }
  const lines = failures.map(({ name, reason }) => {
    const message = reason instanceof Error ? reason.message : String(reason);
    return `[${name}] ${message}`;
  });
  throw new Error(
    `${failures.length} of ${steps.length} concurrent setup step(s) failed:\n${lines.join('\n')}`,
    { cause: failures[0].reason }
  );
}

/**
 * renet's pin file: host-version is the Ceph release every host must run (PLAN-renet-ceph-gpu-non-apt.md 2a).
 */
export const CEPH_IMAGE_PIN_PATH = path.resolve(
  __dirname,
  '..',
  '..',
  '..',
  '..',
  'private',
  'renet',
  '.ceph-image-pin'
);

/**
 * The `host-version=` value of a .ceph-image-pin text; throws when the line is absent.
 */
export function readCephHostVersion(pinText: string): string {
  const line = pinText.split('\n').find((l) => l.trim().startsWith('host-version='));
  const value = line?.trim().slice('host-version='.length).trim() ?? '';
  if (!value) {
    throw new Error('no host-version line in the Ceph image pin file');
  }
  return value;
}

/**
 * The release a `ceph --version` line reports ("ceph version 19.2.3 (sha) squid (stable)"), or '' when unparseable.
 */
export function parseCephVersion(stdout: string): string {
  return /ceph version (\S+)/.exec(stdout)?.[1] ?? '';
}

interface CephVersionProbe {
  executeOnVM: (
    ip: string,
    command: string
  ) => Promise<{ stdout: string; stderr: string; code: number }>;
}

/**
 * Fail unless `ceph --version` on every given VM reports `expected`, naming each VM and what it found.
 * A client of another patch level than the cluster image can reject the admin key it mints (.ceph-image-pin), and on a dnf or zypper host the version comes from a per-distro pin renet installs, so this is where a drifted pin shows as a named failure.
 * `matches` is the comparison, injectable only so the tests can prove the rejection depends on it.
 */
export async function assertCephHostVersion(
  probe: CephVersionProbe,
  ips: readonly string[],
  expected: string,
  matches: (found: string, want: string) => boolean = (found, want) => found === want
): Promise<void> {
  const problems = await Promise.all(
    ips.map(async (ip) => {
      const result = await probe.executeOnVM(ip, 'ceph --version');
      const found = parseCephVersion(result.stdout);
      if (result.code !== 0 || !found) {
        const detail = result.stderr.trim() || result.stdout.trim() || `exit code ${result.code}`;
        return `${ip}: ceph --version gave no version (${detail})`;
      }
      return matches(found, expected) ? null : `${ip}: ceph ${found}, expected ${expected}`;
    })
  );
  const failures = problems.filter((problem): problem is string => problem !== null);
  if (failures.length > 0) {
    throw new Error(
      `Ceph host version check failed on ${failures.length} of ${ips.length} VM(s), host-version=${expected} (${CEPH_IMAGE_PIN_PATH}):\n${failures.join('\n')}`
    );
  }
  console.warn(`  ✓ ceph ${expected} on all ${ips.length} Ceph node(s) and worker(s)`);
}

/**
 * Run one setup step and print its wall time, so a CI log shows where global setup spends its budget.
 */
async function timed<T>(label: string, run: () => Promise<T>): Promise<T> {
  const startedAt = Date.now();
  try {
    return await run();
  } finally {
    console.warn(`  [timing] ${label}: ${((Date.now() - startedAt) / 1000).toFixed(1)}s`);
  }
}

/**
 * Wait for Ceph cluster health check
 */
async function waitForCephHealth(opsManager: ReturnType<typeof getOpsManager>) {
  // eslint-disable-next-line no-console
  console.log('');
  // eslint-disable-next-line no-console
  console.log('Step 1b: Waiting for Ceph cluster health...');
  const healthTimeoutMs = CEPH_HEALTH_TIMEOUT_MS;
  const retryIntervalMs = CEPH_HEALTH_RETRY_MS;
  const startedAt = Date.now();
  let attempt = 0;

  while (Date.now() - startedAt < healthTimeoutMs) {
    attempt += 1;

    // NEVER KILL RENET BEFORE OUR OWN DEADLINE. This call used to pass a hard 120000, while renet's internal wait is CephHealthTimeout, 600s by default (opsconfig/config.go:262, overridable via CEPH_HEALTH_TIMEOUT, which nothing in this repo sets). So every single invocation was SIGTERM'd at 120s, one fifth of the way through renet's own poll.
    //
    // OpsCommandRunner's timeout path returns `code: -1` and appends "Timeout exceeded" to whatever stderr had arrived so far (OpsCommandRunner.ts:59-62), and -1 is not 0, so the loop below read it as "not healthy yet" and retried. The 1200s budget was therefore spent on nine truncated attempts, and the error the nightly finally surfaced was our own timeout marker rather than
    // renet's diagnosis.
    //
    // Giving the call the whole remaining budget lets renet's wait run to its own conclusion and return the real reason. The outer loop stays as a thin retry for the case where budget remains after renet gives up.
    const remainingMs = healthTimeoutMs - (Date.now() - startedAt);
    const healthResult = await opsManager.runOpsCommand(['ceph', 'health'], [], remainingMs);
    if (healthResult.code === 0) {
      // eslint-disable-next-line no-console
      console.log(`  ✓ Ceph cluster is healthy (attempt ${attempt})`);
      return;
    }

    // Exit 11 means renet RECORDED a provisioning failure: the cluster was never built, so no amount of polling will make it healthy. Retrying to the full budget here is what turned a 3-second diagnosis into a 20-minute one, and it is why the nightly reported a generic "Ceph health check failed" instead of the real cause.
    //
    // renet's stderr on this path carries the ORIGINAL provisioning error, e.g. "failed to install prerequisites on node 22: ssh command failed: signal: killed" (an OOM kill during apt), so surface it verbatim.
    //
    // ProvisionUnavailableExitCode, private/renet/pkg/infra/ceph/provisionstate.go.
    // 10 is taken by LicenseRequiredExitCode; those are the only two.
    if (healthResult.code === 11) {
      throw new Error(
        `Ceph was never provisioned, so waiting cannot help. renet reported:\n${healthResult.stderr}`
      );
    }

    if (Date.now() - startedAt >= healthTimeoutMs) {
      throw new Error(`Ceph health check failed: ${healthResult.stderr}`);
    }

    // eslint-disable-next-line no-console
    console.log(
      `  ! Ceph not healthy yet (attempt ${attempt}). Retrying in ${Math.round(retryIntervalMs / 1000)}s...`
    );
    await new Promise((resolve) => {
      setTimeout(resolve, retryIntervalMs);
    });
  }
}

/**
 * Run renet setup on ALL VMs (bridge + workers)
 * This installs Docker and other dependencies on fresh base images.
 *
 * After a reset in this same process, a VM's setup is skipped when ops up already completed it with the local renet binary (InfrastructureManager.isSetupCompleteWithLocalRenet).
 * `renet ops up` runs `renet setup --skip-datastore` on the bridge (setupBridge in private/renet/cmd/renet/ops_up.go) and `sudo renet setup` on each worker in its cluster (worker.Service.Setup), and a second run only takes renet's already-completed path.
 */
async function setupAllVMs(
  opsManager: ReturnType<typeof getOpsManager>,
  infra: InfrastructureManager,
  freshReset: boolean
) {
  console.warn('');
  console.warn('Step 3: Running renet setup on ALL VMs (bridge + workers)...');

  // Get all VM IPs (bridge + workers)
  const bridgeIp = opsManager.getBridgeVMIp();
  const workerIps = opsManager.getWorkerVMIps();
  const allVmIps = [bridgeIp, ...workerIps];

  // Each VM's `renet setup` is an independent SSH round trip against its own machine, so run them concurrently rather than one at a time. Promise.all rejects with the first error; the message below already names the offending IP and VM type, so that identity survives whichever VM happens to finish (or fail) first.
  await Promise.all(
    allVmIps.map(async (ip) => {
      const vmType = ip === bridgeIp ? 'bridge' : 'worker';
      if (freshReset && (await infra.isSetupCompleteWithLocalRenet(ip))) {
        console.warn(`  ✓ Setup already completed by ops up on ${ip} (${vmType}), skipped`);
        return;
      }
      console.warn(`  Setting up ${vmType} VM at ${ip}...`);
      const result = await opsManager.executeOnVM(ip, 'sudo renet setup', RENET_SETUP_TIMEOUT_MS);
      if (result.code === 0) {
        console.warn(`  ✓ Setup completed on ${ip} (${vmType})`);
      } else {
        // Fail fast - subsequent steps depend on setup being successful (Docker installed)
        throw new Error(
          `Setup failed on ${ip} (${vmType}): exit code ${result.code}\nstderr: ${result.stderr}\nstdout: ${result.stdout}`
        );
      }
    })
  );
}

/**
 * Verify all VMs with retry logic
 */
async function verifyVMsWithRetry(
  opsManager: ReturnType<typeof getOpsManager>,
  infra: InfrastructureManager
) {
  console.warn('');
  console.warn('Step 4: Verifying all VMs are ready...');
  // `renet setup` (Step 3) restarts each VM's sshd, and Step 3 now runs on every VM at once, so a VM can still be mid-restart here: opensuse failed "VMs not ready: 192.168.111.1 (SSH not ready)" on two attempts (CI for da85f78ea), where the old serial loop left the bridge time to come back.
  // Wait, bounded, for SSH on every VM before the one-shot verification.
  await Promise.all(opsManager.getAllVMIps().map((ip) => opsManager.waitForVM(ip, 120000)));
  try {
    await opsManager.verifyAllVMsReady();
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (message.includes('(renet not installed)')) {
      // eslint-disable-next-line no-console
      console.log(
        'Renet missing on one or more VMs; re-deploying renet and retrying verification...'
      );
      await infra.ensureRenetOnVMs();
      await opsManager.verifyAllVMsReady();
    } else {
      throw err;
    }
  }
}

/**
 * Step 5: start RustFS S3 storage on the bridge VM.
 * The live RustFS consumers, suites 15 and 19, drive it from worker VMs through the rclone config Step 6 writes.
 */
async function startRustFSStorage(opsManager: ReturnType<typeof getOpsManager>) {
  const rustfsResult = await opsManager.startRustFS();
  if (!rustfsResult.success) {
    throw new Error(`RustFS failed to start: ${rustfsResult.message}`);
  }
  console.warn(`  ✓ Step 5: ${rustfsResult.message}`);
}

/**
 * Step 6: configure rclone on every worker for RustFS access, one `renet ops rustfs configure-worker` per worker, concurrently.
 * `renet ops rustfs configure-workers` is not used: it loops the workers one at a time and exits 0 even when a worker fails (docker.Service.ConfigureWorkers only logs the error), so the harness saw no failure at all.
 * A failure stays non-fatal, as it always was, because suite 19 configures its worker itself; it is printed with the worker's ID and renet's stderr.
 */
async function configureRustFSWorkers(opsManager: ReturnType<typeof getOpsManager>) {
  const workerIds = opsManager.getVMIds().workers;
  const results = await Promise.all(
    workerIds.map(async (vmId) => ({ vmId, ...(await opsManager.configureRustFSWorker(vmId)) }))
  );
  for (const result of results) {
    if (result.success) {
      console.warn(`  ✓ Step 6: ${result.message}`);
    } else {
      console.warn(
        `  ! Step 6: worker ${result.vmId}: ${result.message} (non-fatal, tests may configure individually)`
      );
    }
  }
}

/**
 * Steps 5-8, the worker topology's services, run as three concurrent branches once Step 4 has verified every VM.
 *
 * Data dependencies, measured from the code:
 * - Step 5 (RustFS on the bridge) needs only the bridge's Docker from Step 3. Nothing on a worker reads RustFS during setup: Step 6 writes an rclone config naming the bridge's IP and port and never connects.
 * - Step 6 (rclone) and Step 8 (CRIU) stay ordered, rclone first. Both can reach the worker's package manager (renet's ensureRclone installs rclone with apt, dnf or zypper; the CRIU fallback, `renet ops worker install-criu`, installs CRIU's libraries), and two package managers on one VM contend for its lock.
 * - Step 7 (datastores) runs `renet datastore init`, which touches no package manager and nothing Steps 6 or 8 write, so it runs beside them.
 * Every worker is its own SSH target, so each step also runs its workers concurrently.
 */
async function prepareWorkerServices(
  opsManager: ReturnType<typeof getOpsManager>,
  infra: InfrastructureManager
) {
  console.warn('');
  console.warn('Steps 5-8: RustFS (bridge), rclone then CRIU (workers), datastores (workers)...');
  await runSetupStepsConcurrently([
    {
      name: 'Step 5: RustFS on the bridge',
      run: () => timed('Step 5 RustFS', () => startRustFSStorage(opsManager)),
    },
    {
      name: 'Steps 6+8: rclone then CRIU on the workers',
      run: async () => {
        await timed('Step 6 rclone', () => configureRustFSWorkers(opsManager));
        await timed('Step 8 CRIU', () => infra.deployCRIUToAllVMs());
      },
    },
    {
      name: 'Step 7: datastores on the workers',
      run: () =>
        timed('Step 7 datastores', () =>
          opsManager.initializeAllDatastores('10G', DEFAULT_DATASTORE_PATH)
        ),
    },
  ]);
  console.warn('  ✓ RustFS, rclone, datastores and CRIU ready');
}

/**
 * Write setup error to log file
 */
function writeSetupErrorLog(error: unknown) {
  try {
    const e2eDir = path.resolve(__dirname, '..', '..');
    const errorLogDir = path.join(e2eDir, 'reports', 'bridge-logs');
    const errorLogPath = path.join(errorLogDir, 'setup-error.txt');

    fs.mkdirSync(errorLogDir, { recursive: true });

    const errorMessage = error instanceof Error ? error.message : String(error);
    const errorStack = error instanceof Error ? error.stack : 'No stack trace';
    const timestamp = new Date().toISOString();

    const errorContent = [
      '================================================================================',
      'GLOBAL SETUP FAILED',
      '================================================================================',
      '',
      `Timestamp: ${timestamp}`,
      '',
      '----------------------------------------',
      'ERROR MESSAGE:',
      '----------------------------------------',
      errorMessage,
      '',
      '----------------------------------------',
      'STACK TRACE:',
      '----------------------------------------',
      errorStack,
      '',
      '================================================================================',
      'Tests did not run because setup failed.',
      'Fix the setup issue and run tests again.',
      '================================================================================',
    ].join('\n');

    fs.writeFileSync(errorLogPath, errorContent);
    console.error(`\nSetup error logged to: ${errorLogPath}`);
  } catch (writeError) {
    console.error(`\nFailed to write setup error log: ${writeError}`);
  }
}

/**
 * Global setup for bridge tests.
 *
 * EXECUTION MODEL: All tests run on VMs via SSH
 * Host → Bridge VM → SSH → Worker/Ceph VM → renet command
 *
 * Setup sequence:
 * 1. Soft reset VMs (ops up --force --parallel) - includes Ceph provisioning if enabled
 * 2. Deploy renet binary to all VMs
 * 3. Run renet setup on ALL VMs (bridge + workers) to install Docker and dependencies
 * 4. Verify all VMs are ready (bridge + workers + ceph)
 * 5-8. With workers only, concurrently (prepareWorkerServices names the ordering kept): RustFS on the bridge; rclone then CRIU on the workers; datastores on the workers
 *
 * RENET BINARY:
 * The renet binary must be available before running tests. In CI, it's pre-extracted
 * from the Docker image. Locally, build with: cd renet && ./go dev
 *
 * NOTE: Ceph provisioning is automatically handled by `ops up` when VM_CEPH_NODES is configured.
 * Do NOT call provisionCeph() separately as this causes duplicate provisioning conflicts.
 */
async function bridgeGlobalSetup(_config: FullConfig) {
  // KEEP_CLUSTER implies skip-reset: iteration mode exists to reuse a standing cluster, and a VM reboot both costs minutes per invocation and races the suite against boot recovery (observed live: a scoped re-run red on half-regenerated containerd config). CI sets neither flag.
  const skipReset = process.env.BRIDGE_TEST_SKIP_RESET === '1' || process.env.KEEP_CLUSTER === '1';
  // A reset that returns at all succeeded (a failed one throws below), so every VM was just recreated and provisioned by ops up in this process.
  const freshReset = !skipReset;

  /* eslint-disable no-console */
  console.log('');
  console.log('='.repeat(60));
  console.log('Bridge Test Setup (SSH Mode)');
  console.log('='.repeat(60));
  /* eslint-enable no-console */

  const opsManager = getOpsManager();
  const infra = new InfrastructureManager();

  try {
    // Step 1: Soft reset VMs (mandatory - no skip option)
    // eslint-disable-next-line no-console
    console.log('');
    if (skipReset) {
      // eslint-disable-next-line no-console
      console.log('Step 1: Skipping VM soft reset (BRIDGE_TEST_SKIP_RESET=1)');
    } else {
      // eslint-disable-next-line no-console
      console.log('Step 1: Performing VM soft reset...');
      const resetResult = await opsManager.resetVMs();

      if (!resetResult.success) {
        throw new Error('VM reset failed - cannot proceed with tests');
      }
      // eslint-disable-next-line no-console
      console.log(`  ✓ VM reset completed in ${(resetResult.duration / 1000).toFixed(1)}s`);
    }

    // Note: Ceph provisioning is automatically handled by ops up when VM_CEPH_NODES is configured
    const cephNodes = opsManager.getCephVMIps();
    if (cephNodes.length > 0) {
      await waitForCephHealth(opsManager);
      // Cluster health is NOT the whole precondition. HEALTH_OK is silent about whether the workers were configured as clients, and on 2026-08-16 a SIGKILLed ceph-common install left worker 12 without /etc/ceph while the cluster reported HEALTH_OK and the recorded failure was erased. The suite ran anyway and failed 6 minutes later with "can't open ceph.conf". Asking the workers
      // directly turns that into a named failure here.
      await opsManager.verifyCephClientsReady();
      await assertCephHostVersion(
        opsManager,
        [...cephNodes, ...opsManager.getWorkerVMIps()],
        readCephHostVersion(fs.readFileSync(CEPH_IMAGE_PIN_PATH, 'utf8'))
      );
    }

    // A baked leg must run on the image its key names; Step 3's skip rule trusts the setup marker that image carries.
    await infra.assertBakedImageOnVMs();

    // Step 2: Build renet and deploy to all VMs
    // eslint-disable-next-line no-console
    console.log('');
    // eslint-disable-next-line no-console
    console.log('Step 2: Building and deploying renet...');
    await timed('Step 2 renet deploy', () => infra.ensureInfrastructure({ freshReset }));
    // eslint-disable-next-line no-console
    console.log('  ✓ Renet deployed to all VMs');

    // Step 3 needs Step 2: it runs the deployed renet, and its skip rule reads the ops-up md5 match Step 2 records.
    await timed('Step 3 renet setup', () => setupAllVMs(opsManager, infra, freshReset));

    // Step 4 needs Step 3: `renet setup` restarts sshd, so verification waits for SSH first.
    await timed('Step 4 verify', () => verifyVMsWithRetry(opsManager, infra));

    // Steps 5-8 need Step 4 and nothing from each other beyond what prepareWorkerServices orders. A run without workers is the Ceph-only topology, whose suites under tests/ceph never touch RustFS, datastores on workers or CRIU.
    if (opsManager.getWorkerVMIps().length > 0) {
      await timed('Steps 5-8 total', () => prepareWorkerServices(opsManager, infra));
    } else {
      console.warn('');
      console.warn('Steps 5-8: skipped (no workers in this topology)');
    }

    /* eslint-disable no-console */
    console.log('');
    console.log('='.repeat(60));
    console.log('All VMs ready for SSH-based test execution');
    console.log('='.repeat(60));
    console.log('');
    /* eslint-enable no-console */
  } catch (error) {
    console.error('');
    console.error('='.repeat(60));
    console.error('Setup failed:', error);
    console.error('='.repeat(60));

    writeSetupErrorLog(error);
    throw error;
  }
}

export default bridgeGlobalSetup;

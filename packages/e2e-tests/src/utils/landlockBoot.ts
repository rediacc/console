/**
 * Boot-time Landlock for the E2E VMs. Oracle Linux 10's UEK kernel builds Landlock in but leaves it out of the
 * default `lsm=` list ("landlock: Disabled but requested by user space"), and renet refuses Rediaccfile up()/down()
 * without it. Every VM is probed after `renet setup`; one whose active LSM list lacks `landlock` gets it appended
 * with grubby and one reboot, so every `@landlock` suite runs on every image. The probe, not the image name, decides:
 * an image that already boots with Landlock is left alone.
 */
import { LANDLOCK_INACTIVE_VM_IMAGES } from './landlockSelection';

export interface LandlockBootProbe {
  executeOnVM: (
    ip: string,
    command: string,
    timeoutMs?: number
  ) => Promise<{ stdout: string; stderr: string; code: number }>;
}

export interface LandlockBootOptions {
  /** The `VM_IMAGE` the leg runs; an image named in `LANDLOCK_INACTIVE_VM_IMAGES` is allowed to stay without Landlock. */
  vmImage?: string | undefined;
  /** Bounded wait for the VM to come back from the reboot. */
  rebootTimeoutMs?: number;
  /** Pause between boot-id polls. */
  pollMs?: number;
}

const LSM_PATH = '/sys/kernel/security/lsm';
const BOOT_ID_PATH = '/proc/sys/kernel/random/boot_id';
const DEFAULT_REBOOT_TIMEOUT_MS = 300_000;
const DEFAULT_POLL_MS = 5_000;

/** True when the comma-separated active LSM list names landlock. */
export function lsmHasLandlock(lsm: string): boolean {
  return lsm
    .trim()
    .split(',')
    .some((name) => name === 'landlock');
}

/** The `lsm=` value to boot with: the current active list with `landlock` appended. */
export function lsmWithLandlock(lsm: string): string {
  const names = lsm
    .trim()
    .split(',')
    .filter((name) => name !== '');
  return [...names.filter((name) => name !== 'landlock'), 'landlock'].join(',');
}

async function readLsm(probe: LandlockBootProbe, ip: string): Promise<string> {
  const result = await probe.executeOnVM(ip, `cat ${LSM_PATH}`, 30_000);
  if (result.code !== 0) {
    throw new Error(`${ip}: could not read ${LSM_PATH}: ${result.stderr.trim() || result.stdout}`);
  }
  return result.stdout.trim();
}

async function readBootId(probe: LandlockBootProbe, ip: string): Promise<string> {
  const result = await probe.executeOnVM(ip, `cat ${BOOT_ID_PATH}`, 15_000);
  return result.code === 0 ? result.stdout.trim() : '';
}

/** Poll until the VM reports a boot id other than `before`, or throw when the timeout passes. */
async function waitForNewBoot(
  probe: LandlockBootProbe,
  ip: string,
  before: string,
  options: LandlockBootOptions
): Promise<void> {
  const deadline = Date.now() + (options.rebootTimeoutMs ?? DEFAULT_REBOOT_TIMEOUT_MS);
  const pollMs = options.pollMs ?? DEFAULT_POLL_MS;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, pollMs));
    const bootId = await readBootId(probe, ip).catch(() => '');
    if (bootId !== '' && bootId !== before) {
      return;
    }
  }
  throw new Error(`${ip}: did not come back from the landlock reboot within the timeout`);
}

/** Append landlock to `lsm=` for every installed kernel; throw naming the VM when grubby refuses. */
async function addLandlockToBootArgs(
  probe: LandlockBootProbe,
  ip: string,
  lsm: string
): Promise<void> {
  const grubby = await probe.executeOnVM(
    ip,
    `sudo grubby --update-kernel=ALL --args=lsm=${lsmWithLandlock(lsm)}`,
    60_000
  );
  if (grubby.code !== 0) {
    throw new Error(
      `${ip}: lsm=${lsm} lacks landlock and grubby could not add it (exit ${grubby.code}): ${grubby.stderr.trim() || grubby.stdout.trim()}`
    );
  }
}

/** The outcome once the VM is back: active, declared unavailable, or a loud failure. */
function judgeAfterReboot(
  after: string,
  ip: string,
  options: LandlockBootOptions
): 'rebooted' | 'unavailable' {
  if (lsmHasLandlock(after)) {
    console.warn(`  ✓ ${ip}: landlock active after reboot (lsm=${after})`);
    return 'rebooted';
  }
  if (options.vmImage !== undefined && LANDLOCK_INACTIVE_VM_IMAGES.has(options.vmImage)) {
    console.warn(
      `  ${ip}: landlock still inactive after reboot (lsm=${after}); ${options.vmImage} is declared Landlock-inactive`
    );
    return 'unavailable';
  }
  throw new Error(
    `${ip}: landlock is still absent after adding it to lsm= and rebooting (lsm=${after}); the kernel may not include Landlock`
  );
}

/**
 * Make `landlock` active on one VM. Returns what was done: 'active' (already in the list), 'rebooted' (added and now active),
 * 'unavailable' (still absent after the reboot on an image `LANDLOCK_INACTIVE_VM_IMAGES` names). Any other outcome throws,
 * naming the VM and the list it found.
 */
export async function ensureLandlockActive(
  probe: LandlockBootProbe,
  ip: string,
  options: LandlockBootOptions = {}
): Promise<'active' | 'rebooted' | 'unavailable'> {
  const lsm = await readLsm(probe, ip);
  if (lsmHasLandlock(lsm)) {
    return 'active';
  }
  const bootIdBefore = await readBootId(probe, ip);
  if (bootIdBefore === '') {
    throw new Error(
      `${ip}: could not read ${BOOT_ID_PATH}, so a reboot could not be told from no reboot`
    );
  }
  console.warn(`  ${ip}: lsm=${lsm} lacks landlock; booting with lsm=${lsmWithLandlock(lsm)}`);
  await addLandlockToBootArgs(probe, ip, lsm);
  // The reboot drops the SSH session, so its exit code says nothing; the boot id changing is the proof.
  await probe.executeOnVM(ip, 'sudo systemctl reboot', 15_000);
  await waitForNewBoot(probe, ip, bootIdBefore, options);
  return judgeAfterReboot(await readLsm(probe, ip), ip, options);
}

/** `ensureLandlockActive` on every VM at once; a failure names its VM. */
export async function ensureLandlockActiveOnAll(
  probe: LandlockBootProbe,
  ips: readonly string[],
  options: LandlockBootOptions = {}
): Promise<void> {
  await Promise.all(ips.map((ip) => ensureLandlockActive(probe, ip, options)));
}

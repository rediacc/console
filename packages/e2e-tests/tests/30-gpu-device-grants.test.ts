import { expect, test } from '@playwright/test';
import { WK_INFRA_DOMAIN } from '@rediacc/shared/config/well-known.generated';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';

/**
 * Suite 30: the machine GPU inventory and the repository CDI device grant verbs
 * (PLAN-gpu-device-grants): machine_gpu_list, repository_gpu_grant and
 * repository_gpu_revoke, driven through `renet functions once` on a worker VM
 * that has no GPU.
 *
 * The device is a FAKE CDI device defined by a spec this suite writes under
 * /etc/cdi (kind rediacc.io/e2e), because a grant is refused unless a spec
 * defines the name. Nothing here opens the device node, so no real hardware is
 * needed; the vm:check step G1 proves the container-side effect of a grant.
 *
 * Each step asserts on the output of the verb itself: the grant must show the
 * device, the inventory must list it, and after the revoke the inventory must
 * not carry it. A refusal of an undefined device is the control that shows the
 * grant verb checks the spec rather than recording any name.
 *
 * Expected substrings are lowercase: `getCombinedOutput` lowercases
 * (`TestHelpers.ts`).
 */

const RUN_ID = Date.now();
const NETWORK_ID = 3000 + (RUN_ID % 500);
const KIND = `${WK_INFRA_DOMAIN}/e2e`;
const DEVICE = `${KIND}=one`;
const SPEC_PATH = `/etc/cdi/rediacc-e2e-${RUN_ID}.yaml`;
const SPEC = [
  'cdiVersion: "0.6.0"',
  `kind: ${KIND}`,
  'devices:',
  '  - name: one',
  '    containerEdits:',
  '      deviceNodes:',
  '        - path: /dev/rediacc-e2e-fake',
  '          type: c',
  '          major: 60',
  '          minor: 1',
  '',
].join('\n');

/** The grants-section line of this run's network (gpu.list.grant: `  network <id> (<mount>): <devices>`), or ''. */
function grantLine(output: string): string {
  return output.split('\n').find((l) => l.trim().startsWith(`network ${NETWORK_ID} `)) ?? '';
}

test.describe
  .serial('GPU device grants @bridge', () => {
    let runner: BridgeTestRunner;
    const once = (fn: string, extra = '') =>
      `sudo renet functions once --test-mode --function ${fn} --network-id ${NETWORK_ID}${extra}`;
    const listCmd = 'sudo renet functions once --test-mode --function machine_gpu_list';

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      const b64 = Buffer.from(SPEC).toString('base64');
      const written = await runner.executeOnWorker(
        `sudo mkdir -p /etc/cdi && echo ${b64} | base64 -d | sudo tee ${SPEC_PATH} >/dev/null`
      );
      expect(runner.isSuccess(written), runner.getCombinedOutput(written)).toBe(true);
    });

    test.afterAll(async () => {
      await runner.executeOnWorker(
        `sudo renet daemon grant --network-id ${NETWORK_ID} --clear; sudo rm -f ${SPEC_PATH}`
      );
    });

    test('machine_gpu_list answers with the inventory and the grants', async () => {
      const result = await runner.executeOnWorker(listCmd);
      expect(runner.isSuccess(result), runner.getCombinedOutput(result)).toBe(true);
      expect(runner.getCombinedOutput(result)).toContain('inventory');
    });

    test('repository_gpu_grant refuses a device no CDI spec defines', async () => {
      const result = await runner.executeOnWorker(
        once('repository_gpu_grant', ` --device ${KIND}=missing`)
      );
      expect(result.code, runner.getCombinedOutput(result)).not.toBe(0);
      // The refusal must be renet's own grant.device_not_defined, not an unknown flag or function.
      expect(runner.getCombinedOutput(result)).toContain('is not defined by any cdi spec');
    });

    test('repository_gpu_grant records the defined device', async () => {
      const result = await runner.executeOnWorker(
        once('repository_gpu_grant', ` --device ${DEVICE}`)
      );
      expect(runner.isSuccess(result), runner.getCombinedOutput(result)).toBe(true);
      // `--show` prints the network's grant after the change.
      expect(runner.getCombinedOutput(result)).toContain(DEVICE);

      // The inventory lists every CDI device, granted or not, so the grant is read from
      // the network's own line of the grants section.
      const listed = await runner.executeOnWorker(listCmd);
      expect(runner.isSuccess(listed), runner.getCombinedOutput(listed)).toBe(true);
      expect(grantLine(runner.getCombinedOutput(listed))).toContain(DEVICE);
    });

    test('repository_gpu_revoke removes the device from the grant', async () => {
      const result = await runner.executeOnWorker(
        once('repository_gpu_revoke', ` --device ${DEVICE}`)
      );
      expect(runner.isSuccess(result), runner.getCombinedOutput(result)).toBe(true);
      // `--show` prints the grant after the revoke on stdout (logs go to stderr), so an
      // empty or missing grant cannot pass this by printing nothing.
      const shown = result.stdout.toLowerCase();
      expect(shown, runner.getCombinedOutput(result)).toContain('devices');
      expect(shown).not.toContain(DEVICE);

      // The network's grants line, when the grant record outlives its last device.
      const listed = await runner.executeOnWorker(listCmd);
      expect(runner.isSuccess(listed), runner.getCombinedOutput(listed)).toBe(true);
      expect(grantLine(runner.getCombinedOutput(listed))).not.toContain(DEVICE);
    });
  });

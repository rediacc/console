import { expect, test } from '@playwright/test';
import { WK_DATASTORE_PATH, WK_INFRA_DOMAIN } from '@rediacc/shared/config/well-known.generated';
import { e2eRepoGuid } from '../src/utils/licence';
import { RenetFunctionsTestRunner } from '../src/utils/renet-functions/RenetFunctionsTestRunner';

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
// Every output this suite reads is lowercased (getCombinedOutput), so needles are too.
const DEVICE_LC = DEVICE.toLowerCase();
// repository_gpu_grant keeps the operate licence tier, so the call names a licensed repository.
const REPO = e2eRepoGuid();
const SPEC_PATH = `/etc/cdi/rediacc-e2e-${RUN_ID}.yaml`;
// A grant records the network's repo mount, which renet reads from the network's systemd unit (daemon grant refuses a network whose unit names none), so the suite stages a unit for its fake network. The unit is never started or loaded: nothing runs it.
const UNIT_PATH = `/etc/systemd/system/rediacc-docker-${NETWORK_ID}.service`;
const UNIT = [
  '[Service]',
  `ExecStart=/usr/bin/renet daemon start-foreground --network-id=${NETWORK_ID} --repo-mount-path=${WK_DATASTORE_PATH}/mounts/${REPO}`,
  '',
].join('\n');
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

/**
 * The text a verb printed. `renet functions once` re-emits the verb's stdout through the logger as
 * msg="[<fn>] <line>" on STDERR, with escaped quotes; only those lines are the verb's own, the
 * rest of STDERR is the logger's narration (it echoes the command line).
 */
function verbText(fn: string, result: { stdout: string; stderr: string }): string {
  const wrapped = new RegExp(`msg="\\[${fn}\\] (.*)"$`);
  const lines = result.stdout.split('\n');
  for (const line of result.stderr.split('\n')) {
    const m = wrapped.exec(line);
    if (m) lines.push(m[1].replaceAll('\\"', '"'));
  }
  return lines.join('\n');
}

interface GrantsDoc {
  grants?: { network_id: number; devices?: { name: string }[] }[];
}

/** The device names of this run's network in a machine_gpu_list record (JSON), or '' when it has no grant. */
function grantLine(result: { stdout: string; stderr: string }): string {
  const text = verbText('machine_gpu_list', result);
  const lines = text.split('\n');
  const start = lines.indexOf('{');
  const end = lines.indexOf('}', start);
  if (start < 0 || end < 0) return '';
  const doc = JSON.parse(lines.slice(start, end + 1).join('\n')) as GrantsDoc;
  const mine = doc.grants?.find((g) => g.network_id === NETWORK_ID);
  return (mine?.devices ?? [])
    .map((d) => d.name)
    .join(',')
    .toLowerCase();
}

test.describe
  .serial('GPU device grants @bridge', () => {
    let runner: RenetFunctionsTestRunner;
    const once = (fn: string, extra = '') =>
      `sudo renet functions once --test-mode --function ${fn} --network-id ${NETWORK_ID} --repository ${REPO}${extra}`;
    const listCmd = 'sudo renet functions once --test-mode --function machine_gpu_list';

    test.beforeAll(async () => {
      runner = RenetFunctionsTestRunner.forWorker();
      const b64 = Buffer.from(SPEC).toString('base64');
      const written = await runner.executeOnWorker(
        `sudo mkdir -p /etc/cdi && echo ${b64} | base64 -d | sudo tee ${SPEC_PATH} >/dev/null`
      );
      expect(runner.isSuccess(written), runner.getCombinedOutput(written)).toBe(true);
      const unitB64 = Buffer.from(UNIT).toString('base64');
      const staged = await runner.executeOnWorker(
        `echo ${unitB64} | base64 -d | sudo tee ${UNIT_PATH} >/dev/null`
      );
      expect(runner.isSuccess(staged), runner.getCombinedOutput(staged)).toBe(true);
      const licensed = await runner.licenseRepository(REPO);
      expect(runner.isSuccess(licensed), runner.getCombinedOutput(licensed)).toBe(true);
    });

    test.afterAll(async () => {
      await runner.executeOnWorker(
        `sudo renet daemon grant --network-id ${NETWORK_ID} --clear; sudo rm -f ${SPEC_PATH} ${UNIT_PATH} ${WK_DATASTORE_PATH}/repositories/${REPO}`
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
      expect(runner.getCombinedOutput(result)).toContain(DEVICE_LC);

      // The inventory lists every CDI device, granted or not, so the grant is read from
      // the network's own line of the grants section.
      const listed = await runner.executeOnWorker(listCmd);
      expect(runner.isSuccess(listed), runner.getCombinedOutput(listed)).toBe(true);
      expect(grantLine(listed)).toContain(DEVICE_LC);
    });

    test('repository_gpu_revoke removes the device from the grant', async () => {
      const result = await runner.executeOnWorker(
        once('repository_gpu_revoke', ` --device ${DEVICE}`)
      );
      expect(runner.isSuccess(result), runner.getCombinedOutput(result)).toBe(true);
      // `--show` prints the grant record after the revoke (re-emitted by `functions once`). Revoking the last device drops the grant, so the record is the empty one: a printed record without the device, which a verb that printed nothing cannot pass.
      const shown = verbText('repository_gpu_revoke', result).toLowerCase();
      expect(shown, runner.getCombinedOutput(result)).toContain('"repo_mount_path"');
      expect(shown).not.toContain(DEVICE_LC);

      // The network's grants line, when the grant record outlives its last device.
      const listed = await runner.executeOnWorker(listCmd);
      expect(runner.isSuccess(listed), runner.getCombinedOutput(listed)).toBe(true);
      expect(grantLine(listed)).not.toContain(DEVICE_LC);
    });
  });

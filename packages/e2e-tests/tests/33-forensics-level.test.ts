import { expect, test } from '@playwright/test';
import { WK_ETC_DIR } from '@rediacc/shared/config/well-known.generated';
import { e2eRepoGuid } from '../src/utils/licence';
import { RenetFunctionsTestRunner } from '../src/utils/renet-functions/RenetFunctionsTestRunner';

/**
 * Suite 33: the forensics_level renet function (PLAN-forensics-investigation FI14), driven through
 * `renet functions once` on a worker VM. The verb wraps `renet forensics level <guid> <level>` and
 * writes the root-only /etc/rediacc/forensics/<guid>.json, so each step reads that file back.
 * A level outside basic|standard|full is the control: the verb refuses it and the file keeps
 * the last good level.
 */

// forensics_level keeps the operate licence tier, so the call names a licensed repository.
const REPO = e2eRepoGuid();
const SETTINGS_PATH = `${WK_ETC_DIR}/forensics/${REPO}.json`;

test.describe
  .serial('Forensics level @bridge', () => {
    let runner: RenetFunctionsTestRunner;
    const once = (level: string) =>
      `sudo renet functions once --test-mode --function forensics_level --repository ${REPO} --level ${level}`;
    const settings = async () => {
      const read = await runner.executeOnWorker(`sudo cat ${SETTINGS_PATH}`);
      expect(runner.isSuccess(read), runner.getCombinedOutput(read)).toBe(true);
      return JSON.parse(read.stdout) as { level: unknown };
    };

    test.beforeAll(async () => {
      runner = RenetFunctionsTestRunner.forWorker();
      const licensed = await runner.licenseRepository(REPO);
      expect(runner.isSuccess(licensed), runner.getCombinedOutput(licensed)).toBe(true);
    });

    test.afterAll(async () => {
      await runner.executeOnWorker(`sudo rm -f ${SETTINGS_PATH}`);
    });

    test('forensics_level records full', async () => {
      const result = await runner.executeOnWorker(once('full'));
      expect(runner.isSuccess(result), runner.getCombinedOutput(result)).toBe(true);
      expect((await settings()).level).toBe('full');
    });

    test('forensics_level switches back to basic', async () => {
      const result = await runner.executeOnWorker(once('basic'));
      expect(runner.isSuccess(result), runner.getCombinedOutput(result)).toBe(true);
      expect((await settings()).level).toBe('basic');
    });

    test('forensics_level refuses a level outside basic, standard and full', async () => {
      const before = await settings();
      const result = await runner.executeOnWorker(once('paranoid'));
      // The refusal text names the allowed levels (private/renet i18n key forensics_level.level_invalid), so a misspelled flag or a crashed verb, which also exit non-zero, does not pass here.
      expect(result.code, runner.getCombinedOutput(result)).not.toBe(0);
      expect(runner.getCombinedOutput(result)).toContain('"paranoid" must be basic, standard or full');
      expect(await settings()).toEqual(before);
    });
  });

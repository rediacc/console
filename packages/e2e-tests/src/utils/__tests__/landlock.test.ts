import { describe, expect, it } from 'vitest';
import { assertLandlockSelected, LANDLOCK_INACTIVE_BY_DEFAULT, workerOsId } from '../landlock';
import {
  LANDLOCK_INACTIVE_OS_IDS,
  LANDLOCK_INACTIVE_VM_IMAGES,
  landlockGrepInvert,
} from '../landlockSelection';
import type { RenetFunctionsTestRunner } from '../renet-functions/RenetFunctionsTestRunner';
import { TestHelpers } from '../renet-functions/helpers/TestHelpers';

// The real runner hands the parser the LOWERCASED output (TestHelpers.getCombinedOutput), which is why the parser looks
// for `id=` and `version_id=`; driving it through the same helper keeps this test honest about that contract.
function runnerReading(osRelease: string): RenetFunctionsTestRunner {
  const helpers = new TestHelpers();
  return {
    executeOnWorker: async () => ({ stdout: osRelease, stderr: '', exitCode: 0 }),
    getCombinedOutput: (result: { stdout: string; stderr: string }) =>
      helpers.getCombinedOutput(result as never),
  } as unknown as RenetFunctionsTestRunner;
}

const ORACLE_10 =
  'NAME="Oracle Linux Server"\nVERSION="10.0"\nID="ol"\nID_LIKE="fedora"\nVERSION_ID="10.0"\n';
const UBUNTU_24 =
  'PRETTY_NAME="Ubuntu 24.04.1 LTS"\nNAME="Ubuntu"\nVERSION_ID="24.04"\nID=ubuntu\nID_LIKE=debian\n';

const INACTIVE_OS = new Set(['ol-10']);

describe('workerOsId', () => {
  it('reads Oracle Linux 10 as ol-10, which is no longer Landlock-inactive', async () => {
    const os = await workerOsId(runnerReading(ORACLE_10));
    expect(os).toBe('ol-10');
    expect(LANDLOCK_INACTIVE_BY_DEFAULT.has(os)).toBe(false);
  });

  it('reads Ubuntu 24.04 as ubuntu-24, which the Landlock set does not name (control)', async () => {
    const os = await workerOsId(runnerReading(UBUNTU_24));
    expect(os).toBe('ubuntu-24');
    expect(LANDLOCK_INACTIVE_BY_DEFAULT.has(os)).toBe(false);
  });

  it('refuses an os-release with no ID instead of guessing', async () => {
    await expect(workerOsId(runnerReading('NAME="x"\n'))).rejects.toThrow(
      /could not read the worker's OS/
    );
  });
});

describe('landlock selection machinery', () => {
  it('names no image today: every image runs the @landlock suites, oracle-10 included', () => {
    expect(LANDLOCK_INACTIVE_VM_IMAGES.size).toBe(0);
    expect(LANDLOCK_INACTIVE_OS_IDS.size).toBe(0);
    expect(landlockGrepInvert('oracle-10')).toBeUndefined();
    expect(landlockGrepInvert('ubuntu-24.04')).toBeUndefined();
    expect(landlockGrepInvert(undefined)).toBeUndefined();
  });

  it('drops the @landlock suites on an image a future set names, and only there', () => {
    const pattern = landlockGrepInvert('future-os', new Set(['future-os']));
    expect(pattern?.test('Rediaccfile Lifecycle @bridge @lifecycle @landlock')).toBe(true);
    expect(pattern?.test('Rediaccfile Edge Cases @bridge')).toBe(false);
    expect(landlockGrepInvert('ubuntu-24.04', new Set(['future-os']))).toBeUndefined();
  });

  it('assertLandlockSelected still refuses a worker whose OS a set names', async () => {
    expect(INACTIVE_OS.has('ol-10')).toBe(true);
    await expect(assertLandlockSelected(runnerReading(ORACLE_10))).resolves.toBeUndefined();
  });
});

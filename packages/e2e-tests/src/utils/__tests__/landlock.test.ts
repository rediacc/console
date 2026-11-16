import { describe, expect, it } from 'vitest';
import { LANDLOCK_INACTIVE_BY_DEFAULT, workerOsId } from '../landlock';
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

describe('workerOsId', () => {
  it('reads Oracle Linux 10 as ol-10, which the Landlock set names', async () => {
    const os = await workerOsId(runnerReading(ORACLE_10));
    expect(os).toBe('ol-10');
    expect(LANDLOCK_INACTIVE_BY_DEFAULT.has(os)).toBe(true);
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

describe('landlockGrepInvert', () => {
  it('drops the @landlock suites on oracle-10, the image whose os id the Landlock set names', () => {
    const pattern = landlockGrepInvert('oracle-10');
    expect(pattern?.test('Rediaccfile Lifecycle @bridge @lifecycle @landlock')).toBe(true);
    expect(pattern?.test('Rediaccfile Edge Cases @bridge')).toBe(false);
  });

  it('selects everything on a Landlock-active image or with no VM_IMAGE (control)', () => {
    expect(landlockGrepInvert('ubuntu-24.04')).toBeUndefined();
    expect(landlockGrepInvert(undefined)).toBeUndefined();
  });

  it('pairs each inactive os id with a VM image so the two sets cannot drift apart', () => {
    expect(LANDLOCK_INACTIVE_VM_IMAGES.size).toBe(LANDLOCK_INACTIVE_OS_IDS.size);
  });
});

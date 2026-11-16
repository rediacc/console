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

  it('maps each inactive VM image to its os id and back, so a mismatched pair fails', () => {
    // The CI matrix `os-image` names the image (`oracle-10`); /etc/os-release names the OS (`ol-10`).
    const OS_ID_OF_IMAGE: Record<string, string> = { 'oracle-10': 'ol-10' };
    const byText = (a: string, b: string) => a.localeCompare(b);
    expect([...LANDLOCK_INACTIVE_VM_IMAGES].sort(byText)).toEqual(
      Object.keys(OS_ID_OF_IMAGE).sort(byText)
    );
    expect([...LANDLOCK_INACTIVE_OS_IDS].sort(byText)).toEqual(
      Object.values(OS_ID_OF_IMAGE).sort(byText)
    );
    for (const [image, osId] of Object.entries(OS_ID_OF_IMAGE)) {
      expect(landlockGrepInvert(image), `${image} must drop @landlock`).toBeInstanceOf(RegExp);
      expect(LANDLOCK_INACTIVE_BY_DEFAULT.has(osId), `${osId} must be Landlock-inactive`).toBe(
        true
      );
    }
  });

  it('selects @landlock suites when VM_IMAGE is unset or unmapped, the gap assertLandlockSelected backstops', () => {
    expect(landlockGrepInvert(undefined)).toBeUndefined();
    expect(landlockGrepInvert('ol-10')).toBeUndefined();
  });
});

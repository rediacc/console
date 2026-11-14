import { test } from '@playwright/test';
import type { RenetFunctionsTestRunner } from './renet-functions/RenetFunctionsTestRunner';

/**
 * OS images whose default boot leaves Landlock out of the active LSM list, so `renet sandbox-exec --detect` reports
 * NOT AVAILABLE and repo-key shells refuse there by design. Measured on the CI matrix (run 39640583259, 2026-10-21):
 * Oracle Linux 10 UEK 6.12 boots with `lsm=lockdown,capability,yama,selinux,bpf,ima,evm` and logs
 * "landlock: Disabled but requested by user space"; Ubuntu 24.04, Debian 13, Fedora 43 and openSUSE 16.0 report ABI 4-7.
 *
 * The one source of truth: 01-system-checks pins `--detect` against it, and every test that needs a Rediaccfile `up()` or
 * `down()` to run (or a repository started by one) is skipped through `skipWithoutLandlock`, because renet refuses to run
 * those functions without Landlock: "the Rediaccfile functions were not run: up() and down() need Landlock to confine them".
 */
export const LANDLOCK_INACTIVE_BY_DEFAULT: ReadonlySet<string> = new Set(['ol-10']);

const REQUIREMENTS_DOCS = 'packages/www/src/content/docs/en/requirements.md';

/** The worker's `<id>-<major version>` from /etc/os-release, e.g. `ol-10`, `ubuntu-24`. Read plainly and parsed here: a `$ID` in the remote command is expanded by the runner's own shell. */
export async function workerOsId(runner: RenetFunctionsTestRunner): Promise<string> {
  const release = runner.getCombinedOutput(await runner.executeOnWorker('cat /etc/os-release'));
  const field = (name: string) =>
    release.match(new RegExp(`^${name}="?([^"\\n]*)"?$`, 'm'))?.[1]?.trim() ?? '';
  const id = field('id');
  const major = field('version_id').split('.')[0];
  if (!(id && major)) {
    throw new Error(`could not read the worker's OS from /etc/os-release: ${release}`);
  }
  return `${id}-${major}`;
}

/**
 * Skips the calling beforeAll's tests (or the running test) on an OS where Landlock is inactive by default. Call it right
 * after the runner exists and before any provisioning. Other OSes pass through untouched.
 */
export async function skipWithoutLandlock(runner: RenetFunctionsTestRunner): Promise<void> {
  const os = await workerOsId(runner);
  test.skip(
    LANDLOCK_INACTIVE_BY_DEFAULT.has(os),
    `${os} boots without Landlock in lsm=, so renet refuses to run Rediaccfile up()/down() there by design; see ${REQUIREMENTS_DOCS} (Landlock) for the grubby fix`
  );
}

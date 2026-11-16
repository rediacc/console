import { LANDLOCK_INACTIVE_OS_IDS } from './landlockSelection';
import type { RenetFunctionsTestRunner } from './renet-functions/RenetFunctionsTestRunner';

/**
 * OS images whose default boot leaves Landlock out of the active LSM list, so `renet sandbox-exec --detect` reports
 * NOT AVAILABLE and repo-key shells refuse there by design. Measured on the CI matrix (run 39640583259, 2026-10-21):
 * Oracle Linux 10 UEK 6.12 boots with `lsm=lockdown,capability,yama,selinux,bpf,ima,evm` and logs
 * "landlock: Disabled but requested by user space"; Ubuntu 24.04, Debian 13, Fedora 43 and openSUSE 16.0 report ABI 4-7.
 *
 * The one source of truth: 01-system-checks pins `--detect` against it, and every suite that needs a Rediaccfile `up()` or
 * `down()` to run (or a repository started by one) is tagged `@landlock` and left out of the run on those images by the
 * config (`landlockSelection.ts`), because renet refuses to run
 * those functions without Landlock: "the Rediaccfile functions were not run: up() and down() need Landlock to confine them".
 */
export const LANDLOCK_INACTIVE_BY_DEFAULT: ReadonlySet<string> = LANDLOCK_INACTIVE_OS_IDS;

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
 * Guards a `@landlock` suite's beforeAll. The config's `grepInvert` selects by the `VM_IMAGE` value, not by the worker's
 * OS: with `VM_IMAGE` unset or naming an image outside `LANDLOCK_INACTIVE_VM_IMAGES` (a stale `.env`, an unmapped alias)
 * a `@landlock` suite is selected even when the worker boots an OS in `LANDLOCK_INACTIVE_BY_DEFAULT`. This call is the
 * backstop for that gap: it reads the worker's real OS and fails loudly instead of skipping. Call it right after the
 * runner exists and before any provisioning.
 */
export async function assertLandlockSelected(runner: RenetFunctionsTestRunner): Promise<void> {
  const os = await workerOsId(runner);
  if (LANDLOCK_INACTIVE_BY_DEFAULT.has(os)) {
    throw new Error(
      `${os} boots without Landlock in lsm=, so renet refuses to run Rediaccfile up()/down() there by design, and a @landlock suite must not be selected on it (playwright.config.ts grepInvert); see ${REQUIREMENTS_DOCS} (Landlock) for the grubby fix`
    );
  }
}

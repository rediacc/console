/**
 * Topology selection for Landlock: the OS images that cannot boot with Landlock in the active LSM list are named once
 * here, by the `VM_IMAGE` value a CI leg carries, and the Playwright config drops every suite tagged `@landlock` on them.
 * None is named today: `landlockBoot.ts` adds Landlock to `lsm=` and reboots any VM that boots without it (Oracle Linux 10
 * did). A suite is tagged when it needs a Rediaccfile `up()` or `down()` to run (or a repository started by one). The
 * zero-skip gate wants selection by topology, never collect-then-skip.
 * Selection keys on `VM_IMAGE` alone (`create_e2e_env` writes it into `.env`, defaulting to ubuntu-24.04, and the CI matrix sets
 * it from `os-image`): an unset or unmapped value selects everything, and `assertLandlockSelected` catches that on the worker.
 */

/** The `/etc/os-release` `<id>-<major>` of each Landlock-inactive image; `landlock.ts` pins `renet sandbox-exec --detect` against it. */
export const LANDLOCK_INACTIVE_OS_IDS: ReadonlySet<string> = new Set<string>();

/** The `VM_IMAGE` value (the CI matrix `os-image`) booting each id in `LANDLOCK_INACTIVE_OS_IDS`. */
export const LANDLOCK_INACTIVE_VM_IMAGES: ReadonlySet<string> = new Set<string>();

/** The title tag that marks a describe as needing Landlock. */
const LANDLOCK_TAG = '@landlock';

/** The config's `grepInvert` for a `VM_IMAGE`: the tag on a Landlock-inactive image, no pattern anywhere else. */
export function landlockGrepInvert(
  vmImage: string | undefined,
  inactiveImages: ReadonlySet<string> = LANDLOCK_INACTIVE_VM_IMAGES
): RegExp | undefined {
  return vmImage !== undefined && inactiveImages.has(vmImage)
    ? new RegExp(LANDLOCK_TAG)
    : undefined;
}

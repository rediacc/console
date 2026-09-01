/**
 * The two browser globals this site sets on `window` and reads from a dozen components.
 *
 * WHY THIS FILE DID NOT EXIST. Nothing typechecked `packages/www`: it has a tsconfig, but
 * no `typecheck` script and no CI step that runs one, so 32 `TS2339` errors sat in
 * production components indefinitely. `astro build` does not typecheck TypeScript, and
 * `astro check` is not wired here. The package was found by sweeping the class behind
 * 6ba6a0c4c (packages/cli's tests), and it turned out not to be a test-coverage problem at
 * all -- ZERO of the 32 were in test files.
 *
 * The declarations are derived from the call sites, not invented:
 *
 *   `plausible`     BaseLayout.astro:252 installs the analytics stub, and every caller
 *                   uses the optional form `window.plausible?.(event, { props })`, so it
 *                   is optional and the props bag is a flat record of scalars.
 *   `__pa_get_utm`  the behavioural tracker's captured utm_* params. THREE components
 *                   were already working around the missing declaration with a local
 *                   `(window as unknown as { __pa_get_utm?: … })` cast (ContactModal:139,
 *                   PartnerApplicationForm:202, NewsletterSignup:89) while a fourth read
 *                   it directly and errored. One declaration replaces all four.
 *   `openRegionPicker` / `forceOpenRegionPicker`
 *                   RegionPickerModal.tsx:165-166 assigns them and DELETES them on
 *                   unmount, so both are optional; each takes an optional path
 *                   (RegionPickerModal.tsx:114 and :123) and returns void.
 *
 * Optional rather than required is the honest shape twice over: the analytics script is
 * blockable and may never define `plausible`, and the region picker removes its own
 * handles when it unmounts. Declaring them required would make every existing `?.` look
 * redundant and invite someone to delete the guard.
 */
export {};

declare global {
  interface Window {
    plausible?: (event: string, options?: { props?: Record<string, string | number | boolean> }) => void;
    openRegionPicker?: (path?: string) => void;
    forceOpenRegionPicker?: (path?: string) => void;
    __pa_get_utm?: () => Record<string, string>;
  }
}

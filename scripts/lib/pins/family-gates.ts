/**
 * The gates that judge their own leaves' freshness. check:ci-pin-freshness does not judge a leaf naming one
 * (two verdicts for one pin), and `pins bump --all` / `apply-soaked` skip such a leaf when no pins driver
 * serves it, rather than refusing the whole run over a pin its own gate already owns.
 */
export const FAMILY_GATES: Record<string, string> = {
  'check:ci-embed-asset-freshness': 'the embedded binaries of private/renet',
  'check:ci-devcontainer-pins': 'the devcontainer CLIs it lists',
  'check:ci-real-provider-pins': 'the real-provider lock',
  'check:ci-ceph-image-pin':
    'the Ceph image and host pins (review date and same-host-version rule)',
  'check:ci-breakpoint-drift':
    'the vendored .ci/breakpoint copy, whose pins move only with a re-vendor of the canonical repo',
};

/** The family gate a leaf names, or undefined. */
export function familyGateOf(gates: readonly string[]): string | undefined {
  return gates.find((g) => g in FAMILY_GATES);
}

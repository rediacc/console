/**
 * Resolve a disclosure trigger's thumbnail to its raw SVG markup.
 *
 * These are the pictures that make a collapsed section legible at a glance. A trigger
 * reading only "Show the comparison" asks the reader to spend a click finding out what
 * is behind it; a 120px drawing of a three-column matrix answers that before the click.
 *
 * SEPARATE GLOB FROM `solution-illustration.ts` on purpose. That one is keyed by SOLUTION
 * SLUG and its directory is a 1:1 map onto the 21 solution pages; dropping four files
 * named after section TYPES into it would break that correspondence for anyone reading
 * the directory, and `resolveSolutionIllustration('trigger-calculator')` would resolve.
 * Two namespaces, two directories.
 *
 * Same two constraints as the solution illustrations, and for the same reasons:
 * TEXTLESS (operator decision L4), so one file serves 13 locales; and INLINED rather
 * than referenced by `<img src>`, because they paint from the `--illustration-*` custom
 * properties, which an externally-loaded SVG is a separate document from and can never
 * see. `scripts/check-svg-theme-reach.ts` gates the second one.
 */
const thumbModules = import.meta.glob<string>('../assets/images/disclosure/*.svg', {
  eager: true,
  query: '?raw',
  import: 'default',
  // Index access on a glob record is `string` per TS, but a missing key is `undefined`
  // at runtime, so widen and let the null fallback stay sound.
}) as Record<string, string | undefined>;

/** `'trigger-calculator'`, `'trigger-tech-diff'`, `'trigger-comparison'`, `'trigger-problem-detail'`, `'mechanism-cow'`. */
export function resolveDisclosureThumb(name: string): string | null {
  return thumbModules[`../assets/images/disclosure/${name}.svg`] ?? null;
}

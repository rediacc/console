/**
 * Resolve a solution-page illustration to its raw SVG markup.
 *
 * The drawings are textless (operator decision L4), so one file serves every
 * locale and viewport: `<slug>.svg`. They are inlined into the page rather
 * than referenced by URL because they paint from the `--illustration-*`
 * custom properties (`public/styles/main.css`), which flip with the theme;
 * an external `<img>` SVG is a separate document and can never see them.
 */
const illustrationModules = import.meta.glob<string>('../assets/images/illustrations/*.svg', {
  eager: true,
  query: '?raw',
  import: 'default',
  // Index access on a glob record is `string` per TS, but a missing key is
  // `undefined` at runtime, so widen and let the null fallback stay sound.
}) as Record<string, string | undefined>;

export function resolveSolutionIllustration(slug: string): string | null {
  return illustrationModules[`../assets/images/illustrations/${slug}.svg`] ?? null;
}

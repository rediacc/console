/**
 * `map[key]` lies: the repo does not enable `noUncheckedIndexedAccess`, so a
 * missing key is typed as present while yielding undefined at runtime. Every
 * absence check against one of the curated lookup tables guards a real runtime
 * case (most commands have no examples, no keywords, no metadata entry), and
 * going through this helper is what keeps those checks type-legal — annotating
 * the variable is not enough, because TypeScript narrows a const back to the
 * initializer's (lying) type.
 *
 * Same helper as `at` in src/services/config/config-datastores.ts; duplicated
 * rather than imported so the build scripts do not reach into a runtime service
 * for a two-line type utility.
 */
export function at<T>(map: Readonly<Record<string, T>>, key: string): T | undefined {
  return map[key];
}

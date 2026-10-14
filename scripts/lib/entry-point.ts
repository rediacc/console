/**
 * "Was this module run, or was it loaded?", answered once.
 *
 * A gate that exports its helpers for its own controls (or for a sibling gate) must not run
 * `main()` when it is imported: an unguarded call exits the importing process the moment the
 * module loads (check-locale-only-edits.ts records that happening). The guard is the same
 * three tokens in every such gate, and `check:ci-shape-duplication` counts the third copy of a
 * span as a finding, so the comparison lives here.
 *
 * `import.meta.main` would say it directly and is not available on every Node this repo runs.
 *
 * @param metaUrl The caller's `import.meta.url`.
 */
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

export function isEntryPoint(metaUrl: string): boolean {
  const invoked = process.argv[1];
  return invoked !== undefined && path.resolve(invoked) === path.resolve(fileURLToPath(metaUrl));
}

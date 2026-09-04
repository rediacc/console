/**
 * The parity SURFACE: which workflow files a CI run actually enters, walked from the
 * root workflow. Split out of manifest.ts on 2026-09-04 for the reason its sibling
 * gate-spec.ts records -- a consumer that wants the surface should not import 378 gate
 * entries to get it.
 *
 * Behaviour is unchanged and the doc comment below is the original: an entry job that
 * is not there collapses the surface ON PURPOSE, so a renamed job produces an empty
 * surface and the caller's preflight refuses to run, rather than a job-scoped stub that
 * would go silent over the whole quality tier while reporting a clean run.
 */

import fs from 'node:fs';
import path from 'node:path';

const ENTRY_WORKFLOW = '.github/workflows/ci.yml';
/** Jobs of ENTRY_WORKFLOW that are themselves part of the quality surface. */
const ENTRY_JOBS = ['quality', 'review-gate'];

/**
 * Workflows outside this set are not part of the parity surface.
 *
 * COMPUTED, NEVER HAND-LISTED. Direction B produced 14 release/CD/E2E scripts
 * that are correctly out of scope; listing them as exemptions would be 14
 * permanent lies in a suppression file. So scope is structural: the transitive
 * closure of `uses: ./.github/workflows/*` reachable from ci.yml's `quality`
 * job, plus the `review-gate` job's own steps. Iterating `uses:` rather than
 * matching names is what stops a new lane workflow escaping the gate, and is
 * the same technique test-scope-engine.sh is registered in the anti-vacuity
 * harness for.
 *
 * An entry is a repo-relative workflow path, optionally suffixed `#<jobId>` to
 * scope the surface to a single job of that file. review-gate is job-scoped
 * because the rest of ci.yml (build, release, E2E) is out of scope.
 *
 * AN ENTRY JOB THAT IS NOT THERE COLLAPSES THE SURFACE, ON PURPOSE. If `quality`
 * were renamed, a version of this that quietly emitted a job-scoped stub would
 * hand the caller a non-empty surface containing nothing, and the reverse
 * direction would go silent over the entire quality tier while still reporting
 * a clean run. That is the vacuity failure this file exists to prevent, so a
 * missing entry job returns the empty surface and the caller's preflight
 * refuses to run.
 */
export function paritySurface(repoRoot: string): string[] {
  const entryPath = path.join(repoRoot, ENTRY_WORKFLOW);
  if (!fs.existsSync(entryPath)) return [];

  const out: string[] = [];
  const seen = new Set<string>();
  const queue: string[] = [];

  // job id -> reusable workflow it calls (or '' when it has its own steps), for
  // the jobs of ci.yml only.
  const calls = new Map<string, string>();
  let job = '';
  for (const raw of fs.readFileSync(entryPath, 'utf-8').split('\n')) {
    const jobMatch = raw.match(/^ {2}([\w-]+):\s*$/);
    if (jobMatch) {
      job = jobMatch[1];
      calls.set(job, '');
      continue;
    }
    const uses = raw.match(/^ {4}uses:\s*(\.\/\.github\/workflows\/[\w.-]+)\s*$/);
    if (uses && job) calls.set(job, uses[1].replace(/^\.\//, ''));
  }

  for (const j of ENTRY_JOBS) {
    const called = calls.get(j);
    if (called === undefined) return [];
    if (called) queue.push(called);
    else out.push(`${ENTRY_WORKFLOW}#${j}`);
  }

  while (queue.length > 0) {
    const file = queue.shift();
    if (file === undefined || seen.has(file)) continue;
    seen.add(file);
    const abs = path.join(repoRoot, file);
    if (!fs.existsSync(abs)) continue;
    out.push(file);
    for (const m of fs
      .readFileSync(abs, 'utf-8')
      .matchAll(/^ {4}uses:\s*(\.\/\.github\/workflows\/[\w.-]+)\s*$/gm)) {
      queue.push(m[1].replace(/^\.\//, ''));
    }
  }
  return out;
}

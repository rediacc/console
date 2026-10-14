/**
 * The one failure line every freshness gate prints: the exact `npm run pins -- ...` command
 * that fixes its finding (agent/plans/PLAN-pins-command.md Design 4). Its Python twin is
 * `.ci/rediacc_ci/core/pins.py` (`bump_remedy`, and `lockfiles_remedy` for check:ci-lockfile,
 * which is Python), and builds the same line byte for byte.
 *
 * WHY ONE HELPER. Before it, each gate printed its own to-do list: a sed recipe for actions
 * that missed the gate-bind constant, an `--upgrade` flag followed by three hand steps for the
 * embed assets, a lockfile recipe that named the ambient npm. Every list was correct only by
 * the care of whoever last edited it. The pins command now does those steps in one
 * transaction, so a gate's whole remedy is the one command, and this module is the only place
 * that spells it.
 *
 * THE ID IS CHECKED. A remedy that names a pin id the registry does not hold would send the
 * reader to a refusal, so building one for an unknown id throws, naming the id. The registry
 * read is the console's own (`.ci/config/pins.json` beside this checkout), never a fixture
 * root, because the gates that call this run under their own fixture seams.
 *
 * `REMEDY_PREFIX` starts every line, so a reader (and .ci/rediacc_ci/tests/gates/
 * test_gate_pin_remedies.py) finds the fix by one token whatever else the gate printed.
 */
import path from 'node:path';
import { REPO_ROOT } from '../repo-root.js';
import { loadRegistry, type PinRegistry } from './registry.js';

const REMEDY_PREFIX = 'fix:';

function knownId(id: string): string {
  const registry: PinRegistry = loadRegistry(path.join(REPO_ROOT, '.ci/config/pins.json'));
  if (!registry.entries.some((e) => e.id === id))
    throw new Error(
      `a freshness gate built a remedy for pin id ${JSON.stringify(id)}, which .ci/config/pins.json does not hold; the gate's id mapping is wrong`
    );
  return id;
}

/** `  fix: npm run pins -- bump <id>`, or with `--major --reason "<why>"` for a pin whose only move is a major. */
export function bumpRemedy(id: string, opts: { major?: boolean } = {}): string {
  const tail = opts.major ? ' --major --reason "<why>"' : '';
  return `  ${REMEDY_PREFIX} npm run pins -- bump ${knownId(id)}${tail}`;
}

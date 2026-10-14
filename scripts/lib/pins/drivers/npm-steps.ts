#!/usr/bin/env tsx
/**
 * The two post-install checks the pins npm driver runs as transaction steps
 * (scripts/lib/pins/drivers/npm.ts): they are commands because the transaction runs every
 * step through one runner, journals its declared writes and restores on a non-zero exit.
 *
 *   npm-steps.ts guard <base64 json>   the FRESHNESS-WINDOW GUARD for one `npm update` step:
 *                                      every package the step names must resolve in the
 *                                      step's lockfile to the exact version that was judged
 *                                      (scripts/lib/deps/execute.ts updateMismatches). Reads
 *                                      the lockfile and writes nothing.
 *   npm-steps.ts sync <base64 json>    move the .syncpackrc.json pin groups that hold a
 *                                      package the run moved (scripts/lib/deps/pin-sync.ts).
 *                                      Writes only .syncpackrc.json, and only when every group
 *                                      can move; otherwise it names each laggard and exits 1.
 *
 * Both read the tree named by CHECK_DEPS_ROOT, else the repository this file sits in, the
 * same seam check-deps uses, so a fixture run and a real run take the same code.
 */
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { updateMismatches } from '../../deps/execute.js';
import { planPinGroupSync, SYNCPACK_RC_PATH } from '../../deps/pin-sync.js';
import type { InstallStep } from '../../deps/plan.js';
import { MAJOR_ALLOW_REL, readLockPackages } from '../../deps/shared.js';

const decode = (b64: string): InstallStep[] =>
  JSON.parse(Buffer.from(b64, 'base64').toString('utf8')) as InstallStep[];

/** The guard's verdict for one step: one line per package that did not resolve to its judged version. */
function guardLines(step: InstallStep): { unjudged: string[]; heldBack: string[] } {
  const mismatches = updateMismatches(step, readLockPackages(step.cwd));
  return {
    unjudged: mismatches.filter((m) => !m.held).map((m) => m.line),
    heldBack: mismatches.filter((m) => m.held).map((m) => m.line),
  };
}

function guard(steps: InstallStep[]): number {
  let rc = 0;
  for (const step of steps) {
    const { unjudged, heldBack } = guardLines(step);
    if (unjudged.length > 0) {
      rc = 1;
      console.error(
        `\`npm ${step.args.join(' ')}\` in ${path.relative(process.cwd(), step.cwd) || '.'} resolved a version the gate did not judge (freshness-window guard, .ci/config/release-age.json):`
      );
      for (const l of unjudged) console.error(`  ${l}`);
    }
    if (heldBack.length > 0) {
      rc = 1;
      console.error(
        `\`npm ${step.args.join(' ')}\` left ${heldBack.length} package(s) below the judged version (npm kept the installed one, so nothing unjudged landed):`
      );
      for (const l of heldBack) console.error(`  ${l}`);
      console.error(
        `  A package an installed sibling pins exactly moves only with that sibling: take the sibling's bump (\`bump npm --to <package>@<line> --major --reason\` when it is a held major, which installs before this update), or wait for a sibling release that admits the judged version. ${MAJOR_ALLOW_REL} is no longer where such a decision is recorded.`
      );
    }
  }
  if (rc === 0)
    console.log('freshness guard: every updated package resolved to its judged version');
  return rc;
}

function sync(steps: InstallStep[]): number {
  const plan = planPinGroupSync(steps);
  console.log(
    `syncpack pin groups: ${plan.groups} groups, ${plan.involved} hold a moved package, ${plan.rewritten.length} rewritten`
  );
  for (const r of plan.rewritten) console.log(`  .syncpackrc.json ${r}`);
  if (plan.errors.length > 0) {
    console.error(
      `${plan.errors.length} syncpack pin group(s) not moved (check:version would stay red until each is):`
    );
    for (const e of plan.errors) console.error(`  ${e}`);
    return 1;
  }
  // The only write of this module: the rc file the plan rewrote, inside the pins transaction (declared in its step, journaled, restored on failure).
  if (plan.text !== null) fs.writeFileSync(SYNCPACK_RC_PATH, plan.text);
  return 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(import.meta.filename)) {
  const [verb, payload] = process.argv.slice(2);
  if ((verb !== 'guard' && verb !== 'sync') || !payload) {
    console.error('usage: npm-steps.ts guard|sync <base64 json>');
    process.exit(2);
  }
  process.exit(verb === 'guard' ? guard(decode(payload)) : sync(decode(payload)));
}

/**
 * check:ci-workflow-orphan-step-keys -- a step-level key may not survive the
 * deletion of the step it belonged to.
 *
 * ---- gate ----
 * step: Workflow orphan step keys
 * needs: none
 * why: a refactor deleted a step's name/if/run and left its env block grafted onto the previous step
 * ---- /gate ----
 *
 * WHY THIS EXISTS, found by the Claude review on PR #585 and not by any gate.
 * Commit 1e8026bd extracted the "External dependency freshness" step and removed
 * its `name:`/`if:`/`run:` lines, but left the trailing
 *
 *       # a comment describing that step
 *         env:
 *           EXTERNAL_QUALITY_MODE: ${{ inputs.external_quality }}
 *
 * in place. The file still parses, actionlint is happy, and CI stays green --
 * because YAML silently attaches those keys to the PREVIOUS step. So the repo
 * carried an undocumented env var on an unrelated step, under a comment
 * describing a step that no longer exists: the "comment describing code that
 * isn't there" trap this repo's own TRAPS.md warns about.
 *
 * THE RULE THAT WAS TRIED FIRST AND REJECTED, because the measurement said so.
 * The obvious gate is "every declared env var must be referenced". Measured
 * across .github/workflows: 849 step-level env vars, of which 290 (34%) have no
 * textual reference anywhere in the step or in any script it runs -- GH_TOKEN,
 * AWS_ACCESS_KEY_ID and the whole GH_* shadow family are read IMPLICITLY by the
 * gh and aws CLIs, or by a loop that iterates SHADOW_NAMES rather than naming
 * them. A guard whose usual outcome is a false positive is one people route
 * around, so that rule is a migration, not a gate.
 *
 * THE RULE ENFORCED INSTEAD is the one that is unambiguously a defect, and it is
 * structural rather than semantic. Within a job's `steps:` list, the keys of one
 * step are contiguous. A comment at the LIST-ITEM indent introduces the next
 * step. So a step-level key appearing after such a comment, with no `- ` item
 * between them, belongs to a step that is not there. Measured on the whole tree:
 * 0 findings once the one real instance was fixed.
 */

import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const WORKFLOWS = path.join(ROOT, '.github', 'workflows');

/** Keys that belong to a step rather than to a job or the file. */
const STEP_KEY =
  /^\s{8}(env|run|if|with|name|uses|shell|working-directory|continue-on-error|timeout-minutes):/;
/** The start of a step: `      - name: ...` */
const LIST_ITEM = /^\s{6}- /;
/** A comment at the list-item indent, which introduces the NEXT step. */
const BOUNDARY_COMMENT = /^\s{6}#/;
/** Floor for the corpus: see the VACUOUS refusal in main(). */
const MIN_WORKFLOWS = 10;

interface Finding {
  file: string;
  line: number;
  text: string;
}

export function scan(text: string): Array<{ line: number; text: string }> {
  const out: Array<{ line: number; text: string }> = [];
  let afterBoundary = false;
  text.split('\n').forEach((line, i) => {
    if (LIST_ITEM.test(line)) {
      afterBoundary = false;
      return;
    }
    if (BOUNDARY_COMMENT.test(line)) {
      afterBoundary = true;
      return;
    }
    if (!line.trim()) return; // blank lines do not end a comment block
    if (afterBoundary && STEP_KEY.test(line)) {
      out.push({ line: i + 1, text: line.trim().slice(0, 60) });
    }
    afterBoundary = false;
  });
  return out;
}

/** The exact text 1e8026bd left behind, kept as the plant. */
const PLANT = [
  '      - name: Check E2E skip hygiene (no collected-then-skipped suites)',
  '        run: npm run check:ci-e2e-skip-hygiene',
  '',
  '      # external_quality (not the old inline label expression): hard on a',
  '      # normal PR, absent on a labelled one, soft on the nightly.',
  '        env:',
  '          EXTERNAL_QUALITY_MODE: ${{ inputs.external_quality }}',
  '',
  '      - name: External links',
  '        run: echo hi',
  '',
].join('\n');

/** Returns how many controls ran, so the count printed below cannot drift from
 *  the controls themselves -- the count is what exposed 14 unfalsifiable controls
 *  in this repo on 2026-09-05, and a hand-written number would have hidden it. */
function selftest(): number {
  let ran = 0;
  const planted = scan(PLANT);
  if (planted.length !== 1 || !planted[0]?.text.startsWith('env:')) {
    console.error(`  FAIL  the real orphan was not caught: ${JSON.stringify(planted)}`);
    process.exit(1);
  }
  ran += 1;
  console.log('  PASS  the orphan 1e8026bd left behind is caught');

  // CONTROL: the same file with the orphan removed -- the fix that landed.
  const fixed = PLANT.split('\n')
    .filter((l) => !l.includes('external_quality (not the old') && !l.includes('normal PR, absent'))
    .filter((l) => !l.trim().startsWith('env:') && !l.includes('EXTERNAL_QUALITY_MODE'))
    .join('\n');
  if (scan(fixed).length !== 0) {
    console.error('  FAIL  CONTROL: the fixed shape was still reported');
    process.exit(1);
  }
  ran += 1;
  console.log('  PASS  CONTROL: removing the orphan clears it');

  // CONTROL: a comment introducing a REAL next step is the normal shape and by
  // far the commonest one in this tree. Policing it would make the usual
  // outcome a false positive.
  const legit = [
    '      - name: A step',
    '        run: echo hi',
    '',
    '      # A comment introducing the next step.',
    '      - name: Next step',
    '        env:',
    '          FOO: bar',
    '        run: echo bye',
    '',
  ].join('\n');
  if (scan(legit).length !== 0) {
    console.error('  FAIL  CONTROL: a comment before a real step was policed');
    process.exit(1);
  }
  ran += 1;
  console.log('  PASS  CONTROL: a comment before a real step is not policed');

  // CONTROL: an env block INSIDE a step, with no boundary comment, is normal.
  const inline = [
    '      - name: A step',
    '        run: echo hi',
    '        env:',
    '          FOO: bar',
    '',
  ].join('\n');
  if (scan(inline).length !== 0) {
    console.error('  FAIL  CONTROL: an ordinary step env block was policed');
    process.exit(1);
  }
  ran += 1;
  console.log('  PASS  CONTROL: an ordinary step env block is not policed');
  return ran;
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    const ran = selftest();
    if (ran < 4) {
      console.error(`  FAIL  only ${ran} control(s) ran; the selftest is incomplete`);
      process.exit(1);
    }
    console.log(`check-workflow-orphan-step-keys: selftest ok (${ran} controls)`);
    return;
  }
  if (!fs.existsSync(WORKFLOWS)) {
    console.error(
      `✗ ${path.relative(ROOT, WORKFLOWS)} does not exist, so this gate checked NOTHING`
    );
    process.exit(1);
  }
  const files = fs
    .readdirSync(WORKFLOWS)
    .filter((n) => n.endsWith('.yml') || n.endsWith('.yaml'))
    .sort();
  // A NAMED FLOOR, not merely "> 0". Zero is the obvious collapse; the quiet one
  // is a directory move that leaves the glob finding a couple of workflows while
  // the rest go unchecked, and a tick over 2 reads exactly like a tick over 27.
  if (files.length < MIN_WORKFLOWS) {
    console.error(
      `✗ VACUOUS: found only ${files.length} workflow file(s), below the floor of ` +
        `${MIN_WORKFLOWS}. The corpus is wrong, not the tree.`
    );
    process.exit(1);
  }

  const findings: Finding[] = [];
  for (const name of files) {
    const p = path.join(WORKFLOWS, name);
    for (const f of scan(fs.readFileSync(p, 'utf-8'))) {
      findings.push({ file: path.join('.github/workflows', name), line: f.line, text: f.text });
    }
  }
  if (findings.length > 0) {
    console.error(`✗ ${findings.length} orphaned step key(s):\n`);
    for (const f of findings) console.error(`  ${f.file}:${f.line}  ${f.text}`);
    console.error(
      '\n  A step-level key after a comment at the list-item indent, with no `- ` between\n' +
        '  them, belongs to a step that is not there. YAML attaches it to the PREVIOUS step\n' +
        '  instead, so nothing fails and the comment above it describes code that is gone.\n' +
        '  Delete the leftover, or restore the step the comment is talking about.'
    );
    process.exit(1);
  }
  console.log(
    `✓ workflow orphan step keys: ${files.length} workflow(s), no key left behind by a deleted step`
  );
}

main();

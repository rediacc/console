#!/usr/bin/env tsx
/**
 * A control written INSIDE a string literal asserts nothing, and looks fine.
 *
 * WHAT HAPPENED, 2026-09-08. A session adding three error-path controls to
 * `check-hydration-clean.ts` and `check-form-validation.ts` anchored the
 * insertion on the first `\n  return ` after the function header. In both files
 * that match is inside a JSX fixture held in a template literal, so the three
 * `check(...)` calls landed in the middle of a string. The selftests still
 * exited 0 and printed their usual PASS lines; the new controls printed nothing
 * and asserted nothing. The corruption was found only because the author grepped
 * the output for a label that never appeared.
 *
 * WHY NOTHING ELSE CATCHES IT. `tsc` is happy: the text is a valid string.
 * `eslint` is happy for the same reason. The selftest's own exit code is happy,
 * because a control that never runs cannot fail. It is the same family as a
 * control stranded below an exit verdict -- there is no run that distinguishes
 * the two states, so the only evidence is the SHAPE of the file.
 *
 * WHY THE TYPESCRIPT AST AND NOT A REGEX. The first version of this detector
 * hand-rolled a template-literal scanner and reported 25 findings in two files,
 * every one of them false: a `${...}` interpolation may contain a NESTED
 * template literal, and a flat depth counter mistakes the inner backtick for the
 * outer closer, after which the span swallows the rest of the file. Chasing that
 * edge case is how the instrument stays wrong; the compiler already knows.
 *
 * ---- gate ----
 * step: Controls are not written inside string literals
 * needs: none
 * selftest: true
 * lane: quality-code
 * why: A `check(...)` inside a template literal is inert -- it prints nothing,
 *      asserts nothing, and leaves the selftest exit code unchanged, so no run
 *      can tell it from a healthy control.
 * ---- end gate ----
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const SCAN_DIR = 'scripts';
// THE ONE LIST. It was declared here and never read: the matcher below spelled the same
// four names again inside its own regex literal, so the repository held two copies of the
// control-name set and nothing kept them equal. `check:lint:tooling` reported the unused
// constant, which is the visible half; the invisible half is that adding a fifth control
// name here would have changed nothing at all. Deleting the constant would have removed
// the symptom and left the duplication, so the regex is derived from it instead.
const CONTROL_NAMES = new Set(['check', 'ck', 'control', 'assertEq']);
const CONTROL_ALTERNATION = [...CONTROL_NAMES].join('|');
const MIN_SUBJECTS = 40;

export interface Finding {
  file: string;
  line: number;
  name: string;
}

/**
 * The text of a template literal is NOT parsed into a syntax tree, so a
 * `check(...)` sitting in it is never a CallExpression at all. Detection is
 * therefore textual WITHIN the literal's text spans, which the compiler hands
 * over exactly -- no hand-rolled nesting.
 */
export function controlTextInTemplates(source: string, fileName = 'x.ts'): Finding[] {
  const sf = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const found: Finding[] = [];
  const re = new RegExp(`\\b(${CONTROL_ALTERNATION})\\s*\\(\\s*['"]`, 'g');
  const scanText = (text: string, start: number) => {
    for (const m of text.matchAll(re)) {
      found.push({
        file: fileName,
        line: sf.getLineAndCharacterOfPosition(start + (m.index ?? 0)).line + 1,
        name: m[1],
      });
    }
  };
  const visit = (node: ts.Node): void => {
    if (ts.isNoSubstitutionTemplateLiteral(node)) {
      scanText(node.text, node.getStart(sf) + 1);
    } else if (ts.isTemplateHead(node) || ts.isTemplateMiddle(node) || ts.isTemplateTail(node)) {
      scanText(node.text, node.getStart(sf) + 1);
    }
    ts.forEachChild(node, visit);
  };
  ts.forEachChild(sf, visit);
  return found;
}

export function scanFile(source: string, fileName: string): Finding[] {
  return [...controlTextInTemplates(source, fileName)].sort((a, b) => a.line - b.line);
}

function selftest(): boolean {
  let bad = 0;
  const check = (label: string, ok: boolean, detail = '') => {
    if (ok) console.log(`  PASS  ${label}`);
    else {
      console.error(`  FAIL  ${label}${detail ? `\n        ${detail}` : ''}`);
      bad++;
    }
  };

  const CLEAN = [
    'const F = `const C = () => {',
    '  return <div/>;',
    '};`;',
    "check('live', true);",
  ].join('\n');
  check('a control OUTSIDE every literal is clean', scanFile(CLEAN, 'a.ts').length === 0);

  const SPLICED = [
    'const F = `const C = () => {',
    "  check('spliced into a fixture', true);",
    '  return <div/>;',
    '};`;',
  ].join('\n');
  const spliced = scanFile(SPLICED, 'b.ts');
  check(
    'a control INSIDE a template literal is reported',
    spliced.length === 1,
    JSON.stringify(spliced)
  );
  check('and it is reported at the right line', spliced[0]?.line === 2, JSON.stringify(spliced));

  // THE CASE THE REGEX VERSION GOT WRONG, and the reason this uses the compiler.
  const NESTED = [
    'const log = (ok: boolean, label: string) =>',
    '  console.log(`  ${ok ? `${1}PASS` : `${2}FAIL`}  ${label}`);',
    "check('a control after a NESTED template is still live', true);",
  ].join('\n');
  check(
    'a nested `${`...`}` does not swallow the rest of the file',
    scanFile(NESTED, 'c.ts').length === 0,
    JSON.stringify(scanFile(NESTED, 'c.ts'))
  );

  // AN INTERPOLATION IS CODE, and this control caught the detector's own first
  // version doing the wrong thing. That version also walked for CallExpressions
  // "inside a template" -- but literal TEXT is never parsed into a call, so the
  // only CallExpressions a template contains are the live ones in its `${}`.
  // It flagged them, and this control failed until that half was deleted.
  const INTERP = ["const s = `${check('called from an interpolation', true)}`;"].join('\n');
  check(
    'a control CALLED from an interpolation is not reported',
    scanFile(INTERP, 'd.ts').length === 0,
    JSON.stringify(scanFile(INTERP, 'd.ts'))
  );

  // A quoted (non-template) string holding the same text: also inert, but this
  // detector deliberately does NOT claim it -- one-line strings are not where
  // fixtures live, and claiming them would flag prose in error messages.
  check(
    'a single-quoted string is out of scope, stated rather than silently missed',
    scanFile("const m = 'see check(\\'x\\', true)';", 'e.ts').length === 0
  );

  if (bad > 0) {
    console.error(`\n✗ ${bad} self-test failure(s)`);
    return false;
  }
  console.log(`✓ control-in-string detector: 6 control(s) passed`);
  return true;
}

function main(argv: string[]): number {
  if (argv.includes('--selftest')) return selftest() ? 0 : 1;
  if (!selftest()) {
    console.error('✗ CONTROL FAILED: refusing to report on the tree.');
    return 1;
  }
  const dir = path.join(REPO_ROOT, SCAN_DIR);
  // RECURSIVE, and that is not a style choice. This was a flat readdirSync of
  // `scripts/`, whose subject was the 125 check-*.ts sitting there. W9 P2 moved
  // them one directory down to scripts/gates/ and the corpus fell from 136 to 11,
  // which the MIN_SUBJECTS floor below caught as a refusal rather than reporting
  // a clean tree over eleven files. A depth-1 enumerator answers a question about
  // a directory; the question this gate asks is about the tooling TREE, so it
  // walks, and the next move costs it nothing.
  const files = fs
    .readdirSync(dir, { recursive: true, encoding: 'utf-8' })
    .filter((f) => f.endsWith('.ts'))
    .map((f) => path.join(dir, f));
  if (files.length < MIN_SUBJECTS) {
    console.error(
      `✗ Refusing to run: only ${files.length} .ts file(s) under ${dir}, below the floor of ` +
        `${MIN_SUBJECTS}. Zero findings over an empty glob reads exactly like a clean tree.`
    );
    return 1;
  }
  const findings: Finding[] = [];
  for (const f of files) {
    findings.push(...scanFile(fs.readFileSync(f, 'utf-8'), path.relative(REPO_ROOT, f)));
  }
  if (findings.length > 0) {
    console.error(`✗ ${findings.length} control(s) written inside a string literal:`);
    for (const f of findings) console.error(`    ${f.file}:${f.line}  ${f.name}(...)`);
    console.error(
      '  Such a control prints nothing, asserts nothing, and leaves the exit code unchanged.\n' +
        '  Move it out of the fixture, above the function’s verdict.'
    );
    return 1;
  }
  console.log(`✓ ${files.length} file(s): no control is written inside a string literal`);
  return 0;
}

process.exit(main(process.argv.slice(2)));

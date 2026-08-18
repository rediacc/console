#!/usr/bin/env npx tsx
/**
 * A public method on a singleton service must have a caller.
 *
 * WHY THIS EXISTS. knip cannot see this. Its issue types are files,
 * dependencies, unlisted, unresolved, exports, nsExports, types, nsTypes,
 * enumMembers, namespaceMembers, duplicates, catalog, catalogReferences and
 * cycles -- there is no class-member type, so an unused method on an exported
 * singleton is invisible to it BY CONSTRUCTION. That was verified rather than
 * assumed: a planted unused public method left `npm run lint:unused` at exit 0.
 *
 * WHAT IT COST. One dead method (`storageBrowserService.isAvailable`) was found
 * by hand. Sweeping the class then turned up nine more across five services,
 * including one whose implementation swallowed the only error message a user
 * would need. Dead service methods are not merely clutter: they read as
 * supported API to the next author, who calls them.
 *
 * THE RULE. For every `export const x = new SomeClass()`, each non-private
 * method must be referenced as `.name(` somewhere outside its own file, or be
 * reached internally via `this.name(` (in which case it should be private, and
 * this gate says so rather than demanding deletion).
 *
 * WHAT IT DOES NOT COVER, stated plainly because the gap decides how much this
 * verdict is worth:
 *  - Dynamic dispatch (`svc[name]()`) is not resolved. A method only ever called
 *    that way reads as dead here.
 *  - It is name-based, so two classes sharing a method name shield each other.
 *    That makes it CONSERVATIVE: it under-reports, never invents a victim.
 *  - Interface conformance is not modelled. A method existing solely to satisfy
 *    an interface will be reported; if that happens, the honest fix is usually
 *    that the interface member is dead too.
 */

import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const REPO = path.resolve(import.meta.dirname, '..');
const RED = '\x1b[0;31m';
const GREEN = '\x1b[0;32m';
const NC = '\x1b[0m';

const SINGLETON = /export\s+const\s+\w+\s*=\s*new\s+(\w+)\s*\(/g;
// Two-space indent = class body member. Deliberately not matching deeper
// indents, which are nested functions rather than methods.
const METHOD = /^ {2}(private\s+|protected\s+)?(?:static\s+)?(?:async\s+)?(\w+)\s*\(/gm;
const NOT_A_METHOD = new Set([
  'constructor',
  'if',
  'for',
  'while',
  'switch',
  'catch',
  'return',
  'get',
  'set',
]);

function tracked(): string[] {
  return execFileSync('git', ['ls-files', '--', '*.ts', '*.tsx', '*.js', '*.mjs', '*.astro'], {
    cwd: REPO,
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  })
    .split('\n')
    .filter(Boolean);
}

export interface Finding {
  file: string;
  method: string;
  kind: 'dead' | 'should-be-private';
}

export function audit(files: string[], read: (f: string) => string): [Finding[], number] {
  const sources = new Map<string, string>();
  for (const f of files) {
    try {
      sources.set(f, read(f));
    } catch {
      /* unreadable files are not evidence of anything */
    }
  }

  const findings: Finding[] = [];
  let examined = 0;

  for (const [file, src] of sources) {
    // Only classes DEFINED here and instantiated here as an exported
    // singleton. Two earlier bugs made this necessary: `new Set([...])`
    // satisfied a bare `= new X(` test, and a string literal containing
    // "export const c = new SFTPClient();" made a lint fixture look like a
    // service. Requiring `class <Name> {` in the same file kills both.
    const classNames = new Set<string>();
    for (const s of src.matchAll(new RegExp(SINGLETON.source, 'g'))) {
      const cls = s[1];
      if (new RegExp(`(?:^|\\n)\\s*(?:export\\s+)?(?:abstract\\s+)?class\\s+${cls}\\b`).test(src)) {
        classNames.add(cls);
      }
    }
    if (!classNames.size) continue;

    for (const m of src.matchAll(new RegExp(METHOD.source, 'gm'))) {
      const [, modifier, name] = m;
      if (modifier || NOT_A_METHOD.has(name)) continue;
      // A DEFINITION, not a call. `  walk(tree, []);` is two spaces deep and
      // looks identical to a method head until you require a brace body after
      // the parameter list -- which is what reported two nested arrow-function
      // helpers as dead service methods.
      const rest = src.slice(m.index);
      if (!/^\w+\s*\([^;]*?\)\s*(?::[^;{]+?)?\{/s.test(rest.replace(/^ {2}/, ''))) continue;
      examined++;
      const call = new RegExp(`[.\\[]['"\`]?${name}\\b`);
      let external = false;
      for (const [other, text] of sources) {
        if (other === file) continue;
        if (call.test(text)) {
          external = true;
          break;
        }
      }
      if (external) continue;
      const internal = new RegExp(`this\\.${name}\\s*\\(`).test(src);
      findings.push({ file, method: name, kind: internal ? 'should-be-private' : 'dead' });
    }
  }
  return [findings, examined];
}

function runControls(): string[] {
  const failures: string[] = [];
  const fake = new Map<string, string>([
    [
      'svc.ts',
      [
        'class Thing {',
        '  used() { return 1; }',
        '  deadOne() { return 2; }',
        '  onlyInternal() { return 3; }',
        '  private hidden() { return 4; }',
        '  run() { return this.onlyInternal(); }',
        '}',
        'export const thingService = new Thing();',
      ].join('\n'),
    ],
    ['caller.ts', 'thingService.used();\nthingService.run();'],
    ['plain.ts', 'class NotAService { alsoDead() { return 1; } }'],
  ]);
  const read = (f: string) => fake.get(f) ?? '';
  const [found] = audit([...fake.keys()], read);
  const byName = new Map(found.map((f) => [f.method, f.kind]));

  if (byName.get('deadOne') !== 'dead') failures.push('an uncalled public method was not reported');
  if (byName.get('onlyInternal') !== 'should-be-private')
    failures.push('a this-only method was not reported as should-be-private');
  if (byName.has('used')) failures.push('a called method was reported');
  if (byName.has('hidden')) failures.push('an already-private method was reported');
  if (byName.has('alsoDead'))
    failures.push('a class that is not an exported singleton was inspected');
  return failures;
}

function main(): number {
  console.log('Singleton services: does every public method have a caller?');
  console.log('='.repeat(58));

  const controlFailures = runControls();
  if (controlFailures.length) {
    for (const f of controlFailures) console.log(`${RED}x${NC} control: ${f}`);
    console.log(
      `${RED}x${NC} the rule itself is broken, so no verdict it produces means anything.`
    );
    return 1;
  }
  console.log(
    `${GREEN}v${NC} control fired: dead and this-only caught; called and private are not`
  );

  const files = tracked();
  if (!files.length) {
    console.log(
      `${RED}x${NC} no tracked source files; checking nothing exits 0 exactly like checking everything`
    );
    return 1;
  }

  const [findings, examined] = audit(files, (f) => readFileSync(path.join(REPO, f), 'utf8'));

  if (examined < 20) {
    console.log(
      `${RED}x${NC} only ${examined} public method(s) examined; the rule has been unhooked`
    );
    return 1;
  }

  if (findings.length) {
    for (const f of findings) {
      const why =
        f.kind === 'dead'
          ? 'has no caller anywhere; delete it'
          : 'is only reached via this.*; mark it private';
      console.log(`${RED}x${NC} ${f.file}: ${f.method}() ${why}`);
    }
    console.log();
    console.log(
      `${RED}x${NC} ${findings.length} singleton-service method(s) with no external use.`
    );
    console.log('  knip cannot see class members, so nothing else in the suite catches these.');
    console.log('  A dead method reads as supported API to the next author, who then calls it.');
    return 1;
  }

  console.log(
    `${GREEN}v${NC} ${examined} public method(s) across ${files.length} tracked file(s): every one has a caller`
  );
  return 0;
}

process.exit(main());

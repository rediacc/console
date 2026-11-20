/**
 * check:ci-worklist-path-resolution -- every hook resolves the worklist the
 * same way, through the shared resolver.
 *
 * WHY THIS EXISTS, measured 2026-09-04. `--migrate` resolved its path as
 * `worklist_for(project_root(project_start()))`. That doubled form lands on the
 * REPOSITORY root and ignores CLAUDE_PROJECT_DIR, so under the test harness the
 * verb read its items from the fixture store (which a different env var does
 * redirect) while looking for `.lastevent-*` beside the OPERATOR'S REAL
 * worklist. It found none, concluded a demonstrably live session was idle, and
 * migrated its work -- precisely the outcome the liveness refusal exists to
 * prevent. Sweeping the class found two more: `--publish` and `--epic`
 * resolved from `os.getcwd()` alone, which skips the CLAUDE_PROJECT_DIR rung
 * entirely and, in a tree with repos inside the repo (private/renet,
 * private/growth), walks into a nested one and reads ITS store. That nested-repo
 * incident is the reason project_start() exists at all.
 *
 * WHAT MADE IT INVISIBLE. Each site passed its own tests, because each test ran
 * it the one way that happened to work. Nothing compared the sites to each
 * other, so three spellings of "find the worklist" coexisted and only the
 * unlucky one was ever wrong. A per-site test cannot see that; a cross-site
 * rule can.
 *
 * THE RULE. In .claude/hooks, `worklist_for(...)` takes `project_start(...)`
 * and nothing else. Not `os.getcwd()`, not `project_root(project_start())` --
 * project_start's own ladder already ends at cwd, so the shared form is a
 * superset of both and never resolves worse.
 *
 * THE LANDING PIN (agent/plans/PLAN-two-track-merge-dev.md, box LT14). The
 * landing tree maps to the main checkout for the store, STATE.md and the
 * TMPDIR sidecars, through ONE redirect in wl_core.project_root and its
 * self-contained twin in worklist.py. A twin that loses the redirect points
 * `--path` and the append modes at a different store than the hook reads, and
 * every call site above still passes this gate's first rule. So the pin is
 * structural: project_root calls landing_main, _local_worklist_path calls
 * _local_landing_main, and both readers name the record file the landing
 * verb writes. test-landing-store.py is the behavioural half.
 *
 * ---- gate ----
 * step: Worklist path resolution
 * needs: node
 * selftest: true
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
const HOOKS = path.join(ROOT, '.claude', 'hooks');

/** The one sanctioned argument. `project_start()` and `project_start(event)`
 *  and `project_start({...})` all qualify; anything else does not. */
const OK = /worklist_for\(\s*(?:[A-Za-z_][A-Za-z0-9_]*\.)?project_start\(/;
/** Its own definition and self-contained twin are not call sites. */
const DEFINITION = /def\s+(worklist_for|_local_worklist_path)\b/;
/** Floor for the corpus: see the VACUOUS refusal in main(). */
const MIN_CALL_SITES = 10;

interface Finding {
  file: string;
  line: number;
  text: string;
  why: string;
}

function pyFiles(dir: string): string[] {
  const out: string[] = [];
  const walk = (d: string): void => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name.endsWith('.py')) out.push(p);
    }
  };
  walk(dir);
  return out.sort((a, b) => Number(a > b) - Number(a < b));
}

/**
 * A bare identifier is fine when it PROVABLY holds project_start's output:
 * either this file binds it from project_start, or it is a parameter of some
 * function here (in which case the caller is judged by this same gate, since
 * every hook file is scanned). Demanding the call be written inline would
 * report `worklist_for(start)` two lines under `start = C.project_start(...)`
 * -- a guard whose usual outcome is a false positive is one people route
 * around, which is the failure mode this repo has written down.
 */
function boundFromProjectStart(src: string, ident: string): boolean {
  const esc = ident.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const assigned = new RegExp(`\\b${esc}\\s*=\\s*(?:[A-Za-z_][A-Za-z0-9_]*\\.)?project_start\\(`);
  const param = new RegExp(`def\\s+[A-Za-z_][A-Za-z0-9_]*\\([^)]*\\b${esc}\\b[^)]*\\)`, 's');
  return assigned.test(src) || param.test(src);
}

function scan(files: string[]): Finding[] {
  const out: Finding[] = [];
  for (const f of files) {
    const src = fs.readFileSync(f, 'utf-8');
    const lines = src.split('\n');
    lines.forEach((line, i) => {
      if (!/worklist_for\s*\(/.test(line)) return;
      if (DEFINITION.test(line)) return;
      if (line.trimStart().startsWith('#')) return; // prose about the rule
      if (OK.test(line)) return;
      const bare = /worklist_for\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)/.exec(line);
      if (bare && boundFromProjectStart(src, bare[1] as string)) return;
      const why = /os\.getcwd\(\)/.test(line)
        ? 'resolves from cwd, skipping the CLAUDE_PROJECT_DIR rung -- in a tree with nested repos this reads the WRONG store'
        : /project_root\s*\(/.test(line)
          ? 'double-resolves through project_root, which lands on the repository root and ignores CLAUDE_PROJECT_DIR'
          : 'does not pass project_start(), so it does not use the shared ladder';
      out.push({ file: path.relative(ROOT, f), line: i + 1, text: line.trim().slice(0, 100), why });
    });
  }
  return out;
}

/** The record file commit_policy.write_landing_record writes in the common git dir. */
const LANDING_RECORD = 'rediacc-landing.json';

/** The body of top-level `def name(` in `src`, through the line before the next top-level statement; "" when absent. */
function pyBody(src: string, name: string): string {
  const lines = src.split('\n');
  const start = lines.findIndex((l) => l.startsWith(`def ${name}(`));
  if (start < 0) return '';
  let end = start + 1;
  while (end < lines.length && (lines[end] === '' || /^\s/.test(lines[end] as string))) end++;
  return lines.slice(start, end).join('\n');
}

/** Each missing piece of the landing mapping, named; empty when both resolvers carry it. */
function landingPins(core: string, cli: string): string[] {
  const out: string[] = [];
  if (!/\blanding_main\(/.test(pyBody(core, 'project_root'))) {
    out.push('wl_core.project_root does not call landing_main: the landing tree would keep its own store');
  }
  if (!pyBody(core, 'landing_main') || !core.includes(`"${LANDING_RECORD}"`)) {
    out.push(`wl_core has no landing_main reading ${LANDING_RECORD}`);
  }
  if (!/\b_local_landing_main\(/.test(pyBody(cli, '_local_worklist_path'))) {
    out.push(
      "worklist.py's _local_worklist_path does not call _local_landing_main: --path would name a different store than the hook"
    );
  }
  if (!pyBody(cli, '_local_landing_main') || !cli.includes(`"${LANDING_RECORD}"`)) {
    out.push(`worklist.py has no _local_landing_main twin reading ${LANDING_RECORD}`);
  }
  return out;
}

function selftest(): void {
  const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR ?? '/tmp', 'wlpr-'));
  const w = (name: string, body: string): string => {
    const p = path.join(tmp, name);
    fs.writeFileSync(p, body);
    return p;
  };

  const good = w('good.py', 'def f():\n    wl = C.worklist_for(C.project_start())\n');
  if (scan([good]).length !== 0) {
    console.error('  FAIL  CONTROL: the sanctioned form was reported');
    process.exit(1);
  }
  console.log('  PASS  CONTROL: worklist_for(project_start()) is accepted');

  const evt = w('evt.py', 'def f(event):\n    wl = C.worklist_for(C.project_start(event))\n');
  if (scan([evt]).length !== 0) {
    console.error('  FAIL  CONTROL: project_start(event) was reported');
    process.exit(1);
  }
  console.log('  PASS  CONTROL: project_start(event) is accepted too');

  // PLANT 1: the exact --migrate defect.
  const doubled = w(
    'doubled.py',
    'def f():\n    wl = C.worklist_for(C.project_root(C.project_start()))\n'
  );
  const d = scan([doubled]);
  if (d.length !== 1 || !d[0]?.why.includes('project_root')) {
    console.error(`  FAIL  the doubled form was not caught: ${JSON.stringify(d)}`);
    process.exit(1);
  }
  console.log('  PASS  the doubled project_root form is caught, and named');

  // PLANT 2: the --publish/--epic defect.
  const cwd = w('cwd.py', 'def f():\n    wl = C.worklist_for(os.getcwd())\n');
  const c = scan([cwd]);
  if (c.length !== 1 || !c[0]?.why.includes('cwd')) {
    console.error(`  FAIL  the getcwd form was not caught: ${JSON.stringify(c)}`);
    process.exit(1);
  }
  console.log('  PASS  the getcwd form is caught, and named');

  // The definition itself, and prose about the rule, must not be policed.
  const def = w(
    'def.py',
    'def worklist_for(start):\n    return start\n# use worklist_for(os.getcwd()) is WRONG, says this comment\n'
  );
  if (scan([def]).length !== 0) {
    console.error('  FAIL  CONTROL: the definition or a comment was policed');
    process.exit(1);
  }
  console.log('  PASS  CONTROL: the definition and prose about it are out of scope');

  const core = `LANDING_RECORD_NAME = "${LANDING_RECORD}"\n\n\ndef project_root(start):\n    tree = checkout_root(start)\n    return landing_main(tree) or tree\n\n\ndef landing_main(tree):\n    return None\n`;
  const cli = `def _local_landing_main(tree):\n    return tree / ".git" / "${LANDING_RECORD}"\n\n\ndef _local_worklist_path(start):\n    root = _local_landing_main(start) or start\n    return root\n`;
  const ok = landingPins(core, cli);
  if (ok.length !== 0) {
    console.error(`  FAIL  CONTROL: the landing mapping was reported: ${JSON.stringify(ok)}`);
    process.exit(1);
  }
  console.log('  PASS  CONTROL: a resolver pair carrying the landing redirect is accepted');
  // PLANT 3: the twin loses its redirect while the hook keeps it.
  const lost = landingPins(core, cli.replace('root = _local_landing_main(start) or start', 'root = start'));
  if (lost.length !== 1 || !lost[0]?.includes('_local_worklist_path')) {
    console.error(`  FAIL  a twin without the landing redirect was not caught: ${JSON.stringify(lost)}`);
    process.exit(1);
  }
  console.log('  PASS  a twin without the landing redirect is caught, and named');
  // PLANT 4: project_root loses its redirect.
  const bare = landingPins(core.replace('return landing_main(tree) or tree', 'return tree'), cli);
  if (bare.length !== 1 || !bare[0]?.includes('project_root')) {
    console.error(`  FAIL  a project_root without the landing redirect was not caught: ${JSON.stringify(bare)}`);
    process.exit(1);
  }
  console.log('  PASS  a project_root without the landing redirect is caught, and named');
  fs.rmSync(tmp, { recursive: true, force: true });
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    selftest();
    console.log('check-worklist-path-resolution: selftest ok (8 controls)');
    return;
  }
  if (!fs.existsSync(HOOKS)) {
    console.error(`✗ ${path.relative(ROOT, HOOKS)} does not exist, so this gate checked NOTHING`);
    process.exit(1);
  }
  const files = pyFiles(HOOKS);
  if (files.length === 0) {
    console.error('✗ no python files under .claude/hooks; refusing a verdict');
    process.exit(1);
  }
  // ANTI-VACUITY: if nothing resolves a worklist at all, the matcher is broken rather than the tree being clean. Zero call sites must FAIL.
  const sites = files.reduce(
    (n, f) => n + (fs.readFileSync(f, 'utf-8').match(/worklist_for\s*\(/g) ?? []).length,
    0
  );
  // A NAMED FLOOR, not merely "> 0". Zero is the obvious collapse; the quiet one
  // is a matcher that still finds three call sites after a rename silently took the other seventeen out of view. The floor is well under the real count (20 at the time of writing) so ordinary churn does not trip it, and any drop past it says VACUOUS rather than printing a tick.
  if (sites < MIN_CALL_SITES) {
    console.error(
      `✗ VACUOUS: found only ${sites} worklist_for() call site(s), below the floor of ` +
        `${MIN_CALL_SITES}. The matcher is broken, not the tree.`
    );
    process.exit(1);
  }

  const pins = landingPins(
    fs.readFileSync(path.join(HOOKS, 'stop', 'wl_core.py'), 'utf-8'),
    fs.readFileSync(path.join(HOOKS, 'stop', 'worklist.py'), 'utf-8')
  );
  if (pins.length > 0) {
    console.error(`✗ the landing tree's store mapping is incomplete (PLAN-two-track-merge-dev LT14):\n`);
    for (const why of pins) console.error(`  ${why}`);
    process.exit(1);
  }

  const findings = scan(files);
  if (findings.length > 0) {
    console.error(
      `✗ ${findings.length} worklist path resolution(s) bypassing the shared ladder:\n`
    );
    for (const f of findings) {
      console.error(`  ${f.file}:${f.line}  ${f.text}`);
      console.error(`      ${f.why}`);
    }
    console.error(
      "\n  Use C.worklist_for(C.project_start()) -- project_start()'s ladder ENDS at cwd,\n" +
        '  so the shared form is a superset of every other spelling and never resolves\n' +
        '  worse. On 2026-09-04 the doubled form made --migrate read a fixture store while\n' +
        "  checking liveness against the real one, so it moved a LIVE session's work."
    );
    process.exit(1);
  }
  console.log(
    `✓ worklist path resolution: ${sites} call site(s) across ${files.length} hook file(s), ` +
      'all through project_start(); the landing redirect is pinned in both resolvers'
  );
}

main();

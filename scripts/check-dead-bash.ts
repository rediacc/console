#!/usr/bin/env tsx
/**
 * check-dead-bash.ts — unreferenced shell functions and orphaned shell files.
 *
 * Go has `deadcode` (private/renet/.ci/scripts/quality/deadcode.sh) and TypeScript
 * has knip. Bash had nothing, across 222 tracked .sh files and ~509 functions —
 * so every orphan removed so far was found by hand.
 *
 * TWO INDEPENDENT CHECKS
 *   functions: a `name() {` definition whose name appears nowhere else.
 *   files:     a .sh whose basename is never mentioned by any other tracked file.
 *
 * They are independent on purpose: scripts/dev/linode-cluster-validation.sh is a
 * genuinely orphaned FILE whose functions are nonetheless live (dispatched via
 * "phase_$p"). Merging the checks would hide one behind the other.
 *
 * WHY AN ALLOWLIST AND NOT A HEURISTIC
 * A naive detector reports 54 orphan files, ~85% of them false, for two reasons:
 *   - glob discovery: .ci/scripts/test/run-all.sh expands PATTERN="test-*.sh",
 *     and run.sh iterates "$tutorials_dir"/tutorial-*.sh — those files are never
 *     named individually.
 *   - dynamic dispatch: "phase_$p" builds a function name at runtime.
 * Parsing those two shapes would work today and silently miss `find -exec`,
 * `xargs`, or a glob built from a variable — under-reporting, which is exactly
 * how dead code survives. `.dead-bash-allowlist` states the discovery mechanism
 * explicitly instead, is BLOCKER-gated, and is itself probed by
 * scripts/check-suppression-liveness.ts so it cannot rot.
 *
 * Usage:
 *   npx tsx scripts/check-dead-bash.ts
 *   npx tsx scripts/check-dead-bash.ts --json
 *
 * Env:
 *   DEAD_BASH_ROOT   test seam — treat this directory as the repo root
 *
 * Exit 0 clean; 1 on findings or on a vacuous run (no shell files discovered).
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseBlockeredList, verifyAllBlockers } from './lib/blocker-validator.js';
import { DIM, GREEN, NC, RED, YELLOW } from './utils/console.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = process.env.DEAD_BASH_ROOT || path.join(__dirname, '..');
const ALLOWLIST = path.join(ROOT, '.dead-bash-allowlist');

/** The two real definition forms: `name() {` and `function name {`. */
const DEF_STRICT = /^\s*(?:([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\)\s*\{|function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\{)/;

interface Finding {
  kind: 'function' | 'file';
  name: string;
  file: string;
  line: number;
  why: string;
  fix: string;
}

/**
 * Every file git would consider part of the working tree: tracked PLUS
 * untracked-but-not-ignored.
 *
 * `--others --exclude-standard` is load-bearing, not tidiness. With plain
 * `ls-files` a brand-new, not-yet-committed script is invisible — so a change
 * that ADDS a caller for an existing script reports that script as orphaned,
 * which is precisely the shape of a normal refactor and would make this gate
 * fire on correct work.
 */
function trackedFiles(root: string): string[] {
  try {
    return execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard'], {
      cwd: root,
      encoding: 'utf-8',
      maxBuffer: 64e6,
      // A fixture root is not a git checkout; fall through to the walk below
      // without spraying "fatal: not a git repository" onto stderr.
      stdio: ['ignore', 'pipe', 'ignore'],
    })
      .split('\n')
      .filter(Boolean)
      .filter((f) => fs.existsSync(path.join(root, f)));
  } catch {
    // Not a git checkout (the gate-test fixtures are not): walk instead.
    const out: string[] = [];
    const walk = (dir: string): void => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        if (e.name === '.git' || e.name === 'node_modules') continue;
        const p = path.join(dir, e.name);
        if (e.isDirectory()) walk(p);
        else out.push(path.relative(root, p));
      }
    };
    walk(root);
    return out;
  }
}

/**
 * Which tracked files count as "text that could reference a script".
 *
 * Tested against the BASENAME, not the path: an earlier version anchored
 * /^Dockerfile/ against the repo-relative path, so `.devcontainer/Dockerfile`
 * never matched and every script it COPYs (download-extensions.sh,
 * start-*.sh) was falsely reported orphaned.
 */
const TEXTUAL =
  /(\.(sh|bash|ya?ml|json|jsonc|ts|tsx|js|cjs|mjs|md|txt|nix|toml|cfg|conf|ini|service|timer)$)|(^Dockerfile)|(^\.env)|(^Makefile)/;

interface Allowlist {
  globRoots: string[];
  dispatchPrefixes: string[];
  manualFiles: string[];
}

function loadAllowlist(): Allowlist {
  const out: Allowlist = { globRoots: [], dispatchPrefixes: [], manualFiles: [] };
  if (!fs.existsSync(ALLOWLIST)) return out;

  // Shared parser/validator — never a bespoke one. A private parser is how
  // .actions-upgrade-blocklist stayed outside the BLOCKER convention for so long.
  const entries = parseBlockeredList(ALLOWLIST);
  const failures = verifyAllBlockers(entries, ALLOWLIST);
  if (failures.length > 0) {
    console.error(`${RED}✗${NC} BLOCKER validation failed for ${ALLOWLIST}:`);
    for (const f of failures) console.error(f);
    console.error(
      `\n${RED}✗${NC} Each entry must say WHICH mechanism discovers it (a glob, a dynamic dispatch) and where.`
    );
    process.exit(1);
  }
  for (const { entry } of entries) {
    if (entry.startsWith('glob:')) out.globRoots.push(entry.slice(5));
    else if (entry.startsWith('dispatch:')) out.dispatchPrefixes.push(entry.slice(9));
    else if (entry.startsWith('manual:')) out.manualFiles.push(entry.slice(7));
    else {
      console.error(
        `${RED}✗${NC} ${ALLOWLIST}: entry "${entry}" must start with 'glob:' (a discovery directory), 'dispatch:' (a function-name prefix), or 'manual:' (an operator-invoked entrypoint).`
      );
      console.error(
        '  The allowlist covers DISCOVERY MECHANISMS only — never "this is dead but keep it".'
      );
      process.exit(1);
    }
  }
  return out;
}

function main(): void {
  const jsonMode = process.argv.includes('--json');
  const allow = loadAllowlist();
  const tracked = trackedFiles(ROOT);

  const shellFiles = tracked.filter((f) => f.endsWith('.sh'));
  // Anti-vacuity: no shell files means the tree moved and this gate is blind.
  if (shellFiles.length === 0) {
    console.error(
      `${RED}✗${NC} Found ZERO shell files under ${ROOT} — the layout changed and this gate is asserting nothing.`
    );
    process.exit(1);
  }

  // One corpus of every textual tracked file; both checks search it.
  const texts = new Map<string, string>();
  for (const f of tracked) {
    if (!TEXTUAL.test(path.basename(f))) continue;
    try {
      texts.set(f, fs.readFileSync(path.join(ROOT, f), 'utf-8'));
    } catch {
      /* unreadable: skip */
    }
  }
  const corpus = [...texts.values()].join('\n');

  const findings: Finding[] = [];

  // ---- unused functions --------------------------------------------------
  const defs = new Map<string, { file: string; line: number }[]>();
  for (const f of shellFiles) {
    const text = texts.get(f);
    if (!text) continue;
    text.split('\n').forEach((line, i) => {
      const m = line.match(DEF_STRICT);
      if (!m) return;
      const name = m[1] ?? m[2];
      if (!name) return;
      const list = defs.get(name) ?? [];
      list.push({ file: f, line: i + 1 });
      defs.set(name, list);
    });
  }

  for (const [name, locs] of defs) {
    if (allow.dispatchPrefixes.some((p) => name.startsWith(p))) continue;
    const re = new RegExp(`(?<![A-Za-z0-9_])${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![A-Za-z0-9_])`, 'g');
    const total = (corpus.match(re) ?? []).length;
    // Every definition line contains the name once; more than that means a use.
    if (total > locs.length) continue;
    findings.push({
      kind: 'function',
      name,
      file: locs[0].file,
      line: locs[0].line,
      why: `shell function "${name}" is defined but never called anywhere in the tracked tree`,
      fix: `delete ${name}() from ${locs[0].file}:${locs[0].line} — or, if it is reached by dynamic dispatch, add "dispatch:<prefix>" to .dead-bash-allowlist with a BLOCKER naming the dispatch site`,
    });
  }

  // ---- orphaned files ----------------------------------------------------
  for (const f of shellFiles) {
    if (allow.globRoots.some((g) => f.startsWith(g))) continue;
    if (allow.manualFiles.includes(f)) continue;
    const base = path.basename(f);
    let referenced = false;
    for (const [other, text] of texts) {
      if (other === f) continue;
      if (text.includes(base)) {
        referenced = true;
        break;
      }
    }
    if (referenced) continue;
    findings.push({
      kind: 'file',
      name: base,
      file: f,
      line: 1,
      why: `shell script "${f}" is never referenced by any other tracked file`,
      fix: `delete ${f} — or add "glob:<dir>/" (found by a glob) or "manual:${f}" (an operator runs it directly) to .dead-bash-allowlist, with a BLOCKER naming the discovery site or the workflow it serves`,
    });
  }

  if (jsonMode) {
    console.log(JSON.stringify({ findings, scanned: shellFiles.length }, null, 2));
    process.exit(findings.length > 0 ? 1 : 0);
  }

  console.log('Dead Bash');
  console.log('='.repeat(60));
  console.log(
    `scanned ${shellFiles.length} shell file(s), ${defs.size} function(s); ${findings.length} finding(s)` +
      `   ${DIM}(allowlist: ${allow.globRoots.length} glob, ${allow.dispatchPrefixes.length} dispatch, ${allow.manualFiles.length} manual)${NC}`
  );
  console.log('');

  if (findings.length === 0) {
    console.log(`${GREEN}✓${NC} no dead shell functions or orphaned shell scripts.`);
    return;
  }

  for (const f of findings.sort((a, b) => a.kind.localeCompare(b.kind) || a.file.localeCompare(b.file))) {
    const label = f.kind === 'function' ? `${YELLOW}FUNC${NC}` : `${YELLOW}FILE${NC}`;
    console.log(`${label}  ${f.file}:${f.line}  ${f.name}`);
    console.log(`  DEAD: ${f.why}`);
    console.log(`  FIX:  ${f.fix}`);
    console.log('');
    if (process.env.CI === 'true') {
      console.log(`::error file=${f.file},line=${f.line}::${f.name}: ${f.why}`);
    }
  }
  console.error(`${RED}✗${NC} ${findings.length} dead shell symbol(s) — remove them or declare the discovery mechanism.`);
  process.exit(1);
}

main();

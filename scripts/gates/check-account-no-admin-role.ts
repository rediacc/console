/**
 * check:ci-account-no-admin-role -- the account service has no `admin` USER
 * role: the privileged role is `root`.
 *
 * WHY THIS REPLACED A GREP. The old gate was an inline
 * `! grep -rn "enum.*customer.*admin" <files> 2>/dev/null`. Negated, with stderr
 * discarded, so a moved or renamed file (grep error, exit 2) read as a pass,
 * and a role enum wrapped over several lines (prettier does that once an enum
 * grows) never matched a single-line pattern. Both are green-without-running.
 *
 * THE RULE. In each target file, every enum array (`enum: [...]` for drizzle,
 * `z.enum([...])` for zod), wrapped or not, that holds `customer` (the user
 * role enum) must not also hold `admin`. Each file must contain at least one
 * such user-role enum, or the gate refuses: a file whose role enum was renamed
 * away would otherwise pass with nothing checked.
 *
 * ---- gate ----
 * step: Check no admin user role (must be root)
 * needs: node
 * selftest: true
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
export const TARGETS = ['private/account/src/db/schema.ts', 'private/account/src/types/user.ts'];

export interface EnumHit {
  line: number;
  values: string[];
}

/** Every `enum: [..]` / `enum([..])` array in `src`, wrapped or not. */
export function enumArrays(src: string): EnumHit[] {
  const out: EnumHit[] = [];
  const re = /\benum\s*(?::|\()\s*\[([^\]]*)\]/g;
  for (let m = re.exec(src); m; m = re.exec(src)) {
    const values = [...(m[1] ?? '').matchAll(/['"`]([^'"`]*)['"`]/g)].map((v) => v[1] as string);
    out.push({ line: src.slice(0, m.index).split('\n').length, values });
  }
  return out;
}

export interface Verdict {
  userEnums: number;
  bad: EnumHit[];
}

export function judge(src: string): Verdict {
  const user = enumArrays(src).filter((e) => e.values.includes('customer'));
  return { userEnums: user.length, bad: user.filter((e) => e.values.includes('admin')) };
}

function selftest(): void {
  const fail = (m: string): never => {
    console.error(`  FAIL  ${m}`);
    process.exit(1);
  };
  const clean = "role: text('role', { enum: ['customer', 'root'] })\nz.enum(['customer', 'root'])";
  const c = judge(clean);
  if (c.userEnums !== 2 || c.bad.length !== 0) fail(`CONTROL: clean enums misjudged ${JSON.stringify(c)}`);
  console.log('  PASS  CONTROL: customer/root enums are accepted and counted');

  const other = "role: text('role', { enum: ['owner', 'admin', 'member'] })";
  const o = judge(other);
  if (o.userEnums !== 0 || o.bad.length !== 0) fail('CONTROL: an org-role enum with admin was policed');
  console.log('  PASS  CONTROL: admin in a non-user enum is out of scope');

  const single = "role: text('role', { enum: ['customer', 'admin'] })";
  if (judge(single).bad.length !== 1) fail('single-line plant not caught');
  console.log('  PASS  single-line plant is caught');

  const reorder = "z.enum(['admin', 'customer'])";
  if (judge(reorder).bad.length !== 1) fail('reordered plant not caught');
  console.log('  PASS  reordered plant is caught');

  const wrapped = "role: text('role', {\n  enum: [\n    'customer',\n    'root',\n    'admin',\n  ],\n})";
  const w = judge(wrapped);
  if (w.bad.length !== 1 || w.bad[0]?.line !== 2) fail(`wrapped plant not caught ${JSON.stringify(w)}`);
  console.log('  PASS  wrapped multi-line plant is caught');

  if (judge('const x = 1;').userEnums !== 0) fail('no-enum source counted an enum');
  console.log('  PASS  a file with no user-role enum reports zero (main() refuses it)');
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    selftest();
    console.log('check-account-no-admin-role: selftest ok (6 controls)');
    return;
  }
  let checked = 0;
  let failed = false;
  for (const rel of TARGETS) {
    const p = path.join(ROOT, rel);
    if (!fs.existsSync(p)) {
      console.error(`✗ ${rel} does not exist, so the admin-role rule checked NOTHING there. Update TARGETS if it moved.`);
      failed = true;
      continue;
    }
    const v = judge(fs.readFileSync(p, 'utf-8'));
    if (v.userEnums === 0) {
      console.error(`✗ ${rel} holds no enum containing 'customer'; the user-role enum moved or was renamed, so this gate sees nothing. Update TARGETS.`);
      failed = true;
      continue;
    }
    checked += v.userEnums;
    for (const b of v.bad) {
      console.error(`✗ ${rel}:${b.line} user-role enum [${b.values.join(', ')}] contains 'admin'. The privileged user role is 'root'; remove 'admin' (org and partner roles are separate enums).`);
      failed = true;
    }
  }
  if (failed) process.exit(1);
  console.log(`✓ no admin user role: ${checked} user-role enum(s) across ${TARGETS.length} file(s), none contain 'admin'`);
}

if (import.meta.url === `file://${process.argv[1]}`) main();

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
 * needs: node, submodules
 * lane: quality-go
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

const quotedValues = (body: string): string[] =>
  [...body.matchAll(/['"`]([^'"`]*)['"`]/g)].map((v) => v[1] as string);

/** Every `const NAME = [..]` array in `src` (an `as const` suffix or a type annotation allowed), by name. */
function constArrays(src: string): Map<string, string[]> {
  const out = new Map<string, string[]>();
  const re = /\b(?:const|let)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*\[([^\]]*)\]/g;
  for (let m = re.exec(src); m; m = re.exec(src)) out.set(m[1] as string, quotedValues(m[2] ?? ''));
  return out;
}

/**
 * Every enum in `src`, wrapped or not: an `enum: [..]` / `enum([..])` literal, or an
 * `enum(NAME)` / `enum: NAME` reference resolved through a same-file `const NAME = [..]`
 * (review 5fe6ca54.3). A reference that does not resolve is returned in `unresolved`.
 */
export function enumArrays(src: string): EnumHit[] & { unresolved?: EnumHit[] } {
  const out: EnumHit[] & { unresolved?: EnumHit[] } = [];
  const unresolved: EnumHit[] = [];
  const consts = constArrays(src);
  const lineOf = (index: number): number => src.slice(0, index).split('\n').length;
  const literal = /\benum\s*(?::|\()\s*\[([^\]]*)\]/g;
  for (let m = literal.exec(src); m; m = literal.exec(src)) {
    out.push({ line: lineOf(m.index), values: quotedValues(m[1] ?? '') });
  }
  const reference = /\benum\s*(?::|\()\s*([A-Za-z_$][\w$]*)\b/g;
  for (let m = reference.exec(src); m; m = reference.exec(src)) {
    const values = consts.get(m[1] as string);
    if (values) out.push({ line: lineOf(m.index), values });
    else unresolved.push({ line: lineOf(m.index), values: [m[1] as string] });
  }
  out.unresolved = unresolved;
  return out;
}

export interface Verdict {
  userEnums: number;
  bad: EnumHit[];
  unresolved: EnumHit[];
}

/**
 * A user-role enum is one holding 'customer' or 'root', the user-role vocabulary, so a list
 * that dropped 'customer' but kept 'root' beside 'admin' is still policed (review 5fe6ca54.4);
 * the org ('owner','admin','member') and partner roles hold neither.
 */
export function judge(src: string): Verdict {
  const all = enumArrays(src);
  const user = all.filter((e) => e.values.includes('customer') || e.values.includes('root'));
  return {
    userEnums: user.length,
    bad: user.filter((e) => e.values.includes('admin')),
    unresolved: all.unresolved ?? [],
  };
}

function selftest(): void {
  const fail = (m: string): never => {
    console.error(`  FAIL  ${m}`);
    process.exit(1);
  };
  const clean = "role: text('role', { enum: ['customer', 'root'] })\nz.enum(['customer', 'root'])";
  const c = judge(clean);
  if (c.userEnums !== 2 || c.bad.length !== 0)
    fail(`CONTROL: clean enums misjudged ${JSON.stringify(c)}`);
  console.log('  PASS  CONTROL: customer/root enums are accepted and counted');

  const other = "role: text('role', { enum: ['owner', 'admin', 'member'] })";
  const o = judge(other);
  if (o.userEnums !== 0 || o.bad.length !== 0)
    fail('CONTROL: an org-role enum with admin was policed');
  console.log('  PASS  CONTROL: admin in a non-user enum is out of scope');

  const single = "role: text('role', { enum: ['customer', 'admin'] })";
  if (judge(single).bad.length !== 1) fail('single-line plant not caught');
  console.log('  PASS  single-line plant is caught');

  const reorder = "z.enum(['admin', 'customer'])";
  if (judge(reorder).bad.length !== 1) fail('reordered plant not caught');
  console.log('  PASS  reordered plant is caught');

  const wrapped =
    "role: text('role', {\n  enum: [\n    'customer',\n    'root',\n    'admin',\n  ],\n})";
  const w = judge(wrapped);
  if (w.bad.length !== 1 || w.bad[0]?.line !== 2)
    fail(`wrapped plant not caught ${JSON.stringify(w)}`);
  console.log('  PASS  wrapped multi-line plant is caught');

  if (judge('const x = 1;').userEnums !== 0) fail('no-enum source counted an enum');
  console.log('  PASS  a file with no user-role enum reports zero (main() refuses it)');

  const byRef =
    "const USER_ROLES = ['customer', 'admin'] as const;\nconst UserRole = z.enum(USER_ROLES);";
  if (judge(byRef).bad.length !== 1) fail('a role list passed by reference was not caught');
  console.log('  PASS  an enum passed by reference is resolved and caught');

  const noCustomer =
    "role: text('role', { enum: ['root', 'admin'] })\nz.enum(['customer', 'root'])";
  if (judge(noCustomer).bad.length !== 1) fail("a user-role enum without 'customer' escaped");
  console.log("  PASS  a user-role enum that lost 'customer' but kept 'root' is still policed");

  if (judge('z.enum(IMPORTED_ROLES)').unresolved.length !== 1)
    fail('an unresolvable enum reference was not reported');
  console.log('  PASS  an unresolvable enum reference is reported (main() refuses it)');
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    selftest();
    console.log('check-account-no-admin-role: selftest ok (9 controls)');
    return;
  }
  let checked = 0;
  let failed = false;
  for (const rel of TARGETS) {
    const p = path.join(ROOT, rel);
    if (!fs.existsSync(p)) {
      console.error(
        `✗ ${rel} does not exist, so the admin-role rule checked NOTHING there. Update TARGETS if it moved.`
      );
      failed = true;
      continue;
    }
    const v = judge(fs.readFileSync(p, 'utf-8'));
    if (v.userEnums === 0) {
      console.error(
        `✗ ${rel} holds no enum containing 'customer' or 'root'; the user-role enum moved or was renamed, so this gate sees nothing. Update TARGETS.`
      );
      failed = true;
      continue;
    }
    for (const u of v.unresolved) {
      console.error(
        `✗ ${rel}:${u.line} enum(${u.values[0]}) references a list this gate cannot resolve in the file, so it checked nothing there. Declare it as a same-file const array or extend the gate.`
      );
      failed = true;
    }
    checked += v.userEnums;
    for (const b of v.bad) {
      console.error(
        `✗ ${rel}:${b.line} user-role enum [${b.values.join(', ')}] contains 'admin'. The privileged user role is 'root'; remove 'admin' (org and partner roles are separate enums).`
      );
      failed = true;
    }
  }
  if (failed) process.exit(1);
  console.log(
    `✓ no admin user role: ${checked} user-role enum(s) across ${TARGETS.length} file(s), none contain 'admin'`
  );
}

if (process.argv[1] && path.resolve(process.argv[1]) === import.meta.filename) main();

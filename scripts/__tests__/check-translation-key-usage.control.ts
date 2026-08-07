#!/usr/bin/env node
/**
 * Control harness for check-translation-key-usage.ts's namespace discovery.
 *
 * WHY THIS EXISTS. The gate resolved `t(`${...}.suffix`)` prefixes from a
 * hard-coded pair of variable names, `ns` and `PAGE_KEY`. A component using
 * `const NS = 'pages.partners.form'` was therefore invisible to it, and a key
 * that existed in NO locale shipped to production while the gate reported
 * success. The fix derives names from the source instead.
 *
 * A fix like that regresses silently: someone "simplifies" the regex back to a
 * list and every gate stays green, because the tree happens to contain no
 * unusual name that day. So this asserts the BEHAVIOUR, both directions:
 * unusual names must be discovered, and non-namespace constants must not be.
 *
 * Run: npx tsx scripts/__tests__/check-translation-key-usage.control.ts
 */

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.join(__dirname, '../..');
const WWW_SRC = path.join(REPO, 'packages/www/src');
const GATE = path.join(REPO, 'scripts/check-translation-key-usage.ts');
const EN = path.join(WWW_SRC, 'i18n/translations/en.json');

interface Case {
  name: string;
  source: string;
  /** true when the gate must REPORT the planted bad key */
  shouldDetect: boolean;
}

const BAD = 'thisKeyDoesNotExistAnywhere';

const CASES: Case[] = [
  {
    name: "lowercase `ns` (the original supported spelling)",
    source: "const ns = 'pages.partners.form';\nexport const C = () => <p>{t(`${ns}." + BAD + '`)}</p>;\n',
    shouldDetect: true,
  },
  {
    name: 'uppercase `NS` (the spelling that was invisible)',
    source: "const NS = 'pages.partners.form';\nexport const C = () => <p>{t(`${NS}." + BAD + '`)}</p>;\n',
    shouldDetect: true,
  },
  {
    name: 'arbitrary `FORM_NS`',
    source:
      "const FORM_NS = 'pages.partners.form';\nexport const C = () => <p>{t(`${FORM_NS}." + BAD + '`)}</p>;\n',
    shouldDetect: true,
  },
  {
    name: 'arbitrary `sectionKey`',
    source:
      "const sectionKey = 'pages.partners.form';\nexport const C = () => <p>{t(`${sectionKey}." +
      BAD +
      '`)}</p>;\n',
    shouldDetect: true,
  },
  {
    name: 'PAGE_KEY (the other originally supported spelling)',
    source:
      "const PAGE_KEY = 'pages.partners.form';\nexport const C = () => <p>{t(`${PAGE_KEY}." + BAD + '`)}</p>;\n',
    shouldDetect: true,
  },
  {
    name: 'undotted constant must NOT be treated as a namespace',
    source: "const LABEL = 'Partners';\nexport const C = () => <p>{t(`${LABEL}." + BAD + '`)}</p>;\n',
    shouldDetect: false,
  },
  {
    name: 'dynamic suffix stays unresolvable, as before',
    source:
      "const NS = 'pages.partners.form';\nexport const C = ({ i }: { i: string }) => <p>{t(`${NS}.${i}." +
      BAD +
      '`)}</p>;\n',
    shouldDetect: false,
  },
];

/**
 * Every namespace variable name the www tree ACTUALLY uses today, read from
 * source rather than listed here.
 *
 * This is the anti-enumeration guard, and the distinction is the whole point.
 * A written-down list of "valid namespace patterns" is exactly the bug this
 * gate had: it accepted `ns` and `PAGE_KEY`, and the tree used five names -
 * `NS`, `ctaNamespace` and `metaPath` were all invisible, not just the one
 * that happened to surface a missing key. Any list, however carefully
 * enumerated and however well tested against itself, goes stale the first time
 * someone picks a sixth name, and it goes stale SILENTLY because a
 * list-checks-its-own-list assertion passes regardless of what the code does.
 *
 * So this derives the set and asserts the gate resolves each member. A
 * regression to any fixed list fails here the moment real code steps outside
 * it, with no maintenance and no enumeration to keep current.
 */
function namespaceVarsInUse(): string[] {
  const files = globSync('**/*.{astro,tsx}', { cwd: WWW_SRC, absolute: true });
  const names = new Set<string>();
  const re = /\bt[ao]?\(\s*`\$\{([A-Za-z_$][\w$]*)\}\./g;
  for (const f of files) {
    const content = fs.readFileSync(f, 'utf8');
    let m: RegExpExecArray | null;
    while ((m = re.exec(content)) !== null) names.add(m[1]);
  }
  return [...names].sort();
}

function gateReports(bad: string): boolean {
  try {
    const out = execFileSync('npx', ['tsx', GATE], { cwd: REPO, encoding: 'utf8' });
    return out.includes(bad);
  } catch (err) {
    const e = err as { stdout?: string; stderr?: string };
    return `${e.stdout ?? ''}${e.stderr ?? ''}`.includes(bad);
  }
}

function main(): void {
  // The control must be able to fail. If the gate cannot even see a planted
  // key under the ORIGINAL supported spelling, the harness is measuring
  // nothing and a green run would be meaningless.
  if (!fs.existsSync(EN)) {
    console.error('VACUOUS: en.json not found, nothing can be checked');
    process.exit(1);
  }

  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'keyusage-'));
  const probeDir = path.join(WWW_SRC, 'components');
  let failures = 0;

  for (const c of CASES) {
    const probe = path.join(probeDir, `__control_probe__.tsx`);
    fs.writeFileSync(probe, c.source, 'utf8');
    let detected: boolean;
    try {
      detected = gateReports(BAD);
    } finally {
      fs.unlinkSync(probe);
    }
    const ok = detected === c.shouldDetect;
    failures += ok ? 0 : 1;
    console.log(
      `${ok ? '  ok  ' : '  FAIL'} ${c.name} — want ${c.shouldDetect ? 'detected' : 'ignored'}, got ${
        detected ? 'detected' : 'ignored'
      }`,
    );
  }

  // ── the anti-enumeration guard, derived from the tree, not from a list ──
  const inUse = namespaceVarsInUse();
  if (inUse.length < 2) {
    console.error(
      `VACUOUS: found only ${inUse.length} namespace variable(s) in www source.\n` +
        '  Expected several. Either the scan broke or the convention changed;\n' +
        '  either way this guard would pass while checking nothing.',
    );
    process.exit(1);
  }
  const unresolved: string[] = [];
  for (const name of inUse) {
    const probe = path.join(probeDir, '__control_probe__.tsx');
    fs.writeFileSync(probe, `const ${name} = 'pages.partners.form';\nexport const C = () => <p>{t(\`\${${name}}.${BAD}\`)}</p>;\n`, 'utf8');
    try {
      if (!gateReports(BAD)) unresolved.push(name);
    } finally {
      fs.unlinkSync(probe);
    }
  }
  if (unresolved.length > 0) {
    failures += unresolved.length;
    console.log(`  FAIL in-use namespace names the gate cannot resolve: ${unresolved.join(', ')}`);
  } else {
    console.log(`  ok   all ${inUse.length} in-use namespace names resolve: ${inUse.join(', ')}`);
  }

  fs.rmSync(scratch, { recursive: true, force: true });

  if (failures > 0) {
    console.error(
      `\n✗ ${failures} control case(s) failed. Namespace discovery has regressed —\n` +
        '  most likely back to a hard-coded list of variable names, which is exactly\n' +
        '  how a key missing from every locale shipped to production once already.',
    );
    process.exit(1);
  }
  console.log(`\n✓ namespace discovery handles ${CASES.length} shapes, both directions`);
}

main();

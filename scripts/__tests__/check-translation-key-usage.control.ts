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

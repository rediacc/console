#!/usr/bin/env tsx
/**
 * check:ci-terms-version -- the legal text, its manifest, its archives and the generated legal
 * modules move together (agent/plans/PLAN-terms-acceptance.md Design 6).
 *
 * WHY. Acceptance is recorded against a version and a sha256. If the English text of the Terms
 * changes and nobody declares a version, every recorded acceptance points at a hash whose text no
 * longer exists anywhere, and the record proves nothing. So the published text IS the source of
 * the hash: `scripts/gen/gen-legal.ts` renders it canonically and this gate re-renders it with the
 * same code (it imports `buildOutputs`), so the two cannot disagree about a byte.
 *
 * FINDINGS
 *   1. a document's render differs from its newest archive: the text changed with no version
 *      entry ("add a version entry")
 *   2. an archive is missing, or its sha256 differs from the manifest (archives are immutable)
 *   3. a generated module (documents.generated.ts, consent.generated.ts) or the manifest's filled
 *      hashes differ from their render
 *   4. version or effective dates are malformed, versions do not strictly increase, or effective
 *      dates go backwards
 *   5. a locale lacks a `legal.consent` key, carries it empty, or carries a different set of
 *      `{{tokens}}` than English
 *   6. terms-of-service.astro does not render the version line from the shared legal module
 *
 * Checks 5 and 6 turn on with the legal rewrite: they are INACTIVE while en.json carries no
 * `legal.consent` at all (the rewrite, boxes L1/L2, has not landed), and the run says so by name
 * every time rather than passing quietly. Once English carries the notices, every locale must,
 * and the empty placeholder notices in consent.generated.ts become a check-3 finding.
 *
 * Zero documents is CANNOT RUN (exit 77): an empty manifest would make every check vacuous.
 *
 * Controls (--selftest) plant into a temporary fixture tree, never the real one: an edited
 * paragraph, an edited archive and a missing consent key each turn the gate red, and so do an
 * edited generated module, a backwards version, a page without the version line and an empty
 * manifest (77). The clean fixture must be green first, or every red proves nothing.
 *
 * ---- gate ----
 * step: Terms version
 * needs: node
 * lane: quality-content
 * selftest: true
 * why: an acceptance is recorded against a terms version and its sha256, so a text edit with no
 *      version entry, an edited archive or a stale generated module leaves every recorded
 *      acceptance pointing at a text that no longer exists
 * ---- end gate ----
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { LEGAL_ENTITY } from '@rediacc/shared/legal';

import {
  archiveRel,
  buildOutputs,
  CONSENT_KEYS,
  CONSENT_TS_REL,
  DOCUMENTS_TS_REL,
  ENTITY_REL,
  LegalError,
  LOCALES,
  loadSources,
  MANIFEST_REL,
  type Manifest,
  noticeSubstitutions,
  renderConsentTs,
  sha256,
  TRANSLATIONS_REL,
  tokensIn,
  tsNotice,
  WELL_KNOWN_REL,
} from '../gen/gen-legal.ts';
import { exitWithMainIfEntryPoint } from '../lib/entry-point.ts';

const NAME = 'check:ci-terms-version';
export const TERMS_PAGE_REL = 'packages/www/src/pages/[lang]/terms-of-service.astro';
const DATE = /^\d{4}-\d{2}-\d{2}$/;

export interface Verdict {
  findings: string[];
  notes: string[];
  documents: number;
  versions: number;
}

function validDate(s: string): boolean {
  return DATE.test(s) && new Date(`${s}T00:00:00Z`).toISOString().slice(0, 10) === s;
}

function consentOf(catalog: Record<string, unknown>): Record<string, unknown> | undefined {
  const legal = catalog.legal as Record<string, unknown> | undefined;
  const consent = legal?.consent;
  return consent && typeof consent === 'object' ? (consent as Record<string, unknown>) : undefined;
}

export function check(root: string, locales: readonly string[] = LOCALES): Verdict {
  const findings: string[] = [];
  const notes: string[] = [];
  const manifest = JSON.parse(fs.readFileSync(path.join(root, MANIFEST_REL), 'utf8')) as Manifest;
  const docs = Object.entries(manifest.documents);
  let versions = 0;

  // 4. dates
  for (const [id, doc] of docs) {
    versions += doc.versions.length;
    if (doc.versions.length === 0) findings.push(`4: ${id} declares no version`);
    doc.versions.forEach((v, i) => {
      for (const field of ['version', 'effective'] as const) {
        if (!validDate(v[field]))
          findings.push(`4: ${id} version ${i}: ${field} '${v[field]}' is not a YYYY-MM-DD date`);
      }
      if (typeof v.material !== 'boolean')
        findings.push(`4: ${id} ${v.version}: material is not a boolean`);
      if (i > 0) {
        const prev = doc.versions[i - 1];
        if (!(v.version > prev.version))
          findings.push(`4: ${id}: version ${v.version} does not follow ${prev.version}`);
        if (v.effective < prev.effective)
          findings.push(
            `4: ${id}: effective ${v.effective} of ${v.version} goes back before ${prev.effective}`
          );
      }
    });
  }

  let src: ReturnType<typeof loadSources> | undefined;
  try {
    src = loadSources(root, { locales });
  } catch (err) {
    findings.push(`cannot load the legal sources: ${(err as Error).message}`);
  }

  if (src) {
    for (const [id, doc] of docs) {
      // 2. archives
      for (const v of doc.versions) {
        const rel = archiveRel(id, v.version);
        const file = path.join(root, rel);
        if (!fs.existsSync(file)) {
          findings.push(
            `2: ${id} ${v.version}: archive ${rel} is missing; run npx tsx scripts/gen/gen-legal.ts --write`
          );
        } else if (!v.sha256) {
          findings.push(
            `2: ${id} ${v.version}: the manifest carries no sha256; run npx tsx scripts/gen/gen-legal.ts --write`
          );
        } else if (sha256(fs.readFileSync(file, 'utf8')) !== v.sha256) {
          findings.push(
            `2: ${id} ${v.version}: archive ${rel} does not match its manifest sha256; archives are immutable, restore it`
          );
        }
      }
      // 1. the text against its newest archive
      const newest = doc.versions[doc.versions.length - 1];
      const newestRel = newest ? archiveRel(id, newest.version) : '';
      if (newest && fs.existsSync(path.join(root, newestRel))) {
        let render: string | undefined;
        try {
          render = buildRender(src, id);
        } catch (err) {
          findings.push(`1: ${id}: the text does not render: ${(err as Error).message}`);
        }
        if (
          render !== undefined &&
          render !== fs.readFileSync(path.join(root, newestRel), 'utf8')
        ) {
          findings.push(
            `1: ${id}: pages.${doc.catalogKey} in en.json differs from its newest archive ${newestRel} (version ${newest.version}); add a version entry to ${MANIFEST_REL} and run npx tsx scripts/gen/gen-legal.ts --write`
          );
        }
      }
    }

    // 3. generated modules
    try {
      const out = buildOutputs(src);
      for (const rel of [DOCUMENTS_TS_REL, CONSENT_TS_REL, MANIFEST_REL]) {
        const file = path.join(root, rel);
        const have = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : null;
        if (have !== out.files.get(rel)) {
          findings.push(
            `3: ${rel} differs from its render; run npx tsx scripts/gen/gen-legal.ts --write`
          );
        }
      }
    } catch (err) {
      if (!(err instanceof LegalError)) throw err;
      findings.push(`3: the generated modules do not render: ${err.message}`);
    }

    // 5. consent notices
    const enConsent = consentOf(src.catalogs.en);
    if (!enConsent) {
      notes.push(
        'check 5 INACTIVE: en.json carries no legal.consent yet (the legal rewrite has not landed); it turns on with it'
      );
      notes.push('check 6 INACTIVE: it turns on with check 5, when the rewritten pages land');
    } else {
      for (const key of Object.values(CONSENT_KEYS)) {
        const enText = enConsent[key];
        if (typeof enText !== 'string' || enText.trim() === '') {
          findings.push(`5: en.json legal.consent.${key} is missing or empty`);
          continue;
        }
        const want = [...tokensIn(enText)].sort((a, b) => a.localeCompare(b));
        for (const locale of locales) {
          if (locale === 'en') continue;
          const text = consentOf(src.catalogs[locale])?.[key];
          if (typeof text !== 'string' || text.trim() === '') {
            findings.push(`5: ${locale}.json legal.consent.${key} is missing or empty`);
            continue;
          }
          const have = [...tokensIn(text)].sort((a, b) => a.localeCompare(b));
          if (have.join(',') !== want.join(',')) {
            findings.push(
              `5: ${locale}.json legal.consent.${key} carries tokens {${have.join(', ')}}, English carries {${want.join(', ')}}`
            );
          }
        }
      }
      // 6. the version line
      const page = path.join(root, TERMS_PAGE_REL);
      const text = fs.existsSync(page) ? fs.readFileSync(page, 'utf8') : '';
      if (!rendersVersionLine(text)) {
        findings.push(
          `6: ${TERMS_PAGE_REL} does not render the version line (version and sha256) from '@rediacc/shared/legal'`
        );
      }
    }
  }
  return { findings, notes, documents: docs.length, versions };
}

/**
 * True when the page imports from '@rediacc/shared/legal' and its template (after the
 * frontmatter) interpolates both a version and a sha256 expression. Comments are stripped
 * first, so a mention of either word in a comment does not count.
 */
export function rendersVersionLine(source: string): boolean {
  const code = source
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|\s)\/\/[^\n]*/g, '$1');
  const fm = /^---\r?\n([\s\S]*?)\r?\n---/.exec(code);
  if (!fm) return false;
  const body = code.slice(fm[0].length);
  return (
    /from '@rediacc\/shared\/legal'/.test(fm[1]) &&
    /\{[^}]*\bversion\b[^}]*\}/.test(body) &&
    /\{[^}]*\bsha256\b[^}]*\}/.test(body)
  );
}

/** The process status for a verdict: 77 cannot run, 1 findings, 0 clean. */
export function verdictRc(v: Verdict): number {
  if (v.documents === 0) return 77;
  return v.findings.length > 0 ? 1 : 0;
}

function buildRender(src: ReturnType<typeof loadSources>, id: string): string {
  const out = buildOutputs({
    ...src,
    manifest: { documents: { [id]: src.manifest.documents[id] } },
  });
  const render = out.renders.get(id);
  if (render === undefined) throw new LegalError(`${id} produced no render`);
  return render;
}

function report(v: Verdict): number {
  if (verdictRc(v) === 77) {
    console.error(
      `${NAME}: CANNOT RUN -- ${MANIFEST_REL} declares no document, so every check would be vacuous`
    );
    return 77;
  }
  for (const n of v.notes) console.log(`  ${n}`);
  if (v.findings.length > 0) {
    console.error(`✗ ${NAME}: ${v.findings.length} finding(s):`);
    for (const f of v.findings) console.error(`  ${f}`);
    return 1;
  }
  console.log(
    `✓ ${NAME}: ${v.documents} document(s), ${v.versions} version(s); text, manifest, archives and generated modules agree`
  );
  return 0;
}

// --------------------------------------------------------------------------- selftest

const FIXTURE_LOCALES = ['en', 'de'] as const;

function fixtureCatalog(
  paragraph: string,
  consent: boolean,
  locale: string
): Record<string, unknown> {
  const cat: Record<string, unknown> = {
    pages: {
      termsOfService: {
        hero: { title: 'Terms', effectiveDate: 'Effective 2026-01-01' },
        sections: {
          parties: {
            id: 'parties',
            title: '1. Parties',
            content: [`${paragraph} {{legalName}} ({{registryCode}}), {{country}}.`],
            items: ['See <a href="privacy-policy">Privacy</a>'],
          },
        },
        contact: {
          title: 'Questions?',
          description: 'Mail <a href="mailto:x@example.invalid">us</a>.',
        },
      },
    },
  };
  if (consent) {
    cat.legal = {
      consent: {
        webCheckbox: `[${locale}] I accept the <a href="{{termsUrl}}">Terms</a> of {{legalName}}`,
        cliPrompt: `[${locale}] Accept {{termsUrl}}?`,
        cliRefusal: `[${locale}] Pass --accept-terms or RDC_ACCEPT_TERMS=1 ({{termsUrl}})`,
        stripeCheckout: `[${locale}] I accept {{termsUrl}} and {{privacyUrl}}`,
      },
    };
  }
  return cat;
}

function writeFixture(
  dir: string,
  opts: { consent: boolean; page: boolean | 'comment-only' }
): void {
  const put = (rel: string, content: string) => {
    // tree-write: safe dir is the fixture dir run() made with mkdtemp under os.tmpdir()
    fs.mkdirSync(path.dirname(path.join(dir, rel)), { recursive: true });
    // tree-write: safe dir is the fixture dir run() made with mkdtemp under os.tmpdir()
    fs.writeFileSync(path.join(dir, rel), content);
  };
  put(
    MANIFEST_REL,
    `${JSON.stringify(
      {
        documents: {
          'terms-of-service': {
            page: 'terms-of-service',
            catalogKey: 'termsOfService',
            versions: [{ version: '2026-01-01', effective: '2026-01-01', material: true }],
          },
        },
      },
      null,
      2
    )}\n`
  );
  for (const locale of FIXTURE_LOCALES) {
    put(
      `${TRANSLATIONS_REL}/${locale}.json`,
      JSON.stringify(fixtureCatalog('Agreement with', opts.consent, locale))
    );
  }
  put(
    ENTITY_REL,
    JSON.stringify({
      legalName: 'Fixture OU',
      registryCode: 'F-1',
      registerName: 'Fixture Register',
      vatNumber: 'FV1',
      addressLine1: 'Street 1',
      addressLine2: 'District',
      city: 'City',
      postalCode: '1000',
      countryCode: 'EE',
      registeredAddress: 'City, District, Street 1, 1000',
      sourceSha256: '0'.repeat(64),
    })
  );
  put(WELL_KNOWN_REL, "export const WK_SITE_ORIGIN = 'https://www.example.invalid';\n");
  put(
    TERMS_PAGE_REL,
    opts.page === 'comment-only'
      ? "---\nimport { termsAt } from '@rediacc/shared/legal';\n// renders the version and sha256 line\n---\n<!-- version sha256 -->\n<p>no version line</p>\n"
      : opts.page
        ? "---\nimport { termsAt } from '@rediacc/shared/legal';\nconst t = termsAt(new Date());\n---\n<p>{t.current.version} {t.current.sha256}</p>\n"
        : '---\n---\n<p>no version line</p>\n'
  );
  const out = buildOutputs(loadSources(dir, { locales: FIXTURE_LOCALES }));
  for (const [rel, content] of out.files) put(rel, content);
}

function selftest(): number {
  let failures = 0;
  const run = (
    label: string,
    setup: (dir: string) => void,
    expect: (v: Verdict, rc: number) => boolean
  ) => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'terms-version-'));
    try {
      setup(dir);
      const v = check(dir, FIXTURE_LOCALES);
      const rc = verdictRc(v);
      const ok = expect(v, rc);
      console.log(
        `  ${ok ? 'PASS' : 'FAIL'}  ${label}${ok ? '' : ` -- rc=${rc} findings=${JSON.stringify(v.findings)}`}`
      );
      if (!ok) failures += 1;
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  };
  const has = (v: Verdict, prefix: string) => v.findings.some((f) => f.startsWith(prefix));
  const edit = (dir: string, rel: string, fn: (s: string) => string) => {
    const file = path.join(dir, rel);
    // tree-write: safe dir is the fixture dir run() made with mkdtemp under os.tmpdir()
    fs.writeFileSync(file, fn(fs.readFileSync(file, 'utf8')));
  };
  const archive = archiveRel('terms-of-service', '2026-01-01');

  run(
    'CONTROL: a consistent tree before the rewrite is green, with checks 5 and 6 named INACTIVE',
    (d) => writeFixture(d, { consent: false, page: false }),
    (v, rc) => rc === 0 && v.notes.some((n) => n.startsWith('check 5 INACTIVE'))
  );
  run(
    'CONTROL: a consistent tree after the rewrite is green',
    (d) => writeFixture(d, { consent: true, page: true }),
    (v, rc) => rc === 0 && v.notes.length === 0
  );
  run(
    'an edited paragraph is red and asks for a version entry',
    (d) => {
      writeFixture(d, { consent: false, page: false });
      edit(d, `${TRANSLATIONS_REL}/en.json`, (s) => s.replace('Agreement with', 'Contract with'));
    },
    (v, rc) =>
      rc === 1 && v.findings.some((f) => f.startsWith('1:') && f.includes('add a version entry'))
  );
  run(
    'an edited archive is red',
    (d) => {
      writeFixture(d, { consent: false, page: false });
      edit(d, archive, (s) => s.replace('Parties', 'Partys'));
    },
    (v, rc) => rc === 1 && has(v, '2:')
  );
  run(
    'a missing consent key is red, by locale and key',
    (d) => {
      writeFixture(d, { consent: true, page: true });
      edit(d, `${TRANSLATIONS_REL}/de.json`, (s) => {
        const cat = JSON.parse(s);
        delete cat.legal.consent.cliRefusal;
        return JSON.stringify(cat);
      });
    },
    (v, rc) =>
      rc === 1 && v.findings.some((f) => f.startsWith('5: de.json legal.consent.cliRefusal'))
  );
  run(
    'a consent notice with a different token set is red',
    (d) => {
      writeFixture(d, { consent: true, page: true });
      edit(d, `${TRANSLATIONS_REL}/de.json`, (s) => s.replace('Accept {{termsUrl}}?', 'Accept?'));
    },
    (v, rc) => rc === 1 && has(v, '5: de.json legal.consent.cliPrompt carries tokens')
  );
  run(
    'a hand-edited generated module is red',
    (d) => {
      writeFixture(d, { consent: false, page: false });
      edit(d, DOCUMENTS_TS_REL, (s) => s.replace('material: true', 'material: false'));
    },
    (v, rc) => rc === 1 && has(v, `3: ${DOCUMENTS_TS_REL}`)
  );
  run(
    'a version that does not follow the previous one is red',
    (d) => {
      writeFixture(d, { consent: false, page: false });
      edit(d, MANIFEST_REL, (s) => {
        const m = JSON.parse(s);
        m.documents['terms-of-service'].versions.push({
          version: '2025-12-01',
          effective: '2025-12-01',
          material: false,
        });
        return JSON.stringify(m, null, 2);
      });
    },
    (v, rc) => rc === 1 && has(v, '4:')
  );
  run(
    'a terms page without the version line is red once the rewrite has landed',
    (d) => writeFixture(d, { consent: true, page: false }),
    (v, rc) => rc === 1 && has(v, '6:')
  );
  run(
    'a terms page that only mentions the version and sha256 in comments is red',
    (d) => writeFixture(d, { consent: true, page: 'comment-only' }),
    (v, rc) => rc === 1 && has(v, '6:')
  );
  run(
    'an empty manifest cannot run (77)',
    (d) => {
      writeFixture(d, { consent: false, page: false });
      // tree-write: safe d is the fixture dir run() made with mkdtemp under os.tmpdir()
      fs.writeFileSync(path.join(d, MANIFEST_REL), '{"documents": {}}\n');
    },
    (_v, rc) => rc === 77
  );
  const control = (label: string, ok: boolean) => {
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${label}`);
    if (!ok) failures += 1;
  };
  const evalNotice = (src: string) =>
    new Function('WK_SITE_ORIGIN', 'LEGAL_ENTITY', `return ${src};`)(
      'https://www.example.invalid',
      { legalName: LEGAL_ENTITY.legalName }
    ) as string;
  const subs = noticeSubstitutions('https://www.example.invalid', {
    legalName: LEGAL_ENTITY.legalName,
  });
  const tricky = `${LEGAL_ENTITY.legalName} at https://www.example.invalid/x \\ \`tick\` \${not} line\nnext`;
  const trickySrc = tsNotice(tricky, subs);
  control(
    'a notice with backslash, backtick, ${ and a newline round-trips through tsNotice',
    evalNotice(trickySrc) === tricky && trickySrc.includes('${WK_SITE_ORIGIN}')
  );
  control(
    'a host spelled without www stays literal',
    tsNotice('see https://example.invalid/x', subs).includes('https://example.invalid/x')
  );
  let emptyOriginRefused = false;
  try {
    noticeSubstitutions('', {});
  } catch {
    emptyOriginRefused = true;
  }
  control('an empty site origin is refused', emptyOriginRefused);
  const rendered = renderConsentTs(
    {
      en: {
        'web-checkbox': `Terms of ${LEGAL_ENTITY.legalName}`,
        'cli-prompt': '',
        'cli-flag-unattended': '',
        'stripe-checkout': '',
      },
    },
    'https://www.example.invalid',
    { legalName: LEGAL_ENTITY.legalName }
  );
  control(
    'the entity is emitted as a LEGAL_ENTITY reference with its import',
    rendered.includes("import { LEGAL_ENTITY } from './entity.generated.js';") &&
      rendered.includes('${LEGAL_ENTITY.legalName}')
  );
  console.log(
    failures === 0
      ? `OK  ${NAME} selftest: all controls fired`
      : `✗ ${NAME} selftest: ${failures} control(s) did not fire`
  );
  return failures === 0 ? 0 : 1;
}

function main(argv: string[]): number {
  if (argv.includes('--selftest')) return selftest();
  if (argv.length > 0) {
    console.error(`${NAME}: unknown argument(s): ${argv.join(' ')}`);
    return 2;
  }
  return report(check(path.resolve(import.meta.dirname, '..', '..')));
}

exitWithMainIfEntryPoint(import.meta.filename, main);

#!/usr/bin/env tsx
/**
 * Fetch and normalise the EU NIS2 Directive (Directive (EU) 2022/2555) into
 * vendored plaintext snapshots at scripts/data/nis2-directive-2022-2555-<lang>.txt.
 *
 * Run modes:
 *   tsx scripts/fetch-directive-snapshot.ts                       (English, fetch from EUR-Lex)
 *   tsx scripts/fetch-directive-snapshot.ts --use-local           (English, use the vendored CELEX PDF)
 *   tsx scripts/fetch-directive-snapshot.ts --lang de             (German, fetch from EUR-Lex)
 *   tsx scripts/fetch-directive-snapshot.ts --all                 (loop over all 7 EU languages we ship)
 *   tsx scripts/fetch-directive-snapshot.ts --check               (English; compare hash to manifest)
 *   tsx scripts/fetch-directive-snapshot.ts --check --all         (per-language drift check)
 *
 * The snapshots are the source of truth for scripts/check-directive-quotes.ts.
 * Regenerate only when the directive is amended (rare for OJ instruments) or
 * when normalisation rules change (bump NORMALISATION_VERSION below).
 *
 * Languages we vendor a snapshot for: en, de, es, fr, et, it, pt. All other
 * locales the project supports (ja, ar, ru, tr, zh, ko) fall back to the
 * English snapshot at runtime; the directive has no official translation in
 * those languages.
 *
 * Requires `pdftotext` from poppler-utils on the host.
 */
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const CELEX = '32022L2555';
const NORMALISATION_VERSION = 1;

// EU languages where the directive is officially published AND that we
// translate the surrounding content into. ISO 639-1 codes; EUR-Lex uses
// the uppercase form in URLs (EN, DE, ES, FR, ET, IT, PT).
const SUPPORTED_LANGS = ['en', 'de', 'es', 'fr', 'et', 'it', 'pt'] as const;
type SupportedLang = (typeof SUPPORTED_LANGS)[number];

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..');
const dataDir = path.join(repoRoot, 'scripts', 'data');

const args = process.argv.slice(2);
const argSet = new Set(args);
const checkMode = argSet.has('--check');
const useLocal = argSet.has('--use-local') || argSet.has('--offline');
const allMode = argSet.has('--all');
const langArgIdx = args.indexOf('--lang');
const langArg = langArgIdx >= 0 ? args[langArgIdx + 1] : undefined;

function pathsForLang(lang: SupportedLang) {
  return {
    txt: path.join(dataDir, `nis2-directive-2022-2555-${lang}.txt`),
    manifest: path.join(dataDir, `nis2-directive-2022-2555-${lang}.manifest.json`),
  };
}

function eliUrl(lang: SupportedLang): string {
  // ELI URL uses the 3-letter language code in lowercase; map ISO 639-1 -> ISO 639-3-ish slug used by EUR-Lex.
  // Examples observed:
  //   en -> /eli/dir/2022/2555/oj/eng
  //   de -> /eli/dir/2022/2555/oj/deu
  //   es -> /eli/dir/2022/2555/oj/spa
  //   fr -> /eli/dir/2022/2555/oj/fra
  //   et -> /eli/dir/2022/2555/oj/est
  //   it -> /eli/dir/2022/2555/oj/ita
  //   pt -> /eli/dir/2022/2555/oj/por
  const map: Record<SupportedLang, string> = {
    en: 'eng',
    de: 'deu',
    es: 'spa',
    fr: 'fra',
    et: 'est',
    it: 'ita',
    pt: 'por',
  };
  return `https://eur-lex.europa.eu/eli/dir/2022/2555/oj/${map[lang]}`;
}

function pdfUrl(lang: SupportedLang): string {
  // The PDF endpoint uses the uppercase ISO 639-1 code.
  return `https://eur-lex.europa.eu/legal-content/${lang.toUpperCase()}/TXT/PDF/?uri=CELEX:${CELEX}`;
}

const localCelexPdf = path.join(
  repoRoot,
  'private',
  'growth',
  'nis2pack',
  '01_NIS2_Directive',
  'CELEX_32022L2555_EN_TXT.pdf',
);

function sha256(buf: Buffer | string): string {
  return createHash('sha256').update(buf).digest('hex');
}

function fetchPdfFromEurLex(lang: SupportedLang): Buffer {
  if (useLocal) {
    if (lang !== 'en') {
      throw new Error(
        `--use-local only supports English (the vendored CELEX PDF is the EN edition). Use without --use-local for ${lang}.`,
      );
    }
    if (!fs.existsSync(localCelexPdf)) {
      throw new Error(
        `--use-local requested but local PDF missing: ${localCelexPdf}\n` +
          `Either drop the file in place or run without --use-local to fetch from EUR-Lex.`,
      );
    }
    console.log(`[${lang}] reading local PDF: ${localCelexPdf}`);
    return fs.readFileSync(localCelexPdf);
  }

  const url = pdfUrl(lang);
  console.log(`[${lang}] fetching ${url}`);
  const tmp = path.join(
    fs.mkdtempSync(path.join(os.tmpdir(), `celex-${lang}-`)),
    `celex-${lang}.pdf`,
  );
  execFileSync(
    'curl',
    [
      '-fL',
      '-A',
      'Mozilla/5.0 (compatible; rediacc-ci-fetch-directive-snapshot/1)',
      '--max-time',
      '60',
      '-o',
      tmp,
      url,
    ],
    { stdio: 'inherit' },
  );
  return fs.readFileSync(tmp);
}

/**
 * Convert PDF buffer to plain text via pdftotext, then normalise.
 *
 * Normalisation rules (v1) — language-agnostic; relies on whitespace,
 * smart-quote, and page-furniture removal that applies regardless of locale:
 *  - drop the OJ page-header line that appears on every page
 *  - drop bare page numbers on their own line
 *  - normalise smart quotes / dashes / NBSP to ASCII equivalents
 *  - collapse runs of whitespace to single spaces, but preserve paragraph breaks
 *
 * Bumping NORMALISATION_VERSION forces a regeneration; the runtime check
 * compares its own normalisation output against this snapshot, so the two MUST
 * match. The runtime check applies the same flatten() over the source string
 * before indexOf, so we keep newlines in the snapshot for diff readability.
 */
function normalise(rawText: string): string {
  let s = rawText;

  s = s.replace(/[‘’‚‛]/g, "'");
  s = s.replace(/[“”„‟«»]/g, '"');
  s = s.replace(/[–—―]/g, '-');
  s = s.replace(/…/g, '...');
  s = s.replace(/ /g, ' ');

  // OJ page header is "Official Journal of the European Union" in English; in
  // other locales it is the localised equivalent ("Journal officiel de l'Union
  // européenne", "Diario Oficial de la Unión Europea", etc.). We keep the
  // language-specific variants narrow to avoid stripping body text.
  s = s.replace(/Official Journal of the European Union[^\n]*\n/g, '\n');
  s = s.replace(/Amtsblatt der Europäischen Union[^\n]*\n/g, '\n'); // de
  s = s.replace(/Diario Oficial de la Unión Europea[^\n]*\n/g, '\n'); // es
  s = s.replace(/Journal officiel de l[’']Union européenne[^\n]*\n/g, '\n'); // fr
  s = s.replace(/Euroopa Liidu Teataja[^\n]*\n/g, '\n'); // et
  s = s.replace(/Gazzetta ufficiale dell[’']Unione europea[^\n]*\n/g, '\n'); // it
  s = s.replace(/Jornal Oficial da União Europeia[^\n]*\n/g, '\n'); // pt
  s = s.replace(/CELEX:\s*32022L2555[^\n]*\n/g, '\n');
  s = s.replace(/^\s*\d{1,3}\s*$/gm, '');

  s = s.replace(/[ \t]+/g, ' ');
  s = s.replace(/\n{3,}/g, '\n\n');
  s = s.replace(/[ \t]+\n/g, '\n');
  return s.trim() + '\n';
}

function pdftotextLayout(pdf: Buffer): string {
  const tmpPdf = path.join(
    fs.mkdtempSync(path.join(os.tmpdir(), 'celex-')),
    'celex.pdf',
  );
  fs.writeFileSync(tmpPdf, pdf);
  return execFileSync('pdftotext', ['-layout', '-enc', 'UTF-8', tmpPdf, '-'], {
    encoding: 'utf-8',
    maxBuffer: 32 * 1024 * 1024,
  });
}

function loadManifest(p: string): Record<string, unknown> | null {
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, 'utf-8'));
  } catch {
    return null;
  }
}

function processOne(lang: SupportedLang): { ok: boolean; message: string } {
  const { txt: txtOut, manifest: manifestOut } = pathsForLang(lang);
  let pdf: Buffer;
  try {
    pdf = fetchPdfFromEurLex(lang);
  } catch (err) {
    return {
      ok: false,
      message: `[${lang}] fetch failed: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
  const sourceSha = sha256(pdf);
  let raw: string;
  try {
    raw = pdftotextLayout(pdf);
  } catch (err) {
    return {
      ok: false,
      message: `[${lang}] pdftotext failed: ${err instanceof Error ? err.message : String(err)}`,
    };
  }
  const text = normalise(raw);
  const textSha = sha256(text);

  const existing = loadManifest(manifestOut);

  if (checkMode) {
    if (!existing) {
      return { ok: false, message: `[${lang}] no existing manifest; cannot --check` };
    }
    const sourceDrift = existing['source_pdf_sha256'] !== sourceSha;
    const textDrift = existing['sha256'] !== textSha;
    if (!sourceDrift && !textDrift) {
      return {
        ok: true,
        message: `[${lang}] up-to-date (sha256=${textSha.slice(0, 12)}...)`,
      };
    }
    const drifts: string[] = [];
    if (sourceDrift) {
      drifts.push(
        `source PDF: was ${String(existing['source_pdf_sha256']).slice(0, 12)}..., now ${sourceSha.slice(0, 12)}...`,
      );
    }
    if (textDrift) {
      drifts.push(
        `normalised text: was ${String(existing['sha256']).slice(0, 12)}..., now ${textSha.slice(0, 12)}...`,
      );
    }
    return { ok: false, message: `[${lang}] drift detected — ${drifts.join('; ')}` };
  }

  fs.writeFileSync(txtOut, text, 'utf-8');
  const manifest = {
    celex: CELEX,
    lang,
    eli_url: eliUrl(lang),
    pdf_url: pdfUrl(lang),
    fetched_at: new Date().toISOString(),
    source_pdf_sha256: sourceSha,
    source_pdf_bytes: pdf.length,
    sha256: textSha,
    bytes: Buffer.byteLength(text, 'utf-8'),
    normalisation_version: NORMALISATION_VERSION,
  };
  fs.writeFileSync(manifestOut, JSON.stringify(manifest, null, 2) + '\n', 'utf-8');
  return {
    ok: true,
    message: `[${lang}] wrote ${path.relative(repoRoot, txtOut)} (${manifest.bytes} bytes, sha256=${textSha.slice(0, 12)}...)`,
  };
}

function main() {
  if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

  const langs: SupportedLang[] = allMode
    ? [...SUPPORTED_LANGS]
    : [(langArg as SupportedLang) || 'en'];

  for (const lang of langs) {
    if (!SUPPORTED_LANGS.includes(lang)) {
      console.error(`unknown --lang ${lang}; supported: ${SUPPORTED_LANGS.join(', ')}`);
      process.exit(2);
    }
  }

  let allOk = true;
  for (const lang of langs) {
    const r = processOne(lang);
    if (r.ok) console.log(r.message);
    else {
      allOk = false;
      console.error(r.message);
    }
  }

  if (!allOk) process.exit(checkMode ? 0 : 1);
}

main();

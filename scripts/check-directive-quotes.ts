#!/usr/bin/env tsx
/**
 * CI gate: every verbatim quotation of Directive (EU) 2022/2555 (NIS2) in our
 * content tree must match the official directive text.
 *
 * Run: tsx scripts/check-directive-quotes.ts
 *
 * The vendored snapshot at scripts/data/nis2-directive-2022-2555-en.txt is the
 * source of truth; regenerate via scripts/fetch-directive-snapshot.ts when the
 * directive is amended.
 *
 * In-scope files:
 *   - packages/www/src/content/(blog|docs)/(en|...)/*.{md,mdx}
 *   - packages/www/src/pages/(...)/*.astro
 *   - private/growth/dist/(...)/*.md (skipped if submodule absent)
 *
 * Pre-filter: file must mention "NIS2" / "NIS 2" / "Directive 2022/2555" /
 * "Directive (EU) 2022/2555" / CELEX 32022L2555.
 *
 * Language gate: only files with frontmatter `language: en` (or no frontmatter,
 * defaulting to en) are scanned. Translation files are listed and skipped.
 *
 * In-scope quote rules:
 *   A. Markdown blockquote (`> "..."`) within 3 non-blank lines of an
 *      `Article 2[0-3]` / `Recital N` / `Annex (I|II|III)` reference.
 *   B. Explicit comment marker `<!-- nis2-quote: <ref> -->` on the line
 *      immediately above (or trailing on the same line as) the quoted text.
 *
 * Skip rules (override the above):
 *   - `<!-- nis2-quote-skip: <reason> -->` on the line above or trailing.
 *   - File path matches an entry in .ci/config/directive-quotes-allowlist.txt
 *     (every entry must carry a BLOCKER reason; validated via blocker-validator).
 *
 * Comparison:
 *   - Both quote and source are normalised: smart-quote -> straight, smart-dash
 *     -> ASCII, collapse all whitespace (incl. newlines) to single spaces.
 *   - Quote split on ellipsis tokens (`[...]`, `...`, `…`); each fragment
 *     must appear in the source in order.
 *   - On failure, emit the nearest substring (Levenshtein) for the missing
 *     fragment.
 *
 * Exit codes: 0 = all pass; 1 = at least one quote failed; 2 = configuration
 * error (missing snapshot, allowlist with bad BLOCKER, etc.).
 */
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { globSync } from 'glob';

import { parseBlockeredList, verifyAllBlockers } from './lib/blocker-validator.ts';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..');

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

// Languages that have an official Directive (EU) 2022/2555 translation we
// vendor a snapshot for. Sourced from scripts/data/nis2-directive-2022-2555-<lang>.txt.
const SNAPSHOT_LANGS = ['en', 'de', 'es', 'fr', 'et', 'it', 'pt'] as const;
type SnapshotLang = (typeof SNAPSHOT_LANGS)[number];

// All locales the www site ships content in. Locales not in SNAPSHOT_LANGS
// fall back to the English snapshot for the directive-quote check (no official
// EU directive translation exists in those languages).
const ALL_CONTENT_LANGS = [
  'en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh', 'et', 'ko', 'pt', 'it',
] as const;
type ContentLang = (typeof ALL_CONTENT_LANGS)[number];

function snapshotForLang(lang: ContentLang): SnapshotLang {
  return (SNAPSHOT_LANGS as readonly string[]).includes(lang)
    ? (lang as SnapshotLang)
    : 'en';
}

function snapshotPath(lang: SnapshotLang): { txt: string; manifest: string } {
  return {
    txt: path.join(repoRoot, 'scripts', 'data', `nis2-directive-2022-2555-${lang}.txt`),
    manifest: path.join(
      repoRoot,
      'scripts',
      'data',
      `nis2-directive-2022-2555-${lang}.manifest.json`,
    ),
  };
}

const ALLOWLIST_PATH = path.join(
  repoRoot,
  '.ci',
  'config',
  'directive-quotes-allowlist.txt',
);

// All-language content. File language is detected from path:
//   packages/www/src/content/{blog,docs}/<lang>/...           -> <lang>
//   private/growth/dist/nis2-directive-summary-<lang>-a4/...  -> <lang>
//   private/growth/dist/nis2-directive-summary-a4/...         -> en (legacy en-only path)
//   packages/www/src/pages/.../<file>.astro                   -> en (Astro page is single-template)
const SCAN_GLOBS = [
  'packages/www/src/content/blog/*/**/*.md',
  'packages/www/src/content/blog/*/**/*.mdx',
  'packages/www/src/content/docs/*/**/*.md',
  'packages/www/src/content/docs/*/**/*.mdx',
  'packages/www/src/pages/**/*.astro',
  'private/growth/dist/**/*.md',
];

const NIS2_MENTION_PATTERNS: RegExp[] = [
  /\bNIS\s?2\b/i,
  /Directive\s+\(EU\)\s+2022\/2555/i,
  /Directive\s+2022\/2555/i,
  /\b32022L2555\b/i,
];

// Capture an article reference plus any number of `(N)` / `(a)` modifiers.
// Accept English "Article" plus the most common EU-language equivalents so
// translated content can use the native word for "article" without losing
// the rule-A trigger. ja/ar/ru/tr/zh/ko translations keep English "Article"
// per glossary; this regex still picks them up via the case-insensitive
// English alternative. Avoid trailing `\b` after `)` because that breaks at
// the first `(` and yields a truncated match.
const ARTICLE_REF = /\b(?:Article|Artikel|art[íi]culo|articolo|artigo|artikkel|статья|статьи|Madde|المادة|条|조)\s+2[0-3](?:\([0-9a-z]+\))*/i;
const RECITAL_REF = /\bRecital\s+\d+\b/i;
const ANNEX_REF = /\bAnnex\s+(I|II|III)\b/i;

// Markers (HTML comments).
const QUOTE_MARKER = /<!--\s*nis2-quote:\s*([^-][^>]*?)\s*-->/i;
const SKIP_MARKER = /<!--\s*nis2-quote-skip:\s*([^>]*?)\s*-->/i;
// Override the snapshot the next quote is verified against. Used in non-EU
// language files (ja/ar/ru/tr/zh/ko) when the directive quote is rendered in
// English with surrounding prose explaining why.
const QUOTE_LANG_MARKER = /<!--\s*nis2-quote-lang:\s*([a-z]{2})\s*-->/i;

// Quote payload patterns.
const BLOCKQUOTE_PAT = /^>\s*"([^"]+)"\s*$/;
const INLINE_QUOTE_PAT = /"([^"\n]{20,})"/g; // require 20+ chars to skip scare-quotes

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface QuoteCase {
  file: string;
  line: number;
  rule: 'blockquote' | 'marker';
  ref: string; // e.g., "Article 21(2)(d)"
  text: string; // raw quote without surrounding "
  lang: SnapshotLang; // which snapshot to verify against (resolved after fallback)
  langSource: 'file' | 'marker' | 'fallback'; // for INFO logging
}

interface CheckResult {
  pass: QuoteCase[];
  fail: Array<QuoteCase & { reason: string; nearest?: string }>;
  skipped: Array<{ file: string; line: number; reason: string }>;
  filesScanned: number;
  filesWithMention: number;
  filesSkippedNonEnglish: string[];
  filesSkippedAllowlist: string[];
}

// ---------------------------------------------------------------------------
// Snapshot loading + normalisation
// ---------------------------------------------------------------------------

interface LoadedSnapshot {
  flatText: string;
  sha256: string;
}

function loadAllSnapshots(): Map<SnapshotLang, LoadedSnapshot> {
  const out = new Map<SnapshotLang, LoadedSnapshot>();
  const missing: SnapshotLang[] = [];
  for (const lang of SNAPSHOT_LANGS) {
    const { txt, manifest } = snapshotPath(lang);
    if (!fs.existsSync(txt)) {
      missing.push(lang);
      continue;
    }
    const text = fs.readFileSync(txt, 'utf-8');
    let sha = '';
    if (fs.existsSync(manifest)) {
      try {
        sha = String(
          JSON.parse(fs.readFileSync(manifest, 'utf-8'))['sha256'] ?? '',
        );
      } catch {
        // manifest unreadable — proceed with empty sha
      }
    }
    out.set(lang, { flatText: flatten(text), sha256: sha });
  }
  if (out.size === 0) {
    console.error(
      `FATAL: no directive snapshots found under ${path.relative(repoRoot, path.dirname(snapshotPath('en').txt))}`,
    );
    console.error(`  Run: tsx scripts/fetch-directive-snapshot.ts --all`);
    process.exit(2);
  }
  if (missing.length > 0) {
    console.warn(
      `WARN ${missing.length} snapshot(s) missing: ${missing.join(', ')}; files in those languages will fall back to English`,
    );
  }
  return out;
}

/** Aggressive flatten: collapse ALL whitespace incl. newlines to single space. */
function flatten(s: string): string {
  return (
    s
      .replace(/[‘’‚‛]/g, "'")
      .replace(/[“”„‟]/g, '"')
      .replace(/[–—―]/g, '-')
      .replace(/…/g, '...')
      .replace(/\u00a0/g, ' ')
      // ellipsis variants for fragmenting; keep [...] visible for splitting
      .replace(/\s+/g, ' ')
      .trim()
  );
}

const ELLIPSIS_SPLIT = /\s*(?:\[\.\.\.\]|\.\.\.|…)\s*/;

function fragments(quote: string): string[] {
  return flatten(quote)
    .split(ELLIPSIS_SPLIT)
    .map((f) => f.trim())
    .filter((f) => f.length > 0);
}

function levenshtein(a: string, b: string): number {
  if (a === b) return 0;
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;
  let prev = new Array(n + 1);
  for (let j = 0; j <= n; j++) prev[j] = j;
  for (let i = 1; i <= m; i++) {
    const curr = new Array(n + 1);
    curr[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = a.charCodeAt(i - 1) === b.charCodeAt(j - 1) ? 0 : 1;
      curr[j] = Math.min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
    }
    prev = curr;
  }
  return prev[n];
}

/** Find the substring of `source` of length ~= `frag.length` with the lowest
 *  Levenshtein distance to `frag`. Used only for failure messages, so we
 *  trade accuracy for speed: scan with a step of `frag.length / 4` and pad
 *  +/- 8 chars. */
function nearestSubstring(source: string, frag: string): string | undefined {
  if (!frag) return undefined;
  const len = frag.length;
  const step = Math.max(1, Math.floor(len / 4));
  let bestDist = Infinity;
  let bestStart = -1;
  // Limit search to first 6 MB to keep CI fast (snapshot is ~280 KB so this is fine).
  const cap = Math.min(source.length, 6 * 1024 * 1024);
  for (let i = 0; i + len <= cap; i += step) {
    const slice = source.slice(i, i + len);
    const dist = levenshtein(slice, frag);
    if (dist < bestDist) {
      bestDist = dist;
      bestStart = i;
      if (dist === 0) break;
    }
  }
  if (bestStart < 0) return undefined;
  // Expand to a slightly wider window so the user sees context.
  const ctxStart = Math.max(0, bestStart - 12);
  const ctxEnd = Math.min(source.length, bestStart + len + 12);
  return source.slice(ctxStart, ctxEnd).replace(/\s+/g, ' ').trim();
}

// ---------------------------------------------------------------------------
// File-level scanning
// ---------------------------------------------------------------------------

/**
 * Detect the file's content language from path. Frontmatter `language:` is
 * a sanity check only; existing translation stubs in the repo carry
 * `language: en` even when placed under a non-English folder, so the path is
 * the source of truth.
 */
function detectFileLang(filePath: string): ContentLang {
  const rel = path.relative(repoRoot, filePath).replace(/\\/g, '/');
  // packages/www/src/content/{blog,docs}/<lang>/... -> <lang>
  const wwwMatch = rel.match(/^packages\/www\/src\/content\/(?:blog|docs)\/([a-z]{2})\//);
  if (wwwMatch) {
    const lang = wwwMatch[1] as ContentLang;
    if ((ALL_CONTENT_LANGS as readonly string[]).includes(lang)) return lang;
  }
  // private/growth/dist/nis2-directive-summary-<lang>-a4/... -> <lang>
  const distMatch = rel.match(/^private\/growth\/dist\/nis2-directive-summary-([a-z]{2})-a4\//);
  if (distMatch) {
    const lang = distMatch[1] as ContentLang;
    if ((ALL_CONTENT_LANGS as readonly string[]).includes(lang)) return lang;
  }
  // private/growth/dist/nis2-directive-summary-a4/ (legacy English-only path)
  if (rel.startsWith('private/growth/dist/nis2-directive-summary-a4/')) return 'en';
  // Astro pages and any other path we walk default to English (the source
  // template is a single-template Astro file; the [lang] route param is a
  // runtime concern).
  return 'en';
}

function fileMentionsNis2(content: string): boolean {
  return NIS2_MENTION_PATTERNS.some((re) => re.test(content));
}

function previousNonBlankLines(lines: string[], idx: number, n: number): string[] {
  const out: string[] = [];
  for (let i = idx - 1; i >= 0 && out.length < n; i--) {
    const trimmed = (lines[i] ?? '').trim();
    if (trimmed.length === 0) continue;
    out.push(trimmed);
  }
  return out;
}

function lineHasArticleContext(line: string): boolean {
  return ARTICLE_REF.test(line) || RECITAL_REF.test(line) || ANNEX_REF.test(line);
}

function extractArticleRef(line: string): string | null {
  const a = line.match(ARTICLE_REF);
  if (a) return a[0];
  const r = line.match(RECITAL_REF);
  if (r) return r[0];
  const x = line.match(ANNEX_REF);
  if (x) return x[0];
  return null;
}

function extractQuotesFromFile(
  filePath: string,
  fileLang: ContentLang,
): {
  quotes: QuoteCase[];
  skipped: Array<{ file: string; line: number; reason: string }>;
} {
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split('\n');
  const rel = path.relative(repoRoot, filePath);
  const quotes: QuoteCase[] = [];
  const skipped: Array<{ file: string; line: number; reason: string }> = [];

  // The default snapshot for this file: own snapshot if vendored, else English.
  const defaultSnapshot = snapshotForLang(fileLang);
  const defaultLangSource: 'file' | 'fallback' =
    defaultSnapshot === fileLang ? 'file' : 'fallback';

  function resolveLang(line: string, prevLine: string): {
    lang: SnapshotLang;
    source: 'file' | 'marker' | 'fallback';
  } {
    const m = line.match(QUOTE_LANG_MARKER) ?? prevLine.match(QUOTE_LANG_MARKER);
    if (m) {
      const requested = m[1]!.toLowerCase() as SnapshotLang;
      if ((SNAPSHOT_LANGS as readonly string[]).includes(requested)) {
        return { lang: requested, source: 'marker' };
      }
    }
    return { lang: defaultSnapshot, source: defaultLangSource };
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? '';
    const prevLine = (lines[i - 1] ?? '').trim();

    // Rule A: blockquote with leading `>` and "..." payload.
    const blockMatch = line.match(BLOCKQUOTE_PAT);
    if (blockMatch) {
      const text = blockMatch[1] ?? '';
      // Look at the next-prev 3 non-blank lines for an article ref.
      const prevs = previousNonBlankLines(lines, i, 3);
      const refLine = prevs.find((p) => lineHasArticleContext(p));
      if (refLine) {
        // Check for an explicit skip marker on this line or the previous line.
        const skipHere = line.match(SKIP_MARKER);
        const skipPrev = prevLine.match(SKIP_MARKER);
        if (skipHere || skipPrev) {
          const reason = (skipHere?.[1] ?? skipPrev?.[1] ?? 'skipped').trim();
          skipped.push({ file: rel, line: i + 1, reason });
          continue;
        }
        const ref = extractArticleRef(refLine) ?? 'unknown';
        const { lang, source } = resolveLang(line, prevLine);
        quotes.push({
          file: rel,
          line: i + 1,
          rule: 'blockquote',
          ref,
          text,
          lang,
          langSource: source,
        });
        continue;
      }
    }

    // Rule B: explicit nis2-quote marker on this line or the previous line.
    const trimmed = line.trim();
    const markerHere = line.match(QUOTE_MARKER);
    const markerPrev = prevLine.match(QUOTE_MARKER);
    if (!markerHere && !markerPrev) continue;
    // Skip-marker takes precedence.
    if (line.match(SKIP_MARKER) || prevLine.match(SKIP_MARKER)) {
      const reason =
        line.match(SKIP_MARKER)?.[1] ??
        prevLine.match(SKIP_MARKER)?.[1] ??
        'skipped';
      skipped.push({ file: rel, line: i + 1, reason: reason.trim() });
      continue;
    }
    const ref = (markerHere?.[1] ?? markerPrev?.[1] ?? 'unknown').trim();
    if (markerPrev && trimmed.length === 0) continue;
    INLINE_QUOTE_PAT.lastIndex = 0;
    const m = INLINE_QUOTE_PAT.exec(line);
    const { lang, source } = resolveLang(line, prevLine);
    if (!m) {
      // Marker placed but no inline quote follows. Fail closed.
      quotes.push({
        file: rel,
        line: i + 1,
        rule: 'marker',
        ref,
        text: '<<no quote text on or after marker>>',
        lang,
        langSource: source,
      });
      continue;
    }
    const text = m[1] ?? '';
    quotes.push({
      file: rel,
      line: i + 1,
      rule: 'marker',
      ref,
      text,
      lang,
      langSource: source,
    });
  }

  return { quotes, skipped };
}

// ---------------------------------------------------------------------------
// Verification
// ---------------------------------------------------------------------------

function verifyQuote(
  q: QuoteCase,
  source: string,
): { ok: true } | { ok: false; reason: string; nearest?: string } {
  if (q.text === '<<no quote text on or after marker>>') {
    return {
      ok: false,
      reason:
        'nis2-quote marker is dangling: no inline "..." quote of length >=20 was found on or right after the marker. Either add the quote, drop the marker, or use nis2-quote-skip.',
    };
  }
  const frags = fragments(q.text);
  if (frags.length === 0) {
    return { ok: false, reason: 'empty fragments after normalisation' };
  }
  let cursor = 0;
  for (let i = 0; i < frags.length; i++) {
    const frag = frags[i]!;
    const found = source.indexOf(frag, cursor);
    if (found < 0) {
      const nearest = nearestSubstring(source.slice(cursor), frag);
      return {
        ok: false,
        reason: `fragment ${i + 1}/${frags.length} not found in source after position ${cursor}: "${frag.slice(0, 80)}${frag.length > 80 ? '...' : ''}"`,
        nearest,
      };
    }
    cursor = found + frag.length;
  }
  return { ok: true };
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  // Validate allowlist BLOCKER reasons (fail-closed if anyone forgets).
  let allowlistedPaths = new Set<string>();
  if (fs.existsSync(ALLOWLIST_PATH)) {
    const entries = parseBlockeredList(ALLOWLIST_PATH);
    const failures = verifyAllBlockers(entries, path.relative(repoRoot, ALLOWLIST_PATH));
    if (failures.length > 0) {
      console.error('FATAL: allowlist entries fail BLOCKER validation:');
      failures.forEach((f) => console.error(f));
      process.exit(2);
    }
    allowlistedPaths = new Set(entries.map((e) => e.entry));
  }

  const snapshots = loadAllSnapshots();
  console.log(
    `scanning markdown/Astro under ${SCAN_GLOBS.length} globs; ${snapshots.size} snapshot(s) loaded (${[...snapshots.keys()].join(', ')})`,
  );

  const result: CheckResult = {
    pass: [],
    fail: [],
    skipped: [],
    filesScanned: 0,
    filesWithMention: 0,
    filesSkippedNonEnglish: [],
    filesSkippedAllowlist: [],
  };

  const seenFiles = new Set<string>();
  for (const g of SCAN_GLOBS) {
    for (const file of globSync(g, { cwd: repoRoot, nodir: true, absolute: true })) {
      seenFiles.add(file);
    }
  }
  result.filesScanned = seenFiles.size;

  // Track per-file fallback notice (one INFO line per non-EU language file).
  const fallbackFiles = new Map<string, ContentLang>();

  for (const file of seenFiles) {
    const rel = path.relative(repoRoot, file);
    if (allowlistedPaths.has(rel)) {
      result.filesSkippedAllowlist.push(rel);
      continue;
    }
    const content = fs.readFileSync(file, 'utf-8');
    if (!fileMentionsNis2(content)) continue;
    result.filesWithMention++;

    const fileLang = detectFileLang(file);
    const resolvedSnapshot = snapshotForLang(fileLang);
    if (resolvedSnapshot !== fileLang) {
      fallbackFiles.set(rel, fileLang);
    }

    const { quotes, skipped } = extractQuotesFromFile(file, fileLang);
    result.skipped.push(...skipped);
    for (const q of quotes) {
      const snap = snapshots.get(q.lang);
      if (!snap) {
        result.fail.push({
          ...q,
          reason: `snapshot for lang=${q.lang} is not vendored; cannot verify`,
        });
        continue;
      }
      const v = verifyQuote(q, snap.flatText);
      if (v.ok) result.pass.push(q);
      else result.fail.push({ ...q, reason: v.reason, nearest: v.nearest });
    }
  }

  // Report.
  console.log(
    `${result.filesWithMention} files mention NIS2; ${result.filesSkippedAllowlist.length} allowlisted`,
  );
  if (fallbackFiles.size > 0) {
    console.log(
      `${fallbackFiles.size} file(s) use English snapshot as fallback (no official directive translation in their language):`,
    );
    for (const [f, l] of fallbackFiles) console.log(`  INFO ${f} (${l} → en)`);
  }
  for (const p of result.pass) {
    const fragCount = fragments(p.text).length;
    const langTag =
      p.langSource === 'fallback'
        ? `${p.lang} (fallback)`
        : p.langSource === 'marker'
          ? `${p.lang} (marker)`
          : p.lang;
    console.log(
      `OK   ${p.file}:${p.line} ${p.ref} [${langTag}] (${flatten(p.text).length} chars / ${fragCount} fragment${fragCount === 1 ? '' : 's'})`,
    );
  }
  for (const s of result.skipped) {
    console.log(`SKIP ${s.file}:${s.line} ${s.reason}`);
  }
  for (const f of result.fail) {
    console.error(`FAIL ${f.file}:${f.line} ${f.ref} [${f.lang}]`);
    console.error(`     ${f.reason}`);
    if (f.nearest) {
      console.error(`     nearest source substring: "${f.nearest}"`);
    }
  }

  console.log(
    `\n${result.pass.length} verified, ${result.fail.length} failed, ${result.skipped.length} skipped (skip-marker)`,
  );
  process.exit(result.fail.length > 0 ? 1 : 0);
}

main();

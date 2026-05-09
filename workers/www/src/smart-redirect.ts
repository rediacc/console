/**
 * Smart 404 Redirect — score-based fuzzy URL matching.
 *
 * When a visitor hits a 404, this module scores all known routes against the
 * requested path and returns the best match (if above threshold) for a 302
 * redirect. The route manifest is auto-generated at build time.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RouteEntry {
  path: string; // e.g., "/docs/installation"
  title: string; // e.g., "Installation"
  section: string; // "docs" | "blog" | "solutions" | ""
  slug: string; // e.g., "installation"
  keywords: string[]; // e.g., ["installation"]
}

interface SmartRedirectResult {
  url: string;
  score: number;
}

interface ParsedRequest {
  lang: string;
  pathWithoutLang: string;
  section: string;
  slug: string;
  keywords: string[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SUPPORTED_LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh', 'et', 'ko', 'pt', 'it'];
const REDIRECT_THRESHOLD = 50;
const FILE_EXT_RE = /\.\w{2,5}$/;
const SKIP_PREFIXES = ['/account', '/assets', '/fonts', '/_astro', '/api', '/json'];

// ---------------------------------------------------------------------------
// Manifest cache
// ---------------------------------------------------------------------------

let manifestCache: RouteEntry[] | null = null;

async function loadManifest(assets: Fetcher): Promise<RouteEntry[]> {
  if (manifestCache) return manifestCache;

  try {
    const response = await assets.fetch('https://assets.local/route-manifest.json');
    if (!response.ok) return [];
    manifestCache = (await response.json()) as RouteEntry[];
  } catch {
    manifestCache = [];
  }
  return manifestCache;
}

// ---------------------------------------------------------------------------
// URL parsing
// ---------------------------------------------------------------------------

function parseRequestPath(pathname: string): ParsedRequest {
  // Strip trailing slash and lowercase
  const clean = pathname.replace(/\/+$/, '').toLowerCase() || '/';
  const segments = clean.split('/').filter(Boolean);

  // Detect language prefix
  let lang = 'en';
  let rest = segments;
  if (segments.length > 0 && SUPPORTED_LANGUAGES.includes(segments[0])) {
    lang = segments[0];
    rest = segments.slice(1);
  }

  const knownSections = ['docs', 'blog', 'solutions'];
  let section = '';
  let slugParts = rest;

  if (rest.length > 0 && knownSections.includes(rest[0])) {
    section = rest[0];
    slugParts = rest.slice(1);
  }

  const slug = slugParts.join('/');
  const pathWithoutLang = '/' + rest.join('/');
  const keywords = slug.split(/[-/]/).filter((k) => k.length > 2);

  return { lang, pathWithoutLang, section, slug, keywords };
}

// ---------------------------------------------------------------------------
// Scoring helpers
// ---------------------------------------------------------------------------

function levenshtein(a: string, b: string): number {
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;

  let prev = Array.from({ length: n + 1 }, (_, i) => i);
  let curr = new Array<number>(n + 1);

  for (let i = 1; i <= m; i++) {
    curr[0] = i;
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
    }
    [prev, curr] = [curr, prev];
  }
  return prev[n];
}

function jaccard(a: Set<string>, b: Set<string>): number {
  let intersection = 0;
  for (const item of a) {
    if (b.has(item)) intersection++;
  }
  const union = a.size + b.size - intersection;
  return union === 0 ? 0 : intersection / union;
}

// ---------------------------------------------------------------------------
// Main scoring
// ---------------------------------------------------------------------------

function scoreCandidate(req: ParsedRequest, candidate: RouteEntry): number {
  let score = 0;

  // Signal 1: Exact slug match (50 points)
  if (req.slug && req.slug === candidate.slug) {
    score += 50;
  }

  // Signal 2: Levenshtein slug similarity (0-35 points)
  if (score < 50 && req.slug && candidate.slug) {
    const dist = levenshtein(req.slug, candidate.slug);
    const maxLen = Math.max(req.slug.length, candidate.slug.length);
    if (maxLen > 0 && dist <= 3 && dist / maxLen <= 0.4) {
      score += Math.round(35 * (1 - dist / maxLen));
    }
  }

  // Signal 3: Path segment Jaccard (0-20 points)
  const reqSegments = new Set(req.pathWithoutLang.split(/[-/]/).filter(Boolean));
  const candSegments = new Set(candidate.path.split(/[-/]/).filter(Boolean));
  score += Math.round(20 * jaccard(reqSegments, candSegments));

  // Signal 4: Title keyword overlap (0-15 points)
  if (req.keywords.length > 0) {
    const titleLower = candidate.title.toLowerCase();
    const matching = req.keywords.filter((k) => titleLower.includes(k)).length;
    score += Math.round(15 * (matching / req.keywords.length));
  }

  // Signal 5: Same section (10 points)
  if (req.section && req.section === candidate.section) {
    score += 10;
  }

  // Signal 6: Language boost (5 points -- manifest is lang-agnostic)
  score += 5;

  return score;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function findSmartRedirect(
  pathname: string,
  assets: Fetcher
): Promise<SmartRedirectResult | null> {
  // Guard: skip file-like paths (CSS, JS, images, fonts)
  if (FILE_EXT_RE.test(pathname)) return null;

  // Guard: skip non-content paths
  const lower = pathname.toLowerCase();
  for (const prefix of SKIP_PREFIXES) {
    if (lower.startsWith(prefix)) return null;
  }

  const manifest = await loadManifest(assets);
  if (manifest.length === 0) return null;

  const req = parseRequestPath(pathname);

  // Guard: empty slug (homepage-like) -- never redirect
  if (!req.slug) return null;

  let bestScore = 0;
  let bestEntry: RouteEntry | null = null;

  for (const candidate of manifest) {
    const score = scoreCandidate(req, candidate);
    if (score > bestScore) {
      bestScore = score;
      bestEntry = candidate;
    }
  }

  if (bestScore < REDIRECT_THRESHOLD || !bestEntry) return null;

  // Reconstruct URL with detected language
  const langPrefix = req.lang === 'en' ? '/en' : `/${req.lang}`;
  const url = `${langPrefix}${bestEntry.path}`;

  return { url, score: bestScore };
}

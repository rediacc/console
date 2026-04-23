import { describe, test, expect, vi, beforeEach } from 'vitest';
import worker, { normalizePath, detectLanguage } from '../index';

// Minimal Env stub. DB is only needed when /account/api/* is exercised;
// tests that don't hit that branch omit it (matches stable/edge shape).
function mkEnv(assetResponder: (req: Request) => Response): { ASSETS: Fetcher; DB?: unknown } {
  const ASSETS: Fetcher = {
    fetch: vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = input instanceof Request ? input : new Request(input, init);
      return assetResponder(req);
    }) as unknown as Fetcher['fetch'],
    connect: vi.fn() as unknown as Fetcher['connect'],
  };
  return { ASSETS };
}

function hit(path: string, env: ReturnType<typeof mkEnv>, host = 'www.rediacc.com'): Promise<Response> {
  const req = new Request(`https://${host}${path}`);
  return worker.fetch(req, env as unknown as Parameters<typeof worker.fetch>[1]);
}

describe('normalizePath', () => {
  test('strips trailing slash', () => {
    expect(normalizePath('/foo/')).toEqual({ path: '/foo', changed: true });
  });
  test('keeps root /', () => {
    expect(normalizePath('/')).toEqual({ path: '/', changed: false });
  });
  test('strips .html', () => {
    expect(normalizePath('/foo.html')).toEqual({ path: '/foo', changed: true });
  });
  test('strips .md', () => {
    expect(normalizePath('/foo.md')).toEqual({ path: '/foo', changed: true });
  });
  test('lowercases', () => {
    expect(normalizePath('/FOO/Bar')).toEqual({ path: '/foo/bar', changed: true });
  });
  test('collapses double slashes', () => {
    expect(normalizePath('/foo//bar')).toEqual({ path: '/foo/bar', changed: true });
  });
  test('no change for already canonical', () => {
    expect(normalizePath('/en/docs/installation')).toEqual({
      path: '/en/docs/installation',
      changed: false,
    });
  });
  test('preserves percent-encoded UTF-8 triples (does not lowercase them)', () => {
    // RFC 3986 says %XX is case-insensitive, but CF ASSETS re-encodes to
    // uppercase. If we lowercased the whole path we'd trigger a redirect
    // loop (%C3%B3 -> %c3%b3 -> ASSETS -> %C3%B3 -> ...). Surrounding ASCII
    // still lowercases.
    expect(normalizePath('/ES/Blog/Tags/configuraci%C3%B3n')).toEqual({
      path: '/es/blog/tags/configuraci%C3%B3n',
      changed: true,
    });
  });
  test('preserves already-lowercase paths with percent triples', () => {
    expect(normalizePath('/es/blog/tags/configuraci%C3%B3n')).toEqual({
      path: '/es/blog/tags/configuraci%C3%B3n',
      changed: false,
    });
  });
});

describe('detectLanguage', () => {
  test('detects /en/ prefix', () => {
    expect(detectLanguage('/en/docs/foo')).toEqual({ lang: 'en', pathWithoutLang: '/docs/foo' });
  });
  test('detects /ja/ prefix', () => {
    expect(detectLanguage('/ja/solutions/x')).toEqual({ lang: 'ja', pathWithoutLang: '/solutions/x' });
  });
  test('unrecognized 2-letter prefix is not a language', () => {
    // "xx" is not in SUPPORTED_LANGUAGES
    expect(detectLanguage('/xx/foo')).toEqual({ lang: null, pathWithoutLang: '/xx/foo' });
  });
  test('no prefix', () => {
    expect(detectLanguage('/docs/foo')).toEqual({ lang: null, pathWithoutLang: '/docs/foo' });
  });
  test('/en alone', () => {
    expect(detectLanguage('/en')).toEqual({ lang: 'en', pathWithoutLang: '/' });
  });
});

describe('fetch handler — 404 recovery integration', () => {
  let env: ReturnType<typeof mkEnv>;

  beforeEach(() => {
    // ASSETS returns 404 by default — forces the Worker to consult the alias table.
    env = mkEnv(() => new Response('not found', { status: 404 }));
  });

  test('trailing slash canonicalization: /en/docs/installation/ -> 301 /en/docs/installation', async () => {
    const res = await hit('/en/docs/installation/', env);
    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('https://www.rediacc.com/en/docs/installation');
    expect(res.headers.get('X-Redirect-Reason')).toBe('canonicalize');
  });

  test('.html suffix strip: /en/docs/installation.html -> 301', async () => {
    const res = await hit('/en/docs/installation.html', env);
    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('https://www.rediacc.com/en/docs/installation');
  });

  test('root -> default lang: / -> 301 /en', async () => {
    const res = await hit('/', env);
    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('https://www.rediacc.com/en');
  });

  test('root preserves query: /?foo=bar -> 301 /en?foo=bar', async () => {
    const res = await hit('/?foo=bar', env);
    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('https://www.rediacc.com/en?foo=bar');
  });

  test('curated exact rule with lang: /en/docs/cli-reference -> 301 /en/docs/cli-application', async () => {
    const res = await hit('/en/docs/cli-reference', env);
    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('https://www.rediacc.com/en/docs/cli-application');
    expect(res.headers.get('X-Redirect-Reason')).toBe('curated-exact');
  });

  test('curated exact rule with ja lang preserved: /ja/solutions/data-security -> 301 /ja/solutions/encryption', async () => {
    const res = await hit('/ja/solutions/data-security', env);
    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('https://www.rediacc.com/ja/solutions/encryption');
  });

  test('no lang -> default lang added: /docs/cli-reference -> 301 /en/docs/cli-application', async () => {
    const res = await hit('/docs/cli-reference', env);
    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('https://www.rediacc.com/en/docs/cli-application');
  });

  test('410 for deleted blog post: /en/blog/advanced-task-workflows', async () => {
    const res = await hit('/en/blog/advanced-task-workflows', env);
    expect(res.status).toBe(410);
  });

  test('410 for blog tag phantom: /en/blog/tags/welcome', async () => {
    const res = await hit('/en/blog/tags/welcome', env);
    expect(res.status).toBe(410);
  });

  test('rdc-cheat-sheet pattern: /en/docs/rdc-cheat-sheet/setup -> 301 /en/docs/rdc-cheat-sheet', async () => {
    const res = await hit('/en/docs/rdc-cheat-sheet/setup', env);
    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('https://www.rediacc.com/en/docs/rdc-cheat-sheet');
    expect(res.headers.get('X-Redirect-Reason')).toBe('curated-pattern');
  });

  test('contact-typo pattern: /trntact -> 301 /en/contact', async () => {
    const res = await hit('/trntact', env);
    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('https://www.rediacc.com/en/contact');
  });

  test('console pattern: /console -> 301 /account (no lang prefix)', async () => {
    const res = await hit('/console', env);
    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('https://www.rediacc.com/account');
  });

  test('console pattern preserves query string: /console/login?register=manual -> /account?register=manual', async () => {
    const res = await hit('/console/login?register=manual', env);
    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('https://www.rediacc.com/account?register=manual');
  });

  test('legal concat pattern: /en/cookie-policy/telemetry-policy -> 301 /en/telemetry-policy', async () => {
    const res = await hit('/en/cookie-policy/telemetry-policy', env);
    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('https://www.rediacc.com/en/telemetry-policy');
  });

  test('EXACT wins over PATTERN: /en/terms-of-service/acceptable-use-policy -> 410 (not /en/acceptable-use-policy)', async () => {
    const res = await hit('/en/terms-of-service/acceptable-use-policy', env);
    expect(res.status).toBe(410);
  });

  test('self-redirect guard: /en/checkout/success does NOT infinite-loop', async () => {
    // Rule /checkout/success -> /checkout/success exists to add lang when missing.
    // When lang is already present, the Worker must fall through to ASSETS
    // instead of 301-looping to itself.
    const successEnv = mkEnv((req) => {
      const url = new URL(req.url);
      if (url.pathname === '/en/checkout/success') return new Response('ok', { status: 200 });
      return new Response('not found', { status: 404 });
    });
    const res = await hit('/en/checkout/success', successEnv);
    expect(res.status).toBe(200);
  });

  test('self-redirect from no-lang: /checkout/success -> 301 /en/checkout/success', async () => {
    const res = await hit('/checkout/success', env);
    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('https://www.rediacc.com/en/checkout/success');
  });

  test('live page passes through: /en/docs/installation -> 200 from ASSETS', async () => {
    const liveEnv = mkEnv((req) => {
      const url = new URL(req.url);
      if (url.pathname === '/en/docs/installation') return new Response('live page', { status: 200 });
      return new Response('not found', { status: 404 });
    });
    const res = await hit('/en/docs/installation', liveEnv);
    expect(res.status).toBe(200);
  });

  test('unmatched 404 with no fuzzy match falls through to 404', async () => {
    // ASSETS 404 + no alias rule + smart-redirect returns null (manifest lookup fails in test env)
    const res = await hit('/en/totally-made-up-path', env);
    expect(res.status).toBe(404);
  });
});

describe('fetch handler — static asset paths (case-preserving)', () => {
  // Regression: normalizePath used to lowercase hashed asset filenames
  // (client.BzZdRM54.js, Inter-Regular.woff2), 301-redirecting to paths that
  // don't exist on disk. The asset-path guard must forward to ASSETS with the
  // exact case intact.

  function capture(pathname: string, expectedUrl: string) {
    const captured: string[] = [];
    const env = mkEnv((req) => {
      captured.push(new URL(req.url).pathname);
      return new Response('asset', { status: 200 });
    });
    return { env, captured, run: () => hit(pathname, env).then((r) => ({ res: r, captured, expectedUrl })) };
  }

  test('/assets/<mixed-case-hash>.js preserves case', async () => {
    const { run } = capture('/assets/client.BzZdRM54.js', '/assets/client.BzZdRM54.js');
    const { res, captured } = await run();
    expect(res.status).toBe(200);
    expect(captured).toEqual(['/assets/client.BzZdRM54.js']);
  });

  test('/fonts/inter/Inter-Regular.woff2 preserves case', async () => {
    const { run } = capture('/fonts/inter/Inter-Regular.woff2', '/fonts/inter/Inter-Regular.woff2');
    const { res, captured } = await run();
    expect(res.status).toBe(200);
    expect(captured).toEqual(['/fonts/inter/Inter-Regular.woff2']);
  });

  test('/fonts/jetbrains-mono/JetBrainsMono-Bold.woff2 preserves case', async () => {
    const path = '/fonts/jetbrains-mono/JetBrainsMono-Bold.woff2';
    const { run } = capture(path, path);
    const { res, captured } = await run();
    expect(res.status).toBe(200);
    expect(captured).toEqual([path]);
  });

  test('/_astro/<hashed>.css preserves case', async () => {
    const { run } = capture('/_astro/index.ABC123.css', '/_astro/index.ABC123.css');
    const { res, captured } = await run();
    expect(res.status).toBe(200);
    expect(captured).toEqual(['/_astro/index.ABC123.css']);
  });

  test('/scripts/main.js is served directly (not normalized)', async () => {
    const { run } = capture('/scripts/main.js', '/scripts/main.js');
    const { res, captured } = await run();
    expect(res.status).toBe(200);
    expect(captured).toEqual(['/scripts/main.js']);
  });

  test('content paths are still normalized (guard does not over-broaden)', async () => {
    // /FOO is not under an asset directory — normalizePath must still lowercase it.
    const env = mkEnv(() => new Response('not found', { status: 404 }));
    const res = await hit('/FOO', env);
    expect(res.status).toBe(301);
    expect(res.headers.get('Location')).toBe('https://www.rediacc.com/foo');
    expect(res.headers.get('X-Redirect-Reason')).toBe('canonicalize');
  });
});

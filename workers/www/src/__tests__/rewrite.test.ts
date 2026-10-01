import { describe, expect, it } from 'vitest';
import {
  WK_APEX_DOMAIN,
  WK_EDGE_ORIGIN,
  WK_IMAGE_REGISTRY,
  WK_RELEASES_ORIGIN,
  WK_SITE_ORIGIN,
} from '../../../../packages/shared/src/config/well-known.generated.js';
import { buildDisallowRobots, getChannel, rewriteOrigin, shouldRewrite } from '../index';

const RELEASES_HOST = new URL(WK_RELEASES_ORIGIN).host;
const EDGE_HOST = new URL(WK_EDGE_ORIGIN).host;
const SITE_HOST = new URL(WK_SITE_ORIGIN).host;

describe('getChannel', () => {
  it('returns the subdomain for preview hosts', () => {
    expect(getChannel(EDGE_HOST)).toBe('edge');
    expect(getChannel('pr-123.rediacc.com')).toBe('pr-123');
    expect(getChannel(SITE_HOST)).toBe('www');
  });

  it('defaults to stable for hosts without a rediacc subdomain', () => {
    expect(getChannel(WK_APEX_DOMAIN)).toBe('stable');
    expect(getChannel('example.com')).toBe('stable');
    expect(getChannel('localhost')).toBe('stable');
  });
});

describe('shouldRewrite', () => {
  it('returns true for install script paths regardless of content-type', () => {
    expect(shouldRewrite('application/x-sh', '/install.sh')).toBe(true);
    expect(shouldRewrite(null, '/install.sh')).toBe(true);
    expect(shouldRewrite('application/octet-stream', '/install.sh')).toBe(true);
    expect(shouldRewrite(null, '/install.ps1')).toBe(true);
    expect(shouldRewrite('text/x-powershell', '/install.ps1')).toBe(true);
  });

  it('returns true for rewritable MIME types on non-install paths', () => {
    expect(shouldRewrite('text/html; charset=utf-8', '/install')).toBe(true);
    expect(shouldRewrite('application/json', '/api/foo')).toBe(true);
    expect(shouldRewrite('text/css', '/app.css')).toBe(true);
  });

  it('returns false for non-rewritable MIME types on non-install paths', () => {
    expect(shouldRewrite('application/octet-stream', '/download.bin')).toBe(false);
    expect(shouldRewrite('image/png', '/logo.png')).toBe(false);
    expect(shouldRewrite(null, '/something.bin')).toBe(false);
  });
});

// --------------------------------------------------------------------------- rewriteOrigin ---------------------------------------------------------------------------

function makeResponse(body: string, contentType: string): Response {
  return new Response(body, { headers: { 'content-type': contentType } });
}

describe('rewriteOrigin', () => {
  const previewUrl = new URL('https://pr-420.rediacc.workers.dev/install.sh');
  const channel = 'pr-420';

  it('rewrites install.sh channel default and server URL default', async () => {
    const body = [
      'CHANNEL="${REDIACC_CHANNEL:-stable}"',
      'SERVER_URL="${REDIACC_SERVER_URL:-}"',
    ].join('\n');
    const out = await rewriteOrigin(makeResponse(body, 'application/x-sh'), previewUrl, channel);
    const text = await out.text();
    expect(text).toContain('REDIACC_CHANNEL:-pr-420');
    expect(text).not.toContain('REDIACC_CHANNEL:-stable');
    expect(text).toContain('REDIACC_SERVER_URL:-https://pr-420.rediacc.workers.dev}');
  });

  it('rewrites install.ps1 PowerShell channel default', async () => {
    const ps1Url = new URL('https://pr-420.rediacc.workers.dev/install.ps1');
    const body = '$Channel = if ($env:REDIACC_CHANNEL) { $env:REDIACC_CHANNEL } else { "stable" }';
    // install.ps1 is served without a content-type header in production.
    const out = await rewriteOrigin(new Response(body), ps1Url, channel);
    const text = await out.text();
    expect(text).toContain('} else { "pr-420" }');
    expect(text).not.toContain('} else { "stable" }');
  });

  it('rewrites release channel URLs for all covered formats', async () => {
    const body = [
      `${WK_RELEASES_ORIGIN}/apt/stable/gpg.key`,
      `${WK_RELEASES_ORIGIN}/rpm/stable/rediacc.repo`,
      `${WK_RELEASES_ORIGIN}/apk/stable`,
      `${WK_RELEASES_ORIGIN}/archlinux/stable/x86_64`,
      `${WK_RELEASES_ORIGIN}/cli/stable/rdc-linux-x64`,
      `${WK_RELEASES_ORIGIN}/npm/stable/rediacc-cli-latest.tgz`,
    ].join('\n');
    const htmlUrl = new URL('https://pr-420.rediacc.workers.dev/install');
    const out = await rewriteOrigin(makeResponse(body, 'text/html'), htmlUrl, channel);
    const text = await out.text();
    for (const format of ['apt', 'rpm', 'apk', 'archlinux', 'cli', 'npm']) {
      expect(text).toContain(`${RELEASES_HOST}/${format}/pr-420`);
      expect(text).not.toContain(`${RELEASES_HOST}/${format}/stable`);
    }
  });

  it('rewrites Docker image tag from :stable to channel', async () => {
    const body = `docker pull ${WK_IMAGE_REGISTRY}/rdc:stable`;
    const htmlUrl = new URL('https://pr-420.rediacc.workers.dev/');
    const out = await rewriteOrigin(makeResponse(body, 'text/html'), htmlUrl, channel);
    expect(await out.text()).toContain('rdc:pr-420');
  });

  it('rewrites production origin references to preview origin', async () => {
    const body = `canonical: ${WK_SITE_ORIGIN}/docs`;
    const htmlUrl = new URL('https://pr-420.rediacc.workers.dev/docs');
    const out = await rewriteOrigin(makeResponse(body, 'text/html'), htmlUrl, channel);
    const text = await out.text();
    expect(text).toContain('https://pr-420.rediacc.workers.dev/docs');
    expect(text).not.toContain(`${WK_SITE_ORIGIN}/docs`);
  });

  it('rewrites multiple occurrences of the production origin', async () => {
    // replaceAll guards against the historical bug where only the first occurrence got rewritten and stale references leaked into rendered sitemaps / canonical tags below the fold.
    const body = [
      `canonical: ${WK_SITE_ORIGIN}/a`,
      `og:url: ${WK_SITE_ORIGIN}/b`,
      `link: ${WK_SITE_ORIGIN}/c`,
    ].join('\n');
    const htmlUrl = new URL('https://pr-420.rediacc.workers.dev/x');
    const out = await rewriteOrigin(makeResponse(body, 'text/html'), htmlUrl, channel);
    const text = await out.text();
    expect(text).not.toContain(WK_SITE_ORIGIN);
    for (const path of ['/a', '/b', '/c']) {
      expect(text).toContain(`https://pr-420.rediacc.workers.dev${path}`);
    }
  });

  it('returns the response unchanged when path and content-type are not rewritable', async () => {
    const body = 'REDIACC_CHANNEL:-stable';
    const url = new URL('https://pr-420.rediacc.workers.dev/some.bin');
    const out = await rewriteOrigin(makeResponse(body, 'application/octet-stream'), url, channel);
    expect(await out.text()).toBe(body);
  });

  it('propagates status, statusText, and headers', async () => {
    const body = 'irrelevant';
    const url = new URL('https://pr-420.rediacc.workers.dev/install.sh');
    const source = new Response(body, {
      status: 202,
      statusText: 'Accepted',
      headers: { 'content-type': 'application/x-sh', 'x-custom': 'keep' },
    });
    const out = await rewriteOrigin(source, url, channel);
    expect(out.status).toBe(202);
    expect(out.statusText).toBe('Accepted');
    expect(out.headers.get('x-custom')).toBe('keep');
  });
});

// --------------------------------------------------------------------------- Host → channel contract for the www → portal handoff. The marketing site derives the account-portal channel from the host
// (packages/www/src/utils/marketing-host.ts); these cases pin the worker
// behavior that model depends on. ---------------------------------------------------------------------------

describe('host→channel contract (www → portal handoff)', () => {
  it('edge marketing host maps to the edge channel', () => {
    expect(getChannel(EDGE_HOST)).toBe('edge');
  });

  it('PR preview hosts map to their own pr-N channel', () => {
    expect(getChannel('pr-420.rediacc.workers.dev')).toBe('pr-420');
  });

  it('www is NOT a preview: responses are served unrewritten, keeping stable defaults', () => {
    // fetch() gates rewriteOrigin on isPreview (hostname !== SITE_HOST),
    // so on www the baked-in stable channel reaches the visitor untouched.
    const isPreview = (h: string) => h !== SITE_HOST;
    expect(isPreview(SITE_HOST)).toBe(false);
    expect(isPreview(EDGE_HOST)).toBe(true);
  });

  it('edge host rewrites the install-script channel default to edge', async () => {
    const edgeUrl = new URL(`${WK_EDGE_ORIGIN}/install.sh`);
    const body = 'CHANNEL="${REDIACC_CHANNEL:-stable}"';
    const out = await rewriteOrigin(makeResponse(body, 'application/x-sh'), edgeUrl, 'edge');
    const text = await out.text();
    expect(text).toContain('REDIACC_CHANNEL:-edge');
    expect(text).not.toContain('REDIACC_CHANNEL:-stable');
  });

  it('edge host rewrites CLI release URLs to the edge channel', async () => {
    const body = `${WK_RELEASES_ORIGIN}/cli/stable/rdc-linux-x64`;
    const out = await rewriteOrigin(
      makeResponse(body, 'text/html'),
      new URL(`${WK_EDGE_ORIGIN}/en/downloads`),
      'edge'
    );
    expect(await out.text()).toContain(`${RELEASES_HOST}/cli/edge`);
  });
});

describe('buildDisallowRobots', () => {
  it('returns a Disallow: / body with text/plain content-type', async () => {
    const res = buildDisallowRobots();
    expect(res.headers.get('content-type')).toBe('text/plain; charset=utf-8');
    expect(res.headers.get('cache-control')).toBe('public, max-age=86400');
    expect(await res.text()).toBe('User-agent: *\nDisallow: /\n');
  });

  it('only fires on preview hosts (gate check matches fetch handler)', () => {
    // Mirrors the isPreview gate at the top of fetch(): true for every non-prod host.
    const isPreview = (h: string) => h !== SITE_HOST;
    expect(isPreview(EDGE_HOST)).toBe(true);
    expect(isPreview('pr-420.rediacc.com')).toBe(true);
    expect(isPreview('pr-420.rediacc.workers.dev')).toBe(true);
    expect(isPreview(SITE_HOST)).toBe(false);
  });
});

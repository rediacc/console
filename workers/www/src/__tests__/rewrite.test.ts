import { describe, expect, it } from 'vitest';
import { getChannel, rewriteOrigin, shouldRewrite } from '../index';

describe('getChannel', () => {
  it('returns the subdomain for preview hosts', () => {
    expect(getChannel('edge.rediacc.com')).toBe('edge');
    expect(getChannel('pr-123.rediacc.com')).toBe('pr-123');
    expect(getChannel('www.rediacc.com')).toBe('www');
  });

  it('defaults to stable for hosts without a rediacc subdomain', () => {
    expect(getChannel('rediacc.com')).toBe('stable');
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

// ---------------------------------------------------------------------------
// rewriteOrigin
// ---------------------------------------------------------------------------

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
      'https://releases.rediacc.com/apt/stable/gpg.key',
      'https://releases.rediacc.com/rpm/stable/rediacc.repo',
      'https://releases.rediacc.com/apk/stable',
      'https://releases.rediacc.com/archlinux/stable/x86_64',
      'https://releases.rediacc.com/cli/stable/rdc-linux-x64',
      'https://releases.rediacc.com/npm/stable/rediacc-cli-latest.tgz',
    ].join('\n');
    const htmlUrl = new URL('https://pr-420.rediacc.workers.dev/install');
    const out = await rewriteOrigin(makeResponse(body, 'text/html'), htmlUrl, channel);
    const text = await out.text();
    for (const format of ['apt', 'rpm', 'apk', 'archlinux', 'cli', 'npm']) {
      expect(text).toContain(`releases.rediacc.com/${format}/pr-420`);
      expect(text).not.toContain(`releases.rediacc.com/${format}/stable`);
    }
  });

  it('rewrites Docker image tag from :stable to channel', async () => {
    const body = 'docker pull ghcr.io/rediacc/elite/cli:stable';
    const htmlUrl = new URL('https://pr-420.rediacc.workers.dev/');
    const out = await rewriteOrigin(makeResponse(body, 'text/html'), htmlUrl, channel);
    expect(await out.text()).toContain('elite/cli:pr-420');
  });

  it('rewrites production origin references to preview origin', async () => {
    const body = 'canonical: https://www.rediacc.com/docs';
    const htmlUrl = new URL('https://pr-420.rediacc.workers.dev/docs');
    const out = await rewriteOrigin(makeResponse(body, 'text/html'), htmlUrl, channel);
    const text = await out.text();
    expect(text).toContain('https://pr-420.rediacc.workers.dev/docs');
    expect(text).not.toContain('https://www.rediacc.com/docs');
  });

  it('rewrites multiple occurrences of the production origin', async () => {
    // replaceAll guards against the historical bug where only the first
    // occurrence got rewritten and stale references leaked into rendered
    // sitemaps / canonical tags below the fold.
    const body = [
      'canonical: https://www.rediacc.com/a',
      'og:url: https://www.rediacc.com/b',
      'link: https://www.rediacc.com/c',
    ].join('\n');
    const htmlUrl = new URL('https://pr-420.rediacc.workers.dev/x');
    const out = await rewriteOrigin(makeResponse(body, 'text/html'), htmlUrl, channel);
    const text = await out.text();
    expect(text).not.toContain('https://www.rediacc.com');
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

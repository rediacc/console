import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { tryOpenBrowser } from '../config-remote-relay.js';

// A launcher such as xdg-open hands the URL to a browser that keeps running and inherits the launcher's stdout and stderr. A piped child then holds the CLI's event loop open until the browser quits (config remote enable never returned, 2026-11-25).
describe.skipIf(process.platform === 'win32')('tryOpenBrowser', () => {
  const originalPath = process.env.PATH;
  let dir = '';

  afterEach(() => {
    // An unset PATH is deleted, never assigned the string "undefined".
    if (originalPath === undefined) delete process.env.PATH;
    else process.env.PATH = originalPath;
    try {
      process.kill(Number(readFileSync(join(dir, 'pid'), 'utf8')));
    } catch {
      // already gone
    }
    rmSync(dir, { recursive: true, force: true });
  });

  it('leaves no pipe or child process handle behind a launcher that outlives it', async () => {
    dir = mkdtempSync(join(tmpdir(), 'rdc-browser-'));
    const launcher = join(dir, process.platform === 'darwin' ? 'open' : 'xdg-open');
    // The background child stands for the browser: it inherits the launcher's stdio and outlives it.
    // It also records its argv, so the test can see the URL arrive as one entry.
    writeFileSync(
      launcher,
      `#!/bin/sh\nsleep 15 &\necho $! > "${join(dir, 'pid')}"\necho "$#" > "${join(dir, 'argc')}"\nprintf '%s' "$1" > "${join(dir, 'arg1')}"\n`
    );
    chmodSync(launcher, 0o755);
    process.env.PATH = `${dir}:${originalPath ?? ''}`;

    // The test runner's own pipes are already open; only what the call adds counts.
    const count = () =>
      process.getActiveResourcesInfo().filter((name) => /Pipe|Process/i.test(name)).length;
    const before = count();

    const url = 'https://example.test/#a=b&c=d';
    await tryOpenBrowser(url);
    await new Promise((resolve) => setTimeout(resolve, 400));

    expect(count()).toBe(before);
    // A shell-string launch would split at & and drop the fragment: the launcher got exactly one argument, the whole URL.
    expect(readFileSync(join(dir, 'argc'), 'utf8').trim()).toBe('1');
    expect(readFileSync(join(dir, 'arg1'), 'utf8')).toBe(url);
  });

  // Review 1121-1 3916072a.2 and a641cdbb.1: openBrowser reports a failed launch as false and never throws, so a missing launcher cannot break the enroll flow.
  it('resolves when no launcher is installed', async () => {
    dir = mkdtempSync(join(tmpdir(), 'rdc-browser-'));
    process.env.PATH = dir;

    await expect(tryOpenBrowser('https://example.test/')).resolves.toBeUndefined();
    await new Promise((resolve) => setTimeout(resolve, 100));
  });
});

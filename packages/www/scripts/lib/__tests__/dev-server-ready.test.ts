import { describe, expect, it } from 'vitest';
import { DEV_SERVER_READY, isDevServerReady, stripAnsi } from '../dev-server-ready.js';

/**
 * THE FIXTURES ARE REAL CAPTURES, NOT HAND-TYPED APPROXIMATIONS. Both were produced by
 * running `npm run dev -w @rediacc/www -- --host 127.0.0.1 --port 4511` on 2026-09-01,
 * once with a plain environment and once with `CI=true`, then JSON-encoding the banner
 * lines byte for byte. A transcribed fixture would have hidden the defect, because the
 * defect IS the bytes: the escape sequence lands between `in` and the space.
 */
const PLAIN_BANNER = ' astro  v5.18.1 ready in 4494 ms';
const PLAIN_LOCAL = 'Local    http://127.0.0.1:4511/';
const CI_BANNER =
  '\u001b[42m\u001b[1m astro \u001b[22m\u001b[49m \u001b[32mv5.18.1\u001b[39m \u001b[2mready in\u001b[22m 4739 \u001b[2mms\u001b[22m';
const CI_LOCAL = '\u001b[2m\u2503\u001b[22m Local    \u001b[36mhttp://127.0.0.1:4511/\u001b[39m';

describe('dev server readiness', () => {
  it('SANITY: recognises the plain banner a developer sees locally', () => {
    expect(isDevServerReady(PLAIN_BANNER)).toBe(true);
    expect(isDevServerReady(PLAIN_LOCAL)).toBe(true);
  });

  // THE REGRESSION THIS FILE EXISTS FOR. The gate timed out five times in CI while
  // passing locally, because the raw matcher cannot see through colour.
  it('recognises the ANSI-coloured banner that CI actually produces', () => {
    expect(isDevServerReady(CI_BANNER)).toBe(true);
    expect(isDevServerReady(CI_LOCAL)).toBe(true);
  });

  // The control proving the test above is not vacuous: without stripping, the CI bytes
  // genuinely do NOT match. If this ever starts passing, the fixture stopped being
  // coloured and the test above no longer proves anything.
  it('CONTROL: the CI bytes do not match without stripping', () => {
    expect(DEV_SERVER_READY.test(CI_BANNER)).toBe(false);
    expect(DEV_SERVER_READY.test(CI_LOCAL)).toBe(false);
  });

  it('CONTROL: "address already in use" is not readiness', () => {
    expect(
      isDevServerReady('Error: listen EADDRINUSE: address already in use 127.0.0.1:4511')
    ).toBe(false);
  });

  it('CONTROL: output from before the banner is not readiness', () => {
    expect(isDevServerReady('21:57:26 [content] Syncing content\n')).toBe(false);
  });

  it('matches across a chunk boundary once the buffer is accumulated', () => {
    const chunks = ['\u001b[2mready', ' in\u001b[22m 47', '39 \u001b[2mms\u001b[22m'];
    let buffer = '';
    const seen = chunks.map((chunk) => {
      buffer += chunk;
      return isDevServerReady(buffer);
    });
    // The MIDDLE one is true, and that is correct rather than sloppy: after two chunks
    // the buffer strips to `ready in 47`, which is already unambiguous. Recorded here
    // because the first version of this test asserted [false, false, true] and the
    // control caught the wrong expectation, not a wrong matcher.
    expect(seen).toEqual([false, true, true]);
  });

  it('stripAnsi removes cursor and erase sequences, not just colour', () => {
    expect(stripAnsi('\u001b[2K\u001b[1Gready in 1 ms')).toBe('ready in 1 ms');
  });
});

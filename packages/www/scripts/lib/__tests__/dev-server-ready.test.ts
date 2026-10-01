import { describe, expect, it } from 'vitest';
import {
  boundPort,
  boundPortMismatch,
  DEV_SERVER_READY,
  isDevServerReady,
  stripAnsi,
} from '../dev-server-ready.js';

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

  // THE REGRESSION THIS FILE EXISTS FOR. The gate timed out five times in CI while passing locally, because the raw matcher cannot see through colour.
  it('recognises the ANSI-coloured banner that CI actually produces', () => {
    expect(isDevServerReady(CI_BANNER)).toBe(true);
    expect(isDevServerReady(CI_LOCAL)).toBe(true);
  });

  // The control proving the test above is not vacuous: without stripping, the CI bytes genuinely do NOT match. If this ever starts passing, the fixture stopped being coloured and the test above no longer proves anything.
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
    // The MIDDLE one is true, and that is correct rather than sloppy: after two chunks the buffer strips to `ready in 47`, which is already unambiguous. Recorded here because the first version of this test asserted [false, false, true] and the control caught the wrong expectation, not a wrong matcher.
    expect(seen).toEqual([false, true, true]);
  });

  it('stripAnsi removes cursor and erase sequences, not just colour', () => {
    expect(stripAnsi('\u001b[2K\u001b[1Gready in 1 ms')).toBe('ready in 1 ms');
  });
});

/** REAL capture, 2026-10-02: `python3 -m http.server 4511` held the port, astro was started with `--port 4511`. */
const MOVED_LOG =
  '{"message":"Port 4511 is in use, trying another one...","label":"vite","level":"info"}\n' +
  '{"message":" astro  v7.3.5 ready in 64343 ms\\n┃ Local    http://127.0.0.1:4512/","label":"SKIP_FORMAT","level":"info"}';

describe('bound port verification', () => {
  it('reads the port from the plain and the coloured Local line', () => {
    expect(boundPort(PLAIN_LOCAL)).toBe(4511);
    expect(boundPort(CI_LOCAL)).toBe(4511);
  });

  it('accepts a server that bound the port it was asked for', () => {
    expect(boundPortMismatch(`${PLAIN_BANNER}\n${PLAIN_LOCAL}`, 4511)).toBeNull();
    expect(boundPortMismatch(`${CI_BANNER}\n${CI_LOCAL}`, 4511)).toBeNull();
  });

  // THE REGRESSION: the moved-port capture still reads as "ready", so only this check stands between the gate and the squatter.
  it('CONTROL: the moved-port capture is ready yet is refused, naming both ports', () => {
    expect(isDevServerReady(MOVED_LOG)).toBe(true);
    const message = boundPortMismatch(MOVED_LOG, 4511);
    expect(message).toContain('asked for 4511');
    expect(message).toContain('bound 4512');
  });

  it('CONTROL: a Local URL on another port is refused even without the "in use" line', () => {
    expect(boundPortMismatch(PLAIN_LOCAL, 4600)).toContain('bound 4511');
  });
});

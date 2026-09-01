/**
 * Deciding that `astro dev` is up, from bytes that may or may not be coloured.
 *
 * EXTRACTED SO IT CAN BE CONTROLLED. Living inside the release gate, this logic was
 * only ever exercised by starting a real dev server, which meant the one environment
 * that broke it -- CI -- was also the one place nobody could run a quick check. It
 * now has unit controls carrying the REAL captured bytes from both environments.
 */

/**
 * ANSI escapes out, because THE BANNER IS COLOURED IN CI AND ONLY IN CI.
 *
 * GitHub Actions always sets `CI=true`, and astro's colour library treats that as
 * "colour is supported" even with no TTY attached. The same banner that reads
 * ` astro  v5.18.1 ready in 4494 ms` on a developer's machine arrives as
 * `\x1b[2mready in\x1b[22m 4739 \x1b[2mms\x1b[22m` -- the escape sits exactly BETWEEN
 * `in` and the space, the one place the needle cannot survive it.
 */
export function stripAnsi(text) {
  // General CSI, not just SGR: astro also emits cursor and erase sequences.
  // eslint-disable-next-line no-control-regex
  return text.replaceAll(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, '');
}

/**
 * MATCH ASTRO'S BANNER. Two spellings, because astro prints the host it was GIVEN:
 * `localhost` by default, `127.0.0.1` when started with `--host 127.0.0.1`.
 *
 * The predecessor, `text.includes('ready')`, matched "address already in use" and
 * would have run the whole suite against somebody else's listener.
 */
export const DEV_SERVER_READY = /ready in \s*\d|Local\s+https?:\/\/(localhost|127\.0\.0\.1):/i;

/** True once the accumulated server output says the server is serving. */
export function isDevServerReady(accumulated) {
  return DEV_SERVER_READY.test(stripAnsi(accumulated));
}

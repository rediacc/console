/**
 * Retry policy for a scenario click of the tutorial-player release gate.
 *
 * A click that THREW never reached the page: agent-browser resolves the element and checks it is
 * actionable BEFORE dispatching any input, so these refusals leave the player exactly as it was.
 * Only that class is retried. A click that succeeded and did nothing is a real dropped click, and
 * the scenario's own state assertion still fails on it -- the retry cannot hide that.
 */
export const REFUSED_BEFORE_DISPATCH =
  /not found|not visible|not attached|detached|intercept|obscured|covered by|not stable/i;
export const CLICK_ATTEMPTS = 4;
export const CLICK_RETRY_GAP_MS = 400;

/**
 * `click(selector)` answers `{ ok: true }` or `{ ok: false, reason }`. `reveal()` brings the
 * control bar back (Video.js hides it 2 s after the last pointer activity, so a slow first
 * attempt can leave the bar hidden for every retry); it runs before each retry, not only before
 * the first click. `wait(ms)` and `log(text)` are the gate's own.
 */
export function clickWithRetry({ click, reveal, wait, log }, selector) {
  let result = click(selector);
  for (let attempt = 1; !result.ok && attempt < CLICK_ATTEMPTS; attempt += 1) {
    if (!REFUSED_BEFORE_DISPATCH.test(result.reason)) break;
    log(
      `→ click on ${selector} refused (attempt ${attempt}), retrying: ${result.reason.slice(0, 300)}`
    );
    wait(CLICK_RETRY_GAP_MS);
    reveal();
    result = click(selector);
  }
  // The refusal text is the only evidence of WHY a click failed, and it used to be dropped.
  if (!result.ok) log(`→ click on ${selector} FAILED: ${result.reason.slice(0, 600)}`);
  return result;
}

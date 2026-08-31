import { useCallback, useMemo, useState } from 'react';

/**
 * The Turnstile state machine, shared by every form that gates on a captcha.
 *
 * THE DEFECT THIS EXISTS TO CLOSE. All three forms wrote the same two lines:
 * `onError={() => setTurnstileToken(null)}` beside a submit guard that fires whenever
 * the token is missing. Those two agree only while the widget is actually on screen.
 * When the Turnstile script is blocked (ad blocker, offline, a Cloudflare hiccup) the
 * widget renders nothing at all, so the visitor gets "Please complete the captcha
 * verification." over a form containing no captcha, and no way forward. Observed in
 * production on edge.rediacc.com.
 *
 * The requirement is not the bug and is not relaxed here: `token` still has to be
 * present before a form submits. What changes is that failure becomes VISIBLE and
 * RECOVERABLE.
 *
 * WHY A NONCE. `@marsidev/react-turnstile` renders its widget once per instance, so
 * clearing state does not re-run it. Feeding `nonce` to the component's `key` is what
 * makes a retry actually mount a fresh widget.
 *
 * STATE ONLY, NO STRINGS. The three consumers sit in different translator scopes
 * (`pages.solutionPages.leadMagnetModal.*` for the lead magnet, a bare `captchaRequired`
 * for the two contact forms), so the message stays with the component and only the
 * mechanism is shared.
 */
export interface CaptchaGuard {
  /** Present once the visitor has passed the challenge. */
  token: string | null;
  /** The widget errored, so there may be nothing on screen to complete. */
  failed: boolean;
  /** Pass as the <Turnstile key> so `retry` remounts it. */
  nonce: number;
  onSuccess: (token: string) => void;
  onExpire: () => void;
  onError: () => void;
  retry: () => void;
  /** Clear back to first-load state, for a form that reopens or resets. */
  reset: () => void;
}

/**
 * Pick the message for a blocked submit.
 *
 * A one-line helper rather than a ternary at each call site, and that is a lint
 * constraint rather than taste: the four submit handlers that gate on a captcha were
 * already at the cognitive-complexity limit of 10, so adding the "did it fail or is it
 * merely unsolved" branch inline pushed every one of them to 11 or 12. The branch is the
 * same everywhere, so it belongs here once.
 */
export function captchaMessage(guard: CaptchaGuard, unavailable: string, required: string): string {
  return guard.failed ? unavailable : required;
}

export function useCaptchaGuard(): CaptchaGuard {
  const [token, setToken] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [nonce, setNonce] = useState(0);

  const onSuccess = useCallback((next: string) => {
    setToken(next);
    // A later success clears an earlier failure, so a widget that recovers on its own
    // does not leave the retry prompt sitting under a solved challenge.
    setFailed(false);
  }, []);

  const onExpire = useCallback(() => {
    // Expiry is not failure: the widget is still there and can be solved again.
    setToken(null);
  }, []);

  const onError = useCallback(() => {
    setToken(null);
    setFailed(true);
  }, []);

  const retry = useCallback(() => {
    setToken(null);
    setFailed(false);
    setNonce((n) => n + 1);
  }, []);

  const reset = useCallback(() => {
    setToken(null);
    setFailed(false);
  }, []);

  // MEMOISED, and that is a correctness requirement rather than a micro-optimisation.
  // Consumers put this object in `useCallback`/`useEffect` dependency lists (the lead
  // magnet's `open` resets the captcha), and a fresh object every render would make
  // every one of those callbacks unstable, re-running the effects that depend on them
  // on each render. The handlers are already stable `useCallback`s, so the only thing
  // that has to be pinned is the wrapper.
  return useMemo(
    () => ({ token, failed, nonce, onSuccess, onExpire, onError, retry, reset }),
    [token, failed, nonce, onSuccess, onExpire, onError, retry, reset]
  );
}

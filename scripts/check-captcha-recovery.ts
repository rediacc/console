#!/usr/bin/env tsx
/**
 * Every form that GATES on a captcha must also handle the captcha never arriving.
 *
 * THE DEFECT THIS EXISTS TO CLOSE, observed in production on edge.rediacc.com: a modal
 * showing "Please complete the captcha verification." over a form containing no captcha
 * and no way to produce one. Six forms had independently written the same two lines:
 *
 *     onError={() => setTurnstileToken(null)}          // widget failed, token cleared
 *     if (captchaEnabled && !turnstileToken) { ...error... }   // ...and the guard fires
 *
 * Those agree only while the widget is on screen. When the Turnstile script is blocked
 * (ad blocker, offline, a Cloudflare hiccup) the widget renders nothing, so the visitor
 * meets a requirement they cannot satisfy. The requirement is correct; the dead end is not.
 *
 * WHY A STATIC CHECK AND NOT AN E2E. `captchaEnabled` is `!!PUBLIC_TURNSTILE_SITE_KEY &&
 * !PUBLIC_CI_MODE`, and CI sets `PUBLIC_CI_MODE=true`, so in any test run the guard is
 * disarmed and the <Turnstile> mount is never rendered. A browser test would drive a form
 * with no captcha in it and pass no matter what the error path does. The regression that
 * actually happens is a SEVENTH form pasting the old pattern, and that is visible in the
 * source.
 *
 * Usage:
 *   npx tsx scripts/check-captcha-recovery.ts [--selftest]
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const ROOT = path.resolve(import.meta.dirname, '..');
const SRC = path.join(ROOT, 'packages/www/src');

const TURNSTILE_IMPORT = '@marsidev/react-turnstile';
/** The shared state machine. Its whole point is that failure is representable. */
const GUARD = 'useCaptchaGuard';
/** The old shape: a component minting its own token state instead of using the guard. */
const LOCAL_TOKEN = /\[\s*turnstileToken\s*,\s*setTurnstileToken\s*\]/;

export interface Verdict {
  file: string;
  problems: string[];
}

/**
 * Judged from source text, exported so the controls below exercise the SAME function the
 * real files go through. A control that runs a reimplementation proves nothing.
 */
export function judgeSource(file: string, src: string): Verdict {
  const problems: string[] = [];
  if (!src.includes(TURNSTILE_IMPORT)) return { file, problems };

  if (!src.includes(GUARD)) {
    problems.push(
      `mounts <Turnstile> without ${GUARD}: its failure state cannot be represented, ` +
        'so a widget that never mounts leaves the submit guard unsatisfiable'
    );
  }
  if (LOCAL_TOKEN.test(src)) {
    problems.push(
      'declares its own [turnstileToken, setTurnstileToken] state: this is the pattern ' +
        `that produced the dead end in six forms. Use ${GUARD}.`
    );
  }
  // The recovery has two halves and both are load-bearing: knowing it failed, and
  // offering the way out. A component with `.failed` but no `.retry` tells the visitor
  // what went wrong and still strands them.
  if (!/captcha\.failed/.test(src)) {
    problems.push('never reads `captcha.failed`, so it cannot tell "unsolved" from "never loaded"');
  }
  if (!/captcha\.retry/.test(src)) {
    problems.push('never offers `captcha.retry`, so a failed widget has no recovery path');
  }
  return { file, problems };
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name === 'node_modules' || name === '__tests__') continue;
      walk(full, out);
    } else if (name.endsWith('.tsx')) {
      out.push(full);
    }
  }
  return out;
}

/** Controls, each the real defect reconstructed. */
const CONTROLS: { name: string; src: string; expect: string | null }[] = [
  {
    name: 'a form with its own token state and no guard is reported',
    src: `import { Turnstile } from '${TURNSTILE_IMPORT}';
      const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
      onError={() => setTurnstileToken(null)}`,
    expect: 'useCaptchaGuard',
  },
  {
    name: 'a form using the guard but offering no retry is reported',
    src: `import { Turnstile } from '${TURNSTILE_IMPORT}';
      const captcha = useCaptchaGuard();
      if (captchaEnabled && !captcha.token) setErrorMsg(captcha.failed ? a : b);`,
    expect: 'captcha.retry',
  },
  {
    name: 'a form that cannot distinguish unsolved from never-loaded is reported',
    src: `import { Turnstile } from '${TURNSTILE_IMPORT}';
      const captcha = useCaptchaGuard();
      <button onClick={captcha.retry}>x</button>`,
    expect: 'captcha.failed',
  },
  {
    name: 'a file that never mounts Turnstile is not judged at all',
    src: `const [turnstileToken, setTurnstileToken] = useState(null);`,
    expect: null,
  },
  {
    name: 'a complete form produces no findings',
    src: `import { Turnstile } from '${TURNSTILE_IMPORT}';
      const captcha = useCaptchaGuard();
      setErrorMsg(captcha.failed ? t('captchaUnavailable') : t('captchaRequired'));
      <button onClick={captcha.retry}>{t('captchaRetry')}</button>`,
    expect: null,
  },
];

function main(): void {
  const selftest = process.argv.includes('--selftest');

  if (selftest) {
    let ok = true;
    for (const c of CONTROLS) {
      const { problems } = judgeSource('control.tsx', c.src);
      const fired =
        c.expect === null ? problems.length === 0 : problems.some((p) => p.includes(c.expect!));
      ok &&= fired;
      console.log(`  ${fired ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m'}  CONTROL: ${c.name}`);
    }
    if (!ok) {
      console.error('\x1b[31m✗\x1b[0m a control did not behave, so this gate cannot be trusted');
      process.exit(1);
    }
  }

  const files = walk(SRC);
  const consumers = files
    .map((f) => ({ f, src: readFileSync(f, 'utf8') }))
    .filter(({ src }) => src.includes(TURNSTILE_IMPORT));

  // FLOOR. If the scan finds no consumers the loop below is vacuous and would report a
  // confident green having verified nothing -- the exact failure this repo gates against.
  if (consumers.length === 0) {
    console.error(`\x1b[31m✗\x1b[0m no ${TURNSTILE_IMPORT} consumers found under ${SRC}`);
    console.error('    the scan is broken, or the import moved: this green would be vacuous');
    process.exit(1);
  }

  const verdicts = consumers
    .map(({ f, src }) => judgeSource(path.relative(ROOT, f), src))
    .filter((v) => v.problems.length > 0);

  if (verdicts.length > 0) {
    console.error(`\x1b[31m✗\x1b[0m ${verdicts.length} form(s) can strand a visitor:\n`);
    for (const v of verdicts) {
      console.error(`  ${v.file}`);
      for (const p of v.problems) console.error(`    - ${p}`);
    }
    console.error('\n  The shared state machine is packages/www/src/hooks/useCaptchaGuard.ts.');
    process.exit(1);
  }

  console.log(
    `\x1b[32m✓\x1b[0m ${consumers.length} captcha-gated form(s): each can tell a failed widget ` +
      'from an unsolved one, and each offers a retry.'
  );
}

main();

#!/usr/bin/env tsx
/**
 * A form that switches off the browser's validation must put something in its place.
 *
 * WHAT A VISITOR SEES TODAY.
 *   Submitting the contact form EMPTY answers "Something went wrong. Please try again."
 *     The form carries `noValidate` (`ContactForm.tsx:120`, `ContactModal.tsx:232`) and no
 *     client-side replacement, so the empty payload is POSTed, the server rejects it, and
 *     the generic network-error branch renders. A blank form reads as a broken site.
 *   Submitting the newsletter or lead-magnet form EMPTY does NOTHING AT ALL.
 *     `NewsletterSignup.tsx:45` and `LeadMagnetModal.tsx:133` read the input, find it
 *     empty, and `return` without a message, a focus move or a state change. The button is
 *     dead on the site's main email capture and nothing tells the visitor why.
 *
 * THE ONE THAT IS RIGHT IS THE SPECIFICATION. `PartnerApplicationForm.tsx:149` also sets
 * `noValidate`, and then checks the required fields itself and calls
 * `setErrorMsg(t(`${NS}.errors.requiredFields`))` before returning. That is the whole
 * requirement, and it is why this gate can be strict without being unreasonable: one of the
 * six forms in this repo already does exactly what the other five are asked to do.
 *
 * THE TWO RULES, AND WHY THE SECOND IS NOT COVERED BY THE FIRST.
 *   novalidate-without-replacement -- the form disables browser validation and no guard in
 *     its submit handler both tests a field value and reports an error. A captcha guard
 *     does not count: it is what ContactForm has, and an empty form sails straight past it.
 *   silent-return -- a value read from an input and then discarded with a bare `return`.
 *     This is a defect even on a form that keeps browser validation, because the input may
 *     be optional to the browser and required to the handler, and the user gets nothing.
 *
 * Usage:
 *   tsx scripts/check-form-validation.ts [--root <dir>] [--selftest]
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SOURCE_DIR = 'packages/www/src';

/**
 * Identifiers that name a captcha token rather than a form field. A guard on one of these
 * is a bot check, not input validation, and treating it as validation is precisely the
 * mistake that would let ContactForm pass.
 */
const CAPTCHA_IDENTS = /^(turnstile|captcha|recaptcha|hcaptcha)/i;

/** Fewer forms than this in packages/www means the scan lost its input. */
const MIN_FORMS = 3;

export interface FormFinding {
  file: string;
  line: number;
  rule: 'novalidate-without-replacement' | 'silent-return';
  detail: string;
}

function walk(dir: string, out: string[] = []): string[] {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs
    .readdirSync(dir, { withFileTypes: true })
    .sort((a, b) => a.name.localeCompare(b.name))) {
    if (entry.name.startsWith('.') || entry.name === 'node_modules') continue;
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(abs, out);
    else if (entry.name.endsWith('.tsx') || entry.name.endsWith('.astro')) out.push(abs);
  }
  return out;
}

const lineOf = (src: string, index: number): number => src.slice(0, index).split('\n').length;

/** The balanced `{ ... }` block starting at `open`. */
function block(src: string, open: number): string {
  let depth = 0;
  for (let i = open; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') {
      depth--;
      if (depth === 0) return src.slice(open + 1, i);
    }
  }
  return src.slice(open + 1);
}

/**
 * The bodies of every submit handler in a file.
 *
 * A submit handler is identified by `preventDefault()`, not by its name. Naming it
 * `handleSubmit` is a convention rather than a rule, and a gate that keyed on the name
 * would go quiet the first time somebody called it `onSend`.
 */
export function submitHandlers(src: string): { body: string; at: number }[] {
  const out: { body: string; at: number }[] = [];
  for (const m of src.matchAll(
    /(?:const\s+[A-Za-z_$][\w$]*\s*(?::[^=]+)?=\s*(?:async\s*)?\([^)]*\)\s*(?::[^=]+)?=>|function\s+[A-Za-z_$][\w$]*\s*\([^)]*\))\s*\{/g
  )) {
    const open = src.indexOf('{', m.index! + m[0].length - 1);
    const body = block(src, open);
    if (/\bpreventDefault\s*\(/.test(body)) out.push({ body, at: m.index! });
  }
  return out;
}

/** Identifiers in a handler that hold a value READ FROM AN INPUT. */
export function fieldIdentifiers(body: string): Set<string> {
  const out = new Set<string>();
  for (const m of body.matchAll(/\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*[^;]*\.value\b/g)) {
    out.add(m[1]);
  }
  // `const { name, email } = Object.fromEntries(new FormData(...))` and friends.
  for (const m of body.matchAll(/\b(?:const|let|var)\s*\{([^}]*)\}\s*=\s*[^;]*FormData\b/g)) {
    for (const part of m[1].split(',')) {
      const ident = part.split(':').pop()?.trim();
      if (ident && /^[A-Za-z_$][\w$]*$/.test(ident)) out.add(ident);
    }
  }
  return out;
}

/** Every `if (...) <statement-or-block>` in a body, with its condition and consequent. */
function guards(body: string): { condition: string; consequent: string }[] {
  const out: { condition: string; consequent: string }[] = [];
  for (const m of body.matchAll(/\bif\s*\(/g)) {
    let depth = 0;
    let i = m.index! + m[0].length - 1;
    for (; i < body.length; i++) {
      if (body[i] === '(') depth++;
      else if (body[i] === ')') {
        depth--;
        if (depth === 0) break;
      }
    }
    const condition = body.slice(m.index! + m[0].length, i);
    const rest = body.slice(i + 1);
    const brace = rest.match(/^\s*\{/);
    const consequent = brace
      ? block(rest, rest.indexOf('{'))
      : rest.slice(0, rest.indexOf(';') + 1);
    out.push({ condition, consequent });
  }
  return out;
}

const setsError = (s: string): boolean => /\bset[A-Za-z]*[Ee]rror[A-Za-z]*\s*\(/.test(s);

export function scanComponent(src: string, file: string): FormFinding[] {
  const findings: FormFinding[] = [];
  const handlers = submitHandlers(src);

  // ONE GUARD, ONE FINDING. submitHandlers() matches the enclosing component function too
  // whenever the handler is declared inside it, so the same `if (!email) return;` was
  // reported twice -- once at the component's line and once at the handler's. Keeping the
  // LAST occurrence keeps the innermost (and correct) line, and the key is the guard
  // itself so two genuinely different guards still count as two.
  const seen = new Map<string, FormFinding>();

  for (const handler of handlers) {
    const fields = fieldIdentifiers(handler.body);
    for (const guard of guards(handler.body)) {
      const idents = new Set(guard.condition.match(/[A-Za-z_$][\w$]*/g) ?? []);
      const touchesField = [...fields].some((f) => idents.has(f));
      if (!touchesField) continue;
      if (/\breturn\b/.test(guard.consequent) && !setsError(guard.consequent)) {
        seen.set(`silent-return:${guard.condition.trim()}`, {
          file,
          line: lineOf(src, handler.at),
          rule: 'silent-return',
          detail:
            `a submit handler reads an input, finds it empty (\`if (${guard.condition.trim()})\`) ` +
            `and returns without setting an error, moving focus or changing state. The ` +
            `button does nothing and the visitor is told nothing.`,
        });
      }
    }
  }

  findings.push(...seen.values());

  // One entry per `<form ... noValidate>`.
  for (const m of src.matchAll(/<form\b[^>]*>/g)) {
    const tag = m[0];
    if (!/\bnoValidate\b|\bnovalidate\b/.test(tag)) continue;
    const hasReplacement = handlers.some((h) => {
      const fields = fieldIdentifiers(h.body);
      return guards(h.body).some((g) => {
        const idents = [...new Set(g.condition.match(/[A-Za-z_$][\w$]*/g) ?? [])];
        // A captcha guard is not input validation. An empty form passes it untouched,
        // which is exactly how ContactForm answers "Something went wrong" to a blank
        // submit while LOOKING as though it validates.
        const validating = idents.filter((i) => fields.has(i) && !CAPTCHA_IDENTS.test(i));
        return validating.length > 0 && setsError(g.consequent);
      });
    });
    if (!hasReplacement) {
      findings.push({
        file,
        line: lineOf(src, m.index!),
        rule: 'novalidate-without-replacement',
        detail:
          `this <form> sets noValidate, so the browser stops checking \`required\`, and no ` +
          `guard in its submit handler both tests a field value and reports an error. An ` +
          `empty submit reaches the network. PartnerApplicationForm.tsx:149 is the shape to ` +
          `copy: check the fields, setErrorMsg(...requiredFields), return.`,
      });
    }
  }
  return findings;
}

function selftest(): boolean {
  const failures: string[] = [];
  const check = (name: string, ok: boolean, detail = '') => {
    if (ok) console.log(`  PASS  ${name}`);
    else {
      console.error(`  FAIL  ${name}${detail ? `\n        ${detail}` : ''}`);
      failures.push(name);
    }
  };

  // THE GOOD FORM, reduced from PartnerApplicationForm.tsx. Nothing may be reported here,
  // or the gate is asking for something the repo has already shown to be achievable.
  const GOOD = `const F = () => {
  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    const contactName = contactNameRef.current?.value.trim() ?? '';
    const email = emailRef.current?.value.trim() ?? '';
    if (!contactName || !email) {
      setState('error');
      setErrorMsg(t('errors.requiredFields'));
      return;
    }
    await fetch('/api/x', { method: 'POST' });
  };
  return <form onSubmit={handleSubmit} noValidate><input ref={emailRef} required /></form>;
};`;
  check(
    'a noValidate form WITH a field guard that reports an error is clean (control)',
    scanComponent(GOOD, 'Good.tsx').length === 0,
    JSON.stringify(scanComponent(GOOD, 'Good.tsx'))
  );

  // PLANT 1: ContactForm's shape -- noValidate, and the only guard is the captcha, which
  // an empty form sails straight past.
  const CAPTCHA_STATE = `const F = () => {
  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    const email = emailRef.current?.value.trim() ?? '';
    if (captchaEnabled && !turnstileToken) {
      setErrorMsg(t('captchaRequired'));
      return;
    }
    await fetch('/api/x', { method: 'POST' });
  };
  return <form onSubmit={handleSubmit} noValidate><input ref={emailRef} required /></form>;
};`;
  const captchaState = scanComponent(CAPTCHA_STATE, 'CaptchaState.tsx');
  check(
    'PLANT: a captcha guard does not count as input validation',
    captchaState.length === 1 && captchaState[0].rule === 'novalidate-without-replacement',
    JSON.stringify(captchaState)
  );

  // THE SAME PLANT WITH THE CAPTCHA READ FROM AN INPUT, which is what makes
  // CAPTCHA_IDENTS load-bearing rather than decorative. In the fixture above the token is
  // React state, so `fields.has(...)` already excludes it and the name test decides
  // nothing -- a rule that cannot fire, which is the exact defect class this program
  // exists to remove. Read the token from an input and the name test is the ONLY thing
  // standing between a bot check and a green gate.
  const CAPTCHA_FROM_INPUT = `const F = () => {
  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    const email = emailRef.current?.value.trim() ?? '';
    const captchaAnswer = captchaRef.current?.value.trim() ?? '';
    if (!captchaAnswer) {
      setErrorMsg(t('captchaRequired'));
      return;
    }
    await fetch('/api/x', { method: 'POST' });
  };
  return <form onSubmit={handleSubmit} noValidate><input ref={emailRef} required /></form>;
};`;
  const captchaInput = scanComponent(CAPTCHA_FROM_INPUT, 'CaptchaInput.tsx');
  check(
    'PLANT: a captcha READ FROM AN INPUT still does not count as input validation',
    captchaInput.some((f) => f.rule === 'novalidate-without-replacement'),
    JSON.stringify(captchaInput)
  );

  // PLANT 2: NewsletterSignup's shape -- the value is read and then thrown away.
  const SILENT = `const F = () => {
  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    const email = inputRef.current?.value.trim();
    if (!email) return;
    await fetch('/api/x', { method: 'POST' });
  };
  return <form onSubmit={handleSubmit} noValidate><input ref={inputRef} required /></form>;
};`;
  const silent = scanComponent(SILENT, 'Silent.tsx');
  check(
    'PLANT: a value read from an input and silently discarded is reported',
    silent.some((f) => f.rule === 'silent-return'),
    JSON.stringify(silent)
  );
  check(
    'the same form is also reported for having no replacement validation',
    silent.some((f) => f.rule === 'novalidate-without-replacement')
  );
  // The handler is declared INSIDE the component, so both function bodies contain the
  // same guard. One defect must produce one finding.
  check(
    'one guard nested inside a component function yields ONE finding, not two',
    silent.filter((f) => f.rule === 'silent-return').length === 1,
    JSON.stringify(silent.filter((f) => f.rule === 'silent-return'))
  );

  // PLANT 3: the sixth form. A new form that copies the broken shape must be caught.
  const SIXTH = SILENT.replace('const F =', 'const SixthForm =');
  check(
    'PLANT: a sixth form copying the broken shape is caught too',
    scanComponent(SIXTH, 'Sixth.tsx').length >= 1
  );

  // ---- CONTROLS THAT MUST NOT FIRE ------------------------------------------------
  const NO_NOVALIDATE = `const F = () => {
  const handleSubmit = (e) => { e.preventDefault(); compute(); };
  return <form onSubmit={handleSubmit}><input required /></form>;
};`;
  check(
    'a form that keeps browser validation is not reported (control)',
    scanComponent(NO_NOVALIDATE, 'Plain.tsx').length === 0,
    JSON.stringify(scanComponent(NO_NOVALIDATE, 'Plain.tsx'))
  );

  const GUARD_ON_PROP = `const F = () => {
  const handleSubmit = (e) => {
    e.preventDefault();
    if (!opts) return;
    const email = ref.current?.value;
    if (!email) { setErrorMsg('required'); return; }
    void email;
  };
  return <form onSubmit={handleSubmit} noValidate><input ref={ref} required /></form>;
};`;
  check(
    'a guard on a PROP, not on a field value, is not a silent-return (control)',
    scanComponent(GUARD_ON_PROP, 'Prop.tsx').length === 0,
    JSON.stringify(scanComponent(GUARD_ON_PROP, 'Prop.tsx'))
  );

  const NOT_A_SUBMIT = `const F = () => {
  const onChange = (e) => { const v = e.target.value; if (!v) return; setX(v); };
  return <form noValidate onSubmit={h}><input onChange={onChange} required /></form>;
};
const h = (e) => { e.preventDefault(); const email = r.current?.value; if (!email) { setErrorMsg('x'); return; } };`;
  check(
    'a non-submit handler is not judged as one (control)',
    scanComponent(NOT_A_SUBMIT, 'Change.tsx').length === 0,
    JSON.stringify(scanComponent(NOT_A_SUBMIT, 'Change.tsx'))
  );

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'form-validation-'));
  fs.writeFileSync(path.join(tmp, 'A.tsx'), SILENT);
  check('the walker finds components on disk', walk(tmp).length === 1);
  fs.rmSync(tmp, { recursive: true, force: true });

  if (failures.length > 0) {
    console.error(`\n✗ ${failures.length} self-test failure(s)`);
    return false;
  }
  return true;
}

function main(): void {
  const argv = process.argv.slice(2);
  const arg = (name: string): string | undefined => {
    const i = argv.indexOf(name);
    return i >= 0 ? argv[i + 1] : undefined;
  };

  if (argv.includes('--selftest')) process.exit(selftest() ? 0 : 1);
  if (!argv.includes('--skip-control') && !selftest()) process.exit(1);

  const base = path.resolve(arg('--root') ?? REPO_ROOT);
  const dir = path.join(base, SOURCE_DIR);
  if (!fs.existsSync(dir)) {
    console.error(`✗ Refusing to run: ${dir} does not exist.`);
    process.exit(1);
  }

  const findings: FormFinding[] = [];
  let forms = 0;
  for (const file of walk(dir)) {
    const src = fs.readFileSync(file, 'utf-8');
    const count = [...src.matchAll(/<form\b/g)].length;
    if (count === 0) continue;
    forms += count;
    findings.push(...scanComponent(src, path.relative(base, file)));
  }

  if (forms < MIN_FORMS) {
    console.error(
      `✗ Refusing to run: only ${forms} <form> element(s) found under ${dir}, below the floor ` +
        `of ${MIN_FORMS}.\n  Zero findings over zero forms reads exactly like six correct forms.`
    );
    process.exit(1);
  }

  if (findings.length === 0) {
    console.log(`✓ All ${forms} form(s) either keep browser validation or replace it.`);
    return;
  }

  console.error(`✗ ${findings.length} form defect(s) across ${forms} form(s):\n`);
  for (const f of findings) {
    console.error(`  ${f.file}:${f.line}  [${f.rule}]`);
    console.error(`    ${f.detail}`);
    console.error('');
  }
  process.exit(1);
}

main();

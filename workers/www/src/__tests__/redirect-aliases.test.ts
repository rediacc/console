import { describe, test, expect } from 'vitest';
import { EXACT, PATTERNS, ALLOWED_NON_MANIFEST_TARGETS, applyRedirect } from '../redirect-aliases';
import manifest from '../../../../packages/www/dist/route-manifest.json' with { type: 'json' };

type ManifestEntry = { path: string; title: string; section: string; slug: string; keywords: string[] };
const manifestPaths = new Set((manifest as ManifestEntry[]).map((e) => e.path));
const allLiveTargets = new Set<string>([...manifestPaths, ...ALLOWED_NON_MANIFEST_TARGETS]);

describe('EXACT redirect rules', () => {
  test('every 301 target is a live page', () => {
    const broken: Array<{ from: string; to: string }> = [];
    for (const [from, rule] of Object.entries(EXACT)) {
      if (rule.status === 301 && rule.to !== null) {
        if (!allLiveTargets.has(rule.to)) {
          broken.push({ from, to: rule.to });
        }
      }
    }
    expect(broken).toEqual([]);
  });

  test('no redirect chains (target must not itself redirect elsewhere)', () => {
    // Self-maps like /checkout/success -> /checkout/success are legal —
    // they trigger the lang-prefix addition when the request has no lang,
    // and the Worker's self-redirect guard prevents actual loops when
    // lang is already present.
    //
    // A rule like /apk/x86_64 -> /downloads pointing to a self-map
    // target /downloads -> /downloads is ALSO legal: the Worker resolves
    // the first redirect to /en/downloads in one hop (the lang-prefix
    // is added in the same step), no chain is actually traversed.
    //
    // We only flag genuine chains: A -> B where B -> C with C !== B.
    const chains: Array<{ from: string; to: string; via: string }> = [];
    for (const [from, rule] of Object.entries(EXACT)) {
      if (rule.status !== 301 || rule.to === null || rule.to === from) continue;
      const next = EXACT[rule.to];
      if (next && next.status === 301 && next.to !== null && next.to !== rule.to) {
        chains.push({ from, to: rule.to, via: next.to });
      }
    }
    expect(chains).toEqual([]);
  });

  test('all rules have non-empty rationale', () => {
    for (const [from, rule] of Object.entries(EXACT)) {
      expect(rule.rationale.length).toBeGreaterThan(10);
      expect(from.startsWith('/')).toBe(true);
    }
  });

  test('410 entries have to=null, 301 entries have non-null to', () => {
    for (const [from, rule] of Object.entries(EXACT)) {
      if (rule.status === 410) {
        expect(rule.to).toBeNull();
      } else {
        expect(rule.to).not.toBeNull();
        expect(rule.to!.startsWith('/')).toBe(true);
      }
    }
  });
});

describe('PATTERN redirect rules', () => {
  test('all patterns compile as valid RegExp', () => {
    for (const p of PATTERNS) {
      expect(p.re).toBeInstanceOf(RegExp);
    }
  });

  test('patterns have 301 or 410 status', () => {
    for (const p of PATTERNS) {
      expect([301, 410]).toContain(p.status);
    }
  });
});

describe('applyRedirect() — specific cases from the GSC 404 list', () => {
  test('exact rule: /docs/cli-reference -> /docs/cli-application', () => {
    const r = applyRedirect('/docs/cli-reference');
    expect(r).not.toBeNull();
    expect(r!.to).toBe('/docs/cli-application');
    expect(r!.status).toBe(301);
    expect(r!.via).toBe('exact');
  });

  test('exact 410: /docs/queue-system', () => {
    const r = applyRedirect('/docs/queue-system');
    expect(r).not.toBeNull();
    expect(r!.to).toBeNull();
    expect(r!.status).toBe(410);
  });

  test('exact 410: /blog/advanced-task-workflows (deleted post)', () => {
    const r = applyRedirect('/blog/advanced-task-workflows');
    expect(r).not.toBeNull();
    expect(r!.status).toBe(410);
  });

  test('rdc-cheat-sheet pattern: /docs/rdc-cheat-sheet/setup -> /docs/rdc-cheat-sheet', () => {
    const r = applyRedirect('/docs/rdc-cheat-sheet/setup');
    expect(r).not.toBeNull();
    expect(r!.to).toBe('/docs/rdc-cheat-sheet');
    expect(r!.via).toBe('pattern');
  });

  test('contact-typo pattern: /trntact -> /contact', () => {
    const r = applyRedirect('/trntact');
    expect(r).not.toBeNull();
    expect(r!.to).toBe('/contact');
    expect(r!.via).toBe('pattern');
  });

  test('console pattern: /console -> /account', () => {
    const r = applyRedirect('/console');
    expect(r).not.toBeNull();
    expect(r!.to).toBe('/account');
  });

  test('console pattern: /console/login -> /account (subpath)', () => {
    const r = applyRedirect('/console/login');
    expect(r).not.toBeNull();
    expect(r!.to).toBe('/account');
  });

  test('legal concat pattern: /cookie-policy/telemetry-policy -> /telemetry-policy ($2)', () => {
    const r = applyRedirect('/cookie-policy/telemetry-policy');
    expect(r).not.toBeNull();
    expect(r!.to).toBe('/telemetry-policy');
    expect(r!.via).toBe('pattern');
  });

  test('EXACT wins over PATTERN: /terms-of-service/acceptable-use-policy -> 410 (not /acceptable-use-policy via pattern)', () => {
    const r = applyRedirect('/terms-of-service/acceptable-use-policy');
    expect(r).not.toBeNull();
    expect(r!.via).toBe('exact');
    expect(r!.status).toBe(410);
    expect(r!.to).toBeNull();
  });

  test('unmatched path -> null', () => {
    const r = applyRedirect('/some/random/path-that-does-not-exist');
    expect(r).toBeNull();
  });

  test('live path -> null (no accidental redirect)', () => {
    // /docs/installation is a live page; must not match any rule
    const r = applyRedirect('/docs/installation');
    expect(r).toBeNull();
  });
});

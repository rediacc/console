import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const SECURITY_TXT_PATH = 'packages/www/public/.well-known/security.txt';
const SECURITY_TXT_URL = new URL('../../../public/.well-known/security.txt', import.meta.url);
const MIN_DAYS_AHEAD = 30;
const MAX_DAYS_AHEAD = 366;
const DAY_MS = 24 * 60 * 60 * 1000;

function fields(text: string): Map<string, string[]> {
  const out = new Map<string, string[]>();
  for (const line of text.split(/\r?\n/)) {
    if (line.trim() === '' || line.startsWith('#')) continue;
    const idx = line.indexOf(':');
    if (idx < 1) throw new Error(`${SECURITY_TXT_PATH}: not a "Field: value" line: ${line}`);
    const name = line.slice(0, idx).trim().toLowerCase();
    out.set(name, [...(out.get(name) ?? []), line.slice(idx + 1).trim()]);
  }
  return out;
}

/** Returns the problems found in a security.txt body, empty when it is valid at `now`. */
function problems(text: string, now: Date): string[] {
  const found: string[] = [];
  const f = fields(text);
  if (!(f.get('contact') ?? []).includes('mailto:security@rediacc.com')) {
    found.push('Contact must include mailto:security@rediacc.com');
  }
  const expires = f.get('expires') ?? [];
  if (expires.length !== 1) {
    found.push('exactly one Expires field is required');
  } else {
    const at = new Date(expires[0]);
    if (Number.isNaN(at.getTime())) {
      found.push(`Expires is not a date: ${expires[0]}`);
    } else {
      const days = (at.getTime() - now.getTime()) / DAY_MS;
      if (days < MIN_DAYS_AHEAD) {
        found.push(
          `Expires is ${Math.floor(days)} days away (minimum ${MIN_DAYS_AHEAD}); bump Expires in ${SECURITY_TXT_PATH}`
        );
      }
      if (days > MAX_DAYS_AHEAD) {
        found.push('Expires is more than a year ahead (RFC 9116 section 2.5.5)');
      }
    }
  }
  for (const name of ['canonical', 'policy']) {
    for (const value of f.get(name) ?? []) {
      if (!value.startsWith('https://')) found.push(`${name} must be an https URL`);
    }
    if ((f.get(name) ?? []).length === 0) found.push(`${name} is required`);
  }
  const policy = (f.get('policy') ?? [])[0] ?? '';
  if (!policy.endsWith('/en/docs/security-disclosure-policy')) {
    found.push('Policy must point at the security-disclosure-policy docs page');
  }
  return found;
}

describe('security.txt', () => {
  const real = readFileSync(SECURITY_TXT_URL, 'utf-8');

  it('is valid and has at least 30 days before Expires', () => {
    expect(problems(real, new Date())).toEqual([]);
  });

  it('control: an Expires 10 days ahead fails and names the file to bump', () => {
    const now = new Date();
    const soon = new Date(now.getTime() + 10 * DAY_MS).toISOString();
    const stale = real.replace(/^Expires:.*$/m, `Expires: ${soon}`);
    const found = problems(stale, now);
    expect(found.length).toBe(1);
    expect(found[0]).toContain(SECURITY_TXT_PATH);
  });

  it('control: an Expires already past fails', () => {
    const now = new Date();
    const past = new Date(now.getTime() - DAY_MS).toISOString();
    expect(problems(real.replace(/^Expires:.*$/m, `Expires: ${past}`), now).length).toBe(1);
  });

  it('control: a missing Contact fails', () => {
    expect(problems(real.replace(/^Contact:.*\n/m, ''), new Date())).toHaveLength(1);
  });
});

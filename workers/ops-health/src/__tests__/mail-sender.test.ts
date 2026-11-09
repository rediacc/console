import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import type { Env } from '../env';
import { mailerState, sendSes } from '../mail';
import { SES_ENV } from './helpers';

describe('ops-health sender', () => {
  it('sends from OPS_MAIL_FROM', async () => {
    let from = '';
    const fetchFn = ((_url: RequestInfo | URL, init?: RequestInit) => {
      from = JSON.parse(String(init?.body)).FromEmailAddress;
      return Promise.resolve(Response.json({ MessageId: 'msg-1' }));
    }) as typeof fetch;
    const result = await sendSes(SES_ENV as unknown as Env, fetchFn, { subject: 's', text: 't' });
    expect(result.ok).toBe(true);
    expect(from).toBe('alerts@example.test');
  });

  it('names OPS_MAIL_FROM when it is missing', () => {
    const rest: Record<string, unknown> = { ...SES_ENV };
    delete rest.OPS_MAIL_FROM;
    expect(mailerState(rest as unknown as Env)).toEqual({
      state: 'unknown',
      detail: 'missing OPS_MAIL_FROM',
    });
  });

  it('deploys ai@notify.rediacc.com, apart from the product noreply@ sender', () => {
    const toml = readFileSync(join(__dirname, '..', '..', 'wrangler.toml'), 'utf8');
    expect(toml).toMatch(/^OPS_MAIL_FROM = "ai@notify\.rediacc\.com"$/m);
  });
});

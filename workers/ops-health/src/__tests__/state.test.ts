import { describe, expect, it, vi } from 'vitest';

import { handleFetch, runCron } from '../index';
import type { Env } from '../env';
import { HOUR, harness, MIN, runtime, T0, YieldingStorage, fakeFetch, fakeSocket } from './helpers';

const TARGETS = JSON.stringify({
  version: 1,
  probes: [{ id: 'app', kind: 'https', host: 'app.example.test' }],
});

interface World {
  appStatus: number;
  sesStatus: number;
  sesBody: string;
  mails: Array<{ subject: string; to: string[]; text: string }>;
}

function world(): World {
  return { appStatus: 200, sesStatus: 200, sesBody: '', mails: [] };
}

function fetchFor(w: World) {
  let n = 0;
  return fakeFetch((url, init) => {
    if (url.hostname.startsWith('email.')) {
      if (w.sesStatus !== 200) return new Response(w.sesBody, { status: w.sesStatus });
      const payload = JSON.parse(String(init?.body));
      w.mails.push({
        subject: payload.Content.Simple.Subject.Data,
        to: payload.Destination.ToAddresses,
        text: payload.Content.Simple.Body.Text.Data,
      });
      n += 1;
      return Response.json({ MessageId: `msg-${n}` });
    }
    if (url.hostname === 'app.example.test') return new Response('', { status: w.appStatus });
    return new Response('{}', { status: 200 });
  });
}

const noSocket = () => fakeSocket({ handshake: new Error('no socket in this suite') });

/** The fields of the /v1/status and /v1/ingest answers these tests read. */
interface StatusBody {
  ok?: boolean;
  transition?: boolean;
  error?: string;
  verdict: string;
  last_cron_at: string | null;
  targets_sha: string | null;
  probes: { probe: string; state: string; detail: string }[];
  ingest: { source: string; state: string }[];
  mail_log: { message_id: string; kind: string }[];
  last_mail_error: { detail: string } | null;
  deploy: { code_sha: string | null; secret_digests: Record<string, string> };
}

async function cron(env: Env, w: World, at: number): Promise<void> {
  await runCron(env, runtime(fetchFor(w).fn, noSocket, at));
}

async function status(env: Env, at: number, token = 'read-token', query = '') {
  const res = await handleFetch(
    new Request(`https://ops.example.test/v1/status${query}`, {
      headers: { authorization: `Bearer ${token}` },
    }),
    env,
    runtime(fakeFetch(() => new Response('')).fn, noSocket, at)
  );
  return { code: res.status, body: (await res.json()) as StatusBody };
}

async function ingest(env: Env, body: unknown, at: number, token = 'ingest-token') {
  const res = await handleFetch(
    new Request('https://ops.example.test/v1/ingest', {
      method: 'POST',
      headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),
    env,
    runtime(fakeFetch(() => new Response('')).fn, noSocket, at)
  );
  return { code: res.status, body: (await res.json()) as StatusBody };
}

describe('D-mail dedupe through real cron runs', () => {
  it('mails once on the second red, again after 24 h, and "recovered" after two greens', async () => {
    const { env } = harness({ OPS_HEALTH_TARGETS: TARGETS });
    const w = world();
    await cron(env, w, T0); // all green baseline
    expect(w.mails).toHaveLength(0);

    w.appStatus = 502;
    await cron(env, w, T0 + 10 * MIN);
    expect(w.mails).toHaveLength(0); // a single red run mails nothing

    await cron(env, w, T0 + 20 * MIN);
    expect(w.mails).toHaveLength(1); // the second consecutive red mails once
    expect(w.mails[0].subject).toBe('[rediacc ops] 1 red, 0 recovered');
    expect(w.mails[0].to).toEqual(['ops@example.test', 'second@example.test']);
    expect(w.mails[0].text).toContain('app');

    await cron(env, w, T0 + 30 * MIN);
    expect(w.mails).toHaveLength(1); // a third red mails nothing

    await cron(env, w, T0 + 20 * MIN + 24 * HOUR);
    expect(w.mails).toHaveLength(2); // 24 h later it mails once
    expect(w.mails[1].text).toContain('STILL RED');

    w.appStatus = 200;
    await cron(env, w, T0 + 25 * HOUR);
    expect(w.mails).toHaveLength(2); // one green is not a recovery yet
    await cron(env, w, T0 + 25 * HOUR + 10 * MIN);
    expect(w.mails).toHaveLength(3);
    expect(w.mails[2].subject).toBe('[rediacc ops] 0 red, 1 recovered');

    const s = await status(env, T0 + 25 * HOUR + 11 * MIN, 'read-token', '?mail=1');
    expect(s.body.mail_log.map((m: { message_id: string }) => m.message_id)).toEqual([
      'msg-1',
      'msg-1',
      'msg-1',
    ]);
  });

  it('an empty OPS_ALERT_EMAILS yields the mailer probe unknown', async () => {
    const { env } = harness({ OPS_HEALTH_TARGETS: TARGETS, OPS_ALERT_EMAILS: ' , ' });
    await cron(env, world(), T0);
    const s = await status(env, T0 + MIN);
    const mailer = s.body.probes.find((p: { probe: string }) => p.probe === 'mailer');
    expect(mailer?.state).toBe('unknown');
    expect(s.body.verdict).toBe('unknown');
  });

  it('an absent OPS_HEALTH_TARGETS is the targets probe unknown and the regions probes still run', async () => {
    const { env } = harness();
    await cron(env, world(), T0);
    const s = await status(env, T0 + MIN);
    const ids = s.body.probes.map((p: { probe: string }) => p.probe);
    expect(s.body.probes.find((p: { probe: string }) => p.probe === 'targets')?.state).toBe(
      'unknown'
    );
    expect(ids).toContain('health:account-eu');
    expect(ids).toContain('health:proxy-edge-eu');
  });
});

describe('bearer checks', () => {
  it('a wrong bearer answers 401 on both routes; an unset token never authorizes', async () => {
    const { env } = harness();
    expect((await status(env, T0, 'wrong')).code).toBe(401);
    expect(
      (
        await ingest(
          env,
          { source: 'drift', state: 'red', detail: '', at: new Date(T0).toISOString() },
          T0,
          'wrong'
        )
      ).code
    ).toBe(401);
    expect(
      (
        await ingest(
          env,
          { source: 'drift', state: 'red', detail: '', at: new Date(T0).toISOString() },
          T0,
          'read-token'
        )
      ).code
    ).toBe(401);
    const unset = harness({ OPS_HEALTH_READ_TOKEN: undefined });
    expect((await status(unset.env, T0, '')).code).toBe(401);
    expect((await status(env, T0)).code).toBe(200);
  });
});

describe('the deploy block', () => {
  it('reports the deployed sha vars and parses the digests var the deploy writes', async () => {
    const { env } = harness({
      OPS_HEALTH_TARGETS_SHA: 'aa11',
      OPS_HEALTH_CODE_SHA: 'bb22',
      OPS_HEALTH_SECRET_DIGESTS: 'OPS_ALERT_EMAILS=0123abcd,OPS_HEALTH_TARGETS=89ef,junk',
    });
    const s = await status(env, T0);
    expect(s.body.targets_sha).toBe('aa11');
    expect(s.body.deploy).toEqual({
      code_sha: 'bb22',
      secret_digests: { OPS_ALERT_EMAILS: '0123abcd', OPS_HEALTH_TARGETS: '89ef' },
    });
  });
});

describe('ingest', () => {
  it('refuses a malformed body with 400', async () => {
    const { env } = harness();
    expect(
      (await ingest(env, { source: 'Bad Source', state: 'red', at: '2026-11-04T00:00:00Z' }, T0))
        .code
    ).toBe(400);
    expect(
      (await ingest(env, { source: 'drift', state: 'amber', at: '2026-11-04T00:00:00Z' }, T0)).code
    ).toBe(400);
    expect((await ingest(env, { source: 'drift', state: 'red', at: 'yesterday' }, T0)).code).toBe(
      400
    );
  });

  it('transitions on first receipt and is mailed by the next cron run; a fresh red makes the verdict red', async () => {
    const { env } = harness({ OPS_HEALTH_TARGETS: TARGETS });
    const w = world();
    const first = await ingest(
      env,
      { source: 'drift', state: 'red', detail: 'pins stale', at: new Date(T0).toISOString() },
      T0
    );
    expect(first.body).toEqual({ ok: true, transition: true });
    const again = await ingest(
      env,
      { source: 'drift', state: 'red', detail: 'pins stale', at: new Date(T0).toISOString() },
      T0
    );
    expect(again.body.transition).toBe(false);
    await cron(env, w, T0 + MIN);
    expect(w.mails).toHaveLength(1);
    expect(w.mails[0].text).toContain('ingest drift: pins stale');
    expect((await status(env, T0 + 2 * MIN)).body.verdict).toBe('red');
  });

  it('an ingest POST issued during a cron run is serialized, and both writes survive', async () => {
    const { env } = harness({ OPS_HEALTH_TARGETS: TARGETS });
    const w = world();
    const at = new Date(T0).toISOString();
    await Promise.all([
      cron(env, w, T0),
      ingest(env, { source: 'local-machine-a', state: 'green', detail: 'ok', at }, T0),
      ingest(env, { source: 'ci-weekly', state: 'green', detail: 'ok', at }, T0),
    ]);
    const s = await status(env, T0 + MIN);
    expect(s.body.last_cron_at).toBe(at);
    expect(s.body.ingest.map((r: { source: string }) => r.source)).toEqual([
      'ci-weekly',
      'local-machine-a',
    ]);
  });

  it('the yielding storage really loses a write when two read-modify-writes are not serialized', async () => {
    // Anti-vacuity for the test above: without the object's serial chain, this storage interleaves.
    const storage = new YieldingStorage();
    const naive = async (key: string) => {
      const doc = (await storage.get<Record<string, number>>('doc')) ?? {};
      doc[key] = 1;
      await storage.put('doc', doc);
    };
    await Promise.all([naive('a'), naive('b')]);
    expect(Object.keys((await storage.get<Record<string, number>>('doc')) ?? {})).toHaveLength(1);
  });
});

describe('SES failure (W3)', () => {
  it('a mocked SES 400 is logged with its body and leaves the transition unmailed, so the next run retries', async () => {
    const { env } = harness({ OPS_HEALTH_TARGETS: TARGETS });
    const w = world();
    const errors = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    await cron(env, w, T0);
    w.appStatus = 502;
    w.sesStatus = 400;
    w.sesBody = '{"message":"Email address is not verified"}';
    await cron(env, w, T0 + 10 * MIN);
    await cron(env, w, T0 + 20 * MIN); // due now, but SES refuses
    expect(w.mails).toHaveLength(0);
    expect(errors.mock.calls.flat().join(' ')).toContain('Email address is not verified');
    const failed = await status(env, T0 + 21 * MIN, 'read-token', '?mail=1');
    expect(failed.body.last_mail_error?.detail).toContain('400');
    expect(failed.body.last_mail_error?.detail).toContain('Email address is not verified');
    expect(failed.body.mail_log).toEqual([]);

    w.sesStatus = 200;
    await cron(env, w, T0 + 30 * MIN);
    expect(w.mails).toHaveLength(1);
    expect(w.mails[0].subject).toBe('[rediacc ops] 1 red, 0 recovered');
    errors.mockRestore();
  });
});

describe('the CT cache', () => {
  it('asks certspotter once per host and issuer within ct_cache_hours, and again after', async () => {
    const { env } = harness({
      OPS_HEALTH_TARGETS: JSON.stringify({
        version: 1,
        probes: [
          {
            id: 'imaps',
            kind: 'tls',
            host: 'mail.example.test',
            port: 993,
            expect: "Let's Encrypt",
          },
        ],
      }),
    });
    let ctCalls = 0;
    const f = fakeFetch((url) => {
      if (url.hostname === 'api.certspotter.com') {
        ctCalls += 1;
        return Response.json([
          {
            id: '1',
            not_after: '2027-01-01T00:00:00Z',
            dns_names: ['*.example.test'],
            issuer: { friendly_name: "Let's Encrypt" },
          },
        ]);
      }
      return new Response('{}', { status: 200 });
    });
    const ok = () => fakeSocket({ handshake: 'ok' });
    await runCron(env, runtime(f.fn, ok, T0));
    await runCron(env, runtime(f.fn, ok, T0 + 10 * MIN));
    expect(ctCalls).toBe(1);
    await runCron(env, runtime(f.fn, ok, T0 + 7 * HOUR));
    expect(ctCalls).toBe(2);
    const s = await status(env, T0 + 7 * HOUR + MIN);
    expect(s.body.probes.find((p: { probe: string }) => p.probe === 'imaps')?.state).toBe('green');
  });
});

describe('the Monday digest', () => {
  it('is sent once on Monday at or after 06:00 UTC and logged as a digest', async () => {
    const { env } = harness({ OPS_HEALTH_TARGETS: TARGETS });
    const w = world();
    const monday0550 = Date.parse('2026-11-09T05:50:00.000Z');
    await cron(env, w, monday0550);
    expect(w.mails).toHaveLength(0);
    await cron(env, w, monday0550 + 10 * MIN);
    expect(w.mails).toHaveLength(1);
    expect(w.mails[0].subject).toMatch(
      /^\[rediacc ops\] weekly digest: 0 red, 0 unknown, \d+ green$/
    );
    await cron(env, w, monday0550 + 20 * MIN);
    expect(w.mails).toHaveLength(1);
    const s = await status(env, monday0550 + 21 * MIN, 'read-token', '?mail=1');
    expect(s.body.mail_log[0].kind).toBe('digest');
  });
});

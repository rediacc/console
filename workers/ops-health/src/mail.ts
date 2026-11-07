import { signAwsRequest } from './aws-sigv4';
import type { Env } from './env';
import type { DueItem, StatusView } from './state';
import type { TriState } from './targets';

/**
 * SES v2 mail through the copied SigV4 helper (W3). One mail per cron run lists every due transition; a failed send is logged with SES's body and leaves every transition unmailed, so the next run retries.
 */

export type SendResult = { ok: true; messageId: string } | { ok: false; detail: string };

export function recipients(env: Env): string[] {
  return (env.OPS_ALERT_EMAILS ?? '')
    .split(',')
    .map((address) => address.trim())
    .filter((address) => address.length > 0);
}

const NO_CRON_RUN = 'never';
const SES_KEYS = [
  'AWS_SES_ACCESS_KEY_ID_EU',
  'AWS_SES_SECRET_ACCESS_KEY_EU',
  'AWS_SES_REGION_EU',
  'OPS_MAIL_FROM',
] as const;

/** The `mailer` probe: unknown when there is nobody to mail or a SES setting is missing (named, never printed), green otherwise. */
export function mailerState(env: Env): { state: TriState; detail: string } {
  if (recipients(env).length === 0) {
    return { state: 'unknown', detail: 'OPS_ALERT_EMAILS is empty: no recipient to mail' };
  }
  const missing = SES_KEYS.filter((key) => !env[key]);
  if (missing.length > 0) return { state: 'unknown', detail: `missing ${missing.join(', ')}` };
  return { state: 'green', detail: `${recipients(env).length} recipient(s)` };
}

export function alertSubject(items: DueItem[]): string {
  const red = items.filter((item) => item.reason !== 'recovered').length;
  const recovered = items.length - red;
  return `[rediacc ops] ${red} red, ${recovered} recovered`;
}

const REASON_TEXT: Record<DueItem['reason'], string> = {
  red: 'RED',
  'still-red': 'STILL RED',
  recovered: 'RECOVERED',
};

export function alertBody(items: DueItem[], at: string): string {
  const lines = [`ops-health run at ${at}`, ''];
  for (const item of items) {
    lines.push(`${REASON_TEXT[item.reason]}  ${item.origin} ${item.id}: ${item.detail}`);
  }
  lines.push('', 'Full state: GET /v1/status on the ops-health Worker.');
  return lines.join('\n');
}

export function digestSubject(view: StatusView): string {
  const count = (state: TriState) => view.probes.filter((p) => p.state === state).length;
  return `[rediacc ops] weekly digest: ${count('red')} red, ${count('unknown')} unknown, ${count('green')} green`;
}

export function digestBody(view: StatusView, at: string): string {
  const lines = [
    `ops-health weekly digest at ${at}. This mail arriving is the proof the alerter is alive.`,
    `verdict: ${view.verdict}; last cron run: ${view.last_cron_at ?? NO_CRON_RUN}; targets sha: ${view.targets_sha ?? 'none'}`,
    '',
  ];
  for (const probe of view.probes)
    lines.push(`${probe.state.padEnd(7)} ${probe.probe}: ${probe.detail}`);
  if (view.ingest.length > 0) {
    lines.push('');
    for (const row of view.ingest)
      lines.push(`${row.state.padEnd(7)} ingest ${row.source} (${row.at}): ${row.detail}`);
  }
  return lines.join('\n');
}

export async function sendSes(
  env: Env,
  fetchFn: typeof fetch,
  mail: { subject: string; text: string }
): Promise<SendResult> {
  const to = recipients(env);
  const state = mailerState(env);
  if (state.state !== 'green') return { ok: false, detail: state.detail };
  const region = env.AWS_SES_REGION_EU as string;
  const endpoint = `https://email.${region}.amazonaws.com/v2/email/outbound-emails`;
  const body = JSON.stringify({
    FromEmailAddress: env.OPS_MAIL_FROM,
    Destination: { ToAddresses: to },
    Content: {
      Simple: {
        Subject: { Data: mail.subject, Charset: 'UTF-8' },
        Body: { Text: { Data: mail.text, Charset: 'UTF-8' } },
      },
    },
  });
  try {
    const signed = await signAwsRequest(
      {
        accessKeyId: env.AWS_SES_ACCESS_KEY_ID_EU as string,
        secretAccessKey: env.AWS_SES_SECRET_ACCESS_KEY_EU as string,
        region,
        service: 'ses',
      },
      'POST',
      endpoint,
      { 'content-type': 'application/json' },
      body
    );
    const response = await fetchFn(signed.url, { method: 'POST', headers: signed.headers, body });
    const text = await response.text();
    if (!response.ok) {
      const detail = `SES answered ${response.status}: ${text.slice(0, 500)}`;
      console.error(`ops-health mail failed: ${detail}`);
      return { ok: false, detail };
    }
    let messageId = '';
    try {
      messageId = String((JSON.parse(text) as { MessageId?: string }).MessageId ?? '');
    } catch {
      messageId = '';
    }
    if (!messageId) {
      const detail = `SES answered ${response.status} without a MessageId`;
      console.error(`ops-health mail failed: ${detail}`);
      return { ok: false, detail };
    }
    return { ok: true, messageId };
  } catch (error) {
    const detail = `SES request failed: ${error instanceof Error ? error.message : String(error)}`;
    console.error(`ops-health mail failed: ${detail}`);
    return { ok: false, detail };
  }
}

import { t } from '../../i18n/index.js';
import { ValidationError } from '../../utils/errors.js';
import { readStdinValue } from '../../utils/stdin.js';

/** Environment names of the headless login. Secrets are read from the environment or stdin, never argv. */
export const LOGIN_EMAIL_ENV = 'REDIACC_LOGIN_EMAIL';
export const LOGIN_PASSWORD_ENV = 'REDIACC_LOGIN_PASSWORD';
export const LOGIN_TOTP_ENV = 'REDIACC_LOGIN_TOTP';

const SESSION_COOKIE = 'access_token';
const API = '/account/api/v1';

/** The scopes a device-code login grants; the privileged ones are dropped when the account is a plain member. */
const BASE_SCOPES = [
  'license:activate',
  'license:read',
  'subscription:read',
  'backup:read',
  'config:enroll',
] as const;
const PRIVILEGED_SCOPES = ['audit:write', 'backup:manage'] as const;

export interface PasswordLoginInput {
  email: string;
  password: string;
  totp?: string;
}

/** True when the environment asks for the headless password path. */
export function wantsPasswordLogin(passwordStdin: boolean): boolean {
  return passwordStdin || Boolean(process.env[LOGIN_EMAIL_ENV] && process.env[LOGIN_PASSWORD_ENV]);
}

/** Email from the environment; password from the environment, or stdin under --password-stdin. */
export async function resolvePasswordLoginInput(
  passwordStdin: boolean
): Promise<PasswordLoginInput> {
  const email = process.env[LOGIN_EMAIL_ENV]?.trim();
  if (!email) {
    throw new ValidationError(
      t('commands.subscription.login.passwordMissing', { field: LOGIN_EMAIL_ENV })
    );
  }
  const password = passwordStdin ? await readStdinValue() : process.env[LOGIN_PASSWORD_ENV];
  if (!password) {
    throw new ValidationError(
      t('commands.subscription.login.passwordMissing', {
        field: passwordStdin ? '--password-stdin' : LOGIN_PASSWORD_ENV,
      })
    );
  }
  const totp = process.env[LOGIN_TOTP_ENV]?.trim();
  return { email, password, ...(totp ? { totp } : {}) };
}

interface Reply<T> {
  status: number;
  body: T;
  cookie?: string;
}

async function post<T>(
  serverUrl: string,
  path: string,
  body: unknown,
  cookie?: string
): Promise<Reply<T>> {
  const resp = await fetch(`${serverUrl}${API}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(cookie ? { Cookie: cookie } : {}) },
    body: JSON.stringify(body),
  });
  return readReply<T>(resp);
}

async function readReply<T>(resp: Response): Promise<Reply<T>> {
  const text = await resp.text();
  let body = {} as T;
  try {
    body = text ? (JSON.parse(text) as T) : body;
  } catch {
    // Non-JSON error page: the status alone is reported.
  }
  const found = resp.headers
    .getSetCookie()
    .map((c) => c.split(';')[0])
    .find((c) => c.startsWith(`${SESSION_COOKIE}=`));
  return { status: resp.status, body, cookie: found };
}

/** A refusal that names the step and the server's own message, never a submitted value. */
function refusal(step: string, reply: Reply<{ error?: string; code?: string }>): ValidationError {
  const detail = reply.body.error ?? `HTTP ${reply.status}`;
  return new ValidationError(
    t('commands.subscription.login.passwordRefused', { step, status: reply.status, error: detail })
  );
}

/** Log in with email and password (plus a 2FA code when required) and return the session cookie. */
async function openSession(serverUrl: string, input: PasswordLoginInput): Promise<string> {
  const login = await post<{
    requiresTwoFactor?: boolean;
    challengeToken?: string;
    error?: string;
  }>(serverUrl, '/auth/login', { email: input.email, password: input.password });
  if (login.status >= 400) throw refusal('login', login);

  if (login.body.requiresTwoFactor) {
    if (!input.totp) {
      throw new ValidationError(
        t('commands.subscription.login.totpRequired', { field: LOGIN_TOTP_ENV })
      );
    }
    const verify = await post<{ error?: string }>(serverUrl, '/auth/2fa/verify', {
      challengeToken: login.body.challengeToken,
      code: input.totp,
    });
    if (verify.status >= 400) throw refusal('2fa', verify);
    if (!verify.cookie) throw new ValidationError(t('commands.subscription.login.noSession'));
    return verify.cookie;
  }
  if (!login.cookie) throw new ValidationError(t('commands.subscription.login.noSession'));
  return login.cookie;
}

interface MintReply {
  token?: string;
  error?: string;
  code?: string;
}

/**
 * Mint the CLI api token the way a device-code approval does: a session cookie, the primary
 * subscription from /portal/me, then POST /api-tokens with the device flow's scopes. A plain member
 * is refused the privileged scopes (INSUFFICIENT_ORG_ROLE), so the mint is retried without them.
 */
export async function loginWithPassword(
  serverUrl: string,
  input: PasswordLoginInput
): Promise<string> {
  const cookie = await openSession(serverUrl, input);

  const meResp = await readReply<{
    subscription?: { id?: string } | null;
    activeTeam?: { id?: string } | null;
    error?: string;
  }>(await fetch(`${serverUrl}${API}/portal/me`, { headers: { Cookie: cookie } }));
  if (meResp.status >= 400) throw refusal('session', meResp);
  const subscriptionId = meResp.body.subscription?.id;
  if (!subscriptionId) throw new ValidationError(t('commands.subscription.login.noSubscription'));
  const teamId = meResp.body.activeTeam?.id;

  const mint = (scopes: readonly string[]) =>
    post<MintReply>(
      serverUrl,
      '/api-tokens',
      { subscriptionId, name: 'CLI (headless login)', scopes, ...(teamId ? { teamId } : {}) },
      cookie
    );
  let minted = await mint([...BASE_SCOPES, ...PRIVILEGED_SCOPES]);
  if (minted.status === 403 && minted.body.code === 'INSUFFICIENT_ORG_ROLE') {
    minted = await mint(BASE_SCOPES);
  }
  if (minted.status >= 400) throw refusal('token', minted);
  if (!minted.body.token) throw new ValidationError(t('commands.subscription.login.noSession'));
  return minted.body.token;
}

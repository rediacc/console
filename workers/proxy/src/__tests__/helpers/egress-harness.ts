/** The shared AccountEgress fixture of egress.test.ts and egress-writeback.test.ts: a fake issuer and account binding that record what reached them. */

import { EXECUTOR_TOKEN_PLACEHOLDER } from '../../egress';
import type { ExecutorIssuerRpc } from '../../issued-token';
import { ACCOUNT_EGRESS_HOST } from '../../org-executor-support';

export const API = `http://${ACCOUNT_EGRESS_HOST}/account/api/v1`;

/** `idFromName(name).toString()` is `id:<name>`, which is what OrgExecutor passes as `containerId` for that instance (`this.ctx.id.toString()`). */
export const NAMES = {
  idFromName: (name: string) => ({ toString: () => `id:${name}` }),
};

export function setup() {
  const seen: Request[] = [];
  const state = { issues: [] as string[], fetches: 0, relocates: 0 };
  const issuer = {
    relocate: () => {
      state.relocates += 1;
      return Promise.reject(new Error('the egress never relocates'));
    },
    issue: (orgId: string) => {
      state.issues.push(orgId);
      return Promise.resolve({
        token: `rdt_for_${orgId}`,
        expiresAt: new Date(Date.now() + 45 * 60_000).toISOString(),
      });
    },
    fetch: () => {
      state.fetches += 1;
      return Promise.reject(new Error('never'));
    },
  } as unknown as Service<ExecutorIssuerRpc>;
  const account = {
    fetch: (r: Request) => {
      seen.push(r);
      return Promise.resolve(Response.json({}));
    },
  } as unknown as Fetcher;
  const env = {
    ACCOUNT_URL: 'https://account.test',
    ACCOUNT: account,
    ISSUER: issuer,
  };
  return { env, seen, state };
}

export function introspect(): Request {
  return new Request(`${API}/proxy/introspect`, {
    method: 'POST',
    headers: { authorization: `Bearer ${EXECUTOR_TOKEN_PLACEHOLDER}` },
    body: '{}',
  });
}

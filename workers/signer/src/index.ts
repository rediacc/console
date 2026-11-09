import { WorkerEntrypoint } from 'cloudflare:workers';
import type {
  DelegationCert,
  RepoLicense,
  SignedDelegationCert,
  SignedRepoLicense,
  SignedSubscriptionBlob,
  SubscriptionData,
} from '@rediacc/shared/subscription';
import { CryptoService } from '../../../private/account/src/services/crypto.service.js';
import {
  createLicenseSigner,
  d1CertificateAudit,
  d1ControlScope,
  d1SharedScope,
  parseSignerCaller,
  type SignerCaller,
  type LicenseSigner as SignerService,
  type SignResult,
} from '../../../private/account/src/services/license-signer.service.js';

/**
 * The regional licence signer, `signer-<region>` and `signer-bench-<region>` (agent/plans/PLAN-enterprise-isolation.md, Design "Signers"). It has no route, no workers.dev host and no preview URL: it is reached only through a service binding that names the `LicenseSigner` entrypoint, and the default fetch answers 404 to anything else.
 *
 * The caller's identity is the binding's deploy-time props, `{ tier: 'shared', region }` or `{ tier: 'enterprise', companyId, region }`, read from `ctx.props` and never from an argument, so a caller's Worker code cannot claim another identity. Four RPC methods: `probe()` reports the region and the public key id and signs nothing; `signRepoLicense`, `signSubscriptionBlob` and `signDelegationCert` check the request against the caller's scope and answer `{ ok: true, signed }` or `{ ok: false, reason }` with a `SIGNER_*` code. The scope rules live in private/account/src/services/license-signer.service.ts and are not repeated here.
 *
 * Bindings (workers/signer/wrangler.template.toml, rendered by .ci/rediacc_ci/deploy/deploy_signer.py): `CONTROL`, the region's control database; `SHARED`, the region's `account-<r>` database, read only; the `REGION` and `SHARED_HOSTS` vars; and the secrets `ACCOUNT_ED25519_PRIVATE_KEY` and `ACCOUNT_ED25519_PUBLIC_KEY`. No value of either secret is logged, returned or put in an error: an unexpected failure is logged by its error name alone and rejects with `SIGNER_UNAVAILABLE`.
 */

interface Env {
  CONTROL: D1Database;
  SHARED: D1Database;
  REGION?: string;
  /** Comma-separated hosts a shared caller's renewalUrl may name; unset means `<REGION>.rediacc.cloud`. */
  SHARED_HOSTS?: string;
  ACCOUNT_ED25519_PRIVATE_KEY?: string;
  ACCOUNT_ED25519_PUBLIC_KEY?: string;
}

/** The one rejection an RPC caller sees for anything but a scope refusal. */
const SIGNER_UNAVAILABLE = 'SIGNER_UNAVAILABLE';

/** Key import is per isolate; a failed import is not cached, so the next call retries it. */
let cryptoReady: Promise<CryptoService> | null = null;

function signingKey(env: Env): Promise<CryptoService> {
  if (!cryptoReady) {
    const privateKey = env.ACCOUNT_ED25519_PRIVATE_KEY;
    const publicKey = env.ACCOUNT_ED25519_PUBLIC_KEY;
    if (!privateKey || !publicKey) return Promise.reject(new Error('SIGNER_KEY_UNSET'));
    const service = new CryptoService();
    cryptoReady = service.init(privateKey, publicKey).then(
      () => service,
      (error: unknown) => {
        cryptoReady = null;
        throw error;
      }
    );
  }
  return cryptoReady;
}

function sharedHosts(env: Env): string[] | undefined {
  const hosts = (env.SHARED_HOSTS ?? '')
    .split(',')
    .map((h) => h.trim())
    .filter((h) => h !== '');
  return hosts.length > 0 ? hosts : undefined;
}

async function signer(env: Env): Promise<SignerService> {
  if (!env.REGION) throw new Error('SIGNER_REGION_UNSET');
  const now = () => new Date();
  return createLicenseSigner({
    region: env.REGION,
    crypto: await signingKey(env),
    now,
    control: d1ControlScope(env.CONTROL, now),
    shared: d1SharedScope(env.SHARED),
    audit: d1CertificateAudit(env.CONTROL, `signer-${env.REGION}`, now),
    sharedHosts: sharedHosts(env),
  });
}

/** Run one RPC; any thrown error is logged by name only and replaced by SIGNER_UNAVAILABLE. */
async function guarded<T>(method: string, run: () => Promise<T>): Promise<T> {
  try {
    return await run();
  } catch (error) {
    const name = error instanceof Error ? error.name : typeof error;
    const code =
      error instanceof Error && /^SIGNER_[A-Z_]+$/.test(error.message) ? error.message : '';
    console.error(`signer ${method} failed: ${name}${code ? ` ${code}` : ''}`);
    throw new Error(SIGNER_UNAVAILABLE);
  }
}

/** A binding without valid props is refused before any scope read or signature. */
const UNBOUND = { ok: false, reason: 'SIGNER_CALLER_UNBOUND' } as const;

/**
 * One signing RPC as the binding's props name it, never an argument. A module function, not a method: every method of the entrypoint class is callable over RPC whatever its TypeScript visibility, and this one takes a callback that receives the scope-checking service.
 */
function signAs<T>(
  env: Env,
  props: unknown,
  method: string,
  sign: (service: SignerService, caller: SignerCaller) => Promise<SignResult<T>>
): Promise<SignResult<T>> {
  return guarded(method, async () => {
    const caller = parseSignerCaller(props);
    if (!caller) return UNBOUND;
    return sign(await signer(env), caller);
  });
}

export class LicenseSigner extends WorkerEntrypoint<Env, unknown> {
  probe(): Promise<{ region: string; publicKeyId: string }> {
    return guarded('probe', async () => (await signer(this.env)).probe());
  }

  signRepoLicense(license: RepoLicense): Promise<SignResult<SignedRepoLicense>> {
    return signAs(this.env, this.ctx.props, 'signRepoLicense', (s, caller) =>
      s.signRepoLicense(caller, license)
    );
  }

  signSubscriptionBlob(data: SubscriptionData): Promise<SignResult<SignedSubscriptionBlob>> {
    return signAs(this.env, this.ctx.props, 'signSubscriptionBlob', (s, caller) =>
      s.signSubscriptionBlob(caller, data)
    );
  }

  signDelegationCert(cert: DelegationCert): Promise<SignResult<SignedDelegationCert>> {
    return signAs(this.env, this.ctx.props, 'signDelegationCert', (s, caller) =>
      s.signDelegationCert(caller, cert)
    );
  }
}

export default {
  fetch(): Response {
    return new Response('Not Found', { status: 404 });
  },
};

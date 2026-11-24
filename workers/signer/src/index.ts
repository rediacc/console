import { WorkerEntrypoint } from 'cloudflare:workers';
import type {
  DelegationCert,
  RepoLicense,
  SignedDelegationCert,
  SignedRepoLicense,
  SignedSubscriptionBlob,
  SubscriptionData,
} from '@rediacc/shared/subscription';
import type {
  SignerCaller,
  LicenseSigner as SignerService,
  SignResult,
} from '../../../private/account/src/services/license-signer.service.js';
import { parseSignerCaller } from '../../../private/account/src/services/license-signer.service.js';
import {
  createSignerFromEnv,
  type SignerWorkerEnv,
} from '../../../private/account/src/services/preview-signer.service.js';

/**
 * The regional licence signer, `signer-<region>` and `signer-bench-<region>` (agent/plans/PLAN-enterprise-isolation.md, Design "Signers"). It has no route, no workers.dev host and no preview URL: it is reached only through a service binding that names the `LicenseSigner` entrypoint, and the default fetch answers 404 to anything else.
 *
 * The caller's identity is the binding's deploy-time props, `{ tier: 'shared', region }`, `{ tier: 'enterprise', companyId, region }` or, on a preview's own signer, `{ tier: 'preview', name, host, region }`, read from `ctx.props` and never from an argument, so a caller's Worker code cannot claim another identity. Four RPC methods: `probe()` reports the region, the public key id and the caller identity the props carry, and signs nothing; `signRepoLicense`, `signSubscriptionBlob` and `signDelegationCert` check the request against the caller's scope and answer `{ ok: true, signed }` or `{ ok: false, reason }` with a `SIGNER_*` code. The scope rules live in private/account/src/services/license-signer.service.ts and are not repeated here.
 *
 * Two modes, chosen by which private key the env holds (`signerKeyMode`): `ACCOUNT_ED25519_PRIVATE_KEY` is the master mode above (workers/signer/wrangler.template.toml, rendered by .ci/rediacc_ci/deploy/deploy_signer.py: `CONTROL`, the region's control database; `SHARED`, the region's `account-<r>` database, read only; the `REGION` and `SHARED_HOSTS` vars; the key pair as secrets). `DELEGATED_PRIVATE_KEY` is a preview's own `<name>-signer` (workers/signer/wrangler.preview.template.toml, rendered by .ci/rediacc_ci/deploy/preview_signer.py): no `CONTROL`, `SHARED` is the preview's database, and the `CENTRAL_SIGNER` binding supplies a delegation certificate per preview subscription that every repo licence embeds (agent/plans/PLAN-preview-signer.md S2, D2, D4). A Worker holding both private keys, or neither, builds no signer and answers every call `SIGNER_UNAVAILABLE`. No secret value is logged, returned or put in an error: an unexpected failure is logged by its error name alone and rejects with `SIGNER_UNAVAILABLE`.
 */

/** Both modes bind the same entrypoint: the env type and the construction live with the service (private/account/src/services/preview-signer.service.ts). */
type Env = SignerWorkerEnv;

/** The one rejection an RPC caller sees for anything but a scope refusal. */
const SIGNER_UNAVAILABLE = 'SIGNER_UNAVAILABLE';

function signer(env: Env): Promise<SignerService> {
  return createSignerFromEnv(env);
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
  /** Signs nothing. `caller` is the binding props this signer sees, so a caller can prove its deploy-time identity (live box V1): the Cloudflare API does not return a service binding's props. */
  probe(): Promise<{ region: string; publicKeyId: string; caller: SignerCaller | null }> {
    return guarded('probe', async () => ({
      ...(await (await signer(this.env)).probe()),
      caller: parseSignerCaller(this.ctx.props),
    }));
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

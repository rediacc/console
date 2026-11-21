import { DurableObject } from 'cloudflare:workers';
import accountApp from '../../../private/account/src/entry/cloudflare.js';
import {
  type BackupReplicationKey,
  replicationKeyName,
  replicatorAlarm,
  replicatorKick,
} from '../../../private/account/src/services/backup-replicate.service.js';
import { FENCE_ALARM_DELAY_MS, fence, fencedEnv } from './d1-fence.js';

/** The bindings the replicator and its callers read. */
export interface ReplicatorEnv {
  DB: D1Database;
  REGION?: string;
  BACKUP_REPLICATOR?: DurableObjectNamespace<BackupReplicator>;
}

/**
 * One replicate-mode copy stream, named `<subscription>:<lineage>:<target store>`
 * (private/account/src/services/backup-replicate.service.ts). The queue consumer
 * kicks it; its alarm runs one bounded batch through the account app and re-arms
 * while work remains, at the batch's retry time after a failure. The platform runs
 * one alarm of an object at a time, so one rule's batches never overlap, while
 * every other rule has its own object. The kick and alarm logic lives beside the
 * service (replicatorKick, replicatorAlarm), where the node test suite reaches it;
 * this class is the shell that binds it to Durable Object storage. It lives under
 * workers/ because `cloudflare:workers` must not enter the account's node build.
 * Its DB is wrapped by the D1 write fence (d1-fence.ts), and an alarm that finds
 * the fence up runs no batch and moves itself FENCE_ALARM_DELAY_MS later.
 */
export class BackupReplicator extends DurableObject<ReplicatorEnv> {
  constructor(ctx: DurableObjectState, env: ReplicatorEnv) {
    super(ctx, fencedEnv(env));
  }

  async kick(key: BackupReplicationKey): Promise<void> {
    await replicatorKick(this.ctx.storage, key, Date.now());
  }

  override async alarm(): Promise<void> {
    if (await fence.frozen(this.env.DB)) {
      await this.ctx.storage.setAlarm(Date.now() + FENCE_ALARM_DELAY_MS);
      return;
    }
    // The account app takes the Worker's env as an open record. The mapped copy only exists to hand it an env that is assignable to an index-signature type, which the interface ReplicatorEnv is not.
    const env: { [K in keyof ReplicatorEnv]: ReplicatorEnv[K] } = this.env;
    await replicatorAlarm(
      this.ctx.storage,
      (key) => accountApp.runReplicationBatch(env, key),
      () => Date.now()
    );
  }
}

/**
 * The stub of one rule's replicator. An EU region keeps the object inside the EU
 * jurisdiction, as its D1 and buckets are.
 */
export function replicatorStub(
  env: ReplicatorEnv,
  key: BackupReplicationKey
): DurableObjectStub<BackupReplicator> {
  const namespace = env.BACKUP_REPLICATOR;
  if (!namespace) throw new Error('BACKUP_REPLICATOR is not bound on this Worker');
  const scoped = env.REGION === 'eu' ? namespace.jurisdiction('eu') : namespace;
  return scoped.get(scoped.idFromName(replicationKeyName(key)));
}

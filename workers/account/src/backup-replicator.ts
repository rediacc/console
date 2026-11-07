import { DurableObject } from 'cloudflare:workers';
import accountApp from '../../../private/account/src/entry/cloudflare.js';
import {
  type BackupReplicationKey,
  replicationKeyName,
  replicatorAlarm,
  replicatorKick,
} from '../../../private/account/src/services/backup-replicate.service.js';

/** The bindings the replicator and its callers read. */
export interface ReplicatorEnv {
  DB: D1Database;
  REGION?: string;
  BACKUP_REPLICATOR?: DurableObjectNamespace<BackupReplicator>;
  [key: string]: unknown;
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
 */
export class BackupReplicator extends DurableObject<ReplicatorEnv> {
  async kick(key: BackupReplicationKey): Promise<void> {
    await replicatorKick(this.ctx.storage, key, Date.now());
  }

  override async alarm(): Promise<void> {
    await replicatorAlarm(
      this.ctx.storage,
      (key) => accountApp.runReplicationBatch(this.env, key),
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

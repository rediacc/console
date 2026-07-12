/**
 * The v3 `state` bucket — the STATUS half of the config (R2-F2).
 *
 * Everything mutable-at-runtime that must not bump the version counter or push
 * to a remote store lives here: datastore attach status, per-machine and
 * per-cluster observations, per-repo runtime (networkId, registryPort,
 * pushState, branching refs), the networkId forward counter, and the ACME cert
 * cache. Kept in its own module so schema/schemas.ts stays under its line
 * budget and the spec/status split reads at a glance.
 */

import { z } from 'zod';

const resourceName = z
  .string()
  .min(1)
  .max(63)
  .regex(/^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/);

const tagName = z
  .string()
  .min(1)
  .max(63)
  .regex(/^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/);

const absolutePath = z.string().refine((v) => v.startsWith('/'), 'Must be an absolute path');

const AcmeCertCacheSchema = z.object({
  baseDomain: z.string(),
  updatedAt: z.string(),
  sourceMachine: z.string(),
  certCount: z.number().int(),
  certs: z.record(z.string(), z.string()),
  data: z.union([z.string(), z.array(z.string())]),
  rawSize: z.number().int(),
});

const ReflogEntrySchema = z.object({
  ref: z.string(),
  from: z.string().optional(),
  to: z.string(),
  at: z.string(),
  message: z.string().optional(),
});

const PushStateSchema = z.record(
  z.string(),
  z.object({
    verifiedBase: z.string().optional(),
    lastPushAt: z.string(),
    method: z.enum(['rsync', 'delta']),
  })
);

/**
 * A managed read-replica set (spec 05 §1 / R2-F17): replicate is CRUD-from-birth
 * managed state, NOT a fire-and-forget flag pile. `repo replicate status/remove`
 * read/act on this; `repo status` surfaces it.
 */
const ReplicaSetSchema = z.object({
  repo: z.string(),
  datastore: z.string(),
  cluster: z.string(),
  /** Number of replicas + the fork datastore/mount + node per replica. */
  replicas: z.array(
    z.object({
      index: z.number().int(),
      /** The `<datastore>:<tag>` fork record key. */
      fork: z.string(),
      /** Machine the replica fork is attached to. */
      node: z.string(),
    })
  ),
  headless: z.boolean().optional(),
  /** Auto-refresh interval (e.g. "1h"); a reconciler re-clones one at a time. */
  refresh: z.string().optional(),
  /** The datastore snapshot the current forks clone from (refresh cycles it). */
  snapshot: z.string().optional(),
  createdAt: z.string(),
  refreshedAt: z.string().optional(),
});

/**
 * A managed canary set (spec 05 §2, release-ladder rung 2): a second Deployment
 * + Service on SHARED live data, traffic split by the Rediacc-proxy weight
 * annotation. Recorded from birth (R2-F17) so weight/status/remove operate on
 * known sets. `weight` mirrors the live annotation (0 = dark, 100 = the
 * blue/green flip); `undoSnapshot` is the latest rung-0 group snapshot taken
 * before a release-class mutation of this set.
 */
const CanarySetSchema = z.object({
  repo: z.string(),
  cluster: z.string(),
  /** The stable Service the canary splits traffic with. */
  service: z.string(),
  image: z.string(),
  port: z.number().int(),
  replicas: z.number().int(),
  weight: z.number().int().min(0).max(100),
  /** The latest rung-0 release-undo group snapshot name. */
  undoSnapshot: z.string().optional(),
  createdAt: z.string(),
  updatedAt: z.string().optional(),
});

export const StateSchema = z.object({
  datastores: z
    .record(
      resourceName,
      z.object({
        attachedTo: resourceName.optional(),
        writes: z.enum(['ceph', 'local']).optional(),
        mounted: z.boolean().optional(),
        mountPath: absolutePath.optional(),
        attachedAt: z.string().optional(),
        holders: z
          .object({
            loops: z.array(z.string()).optional(),
            dm: z.array(z.string()).optional(),
            volumes: z.array(z.string()).optional(),
          })
          .optional(),
      })
    )
    .optional(),

  machines: z
    .record(
      resourceName,
      z.object({
        lastSeenAt: z.string().optional(),
        renetVersion: z.string().optional(),
      })
    )
    .optional(),

  clusters: z
    .record(
      resourceName,
      z.object({
        memberIds: z.record(z.string(), z.array(z.number().int().min(1))).optional(),
        k3sVersion: z.string().optional(),
        nodes: z
          .record(
            resourceName,
            z.object({
              k3sVersion: z.string().optional(),
              lastSeenAt: z.string().optional(),
            })
          )
          .optional(),
      })
    )
    .optional(),

  repos: z
    .record(
      resourceName,
      z.record(
        tagName,
        z.object({
          networkId: z.number().int().optional(),
          registryPort: z.number().int().min(21000).max(28999).optional(),
          pushState: PushStateSchema.optional(),
          headCommit: z.string().optional(),
          commitMessage: z.string().optional(),
          commitAuthor: z.string().optional(),
          commitParent: z.string().optional(),
          head: z.string().optional(),
          branches: z.record(z.string(), z.string()).optional(),
          reflog: z.array(ReflogEntrySchema).optional(),
        })
      )
    )
    .optional(),

  networkIds: z.object({ next: z.number().int().optional() }).optional(),
  certCache: z.record(z.string(), AcmeCertCacheSchema).optional(),
  /** Managed read-replica sets keyed by set name (spec 05 §1, R2-F17). */
  replicaSets: z.record(z.string(), ReplicaSetSchema).optional(),
  /** Managed canary sets keyed by set name (spec 05 §2, R2-F17). */
  canaries: z.record(z.string(), CanarySetSchema).optional(),
  reconciledAt: z.string().optional(),
});

export type RdcState = z.infer<typeof StateSchema>;
export type AcmeCertCache = z.infer<typeof AcmeCertCacheSchema>;
export type ReplicaSet = z.infer<typeof ReplicaSetSchema>;
export type CanarySet = z.infer<typeof CanarySetSchema>;
export type ReflogEntry = z.infer<typeof ReflogEntrySchema>;
export type RepoRuntimeState = NonNullable<RdcState['repos']>[string][string];

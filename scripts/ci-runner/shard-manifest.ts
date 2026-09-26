/**
 * T2.10. The committed shard manifest a CI leg and a local `--lane/--shard` replay both
 * read, `.ci/config/shards/<lane>.json`.
 *
 * ONE FILE PER LANE, GENERATED FROM THE SAME `shardPlan` THE WORKFLOW'S `matrix.shard`
 * REGION COMES FROM. `gate-bind --write` writes this file next to the workflow region it
 * rewrites, from the same `shardAssignment` call (see `scripts/gate-bind.ts`), so a leg's
 * `--shard-manifest` and its `matrix.shard == N` conjunct can never name two different
 * plans. Reading it here is pure and offline: no `shardPlan` re-run, no lock, no workflow
 * parse -- both a CI leg and `npm run ci -- --lane <lane> --shard i/N` work from a
 * COMMITTED file, not a re-derivation that could disagree with what review saw.
 */
export interface ShardManifestLeg {
  index: number;
  ids: string[];
}

export interface ShardManifestFile {
  lane: string;
  /** How many legs this lane has in total; every leg in `legs` carries the same value. */
  of: number;
  generatedAt: string;
  legs: ShardManifestLeg[];
}

export function shardManifestPath(lane: string): string {
  return `.ci/config/shards/${lane}.json`;
}

/**
 * One lane's manifest from a `shardPlan` result's `shards` array. Refuses an empty input
 * for the same reason every other refusal in this module's neighbour (`lanes.ts`) does: an
 * empty manifest for a lane that asked to be sharded is not "no shards", it is a planner
 * that produced nothing while believing it produced something.
 */
export function buildShardManifest(
  lane: string,
  shards: readonly { index: number; of: number; ids: readonly string[] }[],
  generatedAt: string = new Date().toISOString()
): ShardManifestFile {
  if (shards.length === 0) {
    throw new Error(`buildShardManifest: lane "${lane}" has no shards to record.`);
  }
  const of = shards[0]?.of as number;
  const mismatched = shards.find((s) => s.of !== of);
  if (mismatched !== undefined) {
    throw new Error(
      `buildShardManifest: lane "${lane}" has shards disagreeing on how many legs there are ` +
        `(${of} and ${mismatched.of}).`
    );
  }
  return {
    lane,
    of,
    generatedAt,
    legs: [...shards]
      .sort((a, b) => a.index - b.index)
      .map((s) => ({ index: s.index, ids: [...s.ids] })),
  };
}

/**
 * The inverse of the id->leg-index map `shardAssignment` (`scripts/gate-bind.ts`) already
 * produces. Grouping by encounter order preserves that map's own iteration order, which is
 * itself `shardPlan`'s per-shard `ids` order (topologically sorted, `needs` edges first) --
 * so a manifest built this way runs its ids in the same sequence CI does.
 */
export function legsFromAssignment(
  legs: ReadonlyMap<string, number>,
  of: number
): { index: number; of: number; ids: string[] }[] {
  const byIndex = new Map<number, string[]>();
  for (const [id, index] of legs) {
    const held = byIndex.get(index) ?? [];
    held.push(id);
    byIndex.set(index, held);
  }
  return [...byIndex.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([index, ids]) => ({ index, of, ids }));
}

export function parseShardManifest(text: string, lane: string): ShardManifestFile {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (err) {
    throw new Error(
      `shard manifest for lane "${lane}" is not valid JSON: ${err instanceof Error ? err.message : String(err)}`
    );
  }
  if (parsed === null || typeof parsed !== 'object') {
    throw new Error(`shard manifest for lane "${lane}" must be a JSON object.`);
  }
  const file = parsed as Partial<ShardManifestFile>;
  if (file.lane !== lane) {
    throw new Error(
      `shard manifest names lane "${String(file.lane)}", but "${lane}" was asked for.`
    );
  }
  if (typeof file.of !== 'number' || !Number.isInteger(file.of) || file.of < 1) {
    throw new Error(`shard manifest for lane "${lane}" is missing a valid "of".`);
  }
  if (!Array.isArray(file.legs)) {
    throw new Error(`shard manifest for lane "${lane}" is missing "legs".`);
  }
  for (const leg of file.legs) {
    if (
      leg === null ||
      typeof leg !== 'object' ||
      typeof (leg as ShardManifestLeg).index !== 'number' ||
      !Array.isArray((leg as ShardManifestLeg).ids)
    ) {
      throw new Error(`shard manifest for lane "${lane}" has a malformed leg entry.`);
    }
  }
  return file as ShardManifestFile;
}

/** The exact ids one leg of a committed manifest holds, or a refusal naming what exists. */
export function legIds(file: ShardManifestFile, index: number, of: number): string[] {
  if (file.of !== of) {
    throw new Error(
      `shard manifest for lane "${file.lane}" has ${file.of} leg(s) on record; asked for ` +
        `shard ${index}/${of}. Regenerate the manifest, or ask for shard ${index}/${file.of}.`
    );
  }
  const leg = file.legs.find((l) => l.index === index);
  if (leg === undefined) {
    throw new Error(
      `shard manifest for lane "${file.lane}" has no leg ${index} (of ${of}); legs on record: ` +
        `${file.legs
          .map((l) => l.index)
          .sort((a, b) => a - b)
          .join(', ')}.`
    );
  }
  if (leg.ids.length === 0) {
    throw new Error(
      `shard manifest for lane "${file.lane}" leg ${index} is EMPTY. An empty leg is a runner ` +
        'that would report green having run nothing; regenerate the manifest.'
    );
  }
  return [...leg.ids];
}

/**
 * Free-space preflight for the backup store the large-repository suite uploads to.
 *
 * The local dev store is a RustFS container whose /data lives on Docker's disk. When that disk fills, the seed's chunk PUTs fail with `erasure write quorum` after minutes of retries, so the suite checks the space first and names what is full. A remote store (R2) has no disk to observe, so it is skipped with a stated reason, never passed silently.
 */

/** The container the local dev store runs in (`.ci/rediacc_ci/core/account.py`). */
export const LOCAL_STORE_CONTAINER = 'account-config-rustfs';

/** True when the endpoint is the dev store on this host, whose container disk can be read. */
function isLocalStoreEndpoint(endpoint: string): boolean {
  try {
    const host = new URL(endpoint).hostname;
    return host === '127.0.0.1' || host === 'localhost' || host === '[::1]' || host === '::1';
  } catch {
    return false;
  }
}

export type StoreSpaceVerdict =
  | { kind: 'ok'; freeBytes: number }
  | { kind: 'skipped'; reason: string }
  | { kind: 'full'; message: string };

export interface StoreSpaceInput {
  endpoint: string;
  neededBytes: number;
  /** Free bytes of the store's data disk, or undefined when it could not be read. */
  freeBytes: number | undefined;
}

const gib = (bytes: number): string => (bytes / 1024 ** 3).toFixed(2);

/** Whether the store's disk admits `neededBytes`; the message names what is full and how to free it. */
export function storeSpaceVerdict(input: StoreSpaceInput): StoreSpaceVerdict {
  if (!isLocalStoreEndpoint(input.endpoint)) {
    return {
      kind: 'skipped',
      reason: `the backup store at ${input.endpoint} is not the local ${LOCAL_STORE_CONTAINER} container (a remote store such as R2 has no observable disk)`,
    };
  }
  if (input.freeBytes === undefined || !Number.isFinite(input.freeBytes)) {
    return {
      kind: 'skipped',
      reason: `the free space of ${LOCAL_STORE_CONTAINER}:/data could not be read (is the container running? \`docker exec ${LOCAL_STORE_CONTAINER} df /data\`)`,
    };
  }
  if (input.freeBytes < input.neededBytes) {
    return {
      kind: 'full',
      message: `the backup store disk is full: ${LOCAL_STORE_CONTAINER}:/data (Docker's disk) has ${gib(input.freeBytes)} GiB free and the seed needs ${gib(input.neededBytes)} GiB. Free space on Docker's disk, for example \`docker builder prune\` for build cache or \`docker system df\` to find the rest.`,
    };
  }
  return { kind: 'ok', freeBytes: input.freeBytes };
}

/** Parse `df -B1 --output=avail` output (a header line then the number). */
export function parseDfAvailBytes(output: string): number | undefined {
  const line = output
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => /^\d+$/.test(l))
    .pop();
  return line === undefined ? undefined : Number.parseInt(line, 10);
}

/**
 * The first line of what a failed `docker exec` said. Node's promisified `exec` rejects with `Command failed: <cmd>` as the first line of `message` and the stderr after it, so stderr (when present) is the detail, and a `Command failed:` line is only the fallback when nothing else was said.
 */
export function dockerErrorDetail(err: unknown): string {
  const firstLine = (t: string): string | undefined =>
    t
      .split('\n')
      .map((l) => l.trim())
      .find((l) => l !== '' && !l.startsWith('Command failed:'));
  const stderr = (err as { stderr?: unknown } | null)?.stderr;
  const message = err instanceof Error ? err.message : String(err);
  return (
    (typeof stderr === 'string' ? firstLine(stderr) : undefined) ??
    firstLine(message) ??
    message.split('\n')[0]
  );
}

/** The ` (docker exec: ...)` suffix of a store-space skip reason: only for the local store, the one the docker probe reads; a remote endpoint's skip is about the endpoint, not docker. An error that said nothing adds no suffix. */
export function dockerSkipDetail(endpoint: string, err: unknown): string {
  if (err === undefined || !isLocalStoreEndpoint(endpoint)) return '';
  const detail = dockerErrorDetail(err).trim();
  return detail === '' ? '' : ` (docker exec: ${detail})`;
}

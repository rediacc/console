/**
 * The dispatch counter behind `GET /v1/busy` (agent/plans/PLAN-console-run-index.md D5).
 *
 * The proxy's OrgExecutor counts a request in flight only until its response body closes, so a
 * client that left mid-run lets the container's idle timer start while the dispatch still runs.
 * The executor therefore counts its own running dispatches, and the Durable Object's alarm asks for
 * the count before it stops the container.
 */

export interface BusyCounter {
  /** Run `work` counted as one running dispatch until it settles, however it settles. */
  track<T>(work: () => Promise<T>): Promise<T>;
  /** Dispatches running now. */
  count(): number;
}

export function createBusyCounter(): BusyCounter {
  let running = 0;
  return {
    async track(work) {
      running += 1;
      try {
        return await work();
      } finally {
        running -= 1;
      }
    },
    count: () => running,
  };
}

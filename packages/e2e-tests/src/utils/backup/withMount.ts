/** The mount, sync and unmount steps `withMount` drives; each throws on failure. */
export interface MountOps {
  mount: () => Promise<void>;
  sync: () => Promise<void>;
  unmount: () => Promise<void>;
}

const messageOf = (e: unknown): string => (e instanceof Error ? e.message : String(e));

/**
 * Mount, run the body, sync, unmount. The unmount runs whenever the mount succeeded. When the body (or the sync) threw, the thrown error names that failure first and an unmount failure second, so a stuck unmount never hides the root cause.
 */
export const withMount = async (ops: MountOps, body: () => Promise<void>): Promise<void> => {
  await ops.mount();
  let bodyError: unknown;
  let bodyFailed = false;
  try {
    await body();
    await ops.sync();
  } catch (e) {
    bodyFailed = true;
    bodyError = e;
  }
  try {
    await ops.unmount();
  } catch (unmountError) {
    if (!bodyFailed) throw unmountError;
    throw new Error(
      `body failed: ${messageOf(bodyError)}; then unmount failed: ${messageOf(unmountError)}`,
      { cause: bodyError }
    );
  }
  if (bodyFailed) throw bodyError;
};

/**
 * Playwright test helpers for S3 integration tests.
 *
 * Reads S3 test configuration from environment variables.
 * All four S3_TEST_* variables MUST be set — tests fail immediately if not.
 */

export interface S3TestEnv {
  endpoint: string;
  accessKeyId: string;
  secretAccessKey: string;
  bucket: string;
}

/**
 * Check whether S3 test environment variables are available.
 * Returns true if all required S3_TEST_* vars are set.
 */
export function hasS3TestEnv(): boolean {
  return !!(
    process.env.S3_TEST_ENDPOINT &&
    process.env.S3_TEST_ACCESS_KEY &&
    process.env.S3_TEST_SECRET_KEY &&
    process.env.S3_TEST_BUCKET
  );
}

/**
 * Get S3 test environment from env vars.
 * Throws if any required variable is missing.
 */
export function getS3TestEnv(): S3TestEnv {
  const endpoint = process.env.S3_TEST_ENDPOINT;
  const accessKeyId = process.env.S3_TEST_ACCESS_KEY;
  const secretAccessKey = process.env.S3_TEST_SECRET_KEY;
  const bucket = process.env.S3_TEST_BUCKET;

  if (!endpoint || !accessKeyId || !secretAccessKey || !bucket) {
    const missing = [
      !endpoint && 'S3_TEST_ENDPOINT',
      !accessKeyId && 'S3_TEST_ACCESS_KEY',
      !secretAccessKey && 'S3_TEST_SECRET_KEY',
      !bucket && 'S3_TEST_BUCKET',
    ].filter(Boolean);

    throw new Error(
      `S3 integration test env vars not set: ${missing.join(', ')}. ` +
        'All four S3_TEST_* variables are required.'
    );
  }

  return { endpoint, accessKeyId, secretAccessKey, bucket };
}

/**
 * Generate a unique S3 context name for test isolation.
 */
export function generateS3ContextName(prefix = 's3-test'): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

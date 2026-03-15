/**
 * Shared S3 test configuration for integration tests.
 *
 * Reads S3 connection details from environment variables.
 * All four S3_TEST_* variables MUST be set — tests fail immediately if not.
 */

import { randomBytes } from 'node:crypto';
import type { S3Config } from '../../types/index.js';
import { S3ClientService } from '../s3-client.js';

export interface S3TestConfig {
  endpoint: string;
  accessKeyId: string;
  secretAccessKey: string;
  bucket: string;
  region: string;
  /** Unique per run: `test-{timestamp}-{randomHex}/` */
  prefix: string;
}

/**
 * Read S3 test config from environment variables.
 * Throws if any required variable is missing.
 */
export function getS3TestConfig(): S3TestConfig {
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

  const prefix = `test-${Date.now()}-${randomBytes(4).toString('hex')}`;

  return {
    endpoint,
    accessKeyId,
    secretAccessKey,
    bucket,
    region: 'us-east-1',
    prefix,
  };
}

/**
 * Create an S3ClientService configured for testing.
 * Uses a unique prefix to isolate each test run.
 */
export function createTestS3Client(overrides?: Partial<S3TestConfig>): S3ClientService {
  const config = getS3TestConfig();
  const merged = { ...config, ...overrides };

  const s3Config: S3Config = {
    endpoint: merged.endpoint,
    bucket: merged.bucket,
    region: merged.region,
    accessKeyId: merged.accessKeyId,
    secretAccessKey: merged.secretAccessKey,
    prefix: merged.prefix,
  };

  return new S3ClientService(s3Config);
}

/**
 * Delete all objects under the given prefix.
 * Used in afterAll to clean up test data.
 */
export async function cleanupS3Prefix(client: S3ClientService, prefix: string): Promise<void> {
  const keys = await client.listKeys(prefix);
  for (const key of keys) {
    await client.deleteObject(key);
  }
}

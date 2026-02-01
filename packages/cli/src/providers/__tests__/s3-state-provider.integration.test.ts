/**
 * S3StateProvider integration tests against a real S3-compatible server (RustFS).
 *
 * Tests the provider-level abstraction (S3MachineProvider.getWithVaultStatus)
 * using a real S3 backend instead of a mocked S3ClientService.
 *
 * Requires S3_TEST_ENDPOINT, S3_TEST_ACCESS_KEY, S3_TEST_SECRET_KEY, S3_TEST_BUCKET.
 */

import { describe, it, expect, afterAll } from 'vitest';
import {
  getS3TestConfig,
  createTestS3Client,
  cleanupS3Prefix,
} from '../../services/__tests__/s3-test-config.js';
import { S3StateProvider } from '../s3-state-provider.js';
import type { NamedContext } from '../../types/index.js';

const config = getS3TestConfig();
const client = createTestS3Client();

afterAll(async () => {
  await cleanupS3Prefix(client, '');
});

/**
 * Create an S3StateProvider in plaintext mode (no masterPassword),
 * using the same prefix as the test S3 client so they share data.
 */
async function createProvider(): Promise<InstanceType<typeof S3StateProvider>> {
  const context: NamedContext = {
    name: 'integration-test',
    mode: 's3',
    apiUrl: '',
    s3: {
      endpoint: config.endpoint,
      bucket: config.bucket,
      region: config.region,
      accessKeyId: config.accessKeyId,
      secretAccessKey: config.secretAccessKey,
      prefix: config.prefix,
    },
  };

  return S3StateProvider.create(context);
}

describe('S3StateProvider (real S3)', () => {
  describe('machines.getWithVaultStatus', () => {
    it('should return machine with vaultStatus null when machine exists', async () => {
      await client.putJson('machines/test-machine.json', {
        machineName: 'test-machine',
        ip: '10.0.0.1',
        user: 'ubuntu',
        vaultContent: '{"key":"value"}',
        createdAt: '2025-01-01T00:00:00Z',
        updatedAt: '2025-01-01T00:00:00Z',
      });

      const provider = await createProvider();
      const result = await provider.machines.getWithVaultStatus({
        teamName: 'any-team',
        machineName: 'test-machine',
      });

      expect(result).not.toBeNull();
      expect(result!.machineName).toBe('test-machine');
      expect(result!.vaultStatus).toBeNull();
      expect(result!.vaultContent).toBe('{"key":"value"}');
    });

    it('should return null when machine does not exist', async () => {
      const provider = await createProvider();
      const result = await provider.machines.getWithVaultStatus({
        teamName: 'any-team',
        machineName: 'non-existent',
      });

      expect(result).toBeNull();
    });
  });

  it('should have mode set to s3', async () => {
    const provider = await createProvider();
    expect(provider.mode).toBe('s3');
  });
});

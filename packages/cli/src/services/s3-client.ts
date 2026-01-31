/**
 * S3ClientService - Thin wrapper around @aws-sdk/client-s3.
 * Provides JSON and raw read/write operations with auto-prefixing.
 */

import {
  DeleteObjectCommand,
  GetObjectCommand,
  HeadBucketCommand,
  ListObjectsV2Command,
  PutObjectCommand,
  S3Client,
  CopyObjectCommand,
} from '@aws-sdk/client-s3';
import type { S3Config } from '../types/index.js';

export class S3OperationError extends Error {
  constructor(
    message: string,
    public readonly operation: string,
    public readonly cause?: unknown
  ) {
    super(message);
    this.name = 'S3OperationError';
  }
}

export class S3ClientService {
  private client: S3Client;
  private bucket: string;
  private prefix: string;

  constructor(config: S3Config) {
    this.client = new S3Client({
      endpoint: config.endpoint,
      region: config.region,
      credentials: {
        accessKeyId: config.accessKeyId,
        secretAccessKey: config.secretAccessKey,
      },
      forcePathStyle: true,
    });
    this.bucket = config.bucket;
    this.prefix = config.prefix ? `${config.prefix}/` : '';
  }

  private fullKey(key: string): string {
    return `${this.prefix}${key}`;
  }

  async getJson<T>(key: string): Promise<T | null> {
    try {
      const raw = await this.getRaw(key);
      if (raw === null) return null;
      return JSON.parse(raw) as T;
    } catch (error) {
      if (error instanceof S3OperationError) throw error;
      throw new S3OperationError(`Failed to get JSON from ${key}`, 'getJson', error);
    }
  }

  async putJson(key: string, data: unknown): Promise<void> {
    try {
      await this.putRaw(key, JSON.stringify(data, null, 2));
    } catch (error) {
      if (error instanceof S3OperationError) throw error;
      throw new S3OperationError(`Failed to put JSON to ${key}`, 'putJson', error);
    }
  }

  async getRaw(key: string): Promise<string | null> {
    try {
      const response = await this.client.send(
        new GetObjectCommand({
          Bucket: this.bucket,
          Key: this.fullKey(key),
        })
      );
      return (await response.Body?.transformToString('utf-8')) ?? null;
    } catch (error: unknown) {
      if (this.isNotFoundError(error)) return null;
      throw new S3OperationError(`Failed to get ${key}`, 'getRaw', error);
    }
  }

  async putRaw(key: string, content: string): Promise<void> {
    try {
      await this.client.send(
        new PutObjectCommand({
          Bucket: this.bucket,
          Key: this.fullKey(key),
          Body: content,
          ContentType: 'application/octet-stream',
        })
      );
    } catch (error) {
      throw new S3OperationError(`Failed to put ${key}`, 'putRaw', error);
    }
  }

  async deleteObject(key: string): Promise<void> {
    try {
      await this.client.send(
        new DeleteObjectCommand({
          Bucket: this.bucket,
          Key: this.fullKey(key),
        })
      );
    } catch (error) {
      // S3 delete is idempotent — 404 is fine
      if (!this.isNotFoundError(error)) {
        throw new S3OperationError(`Failed to delete ${key}`, 'deleteObject', error);
      }
    }
  }

  async listKeys(prefix: string): Promise<string[]> {
    const keys: string[] = [];
    let continuationToken: string | undefined;
    const fullPrefix = this.fullKey(prefix);

    try {
      do {
        const response = await this.client.send(
          new ListObjectsV2Command({
            Bucket: this.bucket,
            Prefix: fullPrefix,
            ContinuationToken: continuationToken,
          })
        );

        for (const obj of response.Contents ?? []) {
          if (obj.Key) {
            // Return keys relative to the configured prefix
            const relativeKey = this.prefix ? obj.Key.slice(this.prefix.length) : obj.Key;
            keys.push(relativeKey);
          }
        }

        continuationToken = response.NextContinuationToken;
      } while (continuationToken);

      return keys;
    } catch (error) {
      throw new S3OperationError(`Failed to list keys with prefix ${prefix}`, 'listKeys', error);
    }
  }

  async verifyAccess(): Promise<void> {
    try {
      await this.client.send(
        new HeadBucketCommand({
          Bucket: this.bucket,
        })
      );
    } catch (error) {
      throw new S3OperationError(
        `Failed to access bucket "${this.bucket}". Check credentials and endpoint.`,
        'verifyAccess',
        error
      );
    }
  }

  async moveObject(from: string, to: string): Promise<void> {
    try {
      // Copy then delete (S3 has no native move)
      await this.client.send(
        new CopyObjectCommand({
          Bucket: this.bucket,
          CopySource: `${this.bucket}/${this.fullKey(from)}`,
          Key: this.fullKey(to),
        })
      );
      await this.deleteObject(from);
    } catch (error) {
      if (error instanceof S3OperationError) throw error;
      throw new S3OperationError(`Failed to move ${from} to ${to}`, 'moveObject', error);
    }
  }

  private isNotFoundError(error: unknown): boolean {
    if (typeof error === 'object' && error !== null) {
      const err = error as { name?: string; $metadata?: { httpStatusCode?: number } };
      if (err.name === 'NoSuchKey' || err.name === 'NotFound') return true;
      if (err.$metadata?.httpStatusCode === 404) return true;
    }
    return false;
  }
}

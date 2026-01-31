/**
 * S3QueueService - Queue operations stored as JSON files in S3.
 *
 * Queue items are stored at:
 *   queue/{status}/{taskId}.json
 *
 * Status directories: pending/, active/, completed/, failed/, cancelled/
 */

import { randomUUID } from 'node:crypto';
import type { S3ClientService } from './s3-client.js';

export interface S3QueueItem {
  taskId: string;
  status: 'PENDING' | 'ACTIVE' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  functionName: string;
  machineName?: string;
  bridgeName?: string;
  teamName: string;
  vaultContent: string;
  priority: number;
  params?: Record<string, unknown>;
  retryCount: number;
  errorMessage?: string;
  exitCode?: number;
  consoleOutput?: string;
  createdAt: string;
  updatedAt: string;
  startedAt?: string;
  completedAt?: string;
}

const STATUS_DIRS: Record<S3QueueItem['status'], string> = {
  PENDING: 'queue/pending',
  ACTIVE: 'queue/active',
  COMPLETED: 'queue/completed',
  FAILED: 'queue/failed',
  CANCELLED: 'queue/cancelled',
};

const ALL_STATUSES = Object.keys(STATUS_DIRS) as S3QueueItem['status'][];

export class S3QueueService {
  constructor(private s3: S3ClientService) {}

  async create(item: Omit<S3QueueItem, 'taskId' | 'status' | 'retryCount' | 'createdAt' | 'updatedAt'>): Promise<string> {
    const taskId = randomUUID();
    const now = new Date().toISOString();
    const queueItem: S3QueueItem = {
      ...item,
      taskId,
      status: 'PENDING',
      retryCount: 0,
      createdAt: now,
      updatedAt: now,
    };

    await this.s3.putJson(`${STATUS_DIRS.PENDING}/${taskId}.json`, queueItem);
    return taskId;
  }

  async claim(taskId: string): Promise<S3QueueItem> {
    const item = await this.s3.getJson<S3QueueItem>(`${STATUS_DIRS.PENDING}/${taskId}.json`);
    if (!item) {
      throw new Error(`Queue item ${taskId} not found in pending state`);
    }

    const now = new Date().toISOString();
    const updated: S3QueueItem = {
      ...item,
      status: 'ACTIVE',
      startedAt: now,
      updatedAt: now,
    };

    await this.s3.putJson(`${STATUS_DIRS.ACTIVE}/${taskId}.json`, updated);
    await this.s3.deleteObject(`${STATUS_DIRS.PENDING}/${taskId}.json`);
    return updated;
  }

  async complete(taskId: string, result: { exitCode: number; consoleOutput?: string; errorMessage?: string }): Promise<void> {
    const item = await this.s3.getJson<S3QueueItem>(`${STATUS_DIRS.ACTIVE}/${taskId}.json`);
    if (!item) {
      throw new Error(`Queue item ${taskId} not found in active state`);
    }

    const now = new Date().toISOString();
    const isSuccess = result.exitCode === 0;
    const targetStatus: S3QueueItem['status'] = isSuccess ? 'COMPLETED' : 'FAILED';
    const targetDir = STATUS_DIRS[targetStatus];

    const updated: S3QueueItem = {
      ...item,
      status: targetStatus,
      exitCode: result.exitCode,
      consoleOutput: result.consoleOutput,
      errorMessage: result.errorMessage,
      completedAt: now,
      updatedAt: now,
    };

    await this.s3.putJson(`${targetDir}/${taskId}.json`, updated);
    await this.s3.deleteObject(`${STATUS_DIRS.ACTIVE}/${taskId}.json`);
  }

  async cancel(taskId: string): Promise<void> {
    // Try to find in pending first, then active
    for (const status of ['PENDING', 'ACTIVE'] as const) {
      const key = `${STATUS_DIRS[status]}/${taskId}.json`;
      const item = await this.s3.getJson<S3QueueItem>(key);
      if (item) {
        const now = new Date().toISOString();
        const updated: S3QueueItem = {
          ...item,
          status: 'CANCELLED',
          updatedAt: now,
        };
        await this.s3.putJson(`${STATUS_DIRS.CANCELLED}/${taskId}.json`, updated);
        await this.s3.deleteObject(key);
        return;
      }
    }
    throw new Error(`Queue item ${taskId} not found in cancellable state`);
  }

  async trace(taskId: string): Promise<S3QueueItem | null> {
    // Search all status directories
    for (const status of ALL_STATUSES) {
      const item = await this.s3.getJson<S3QueueItem>(`${STATUS_DIRS[status]}/${taskId}.json`);
      if (item) return item;
    }
    return null;
  }

  async list(options?: { status?: S3QueueItem['status']; limit?: number }): Promise<S3QueueItem[]> {
    const statuses = options?.status ? [options.status] : ALL_STATUSES;
    const items: S3QueueItem[] = [];
    const limit = options?.limit ?? 50;

    for (const status of statuses) {
      const keys = await this.s3.listKeys(`${STATUS_DIRS[status]}/`);
      for (const key of keys) {
        if (items.length >= limit) break;
        const item = await this.s3.getJson<S3QueueItem>(key);
        if (item) items.push(item);
      }
      if (items.length >= limit) break;
    }

    return items;
  }

  async retry(taskId: string): Promise<void> {
    const item = await this.s3.getJson<S3QueueItem>(`${STATUS_DIRS.FAILED}/${taskId}.json`);
    if (!item) {
      throw new Error(`Queue item ${taskId} not found in failed state`);
    }

    const now = new Date().toISOString();
    const updated: S3QueueItem = {
      ...item,
      status: 'PENDING',
      retryCount: item.retryCount + 1,
      errorMessage: undefined,
      exitCode: undefined,
      consoleOutput: undefined,
      completedAt: undefined,
      startedAt: undefined,
      updatedAt: now,
    };

    await this.s3.putJson(`${STATUS_DIRS.PENDING}/${taskId}.json`, updated);
    await this.s3.deleteObject(`${STATUS_DIRS.FAILED}/${taskId}.json`);
  }

  async delete(taskId: string): Promise<void> {
    // Try to delete from all status dirs
    for (const status of ALL_STATUSES) {
      await this.s3.deleteObject(`${STATUS_DIRS[status]}/${taskId}.json`);
    }
  }
}

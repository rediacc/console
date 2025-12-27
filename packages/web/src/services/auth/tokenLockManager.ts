/**
 * Token Lock Manager
 *
 * Provides mutual exclusion (mutex) for token operations to prevent race conditions.
 * Uses promise-based locking to ensure only one token operation happens at a time.
 *
 * Features:
 * - Promise-based mutex for async operations
 * - Token versioning to detect stale overwrites
 * - Lightweight and efficient
 */

class TokenLockManager {
  private tokenLock: Promise<void> = Promise.resolve();
  private currentVersion = 0;

  /**
   * Acquire lock for token operation
   * Returns a release function that MUST be called to release the lock
   */
  private async acquire(): Promise<() => void> {
    let release: () => void;

    const newLock = new Promise<void>((resolve) => {
      release = resolve;
    });

    const previousLock = this.tokenLock;
    this.tokenLock = newLock;

    // Wait for previous lock to be released
    await previousLock;

    return release!;
  }

  /**
   * Execute operation with automatic lock acquisition and release
   * Guarantees lock is released even if operation throws
   */
  async withLock<T>(operation: () => Promise<T>): Promise<T> {
    const release = await this.acquire();
    try {
      return await operation();
    } finally {
      release();
    }
  }

  /**
   * Get next version number for token versioning
   * Increments on each token update to detect stale overwrites
   */
  nextVersion(): number {
    return ++this.currentVersion;
  }

  /**
   * Validate if a token version is current
   * Used to prevent stale token overwrites
   */
  isVersionCurrent(version: number): boolean {
    return version === this.currentVersion;
  }

  /**
   * Get current version (read-only access)
   */
  getCurrentVersion(): number {
    return this.currentVersion;
  }
}

// Export singleton instance
export const tokenLockManager = new TokenLockManager();

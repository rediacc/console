import { BridgeTestRunner, ExecResult } from "./BridgeTestRunner";
import { DEFAULT_DATASTORE_PATH } from "../../constants";

/**
 * Test resource manager for tracking and cleaning up resources created during tests.
 *
 * Tracks:
 * - Repositories created
 * - Containers started
 * - Daemons started
 * - Mount points created
 *
 * Ensures proper cleanup in the correct order to avoid orphaned resources.
 */
export class TestResourceManager {
  private runner: BridgeTestRunner;
  private testId: string;
  private datastorePath: string;

  // Track created resources
  private createdRepositories: string[] = [];
  private mountedRepositories: string[] = [];
  private startedContainers: Map<string, string[]> = new Map(); // repository -> containers
  private startedDaemons: string[] = []; // repository names with daemons running

  constructor(runner: BridgeTestRunner, datastorePath?: string) {
    this.runner = runner;
    this.testId = Date.now().toString(36);
    this.datastorePath = datastorePath ?? DEFAULT_DATASTORE_PATH;
  }

  // ===========================================================================
  // Resource Name Generation
  // ===========================================================================

  /**
   * Generate unique repository name for testing.
   */
  generateRepositoryName(suffix?: string): string {
    return `test-repo-${this.testId}${suffix ? `-${suffix}` : ""}`;
  }

  /**
   * Generate unique container name for testing.
   */
  generateContainerName(suffix?: string): string {
    return `test-container-${this.testId}${suffix ? `-${suffix}` : ""}`;
  }

  /**
   * Generate unique checkpoint name for testing.
   */
  generateCheckpointName(suffix?: string): string {
    return `test-ckpt-${this.testId}${suffix ? `-${suffix}` : ""}`;
  }

  // ===========================================================================
  // Repository Operations with Tracking
  // ===========================================================================

  /**
   * Create a repository and track it for cleanup.
   */
  async createRepository(name: string, size: string, password?: string): Promise<ExecResult> {
    const result = await this.runner.repositoryNew(name, size, password, this.datastorePath);
    if (result.code === 0) {
      this.createdRepositories.push(name);
    }
    return result;
  }

  /**
   * Mount a repository and track it.
   */
  async mountRepository(name: string, password?: string): Promise<ExecResult> {
    const result = await this.runner.repositoryMount(name, password, this.datastorePath);
    if (result.code === 0) {
      this.mountedRepositories.push(name);
    }
    return result;
  }

  /**
   * Unmount a repository and update tracking.
   */
  async unmountRepository(name: string): Promise<ExecResult> {
    const result = await this.runner.repositoryUnmount(name, this.datastorePath);
    if (result.code === 0) {
      this.mountedRepositories = this.mountedRepositories.filter((r) => r !== name);
    }
    return result;
  }

  /**
   * Start repository services (up) and track.
   */
  async repositoryUp(name: string): Promise<ExecResult> {
    const result = await this.runner.repositoryUp(name, this.datastorePath);
    if (result.code === 0) {
      this.startedDaemons.push(name);
    }
    return result;
  }

  /**
   * Stop repository services (down) and update tracking.
   */
  async repositoryDown(name: string): Promise<ExecResult> {
    const result = await this.runner.repositoryDown(name, this.datastorePath);
    if (result.code === 0) {
      this.startedDaemons = this.startedDaemons.filter((r) => r !== name);
    }
    return result;
  }

  /**
   * Delete a repository and update tracking.
   */
  async deleteRepository(name: string): Promise<ExecResult> {
    const result = await this.runner.repositoryRm(name, this.datastorePath);
    if (result.code === 0) {
      this.createdRepositories = this.createdRepositories.filter((r) => r !== name);
    }
    return result;
  }

  // ===========================================================================
  // Container Operations with Tracking
  // ===========================================================================

  /**
   * Start a container and track it.
   */
  async startContainer(containerName: string, repository: string): Promise<ExecResult> {
    const result = await this.runner.containerStart(containerName, repository, this.datastorePath);
    if (result.code === 0) {
      if (!this.startedContainers.has(repository)) {
        this.startedContainers.set(repository, []);
      }
      this.startedContainers.get(repository)!.push(containerName);
    }
    return result;
  }

  /**
   * Stop a container and update tracking.
   */
  async stopContainer(containerName: string, repository: string): Promise<ExecResult> {
    const result = await this.runner.containerStop(containerName, repository, this.datastorePath);
    if (result.code === 0) {
      const containers = this.startedContainers.get(repository);
      if (containers) {
        this.startedContainers.set(
          repository,
          containers.filter((c) => c !== containerName),
        );
      }
    }
    return result;
  }

  // ===========================================================================
  // Full Lifecycle Helpers
  // ===========================================================================

  /**
   * Create and mount a repository ready for use.
   */
  async createAndMountRepository(
    size: string,
    password?: string,
    suffix?: string,
  ): Promise<{ name: string; mounted: boolean }> {
    const name = this.generateRepositoryName(suffix);

    const createResult = await this.createRepository(name, size, password);
    if (createResult.code !== 0) {
      throw new Error(`Failed to create repository: ${createResult.stderr}`);
    }

    const mountResult = await this.mountRepository(name, password);
    if (mountResult.code !== 0) {
      // Cleanup created repo
      await this.deleteRepository(name);
      throw new Error(`Failed to mount repository: ${mountResult.stderr}`);
    }

    return { name, mounted: true };
  }

  /**
   * Full repository lifecycle: create -> mount -> up.
   */
  async createMountAndStart(
    size: string,
    password?: string,
    suffix?: string,
  ): Promise<{ name: string; started: boolean }> {
    const { name } = await this.createAndMountRepository(size, password, suffix);

    const upResult = await this.repositoryUp(name);
    if (upResult.code !== 0) {
      // Cleanup
      await this.unmountRepository(name);
      await this.deleteRepository(name);
      throw new Error(`Failed to start repository: ${upResult.stderr}`);
    }

    return { name, started: true };
  }

  // ===========================================================================
  // Cleanup
  // ===========================================================================

  /**
   * Clean up all resources created during testing.
   * CRITICAL: Must follow correct order:
   * 1. Stop containers
   * 2. Stop daemons (down)
   * 3. Unmount repositories
   * 4. Delete repositories
   */
  async cleanup(): Promise<{ success: boolean; errors: string[] }> {
    const errors: string[] = [];

    // 1. Stop all started containers
    for (const [repository, containers] of this.startedContainers) {
      for (const container of containers) {
        try {
          const result = await this.runner.containerStop(container, repository, this.datastorePath);
          if (result.code !== 0) {
            errors.push(`Failed to stop container ${container}: ${result.stderr}`);
          }
        } catch (e) {
          errors.push(`Exception stopping container ${container}: ${e}`);
        }
      }
    }
    this.startedContainers.clear();

    // 2. Stop all daemons (down)
    for (const repository of this.startedDaemons) {
      try {
        const result = await this.runner.repositoryDown(repository, this.datastorePath);
        if (result.code !== 0) {
          errors.push(`Failed to stop daemon for ${repository}: ${result.stderr}`);
        }
      } catch (e) {
        errors.push(`Exception stopping daemon for ${repository}: ${e}`);
      }
    }
    this.startedDaemons = [];

    // 3. Unmount all mounted repositories
    for (const repository of this.mountedRepositories) {
      try {
        const result = await this.runner.repositoryUnmount(repository, this.datastorePath);
        if (result.code !== 0) {
          errors.push(`Failed to unmount ${repository}: ${result.stderr}`);
        }
      } catch (e) {
        errors.push(`Exception unmounting ${repository}: ${e}`);
      }
    }
    this.mountedRepositories = [];

    // 4. Delete all created repositories
    for (const repository of this.createdRepositories) {
      try {
        const result = await this.runner.repositoryRm(repository, this.datastorePath);
        if (result.code !== 0) {
          errors.push(`Failed to delete ${repository}: ${result.stderr}`);
        }
      } catch (e) {
        errors.push(`Exception deleting ${repository}: ${e}`);
      }
    }
    this.createdRepositories = [];

    return {
      success: errors.length === 0,
      errors,
    };
  }

  // ===========================================================================
  // Verification Helpers
  // ===========================================================================

  /**
   * Check if a repository exists.
   */
  async repositoryExists(name: string): Promise<boolean> {
    const result = await this.runner.repositoryList(this.datastorePath);
    return result.code === 0 && result.stdout.includes(name);
  }

  /**
   * Get list of created repositories.
   */
  getCreatedRepositories(): string[] {
    return [...this.createdRepositories];
  }

  /**
   * Get list of mounted repositories.
   */
  getMountedRepositories(): string[] {
    return [...this.mountedRepositories];
  }

  /**
   * Get list of started daemons.
   */
  getStartedDaemons(): string[] {
    return [...this.startedDaemons];
  }
}

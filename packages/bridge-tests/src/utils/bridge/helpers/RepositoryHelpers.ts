import type { ExecResult } from '../types';

/**
 * Repository-specific helper utilities for BridgeTestRunner.
 * Contains fork operations, file operations, and database helpers.
 */
export class RepositoryHelpers {
  constructor(
    private readonly executeViaBridge: (command: string, timeout?: number) => Promise<ExecResult>
  ) {}

  /**
   * Write a file to a mounted repository.
   * Uses base64 encoding to safely handle special characters.
   * Uses sudo because repository mounts may have restricted permissions.
   *
   * Repository structure:
   * - Datastore: {datastorePath}
   * - Mounts: {datastorePath}/mounts/{repositoryName}  ← where content is accessible
   */
  async writeFileToRepository(
    repositoryName: string,
    filePath: string,
    content: string,
    datastorePath: string
  ): Promise<ExecResult> {
    const base64Content = Buffer.from(content).toString('base64');
    // Repository content is at {datastore}/mounts/{repositoryName}
    const mountPath = `${datastorePath}/mounts/${repositoryName}`;
    const fullPath = `${mountPath}/${filePath}`;

    return this.executeViaBridge(
      `sudo mkdir -p "$(dirname ${fullPath})" && echo "${base64Content}" | base64 -d | sudo tee ${fullPath} > /dev/null`
    );
  }

  /**
   * Check if a Docker container is running in a network-isolated docker daemon.
   * Uses sudo because Docker daemon access may require elevated privileges.
   * @param containerName The container name to check
   * @param networkId Network ID for network-isolated docker daemon (uses socket at /var/run/rediacc/docker-{networkId}.sock)
   */
  async isContainerRunning(containerName: string, networkId: string): Promise<boolean> {
    const CONTAINER_RUNNING_MARKER = 'running';
    const result = await this.executeViaBridge(
      `sudo docker -H unix:///var/run/rediacc/docker-${networkId}.sock ps --filter "name=^${containerName}$" --format "{{.Names}}" | grep -q "^${containerName}$" && echo "${CONTAINER_RUNNING_MARKER}" || echo "stopped"`
    );
    return result.stdout.trim() === CONTAINER_RUNNING_MARKER;
  }

  /**
   * Create a fork of a repository by copying its LUKS image file.
   * This uses the renet repository fork command for proper CoW forking.
   *
   * IMPORTANT: Parent repository MUST be unmounted before forking.
   *
   * Repository structure: ${datastorePath}/repositories/${repositoryName}
   * Each repository is a single LUKS-encrypted image file (not a directory).
   *
   * @param parentRepo Name of the parent repository
   * @param tag Fork tag/name (cannot be 'latest')
   * @param datastorePath Path to the datastore
   */
  async createRepositoryFork(
    parentRepo: string,
    tag: string,
    datastorePath: string
  ): Promise<ExecResult> {
    // Use renet repository fork command for proper CoW forking
    return this.executeViaBridge(
      `sudo renet repository fork --name "${parentRepo}" --tag "${tag}" --datastore "${datastorePath}"`
    );
  }

  /**
   * Freeze a working fork into a new immutable commit (issue #75 Phase 2).
   * Drives the renet CLI directly (commit/log/merge params are not in the bridge
   * once test-mode flag allowlist), mirroring createRepositoryFork.
   */
  async repositoryCommit(
    workingFork: string,
    commitGuid: string,
    message: string,
    datastorePath: string,
    commitParent?: string
  ): Promise<ExecResult> {
    const parentFlag = commitParent ? ` --commit-parent "${commitParent}"` : '';
    return this.executeViaBridge(
      `sudo renet repository commit --name "${workingFork}" --tag "${commitGuid}" --message "${message}" --datastore "${datastorePath}"${parentFlag}`
    );
  }

  /**
   * Check a commit out into a fresh writable working fork. At the renet layer a
   * checkout is a reflink fork of the immutable commit, so this reuses fork.
   */
  async repositoryCheckout(
    commitGuid: string,
    tag: string,
    datastorePath: string
  ): Promise<ExecResult> {
    return this.createRepositoryFork(commitGuid, tag, datastorePath);
  }

  /** Walk the commit history reachable from a working fork or commit. */
  async repositoryLog(startGuid: string, datastorePath: string): Promise<ExecResult> {
    return this.executeViaBridge(
      `sudo renet repository log --name "${startGuid}" --datastore "${datastorePath}" -o json`
    );
  }

  /**
   * Lifecycle-safe merge of a source commit/fork into a target working fork.
   * Without `resolve` it is a whole-image take-theirs; with `resolve` (+ `base`,
   * the common ancestor) it is a per-file three-way merge, which mounts the
   * lineage and therefore needs the repo `password` (piped via --password-stdin).
   */
  async repositoryMerge(
    target: string,
    source: string,
    datastorePath: string,
    opts: { force?: boolean; resolve?: 'ours' | 'theirs'; base?: string; password?: string } = {}
  ): Promise<ExecResult> {
    let cmd = `sudo renet repository merge --name "${target}" --from "${source}" --datastore "${datastorePath}"`;
    if (opts.force) cmd += ' --force';
    if (opts.resolve) cmd += ` --resolve ${opts.resolve}`;
    if (opts.base) cmd += ` --base "${opts.base}"`;
    if (opts.password) {
      cmd += ' --password-stdin';
      // Pipe the credential so the three-way mount of base/ours/theirs can unlock.
      return this.executeViaBridge(`printf '%s' '${opts.password}' | ${cmd}`);
    }
    return this.executeViaBridge(cmd);
  }

  /**
   * Create an immutable (read-only) fork — the commit-equivalent base. It refuses
   * to mount; check it out into a writable fork to use it.
   */
  async repositoryForkImmutable(
    parentRepo: string,
    tag: string,
    datastorePath: string
  ): Promise<ExecResult> {
    return this.executeViaBridge(
      `sudo renet repository fork --name "${parentRepo}" --tag "${tag}" --datastore "${datastorePath}" --immutable`
    );
  }

  /**
   * Deterministic CoW-delta push of a repo from THIS worker to another machine,
   * via the renet CLI directly (delta params are not in the bridge once test-mode
   * allowlist). retainBase retains an immutable base on both ends for the next
   * push; deltaBase ships only the changed extents against an existing base.
   * --dest-user omitted → renet infers it from SUDO_USER (we run under sudo).
   */
  async deltaPushToMachine(
    repoGuid: string,
    destHost: string,
    datastorePath: string,
    opts: { destUser?: string; deltaBase?: string; retainBase?: string } = {}
  ): Promise<ExecResult> {
    let cmd =
      `sudo renet backup push --name "${repoGuid}" --datastore "${datastorePath}"` +
      ` --target machine --dest-host "${destHost}"` +
      ` --dest-path "${datastorePath}" --dest "${repoGuid}" --strategy physical`;
    if (opts.destUser) cmd += ` --dest-user "${opts.destUser}"`;
    if (opts.deltaBase) cmd += ` --delta-base "${opts.deltaBase}"`;
    if (opts.retainBase) cmd += ` --retain-base "${opts.retainBase}"`;
    return this.executeViaBridge(cmd);
  }

  /**
   * Deterministic CoW-delta pull of a repo from another machine onto THIS worker.
   * deltaBase ships only the changed extents against a base byte-identical on both
   * ends; force overwrites an existing local repo.
   */
  async deltaPullFromMachine(
    repoGuid: string,
    srcHost: string,
    datastorePath: string,
    opts: { srcUser?: string; deltaBase?: string; force?: boolean } = {}
  ): Promise<ExecResult> {
    let cmd =
      `sudo renet backup pull --name "${repoGuid}" --datastore "${datastorePath}"` +
      ` --source machine --src-host "${srcHost}"` +
      ` --src-path "${datastorePath}" --src "${repoGuid}" --strategy physical`;
    if (opts.srcUser) cmd += ` --src-user "${opts.srcUser}"`;
    if (opts.deltaBase) cmd += ` --delta-base "${opts.deltaBase}"`;
    if (opts.force) cmd += ' --force';
    return this.executeViaBridge(cmd);
  }

  /** sha256 of a repository image file (for byte-identity assertions). */
  async repositoryImageSha256(repoGuid: string, datastorePath: string): Promise<ExecResult> {
    return this.executeViaBridge(
      `sudo sha256sum "${datastorePath}/repositories/${repoGuid}" | cut -d' ' -f1`
    );
  }

  /**
   * Check if a repository exists in the datastore.
   * Repositories are LUKS image files, not directories.
   */
  async repositoryExists(repositoryName: string, datastorePath: string): Promise<boolean> {
    const REPO_EXISTS_MARKER = 'exists';
    const result = await this.executeViaBridge(
      `test -f "${datastorePath}/repositories/${repositoryName}" && echo "${REPO_EXISTS_MARKER}" || echo "not_found"`
    );
    return result.stdout.trim() === REPO_EXISTS_MARKER;
  }

  /**
   * Wait for PostgreSQL container to be ready to accept connections.
   * Uses an actual query (SELECT 1) to verify database is fully operational,
   * not just pg_isready which only checks if socket accepts connections.
   *
   * @param containerName PostgreSQL container name
   * @param networkId Network ID for the docker socket
   * @param maxAttempts Maximum number of attempts (default: 30)
   * @param intervalMs Interval between attempts in ms (default: 1000)
   * @returns true if PostgreSQL is ready, false if timed out
   */
  async waitForPostgresReady(
    containerName: string,
    networkId: string,
    maxAttempts = 30,
    intervalMs = 1000
  ): Promise<boolean> {
    for (let i = 0; i < maxAttempts; i++) {
      // Use actual query instead of pg_isready - this verifies the database
      // is fully operational, not just that the socket accepts connections.
      // This avoids race conditions where pg_isready passes but init scripts
      // are still running or the database is restarting.
      const result = await this.executeViaBridge(
        `sudo docker -H unix:///var/run/rediacc/docker-${networkId}.sock exec ${containerName} psql -U postgres -d testdb -c "SELECT 1" -t -q 2>/dev/null`
      );
      if (result.code === 0) {
        // eslint-disable-next-line no-console
        console.log(`[PostgreSQL] Container ${containerName} is ready after ${i + 1} attempts`);
        return true;
      }
      // eslint-disable-next-line no-console
      console.log(`[PostgreSQL] Waiting for ${containerName}... (${i + 1}/${maxAttempts})`);
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    // eslint-disable-next-line no-console
    console.log(
      `[PostgreSQL] Container ${containerName} failed to be ready after ${maxAttempts} attempts`
    );
    return false;
  }
}

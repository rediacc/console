/**
 * SSH-based validator for E2E tests.
 *
 * Executes commands on remote VMs via SSH and provides high-level
 * validation methods for checking filesystem state, mounts, containers,
 * and services.
 */
import { execa } from 'execa';

export interface SSHResult {
  stdout: string;
  stderr: string;
  code: number;
  success: boolean;
}

export class SSHValidator {
  constructor(
    private readonly host: string,
    private readonly user: string,
    private readonly sshKeyPath: string
  ) {}

  private get sshArgs(): string[] {
    return [
      '-o',
      'StrictHostKeyChecking=no',
      '-o',
      'UserKnownHostsFile=/dev/null',
      '-o',
      'ConnectTimeout=10',
      '-o',
      'BatchMode=yes',
      '-o',
      'LogLevel=ERROR',
      '-i',
      this.sshKeyPath,
    ];
  }

  /**
   * Execute a raw SSH command on the remote host.
   */
  async exec(command: string, timeoutMs = 60_000): Promise<SSHResult> {
    try {
      const result = await execa('ssh', [...this.sshArgs, `${this.user}@${this.host}`, command], {
        timeout: timeoutMs,
        reject: false,
      });
      return {
        stdout: result.stdout,
        stderr: result.stderr,
        code: result.exitCode,
        success: result.exitCode === 0,
      };
    } catch (error: unknown) {
      const err = error as Error & { stdout?: string; stderr?: string; exitCode?: number };
      return {
        stdout: err.stdout ?? '',
        stderr: err.stderr ?? err.message,
        code: err.exitCode ?? 1,
        success: false,
      };
    }
  }

  // --- Filesystem checks ---

  async fileExists(filePath: string): Promise<boolean> {
    const result = await this.exec(`test -f ${filePath} && echo YES || echo NO`);
    return result.stdout.trim() === 'YES';
  }

  async dirExists(dirPath: string): Promise<boolean> {
    const result = await this.exec(`test -d ${dirPath} && echo YES || echo NO`);
    return result.stdout.trim() === 'YES';
  }

  async readFile(filePath: string): Promise<string> {
    const result = await this.exec(`cat ${filePath}`);
    return result.stdout;
  }

  async fileChecksum(filePath: string): Promise<string> {
    const result = await this.exec(`md5sum ${filePath} | awk '{print $1}'`);
    return result.stdout.trim();
  }

  // --- Mount/disk checks ---

  async mountExists(mountPoint: string): Promise<boolean> {
    const result = await this.exec(`mount | grep ' ${mountPoint} '`);
    return result.success && result.stdout.trim().length > 0;
  }

  async btrfsSubvolumes(mountPath: string): Promise<string[]> {
    const result = await this.exec(`sudo btrfs subvolume list ${mountPath}`);
    if (!result.success) return [];
    return result.stdout
      .trim()
      .split('\n')
      .filter((l) => l.length > 0);
  }

  async luksIsOpen(name: string): Promise<boolean> {
    const result = await this.exec(`sudo cryptsetup status ${name} 2>/dev/null && echo OPEN`);
    return result.success && result.stdout.includes('OPEN');
  }

  async diskUsage(mountPath: string): Promise<string> {
    const result = await this.exec(`df -h ${mountPath} | tail -1`);
    return result.stdout.trim();
  }

  // --- Docker/container checks ---

  async containerRunning(name: string): Promise<boolean> {
    const result = await this.exec(
      `sudo docker ps --format '{{.Names}}' | grep -w '${name}'`
    );
    return result.success && result.stdout.trim().length > 0;
  }

  async containerExists(name: string): Promise<boolean> {
    const result = await this.exec(
      `sudo docker ps -a --format '{{.Names}}' | grep -w '${name}'`
    );
    return result.success && result.stdout.trim().length > 0;
  }

  async dockerImageExists(name: string): Promise<boolean> {
    const result = await this.exec(
      `sudo docker images --format '{{.Repository}}:{{.Tag}}' | grep '${name}'`
    );
    return result.success && result.stdout.trim().length > 0;
  }

  async containerState(name: string): Promise<string> {
    const result = await this.exec(
      `sudo docker inspect --format '{{.State.Status}}' ${name}`
    );
    return result.stdout.trim();
  }

  async runningContainerNames(): Promise<string[]> {
    const result = await this.exec(`sudo docker ps --format '{{.Names}}'`);
    if (!result.success) return [];
    return result.stdout
      .trim()
      .split('\n')
      .filter((l) => l.length > 0);
  }

  async allContainerNames(): Promise<string[]> {
    const result = await this.exec(`sudo docker ps -a --format '{{.Names}}'`);
    if (!result.success) return [];
    return result.stdout
      .trim()
      .split('\n')
      .filter((l) => l.length > 0);
  }

  // --- Service checks ---

  async serviceActive(name: string): Promise<boolean> {
    const result = await this.exec(`systemctl is-active ${name}`);
    return result.stdout.trim() === 'active';
  }

  async commandExists(cmd: string): Promise<boolean> {
    const result = await this.exec(`command -v ${cmd} && echo YES`);
    return result.success && result.stdout.includes('YES');
  }

  // --- Write operations (test setup) ---

  async writeFile(filePath: string, content: string): Promise<void> {
    // Use heredoc via SSH to write content
    const escapedContent = content.replace(/'/g, "'\\''");
    await this.exec(`sudo mkdir -p $(dirname ${filePath}) && echo '${escapedContent}' | sudo tee ${filePath} > /dev/null`);
  }

  async createTestFile(filePath: string, sizeMB: number): Promise<void> {
    await this.exec(
      `sudo dd if=/dev/urandom of=${filePath} bs=1M count=${sizeMB} 2>/dev/null`
    );
  }

  async removeFile(filePath: string): Promise<void> {
    await this.exec(`sudo rm -f ${filePath}`);
  }

  async listDir(dirPath: string): Promise<string[]> {
    const result = await this.exec(`ls ${dirPath}`);
    if (!result.success) return [];
    return result.stdout
      .trim()
      .split('\n')
      .filter((l) => l.length > 0);
  }

  // --- Ceph checks ---

  async rbdList(pool = 'rbd'): Promise<string[]> {
    const result = await this.exec(`sudo rbd ls ${pool}`);
    if (!result.success) return [];
    return result.stdout
      .trim()
      .split('\n')
      .filter((l) => l.length > 0);
  }

  async rbdInfo(image: string, pool = 'rbd'): Promise<string> {
    const result = await this.exec(`sudo rbd info ${pool}/${image}`);
    return result.stdout;
  }

  async rbdSnapList(image: string, pool = 'rbd'): Promise<string[]> {
    const result = await this.exec(`sudo rbd snap ls ${pool}/${image}`);
    if (!result.success) return [];
    return result.stdout
      .trim()
      .split('\n')
      .filter((l) => l.length > 0);
  }

  async rbdShowMapped(): Promise<string> {
    const result = await this.exec(`sudo rbd showmapped`);
    return result.stdout;
  }

  async cephFsMounted(mountPoint: string): Promise<boolean> {
    const result = await this.exec(`mount | grep '${mountPoint}' | grep ceph`);
    return result.success && result.stdout.trim().length > 0;
  }
}

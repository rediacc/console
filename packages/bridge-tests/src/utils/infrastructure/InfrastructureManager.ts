import { exec } from "child_process";
import * as crypto from "crypto";
import * as fs from "fs";
import * as path from "path";
import { promisify } from "util";
import { RENET_BINARY_PATH } from "../../constants";
import { getOpsManager, OpsManager } from "../bridge/OpsManager";

const execAsync = promisify(exec);

/**
 * Calculate MD5 hash of a file.
 */
function getFileMD5(filePath: string): string {
  const content = fs.readFileSync(filePath);
  return crypto.createHash("md5").update(content).digest("hex");
}

export interface InfrastructureConfig {
  renetRoot: string;
  renetPath: string;
  bridgeVM: string;
  workerVM: string;
  defaultTimeout: number;
}

/**
 * InfrastructureManager for bridge tests.
 *
 * Always runs in full VM mode:
 * - Automatically starts VMs using renet ops commands if not running
 * - Verifies renet is installed on all VMs
 * - No middleware or Docker containers required - renet runs in local/test mode
 */
export class InfrastructureManager {
  private config: InfrastructureConfig;
  private detectedRenetPath: string | null = null;
  private opsManager: OpsManager;

  constructor() {
    this.opsManager = getOpsManager();

    // Auto-detect renet root: use RENET_ROOT env var or resolve from current location
    // Path from this file: renet/tests/bridge/src/utils/infrastructure/ -> renet/
    const renetRoot = process.env.RENET_ROOT ?? path.resolve(__dirname, "../../../../../..");

    this.config = {
      renetRoot,
      renetPath: process.env.RENET_PATH ?? "",
      bridgeVM: this.opsManager.getBridgeVMIp(),
      workerVM: this.opsManager.getWorkerVMIps()[0],
      defaultTimeout: parseInt(process.env.BRIDGE_TIMEOUT ?? "30000"),
    };
  }

  /**
   * Get the path to renet binary (cached after first detection).
   */
  getRenetPath(): string {
    if (this.detectedRenetPath) {
      return this.detectedRenetPath;
    }
    return this.config.renetPath.length > 0 ? this.config.renetPath : "renet";
  }

  /**
   * Check if renet binary is available locally.
   *
   * CI Mode: Checks RENET_BINARY_PATH first (set after Docker extraction).
   */
  async isRenetAvailable(): Promise<{ available: boolean; path: string }> {
    // 0. CI mode: check pre-extracted binary path first
    const ciRenetPath = process.env.RENET_BINARY_PATH;
    if (ciRenetPath && process.env.CI === "true") {
      try {
        await execAsync(`${ciRenetPath} version`, { timeout: 5000 });
        this.detectedRenetPath = ciRenetPath;
        return { available: true, path: ciRenetPath };
      } catch {
        // Continue to other options
      }
    }

    // 1. Check explicit path from env
    if (this.config.renetPath) {
      try {
        await execAsync(`${this.config.renetPath} version`, { timeout: 5000 });
        this.detectedRenetPath = this.config.renetPath;
        return { available: true, path: this.config.renetPath };
      } catch {
        // Continue to other options
      }
    }

    // 2. Check if in PATH
    try {
      await execAsync("renet version", { timeout: 5000 });
      this.detectedRenetPath = "renet";
      return { available: true, path: "renet" };
    } catch {
      // Continue to other options
    }

    // 3. Check renet build path
    const buildPath = path.join(this.config.renetRoot, "bin/renet");
    try {
      await execAsync(`${buildPath} version`, { timeout: 5000 });
      this.detectedRenetPath = buildPath;
      return { available: true, path: buildPath };
    } catch {
      // Not found
    }

    return { available: false, path: "" };
  }

  /**
   * Check if bridge VM is reachable via SSH.
   */
  async isBridgeVMReachable(): Promise<boolean> {
    try {
      await execAsync(
        `ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no ${this.config.bridgeVM} "echo ok"`,
        { timeout: 10000 },
      );
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Check if worker VM is reachable via SSH.
   */
  async isWorkerVMReachable(): Promise<boolean> {
    try {
      await execAsync(
        `ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no ${this.config.workerVM} "echo ok"`,
        { timeout: 10000 },
      );
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Get current infrastructure status.
   */
  async getStatus(): Promise<{
    renet: { available: boolean; path: string };
    bridgeVM: boolean;
    workerVM: boolean;
  }> {
    const [renet, bridgeVM, workerVM] = await Promise.all([
      this.isRenetAvailable(),
      this.isBridgeVMReachable(),
      this.isWorkerVMReachable(),
    ]);

    return { renet, bridgeVM, workerVM };
  }

  /**
   * Ensure infrastructure is ready for tests.
   * - Builds renet if not available or if RENET_AUTO_BUILD=true
   * - Starts VMs if not running
   * - Deploys renet to VMs if outdated
   */
  async ensureInfrastructure(): Promise<void> {
    console.log("Checking infrastructure status...");

    let status = await this.getStatus();
    console.log("");
    console.log("Initial Status:");
    console.log("  Renet:", status.renet.available ? `OK (${status.renet.path})` : "NOT FOUND");
    console.log("  Bridge VM:", status.bridgeVM ? "OK" : "DOWN");
    console.log("  Worker VM:", status.workerVM ? "OK" : "DOWN");

    // Build renet if not available or if auto-build is enabled
    const autoBuild = process.env.RENET_AUTO_BUILD !== "false";
    if (!status.renet.available || autoBuild) {
      console.log("");
      try {
        const buildResult = await this.buildRenet();
        this.detectedRenetPath = buildResult.path;
        status = await this.getStatus();
      } catch (error: unknown) {
        const err = error as { message?: string };
        if (!status.renet.available) {
          throw new Error(
            `Renet binary not found and build failed: ${err.message ?? "Unknown error"}\n` +
              "Build manually with: cd renet && go build -o bin/renet ./cmd/renet\n" +
              "Or set RENET_PATH environment variable.",
          );
        }
        // Build failed but we have an existing binary
        console.log(
          `  Warning: Build failed (${err.message ?? "Unknown error"}), using existing binary`,
        );
      }
    }

    // Always ensure VMs are running
    const vmsReady = status.bridgeVM && status.workerVM;

    if (!vmsReady) {
      console.log("");
      console.log("VMs not ready - starting via ops scripts...");

      const result = await this.opsManager.ensureVMsRunning();

      if (!result.success) {
        throw new Error(`Failed to start VMs: ${result.message}\n` + "Check ops logs for details.");
      }

      console.log(result.message);

      // Verify VMs are now ready
      const newStatus = await this.getStatus();
      console.log("");
      console.log("Updated Status:");
      console.log("  Bridge VM:", newStatus.bridgeVM ? "OK" : "DOWN");
      console.log("  Worker VM:", newStatus.workerVM ? "OK" : "DOWN");

      if (!newStatus.bridgeVM || !newStatus.workerVM) {
        const missing: string[] = [];
        if (!newStatus.bridgeVM) missing.push("bridge VM");
        if (!newStatus.workerVM) missing.push("worker VM");

        throw new Error(
          `VMs started but still not reachable: ${missing.join(", ")}\n` +
            "Check network connectivity and SSH configuration.",
        );
      }
    }

    // Ensure renet is installed on all VMs
    await this.ensureRenetOnVMs();
  }

  /**
   * Build renet binary if source has changed.
   *
   * CI Mode: Skips building if RENET_BINARY_PATH is set (binary pre-extracted from Docker).
   */
  async buildRenet(): Promise<{ built: boolean; path: string }> {
    // CI mode: skip building if binary was pre-extracted from Docker image
    const ciRenetPath = process.env.RENET_BINARY_PATH;
    if (process.env.CI === "true" && ciRenetPath) {
      console.log("CI Mode: Using pre-extracted renet binary");
      console.log(`  Binary path: ${ciRenetPath}`);
      return { built: false, path: ciRenetPath };
    }

    const renetDir = this.config.renetRoot;
    const binaryPath = path.join(renetDir, "bin", "renet");

    console.log("Building renet binary...");

    try {
      const { stderr } = await execAsync("go build -o bin/renet ./cmd/renet", {
        cwd: renetDir,
        timeout: 120000,
      });

      if (stderr && !stderr.includes("warning")) {
        console.log("  Build warnings:", stderr.trim());
      }

      console.log("  ✓ Build complete");
      return { built: true, path: binaryPath };
    } catch (error: unknown) {
      const err = error as { message?: string };
      throw new Error(`Failed to build renet: ${err.message ?? "Unknown error"}`);
    }
  }

  /**
   * Get MD5 hash of renet binary on a remote VM.
   */
  private async getRemoteRenetMD5(ip: string): Promise<string | null> {
    const result = await this.opsManager.executeOnVM(
      ip,
      `md5sum ${RENET_BINARY_PATH} 2>/dev/null | cut -d" " -f1`,
    );
    if (result.code === 0 && result.stdout.trim().length === 32) {
      return result.stdout.trim();
    }
    return null;
  }

  /**
   * Deploy renet binary to a VM if it's different from the local version.
   * Verifies the deployment by checking MD5 after copy.
   */
  private async deployRenetToVM(ip: string, localPath: string, localMD5: string): Promise<boolean> {
    const remoteMD5 = await this.getRemoteRenetMD5(ip);

    if (remoteMD5 === localMD5) {
      return false; // Already up to date
    }

    // Deploy via scp to temp then sudo mv
    const user = process.env.USER;
    if (!user) {
      throw new Error("USER environment variable is not set");
    }
    try {
      // Copy to temp location
      await execAsync(
        `scp -q -o StrictHostKeyChecking=no "${localPath}" ${user}@${ip}:/tmp/renet`,
        { timeout: 60000 }, // Increased timeout for larger binaries
      );

      // Move to final location and set permissions
      await execAsync(
        `ssh -q -o StrictHostKeyChecking=no ${user}@${ip} "sudo mv /tmp/renet ${RENET_BINARY_PATH} && sudo chmod +x ${RENET_BINARY_PATH}"`,
        { timeout: 10000 },
      );

      // Verify the deployment by checking MD5
      const newRemoteMD5 = await this.getRemoteRenetMD5(ip);
      if (newRemoteMD5 !== localMD5) {
        throw new Error(`MD5 mismatch after deploy: local=${localMD5}, remote=${newRemoteMD5}`);
      }

      return true;
    } catch (error: unknown) {
      const err = error as { message?: string };
      throw new Error(`Failed to deploy renet to ${ip}: ${err.message ?? "Unknown error"}`);
    }
  }

  /**
   * Verify renet is installed and up-to-date on all VMs (bridge, workers, ceph).
   * Deploys the local version if VMs have outdated binary.
   */
  async ensureRenetOnVMs(): Promise<void> {
    console.log("");
    console.log("Verifying renet on all VMs...");

    const localPath = this.getRenetPath();
    let localMD5: string;

    try {
      localMD5 = getFileMD5(localPath);
    } catch {
      throw new Error(`Cannot read local renet binary at ${localPath}`);
    }

    // Deploy to all VMs: bridge + workers + ceph
    const allIPs = this.opsManager.getAllVMIps();

    for (const ip of allIPs) {
      const hasRenet = await this.opsManager.isRenetInstalledOnVM(ip);

      if (!hasRenet) {
        // Install renet for the first time
        console.log(`  ${ip}: Installing renet...`);
        await this.deployRenetToVM(ip, localPath, localMD5);
        const version = await this.opsManager.getRenetVersionOnVM(ip);
        console.log(`  ✓ ${ip}: renet installed (${version ?? "unknown version"})`);
      } else {
        // Check if update is needed
        const wasUpdated = await this.deployRenetToVM(ip, localPath, localMD5);
        const version = await this.opsManager.getRenetVersionOnVM(ip);

        if (wasUpdated) {
          console.log(`  ✓ ${ip}: renet updated (${version ?? "unknown version"})`);
        } else {
          console.log(`  ✓ ${ip}: renet installed (${version ?? "unknown version"})`);
        }
      }
    }
  }

  /**
   * Get the OpsManager instance for direct VM operations.
   */
  getOpsManager(): OpsManager {
    return this.opsManager;
  }

  /**
   * Deploy CRIU to all worker VMs.
   *
   * Strategy:
   * 1. Try to extract CRIU from bridge container (pre-built, fast)
   * 2. Fall back to building from source if container not available
   *
   * CRIU is required for container checkpointing tests.
   */
  async deployCRIUToAllVMs(): Promise<void> {
    console.log("Checking CRIU deployment...");

    const bridgeIP = this.opsManager.getBridgeVMIp();
    const workerIPs = this.opsManager.getWorkerVMIps();
    const user = process.env.USER;
    if (!user) {
      throw new Error("USER environment variable is not set");
    }

    // Check if any worker already has CRIU installed
    let anyNeedsCriu = false;
    for (const ip of workerIPs) {
      const result = await this.opsManager.executeOnVM(ip, "which criu 2>/dev/null");
      if (result.code !== 0) {
        anyNeedsCriu = true;
        break;
      }
    }

    if (!anyNeedsCriu) {
      console.log("  CRIU already installed on all workers");
      return;
    }

    // Try to extract CRIU from bridge container
    let criuSourcePath: string | null = null;

    // Check if bridge container has CRIU
    const containerCheck = await this.opsManager.executeOnVM(
      bridgeIP,
      "docker ps --filter 'name=bridge' --format '{{.Names}}' | head -1",
    );

    if (containerCheck.code === 0 && containerCheck.stdout.trim()) {
      const containerName = containerCheck.stdout.trim();
      console.log(`  Found bridge container: ${containerName}`);

      // Extract CRIU from container to bridge VM temp location
      const extractResult = await this.opsManager.executeOnVM(
        bridgeIP,
        `docker cp ${containerName}:/opt/criu/criu-linux-amd64 /tmp/criu 2>/dev/null && chmod +x /tmp/criu && echo "extracted"`,
      );

      if (extractResult.code === 0 && extractResult.stdout.includes("extracted")) {
        criuSourcePath = "/tmp/criu";
        console.log("  ✓ Extracted CRIU from bridge container");
      }
    }

    // Deploy CRIU to each worker VM
    for (const ip of workerIPs) {
      // Check if CRIU already installed on this worker
      const criuCheck = await this.opsManager.executeOnVM(ip, "which criu 2>/dev/null");
      if (criuCheck.code === 0 && criuCheck.stdout.trim()) {
        console.log(`  ✓ ${ip}: CRIU already installed`);
        continue;
      }

      if (criuSourcePath) {
        // Copy from bridge VM to worker VM
        console.log(`  ${ip}: Copying CRIU from bridge...`);
        const copyResult = await this.opsManager.executeOnVM(
          bridgeIP,
          `scp -o StrictHostKeyChecking=no ${criuSourcePath} ${user}@${ip}:/tmp/criu && ssh -o StrictHostKeyChecking=no ${user}@${ip} "sudo mv /tmp/criu /usr/local/bin/criu && sudo chmod +x /usr/local/bin/criu"`,
        );

        if (copyResult.code === 0) {
          console.log(`  ✓ ${ip}: CRIU installed from container`);
          continue;
        }
        console.log(`  Warning: Copy failed for ${ip}, will try building from source`);
      }

      // Fall back to building from source using renet ops
      console.log(`  ${ip}: Building CRIU from source (this may take a few minutes)...`);

      // Extract VM ID from IP address (last octet)
      const vmId = ip.split(".").pop();

      // Use renet ops worker install-criu command
      await execAsync(
        `${path.join(this.config.renetRoot, "bin/renet")} ops worker install-criu ${vmId}`,
        { timeout: 600000 }, // 10 minute timeout for build
      ).catch((error: unknown) => ({
        stdout: "",
        stderr: error instanceof Error ? error.message : String(error),
      }));

      // Verify CRIU was installed
      const verifyResult = await this.opsManager.executeOnVM(ip, "criu --version");
      if (verifyResult.code === 0) {
        console.log(`  ✓ ${ip}: CRIU built and installed`);
      } else {
        console.log(`  Warning: CRIU installation failed on ${ip} (non-fatal for most tests)`);
      }
    }

    // Cleanup temp file on bridge
    if (criuSourcePath) {
      await this.opsManager.executeOnVM(bridgeIP, "rm -f /tmp/criu");
    }
  }
}

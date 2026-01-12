import { exec, execSync } from "child_process";
import * as fs from "fs";
import * as path from "path";
import { promisify } from "util";

const execAsync = promisify(exec);

/**
 * Default path to renet binary (relative to tests/bridge directory)
 * tests/bridge/src/utils/image -> renet/bin/renet
 */
const DEFAULT_RENET_BIN = path.resolve(__dirname, "..", "..", "..", "..", "..", "bin", "renet");

/**
 * Default path to disks directory (where renet saves images when run from tests/bridge)
 * This path is used by renet when executed from the tests/bridge directory
 */
const DEFAULT_DISKS_PATH = path.resolve(__dirname, "..", "..", "..", "..", "ops", "disks");

/**
 * OS Image configuration matching pkg/infra/config/images.go
 */
export interface OSImage {
  name: string;
  url: string;
  distro: string;
  variant: string;
  family: "debian" | "rhel" | "suse";
}

/**
 * Result of an image build operation
 */
export interface BuildResult {
  success: boolean;
  imagePath: string;
  duration: number;
  stdout: string;
  stderr: string;
  error?: string;
}

/**
 * Image validation result
 */
export interface ValidationResult {
  valid: boolean;
  format: string;
  size: number;
  compressed: boolean;
  error?: string;
}

/**
 * All configured OS images matching pkg/infra/config/images.go
 */
export const CONFIGURED_IMAGES: OSImage[] = [
  // Debian family
  {
    name: "ubuntu-24.04",
    url: "https://cloud-images.ubuntu.com/minimal/releases/noble/release/ubuntu-24.04-minimal-cloudimg-amd64.img",
    distro: "ubuntu",
    variant: "ubuntu24.04",
    family: "debian",
  },
  {
    name: "debian-12",
    url: "https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2",
    distro: "debian",
    variant: "debian12",
    family: "debian",
  },

  // RHEL family
  {
    name: "centos-10-stream",
    url: "https://cloud.centos.org/centos/10-stream/x86_64/images/CentOS-Stream-GenericCloud-x86_64-10-latest.x86_64.qcow2",
    distro: "centos",
    variant: "centos-stream9",
    family: "rhel",
  },
  {
    name: "fedora-43",
    url: "https://download.fedoraproject.org/pub/fedora/linux/releases/43/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-43-1.6.x86_64.qcow2",
    distro: "fedora",
    variant: "fedora-unknown",
    family: "rhel",
  },
  {
    name: "fedora-41",
    url: "https://download.fedoraproject.org/pub/fedora/linux/releases/41/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-41-1.4.x86_64.qcow2",
    distro: "fedora",
    variant: "fedora-unknown",
    family: "rhel",
  },
  {
    name: "oracle-9",
    url: "https://yum.oracle.com/templates/OracleLinux/OL9/u6/x86_64/OL9U6_x86_64-kvm-b265.qcow2",
    distro: "oracle",
    variant: "ol9.0",
    family: "rhel",
  },
  {
    name: "oracle-8",
    url: "https://yum.oracle.com/templates/OracleLinux/OL8/u10/x86_64/OL8U10_x86_64-kvm-b258.qcow2",
    distro: "oracle",
    variant: "ol8.0",
    family: "rhel",
  },
  {
    name: "rocky-9",
    url: "https://dl.rockylinux.org/pub/rocky/9/images/x86_64/Rocky-9-GenericCloud-Base.latest.x86_64.qcow2",
    distro: "rocky",
    variant: "rocky9-unknown",
    family: "rhel",
  },

  // SUSE family
  {
    name: "opensuse-15.6",
    url: "https://download.opensuse.org/repositories/Cloud:/Images:/Leap_15.6/images/openSUSE-Leap-15.6.x86_64-NoCloud.qcow2",
    distro: "suse",
    variant: "opensuse15.5",
    family: "suse",
  },
  {
    name: "opensuse-15.5",
    url: "https://download.opensuse.org/repositories/Cloud:/Images:/Leap_15.5/images/openSUSE-Leap-15.5.x86_64-NoCloud.qcow2",
    distro: "suse",
    variant: "opensuse15.5",
    family: "suse",
  },
];

/**
 * Minimum valid image size in bytes (10MB)
 */
const MIN_IMAGE_SIZE = 10_000_000;

/**
 * Default build timeout in milliseconds (30 minutes)
 */
const DEFAULT_BUILD_TIMEOUT = 30 * 60 * 1000;

/**
 * Helper class for image build testing.
 *
 * Provides utilities for:
 * - Building custom VM images via renet ops image commands
 * - Validating built images (format, size, compression)
 * - Managing build artifacts and cleanup
 */
export class ImageTestHelper {
  private disksPath: string;
  private renetBin: string;
  private buildTimeout: number;

  constructor(options?: { disksPath?: string; renetBin?: string; buildTimeout?: number }) {
    this.disksPath = options?.disksPath ?? process.env.DISKS_PATH ?? DEFAULT_DISKS_PATH;
    this.renetBin = options?.renetBin ?? process.env.RENET_BIN ?? DEFAULT_RENET_BIN;
    this.buildTimeout = options?.buildTimeout ?? DEFAULT_BUILD_TIMEOUT;

    // Verify renet binary exists
    if (!fs.existsSync(this.renetBin)) {
      console.warn(`Warning: renet binary not found at ${this.renetBin}`);
      console.warn('Run "./go dev" in the renet directory to build it');
    }
  }

  /**
   * Returns all configured OS images
   */
  getConfiguredImages(): OSImage[] {
    return CONFIGURED_IMAGES;
  }

  /**
   * Returns images filtered by distro family
   */
  getImagesByFamily(family: "debian" | "rhel" | "suse"): OSImage[] {
    return CONFIGURED_IMAGES.filter((img) => img.family === family);
  }

  /**
   * Find an image by name
   */
  getImageByName(name: string): OSImage | undefined {
    return CONFIGURED_IMAGES.find((img) => img.name === name);
  }

  /**
   * Build a single custom image
   *
   * @param imageName - The image name (e.g., 'ubuntu-24.04')
   * @param force - Force rebuild even if image exists
   * @returns Build result with success status and output
   */
  async buildImage(imageName: string, force = false): Promise<BuildResult> {
    const image = this.getImageByName(imageName);
    if (!image) {
      return {
        success: false,
        imagePath: "",
        duration: 0,
        stdout: "",
        stderr: "",
        error: `Unknown image: ${imageName}`,
      };
    }

    const startTime = Date.now();
    const forceFlag = force ? "--force" : "";
    const cmd = `${this.renetBin} ops image build "${image.url}" ${forceFlag}`.trim();

    try {
      const { stdout, stderr } = await execAsync(cmd, {
        timeout: this.buildTimeout,
        maxBuffer: 50 * 1024 * 1024, // 50MB buffer for long outputs
      });

      const duration = Date.now() - startTime;
      const imagePath = this.getCustomImagePath(imageName);

      return {
        success: this.customImageExists(imageName),
        imagePath,
        duration,
        stdout,
        stderr,
      };
    } catch (error: unknown) {
      const duration = Date.now() - startTime;
      const err = error as { stdout?: string; stderr?: string; message?: string };

      return {
        success: false,
        imagePath: "",
        duration,
        stdout: err.stdout ?? "",
        stderr: err.stderr ?? "",
        error: err.message ?? String(error),
      };
    }
  }

  /**
   * Build all configured images sequentially
   *
   * @param force - Force rebuild even if images exist
   * @returns Map of image name to build result
   */
  async buildAllImages(force = false): Promise<Map<string, BuildResult>> {
    const results = new Map<string, BuildResult>();

    for (const image of CONFIGURED_IMAGES) {
      console.log(`Building image: ${image.name}...`);
      const result = await this.buildImage(image.name, force);
      results.set(image.name, result);

      if (result.success) {
        console.log(
          `  ✓ ${image.name} built successfully (${Math.round(result.duration / 1000)}s)`,
        );
      } else {
        console.log(`  ✗ ${image.name} failed: ${result.error ?? "unknown error"}`);
      }
    }

    return results;
  }

  /**
   * Check if a custom image exists
   */
  customImageExists(imageName: string): boolean {
    const imagePath = this.getCustomImagePath(imageName);
    return fs.existsSync(imagePath);
  }

  /**
   * Get the full path to a custom image
   *
   * Custom images are named: rediacc-<base-filename>
   */
  getCustomImagePath(imageName: string): string {
    const image = this.getImageByName(imageName);
    if (!image) {
      return path.join(this.disksPath, `rediacc-custom-${imageName}-amd64.qcow2`);
    }

    // Extract base filename from URL
    const urlPath = new URL(image.url).pathname;
    const baseFilename = path.basename(urlPath);

    return path.join(this.disksPath, `rediacc-${baseFilename}`);
  }

  /**
   * Get the file size of an image in bytes
   */
  getImageSize(imagePath: string): number {
    try {
      const stats = fs.statSync(imagePath);
      return stats.size;
    } catch {
      return 0;
    }
  }

  /**
   * Validate a built image
   *
   * Checks:
   * - File exists and is readable
   * - Format is qcow2
   * - Size is greater than minimum
   * - Image is compressed
   */
  validateImage(imagePath: string): ValidationResult {
    if (!fs.existsSync(imagePath)) {
      return {
        valid: false,
        format: "",
        size: 0,
        compressed: false,
        error: "Image file does not exist",
      };
    }

    const size = this.getImageSize(imagePath);
    if (size < MIN_IMAGE_SIZE) {
      return {
        valid: false,
        format: "",
        size,
        compressed: false,
        error: `Image too small: ${size} bytes (minimum: ${MIN_IMAGE_SIZE})`,
      };
    }

    try {
      const info = execSync(`qemu-img info "${imagePath}"`, { encoding: "utf-8" });

      const formatMatch = info.match(/file format: (\w+)/);
      const format = formatMatch ? formatMatch[1] : "unknown";

      // Check for compression indicators in qemu-img output
      const compressed = info.includes("compressed") || info.includes("compression");

      if (format !== "qcow2") {
        return {
          valid: false,
          format,
          size,
          compressed,
          error: `Expected qcow2 format, got: ${format}`,
        };
      }

      return {
        valid: true,
        format,
        size,
        compressed,
      };
    } catch (error: unknown) {
      return {
        valid: false,
        format: "",
        size,
        compressed: false,
        error: `qemu-img info failed: ${(error as Error).message}`,
      };
    }
  }

  /**
   * Validate all built images
   */
  validateAllImages(): Map<string, ValidationResult> {
    const results = new Map<string, ValidationResult>();

    for (const image of CONFIGURED_IMAGES) {
      const imagePath = this.getCustomImagePath(image.name);
      results.set(image.name, this.validateImage(imagePath));
    }

    return results;
  }

  /**
   * List all custom images in the disks directory
   */
  listCustomImages(): string[] {
    try {
      const files = fs.readdirSync(this.disksPath);
      return files.filter(
        (f) => f.startsWith("rediacc-") && (f.endsWith(".qcow2") || f.endsWith(".img")),
      );
    } catch {
      return [];
    }
  }

  /**
   * Clean up build artifacts
   *
   * @param imageName - If provided, only clean this image. Otherwise clean all.
   */
  cleanup(imageName?: string): void {
    if (imageName) {
      const imagePath = this.getCustomImagePath(imageName);
      if (fs.existsSync(imagePath)) {
        fs.unlinkSync(imagePath);
      }
    } else {
      // Run renet ops image cleanup
      try {
        execSync(`${this.renetBin} ops image cleanup --preserve-custom=false`, {
          encoding: "utf-8",
        });
      } catch {
        // Ignore cleanup errors
      }
    }
  }

  /**
   * Get build summary for all configured images
   */
  getBuildSummary(): { total: number; built: number; missing: string[] } {
    const missing: string[] = [];

    for (const image of CONFIGURED_IMAGES) {
      if (!this.customImageExists(image.name)) {
        missing.push(image.name);
      }
    }

    return {
      total: CONFIGURED_IMAGES.length,
      built: CONFIGURED_IMAGES.length - missing.length,
      missing,
    };
  }
}

export default ImageTestHelper;

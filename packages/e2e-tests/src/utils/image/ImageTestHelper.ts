import { exec, execSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { promisify } from 'node:util';
import { log } from '../log';
import { getRenetBinaryPath } from '../renetPath';

const execAsync = promisify(exec);

/**
 * Default path to disks directory (where renet saves images when run from tests/bridge)
 * This path is used by renet when executed from the tests/bridge directory
 */
const DEFAULT_DISKS_PATH = path.resolve(__dirname, '..', '..', '..', '..', 'ops', 'disks');

/**
 * OS Image configuration matching pkg/infra/opsconfig/images.go (GetKVMImages)
 */
export interface OSImage {
  name: string;
  url: string;
  distro: string;
  variant: string;
  family: 'debian' | 'rhel' | 'suse';
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
 * All configured OS images matching pkg/infra/opsconfig/images.go (GetKVMImages)
 */
export const CONFIGURED_IMAGES: OSImage[] = [
  // Debian family
  {
    name: 'ubuntu-24.04',
    url: 'https://cloud-images.ubuntu.com/minimal/releases/noble/release/ubuntu-24.04-minimal-cloudimg-amd64.img',
    distro: 'ubuntu',
    variant: 'ubuntu24.04',
    family: 'debian',
  },
  {
    name: 'debian-13',
    url: 'https://cloud.debian.org/images/cloud/trixie/latest/debian-13-genericcloud-amd64.qcow2',
    distro: 'debian',
    variant: 'debian13',
    family: 'debian',
  },

  // RHEL family
  {
    name: 'fedora-43',
    url: 'https://download.fedoraproject.org/pub/fedora/linux/releases/43/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-43-1.6.x86_64.qcow2',
    distro: 'fedora',
    variant: 'fedora-unknown',
    family: 'rhel',
  },
  {
    name: 'oracle-10',
    url: 'https://yum.oracle.com/templates/OracleLinux/OL10/u1/x86_64/OL10U1_x86_64-kvm-b270.qcow2',
    distro: 'oracle',
    variant: 'ol9.4',
    family: 'rhel',
  },

  // SUSE family
  {
    name: 'opensuse-16.0',
    url: 'https://download.opensuse.org/distribution/leap/16.0/appliances/Leap-16.0-Minimal-VM.x86_64-Cloud.qcow2',
    distro: 'suse',
    variant: 'opensuse15.5',
    family: 'suse',
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
  private readonly disksPath: string;
  private readonly renetBin: string;
  private readonly buildTimeout: number;

  constructor(options?: { disksPath?: string; renetBin?: string; buildTimeout?: number }) {
    this.disksPath = options?.disksPath ?? process.env.DISKS_PATH ?? DEFAULT_DISKS_PATH;
    this.renetBin = options?.renetBin ?? getRenetBinaryPath();
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
  getImagesByFamily(family: 'debian' | 'rhel' | 'suse'): OSImage[] {
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
   * @returns Build result with success status and output
   */
  async buildImage(imageName: string): Promise<BuildResult> {
    const image = this.getImageByName(imageName);
    if (!image) {
      return {
        success: false,
        imagePath: '',
        duration: 0,
        stdout: '',
        stderr: '',
        error: `Unknown image: ${imageName}`,
      };
    }

    const startTime = Date.now();
    // renet requires --output; the helper reads the built image back from the same disks path.
    const cmd = `${this.renetBin} ops image build --os ${image.name} --output "${this.disksPath}"`;

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
        imagePath: '',
        duration,
        stdout: err.stdout ?? '',
        stderr: err.stderr ?? '',
        error: err.message ?? String(error),
      };
    }
  }

  /**
   * Build all configured images sequentially
   *
   * @returns Map of image name to build result
   */
  async buildAllImages(): Promise<Map<string, BuildResult>> {
    const results = new Map<string, BuildResult>();

    for (const image of CONFIGURED_IMAGES) {
      log(`Building image: ${image.name}...`);
      const result = await this.buildImage(image.name);
      results.set(image.name, result);

      if (result.success) {
        log(`  ✓ ${image.name} built successfully (${Math.round(result.duration / 1000)}s)`);
      } else {
        log(`  ✗ ${image.name} failed: ${result.error ?? 'unknown error'}`);
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
   * renet writes the image into --output under the base filename of the
   * source URL (opsconfig.OSImage.GetFilename), with no prefix.
   */
  getCustomImagePath(imageName: string): string {
    const image = this.getImageByName(imageName);
    if (!image) {
      return path.join(this.disksPath, `${imageName}.qcow2`);
    }

    // Extract base filename from URL
    const urlPath = new URL(image.url).pathname;
    const baseFilename = path.basename(urlPath);

    return path.join(this.disksPath, baseFilename);
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
        format: '',
        size: 0,
        compressed: false,
        error: 'Image file does not exist',
      };
    }

    const size = this.getImageSize(imagePath);
    if (size < MIN_IMAGE_SIZE) {
      return {
        valid: false,
        format: '',
        size,
        compressed: false,
        error: `Image too small: ${size} bytes (minimum: ${MIN_IMAGE_SIZE})`,
      };
    }

    try {
      const info = execSync(`qemu-img info "${imagePath}"`, { encoding: 'utf-8' });

      const formatMatch = /file format: (\w+)/.exec(info);
      const format = formatMatch ? formatMatch[1] : 'unknown';

      // Check for compression indicators in qemu-img output
      const compressed = info.includes('compressed') || info.includes('compression');

      if (format !== 'qcow2') {
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
        format: '',
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
      return files.filter((f) => f.endsWith('.qcow2') || f.endsWith('.img'));
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
          encoding: 'utf-8',
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

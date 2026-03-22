/**
 * OS Image configuration matching pkg/infra/config/images.go
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
 * All configured OS images matching pkg/infra/config/images.go
 */
export declare const CONFIGURED_IMAGES: OSImage[];
/**
 * Helper class for image build testing.
 *
 * Provides utilities for:
 * - Building custom VM images via renet ops image commands
 * - Validating built images (format, size, compression)
 * - Managing build artifacts and cleanup
 */
export declare class ImageTestHelper {
    private readonly disksPath;
    private readonly renetBin;
    private readonly buildTimeout;
    constructor(options?: {
        disksPath?: string;
        renetBin?: string;
        buildTimeout?: number;
    });
    /**
     * Returns all configured OS images
     */
    getConfiguredImages(): OSImage[];
    /**
     * Returns images filtered by distro family
     */
    getImagesByFamily(family: 'debian' | 'rhel' | 'suse'): OSImage[];
    /**
     * Find an image by name
     */
    getImageByName(name: string): OSImage | undefined;
    /**
     * Build a single custom image
     *
     * @param imageName - The image name (e.g., 'ubuntu-24.04')
     * @param force - Force rebuild even if image exists
     * @returns Build result with success status and output
     */
    buildImage(imageName: string, force?: boolean): Promise<BuildResult>;
    /**
     * Build all configured images sequentially
     *
     * @param force - Force rebuild even if images exist
     * @returns Map of image name to build result
     */
    buildAllImages(force?: boolean): Promise<Map<string, BuildResult>>;
    /**
     * Check if a custom image exists
     */
    customImageExists(imageName: string): boolean;
    /**
     * Get the full path to a custom image
     *
     * Custom images are named: rediacc-<base-filename>
     */
    getCustomImagePath(imageName: string): string;
    /**
     * Get the file size of an image in bytes
     */
    getImageSize(imagePath: string): number;
    /**
     * Validate a built image
     *
     * Checks:
     * - File exists and is readable
     * - Format is qcow2
     * - Size is greater than minimum
     * - Image is compressed
     */
    validateImage(imagePath: string): ValidationResult;
    /**
     * Validate all built images
     */
    validateAllImages(): Map<string, ValidationResult>;
    /**
     * List all custom images in the disks directory
     */
    listCustomImages(): string[];
    /**
     * Clean up build artifacts
     *
     * @param imageName - If provided, only clean this image. Otherwise clean all.
     */
    cleanup(imageName?: string): void;
    /**
     * Get build summary for all configured images
     */
    getBuildSummary(): {
        total: number;
        built: number;
        missing: string[];
    };
}
//# sourceMappingURL=ImageTestHelper.d.ts.map

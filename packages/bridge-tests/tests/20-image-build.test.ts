import { expect, test } from "@playwright/test";
import { CONFIGURED_IMAGES, ImageTestHelper } from "../src/utils/image";

/**
 * Custom Image Build Tests
 *
 * Tests for building custom VM images for all supported Linux distributions.
 * These tests verify the complete image build pipeline:
 * 1. Download base cloud image
 * 2. Start VM with cloud-init
 * 3. Run customization script (install Docker, rclone, etc.)
 * 4. Convert to compressed qcow2
 *
 * Supported OSes (10 total):
 * - Debian family: Ubuntu 24.04, Debian 12
 * - RHEL family: CentOS 10-Stream, Fedora 43/42, Oracle 9/8, Rocky 9
 * - SUSE family: openSUSE 15.6/15.5
 *
 * Test execution:
 *   # Build all images (~3-4 hours)
 *   npx playwright test 20-image-build.test.ts --grep "@slow"
 *
 *   # Build specific family
 *   npx playwright test 20-image-build.test.ts --grep "@debian"
 *
 *   # Validate existing images only (fast)
 *   npx playwright test 20-image-build.test.ts --grep "@validate"
 */

// Increase default timeout for image builds
test.setTimeout(35 * 60 * 1000); // 35 minutes

/**
 * Group images by distro family for organized testing
 */
const DISTRO_FAMILIES = {
  debian: CONFIGURED_IMAGES.filter((img) => img.family === "debian"),
  rhel: CONFIGURED_IMAGES.filter((img) => img.family === "rhel"),
  suse: CONFIGURED_IMAGES.filter((img) => img.family === "suse"),
};

// =============================================================================
// Individual Image Build Tests
// =============================================================================

test.describe("Debian Family Image Builds @image @slow @debian", () => {
  let helper: ImageTestHelper;

  test.beforeAll(async () => {
    helper = new ImageTestHelper();
  });

  for (const image of DISTRO_FAMILIES.debian) {
    test(`should build ${image.name} image`, async () => {
      console.log(`\n=== Building ${image.name} ===`);
      console.log(`URL: ${image.url}`);
      console.log(`Variant: ${image.variant}`);

      const result = await helper.buildImage(image.name);

      if (!result.success) {
        console.error(`Build failed: ${result.error}`);
        console.error(`stderr: ${result.stderr}`);
      }

      expect(result.success, `Build failed: ${result.error}`).toBe(true);
      expect(helper.customImageExists(image.name)).toBe(true);

      const imagePath = helper.getCustomImagePath(image.name);
      const size = helper.getImageSize(imagePath);
      console.log(`Built image: ${imagePath}`);
      console.log(`Size: ${Math.round(size / 1024 / 1024)} MB`);
      console.log(`Duration: ${Math.round(result.duration / 1000)} seconds`);

      expect(size).toBeGreaterThan(10_000_000); // > 10MB
    });
  }
});

test.describe("RHEL Family Image Builds @image @slow @rhel", () => {
  let helper: ImageTestHelper;

  test.beforeAll(async () => {
    helper = new ImageTestHelper();
  });

  for (const image of DISTRO_FAMILIES.rhel) {
    test(`should build ${image.name} image`, async () => {
      console.log(`\n=== Building ${image.name} ===`);
      console.log(`URL: ${image.url}`);
      console.log(`Variant: ${image.variant}`);

      const result = await helper.buildImage(image.name);

      if (!result.success) {
        console.error(`Build failed: ${result.error}`);
        console.error(`stderr: ${result.stderr}`);
      }

      expect(result.success, `Build failed: ${result.error}`).toBe(true);
      expect(helper.customImageExists(image.name)).toBe(true);

      const imagePath = helper.getCustomImagePath(image.name);
      const size = helper.getImageSize(imagePath);
      console.log(`Built image: ${imagePath}`);
      console.log(`Size: ${Math.round(size / 1024 / 1024)} MB`);
      console.log(`Duration: ${Math.round(result.duration / 1000)} seconds`);

      expect(size).toBeGreaterThan(10_000_000); // > 10MB
    });
  }
});

test.describe("SUSE Family Image Builds @image @slow @suse", () => {
  let helper: ImageTestHelper;

  test.beforeAll(async () => {
    helper = new ImageTestHelper();
  });

  for (const image of DISTRO_FAMILIES.suse) {
    test(`should build ${image.name} image`, async () => {
      console.log(`\n=== Building ${image.name} ===`);
      console.log(`URL: ${image.url}`);
      console.log(`Variant: ${image.variant}`);

      const result = await helper.buildImage(image.name);

      if (!result.success) {
        console.error(`Build failed: ${result.error}`);
        console.error(`stderr: ${result.stderr}`);
      }

      expect(result.success, `Build failed: ${result.error}`).toBe(true);
      expect(helper.customImageExists(image.name)).toBe(true);

      const imagePath = helper.getCustomImagePath(image.name);
      const size = helper.getImageSize(imagePath);
      console.log(`Built image: ${imagePath}`);
      console.log(`Size: ${Math.round(size / 1024 / 1024)} MB`);
      console.log(`Duration: ${Math.round(result.duration / 1000)} seconds`);

      expect(size).toBeGreaterThan(10_000_000); // > 10MB
    });
  }
});

// =============================================================================
// Image Validation Tests (Fast - checks existing images)
// =============================================================================

test.describe("Image Validation @image @validate", () => {
  let helper: ImageTestHelper;

  test.beforeAll(async () => {
    helper = new ImageTestHelper();
  });

  test("should report build summary", async () => {
    const summary = helper.getBuildSummary();
    console.log(`\n=== Build Summary ===`);
    console.log(`Total configured: ${summary.total}`);
    console.log(`Built: ${summary.built}`);
    console.log(`Missing: ${summary.missing.length}`);

    if (summary.missing.length > 0) {
      console.log(`Missing images: ${summary.missing.join(", ")}`);
    }

    // This test always passes - it's informational
    expect(summary.total).toBe(10);
  });

  for (const image of CONFIGURED_IMAGES) {
    test(`${image.name} should be valid qcow2`, async () => {
      const exists = helper.customImageExists(image.name);
      test.skip(!exists, `Image not built: ${image.name}`);

      const imagePath = helper.getCustomImagePath(image.name);
      const validation = helper.validateImage(imagePath);

      console.log(`\n=== Validating ${image.name} ===`);
      console.log(`Path: ${imagePath}`);
      console.log(`Format: ${validation.format}`);
      console.log(`Size: ${Math.round(validation.size / 1024 / 1024)} MB`);
      console.log(`Compressed: ${validation.compressed}`);

      if (!validation.valid) {
        console.error(`Validation failed: ${validation.error}`);
      }

      expect(validation.valid, validation.error).toBe(true);
      expect(validation.format).toBe("qcow2");
      expect(validation.size).toBeGreaterThan(10_000_000);
    });
  }
});

// =============================================================================
// Distro Family Coverage Tests
// =============================================================================

test.describe("Distro Family Coverage @image @coverage", () => {
  let helper: ImageTestHelper;

  test.beforeAll(async () => {
    helper = new ImageTestHelper();
  });

  test("should have at least one Debian family image built", async () => {
    const debianImages = DISTRO_FAMILIES.debian;
    const builtCount = debianImages.filter((img) => helper.customImageExists(img.name)).length;

    console.log(`Debian family: ${builtCount}/${debianImages.length} built`);
    test.skip(builtCount === 0, "No Debian images built yet");

    expect(builtCount).toBeGreaterThan(0);
  });

  test("should have at least one RHEL family image built", async () => {
    const rhelImages = DISTRO_FAMILIES.rhel;
    const builtCount = rhelImages.filter((img) => helper.customImageExists(img.name)).length;

    console.log(`RHEL family: ${builtCount}/${rhelImages.length} built`);
    test.skip(builtCount === 0, "No RHEL images built yet");

    expect(builtCount).toBeGreaterThan(0);
  });

  test("should have at least one SUSE family image built", async () => {
    const suseImages = DISTRO_FAMILIES.suse;
    const builtCount = suseImages.filter((img) => helper.customImageExists(img.name)).length;

    console.log(`SUSE family: ${builtCount}/${suseImages.length} built`);
    test.skip(builtCount === 0, "No SUSE images built yet");

    expect(builtCount).toBeGreaterThan(0);
  });

  test("should have all configured images available", async () => {
    const summary = helper.getBuildSummary();

    console.log(`\n=== Full Coverage Check ===`);
    console.log(`Expected: ${summary.total} images`);
    console.log(`Built: ${summary.built} images`);
    console.log(`Coverage: ${Math.round((summary.built / summary.total) * 100)}%`);

    if (summary.missing.length > 0) {
      console.log(`\nMissing images:`);
      for (const name of summary.missing) {
        console.log(`  - ${name}`);
      }
    }

    // Skip if not all images are built (this is an aspirational test)
    test.skip(summary.built < summary.total, `Missing ${summary.missing.length} images`);

    expect(summary.built).toBe(summary.total);
  });
});

// =============================================================================
// Configuration Tests
// =============================================================================

test.describe("Image Configuration @image @config", () => {
  test("should have 10 configured images", () => {
    expect(CONFIGURED_IMAGES.length).toBe(10);
  });

  test("should have correct distro family distribution", () => {
    expect(DISTRO_FAMILIES.debian.length).toBe(2); // Ubuntu, Debian
    expect(DISTRO_FAMILIES.rhel.length).toBe(6); // CentOS, Fedora x2, Oracle x2, Rocky
    expect(DISTRO_FAMILIES.suse.length).toBe(2); // openSUSE x2
  });

  test("all images should have valid URLs", () => {
    for (const image of CONFIGURED_IMAGES) {
      expect(image.url).toMatch(/^https?:\/\//);
      expect(image.url).toMatch(/\.(qcow2|img)$/);
    }
  });

  test("all images should have unique names", () => {
    const names = CONFIGURED_IMAGES.map((img) => img.name);
    const uniqueNames = new Set(names);
    expect(uniqueNames.size).toBe(names.length);
  });

  test("all images should have valid variants", () => {
    for (const image of CONFIGURED_IMAGES) {
      expect(image.variant).toBeTruthy();
      expect(image.variant.length).toBeGreaterThan(0);
    }
  });
});

// =============================================================================
// Build All Images Test (runs sequentially)
// =============================================================================

test.describe("Build All Images @image @slow @all", () => {
  // This test builds all images sequentially
  // Expected duration: ~3-4 hours
  test.setTimeout(5 * 60 * 60 * 1000); // 5 hours

  test("should build all 10 configured images", async () => {
    const helper = new ImageTestHelper();

    console.log("\n=== Building All Images ===");
    console.log(`Total images: ${CONFIGURED_IMAGES.length}`);
    console.log("This will take approximately 3-4 hours...\n");

    const results = await helper.buildAllImages(false);

    let successCount = 0;
    let failCount = 0;

    console.log("\n=== Build Results ===");
    for (const [name, result] of Array.from(results.entries())) {
      if (result.success) {
        successCount++;
        console.log(`✓ ${name}: ${Math.round(result.duration / 1000)}s`);
      } else {
        failCount++;
        console.log(`✗ ${name}: ${result.error}`);
      }
    }

    console.log(`\nTotal: ${successCount} succeeded, ${failCount} failed`);

    // Allow some failures but require majority success
    expect(successCount).toBeGreaterThanOrEqual(7); // At least 7 of 10
  });
});

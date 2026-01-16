#!/usr/bin/env node

/**
 * Favicon Generation Script for Rediacc Website
 *
 * This script converts the existing favicon.svg to multiple PNG formats
 * for maximum browser compatibility and proper Apple touch icon support.
 *
 * Usage:
 *   npm install sharp  # Install dependency first
 *   node scripts/generate-favicons.js
 *
 * Requirements:
 *   - Node.js
 *   - sharp package for image processing
 */

const fs = require('fs');
const path = require('path');

// Check if sharp is available
let sharp;
try {
  sharp = require('sharp');
} catch (error) {
  console.error('❌ Sharp package not found. Please install it first:');
  console.error('   npm install sharp');
  console.error('   Then run: node scripts/generate-favicons.js');
  process.exit(1);
}

const publicDir = path.join(__dirname, '..', 'public');
const svgPath = path.join(publicDir, 'favicon.svg');

// Favicon sizes to generate
const faviconSizes = [
  { name: 'favicon-16x16.png', size: 16 },
  { name: 'favicon-32x32.png', size: 32 },
  { name: 'apple-touch-icon.png', size: 180 },
  { name: 'android-chrome-192x192.png', size: 192 },
  { name: 'android-chrome-512x512.png', size: 512 },
];

async function generateFavicons() {
  try {
    // Check if SVG exists
    if (!fs.existsSync(svgPath)) {
      console.error('❌ favicon.svg not found at:', svgPath);
      process.exit(1);
    }

    console.log('🎨 Generating favicons from favicon.svg...');

    // Generate each favicon size
    for (const favicon of faviconSizes) {
      const outputPath = path.join(publicDir, favicon.name);

      await sharp(svgPath)
        .resize(favicon.size, favicon.size)
        .png({ quality: 90, compressionLevel: 9 })
        .toFile(outputPath);

      console.log(`✅ Generated ${favicon.name} (${favicon.size}x${favicon.size})`);
    }

    // Generate ICO file (multi-size)
    const icoPath = path.join(publicDir, 'favicon.ico');
    await sharp(svgPath)
      .resize(32, 32)
      .png()
      .toFile(icoPath.replace('.ico', '-temp.png'));

    // Note: Sharp doesn't support ICO directly, so we create a 32x32 PNG
    // For true ICO support, you'd need a different tool like ico-convert
    fs.renameSync(icoPath.replace('.ico', '-temp.png'), icoPath);
    console.log('✅ Generated favicon.ico (32x32)');

    console.log('\n🎉 All favicons generated successfully!');
    console.log('\n📝 Next steps:');
    console.log('1. Update BaseLayout.astro to use the new PNG files');
    console.log('2. Update site.webmanifest to reference PNG icons');
    console.log('3. Test the favicon display in different browsers');

  } catch (error) {
    console.error('❌ Error generating favicons:', error.message);
    process.exit(1);
  }
}

// Check if script is run directly
if (require.main === module) {
  generateFavicons();
}

module.exports = { generateFavicons };
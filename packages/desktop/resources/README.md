# Desktop Application Resources

This directory contains icon assets for the Electron application.

## Required Icons

Before building distributable installers, add the following icon files:

### macOS
- `icon.icns` - Apple Icon Image format (required for macOS builds)
  - Recommended: 1024x1024 source image
  - Generate with: `iconutil -c icns icon.iconset/`

### Windows
- `icon.ico` - Windows Icon format (required for Windows builds)
  - Include sizes: 16, 32, 48, 64, 128, 256 pixels
  - Generate with tools like ImageMagick or online converters

### Linux
- `icon.png` - PNG image (required for Linux builds)
  - Recommended: 256x256 or 512x512 pixels
  - Should be a square image with transparency

## Generating Icons

You can use the following tools to generate icons from a source PNG:

### Using electron-icon-builder (recommended)
```bash
npm install -g electron-icon-builder
electron-icon-builder --input=source.png --output=./resources
```

### Using ImageMagick (for ICO)
```bash
convert source.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico
```

### Using iconutil (for ICNS on macOS)
```bash
mkdir icon.iconset
sips -z 16 16 source.png --out icon.iconset/icon_16x16.png
sips -z 32 32 source.png --out icon.iconset/icon_16x16@2x.png
sips -z 32 32 source.png --out icon.iconset/icon_32x32.png
sips -z 64 64 source.png --out icon.iconset/icon_32x32@2x.png
sips -z 128 128 source.png --out icon.iconset/icon_128x128.png
sips -z 256 256 source.png --out icon.iconset/icon_128x128@2x.png
sips -z 256 256 source.png --out icon.iconset/icon_256x256.png
sips -z 512 512 source.png --out icon.iconset/icon_256x256@2x.png
sips -z 512 512 source.png --out icon.iconset/icon_512x512.png
sips -z 1024 1024 source.png --out icon.iconset/icon_512x512@2x.png
iconutil -c icns icon.iconset
```

## Note

Without these icon files, electron-builder will use default Electron icons.
Add your custom icons before creating production builds.

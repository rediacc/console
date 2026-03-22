# Desktop Application Resources

This directory contains icon assets for the Electron application.

## Required Icons

Before building distributable installers, add the following icon files:

### macOS
- `icon.icns` - Apple Icon Image format (includes 16, 32, 48, 128, 256, 512px sizes)

### Windows
- `icon.ico` - Windows Icon format

### Linux
- `icon.png` - PNG image (512x512), also used as the BrowserWindow runtime icon

## Regenerating Icons

To regenerate all icons from `icon.png`:

```bash
# ICO (Windows) - requires ImageMagick
convert icon.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico

# ICNS (macOS) - requires icnsutils
for size in 16 32 48 128 256 512; do convert icon.png -resize ${size}x${size} /tmp/icon_${size}.png; done
png2icns icon.icns /tmp/icon_{16,32,48,128,256,512}.png
```

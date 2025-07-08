# Rediacc Console Desktop Application

This document describes how to build and use the Tauri-based desktop version of Rediacc Console.

## Overview

The desktop application provides:
- Native file system access for sync operations
- Direct Python script execution
- System tray integration
- Offline capabilities with local Python CLI
- Native notifications
- Better performance for file operations

## Prerequisites

### Development Requirements

1. **Node.js 18+** and npm
2. **Rust** (latest stable)
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   ```
3. **Platform-specific dependencies:**
   - **Linux**: `sudo apt install libwebkit2gtk-4.0-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev`
   - **Windows**: Windows Build Tools
   - **macOS**: Xcode Command Line Tools

### Runtime Requirements

1. **Python 3.6+** (for CLI operations)
2. **Rediacc CLI tools** installed and in PATH
   ```bash
   pip install rediacc-cli
   ```

## Building the Desktop App

### Development Mode

```bash
cd console
npm install
npm run tauri:dev
```

This will:
- Start the Vite dev server
- Launch the Tauri app in development mode
- Enable hot-reload for both frontend and Rust code

### Production Build

```bash
cd console
npm install
npm run build
npm run tauri:build
```

Platform-specific builds:
```bash
# macOS Universal Binary (x64 + ARM64)
npm run tauri:build:mac

# macOS ARM64 only (Apple Silicon)
npm run tauri:build:mac:arm

# Windows x64
npm run tauri:build:win

# Windows ARM64
npm run tauri:build:win:arm

# Linux x64
npm run tauri:build:linux

# Linux ARM64 (64-bit ARM - Raspberry Pi 4, ARM servers)
npm run tauri:build:linux:arm

# Linux ARMv7 (32-bit ARM - Raspberry Pi 3, older ARM devices)
npm run tauri:build:linux:armhf
```

Or using the go script:
```bash
# From monorepo root
./go system build_tauri --mac          # macOS universal
./go system build_tauri --mac-arm      # macOS ARM64 only
./go system build_tauri --linux-arm    # Linux ARM64
./go system build_tauri --linux-armhf  # Linux ARMv7
```

Build outputs will be in `console/src-tauri/target/release/bundle/`

## Features

### Desktop-Only Features

1. **Native File Browser**
   - Click "Browse" button in sync operations
   - Uses system file dialog

2. **Direct Python Execution**
   - Execute Python scripts directly
   - Stream output in real-time

3. **System Tray**
   - Minimize to system tray
   - Quick access from tray icon

4. **Offline Mode**
   - Works without internet for local operations
   - Cached API responses

### Web vs Desktop

| Feature | Web Browser | Desktop App |
|---------|------------|-------------|
| API Access | ✅ Via HTTP | ✅ Via HTTP or CLI |
| File Sync | ❌ Command only | ✅ Direct execution |
| Python Scripts | ❌ | ✅ |
| File Browser | ❌ | ✅ Native dialog |
| System Tray | ❌ | ✅ |
| Auto-update | ✅ Deploy | ✅ Built-in |

## Usage

### First Launch

1. The app will check for Python and Rediacc CLI
2. If missing, you'll see warnings with installation instructions
3. Login with your Rediacc credentials

### File Sync Operations

1. Select team, machine, and repository
2. Choose Upload or Download
3. Click "Browse" to select local directory
4. Configure options (mirror, verify)
5. Click "Execute Sync" to start

### Terminal Commands

1. Enter command in the terminal tab
2. Click "Execute Command"
3. View output in real-time

## Configuration

### App Settings

Settings are stored in:
- **Windows**: `%APPDATA%\com.rediacc.console\`
- **macOS**: `~/Library/Application Support/com.rediacc.console/`
- **Linux**: `~/.config/com.rediacc.console/`

### Environment Variables

The desktop app respects these environment variables:
- `REDIACC_API_URL` - Override API endpoint
- `PYTHON_PATH` - Custom Python executable path
- `REDIACC_CLI_PATH` - Custom CLI tools path

## Troubleshooting

### Python Not Found

If Python is not detected:
1. Install Python 3.6 or later
2. Ensure `python3` or `python` is in PATH
3. Restart the application

### CLI Tools Not Found

If Rediacc CLI is not detected:
1. Install via pip: `pip install rediacc-cli`
2. Or download from releases
3. Add to PATH
4. Restart the application

### Build Issues

**Linux**: Missing webkit2gtk
```bash
sudo apt update
sudo apt install libwebkit2gtk-4.0-dev
```

**Windows**: Missing Visual Studio Build Tools
- Download from Microsoft
- Install "Desktop development with C++"

**macOS**: Code signing issues
- For development, disable signing in `tauri.conf.json`
- For distribution, configure Apple Developer certificates

## Distribution

### Creating Installers

The build process creates platform-specific installers:
- **Windows**: `.msi` and `.exe` installer
- **macOS**: `.dmg` and `.app` bundle
- **Linux**: `.deb`, `.AppImage`

### Auto-Updates

To enable auto-updates:
1. Configure update server in `tauri.conf.json`
2. Sign releases with appropriate certificates
3. Host update manifests

## Security

The desktop app includes:
- Content Security Policy
- Restricted file system access (configured paths only)
- Command execution limited to whitelisted binaries
- Encrypted storage for sensitive data

## Development

### Project Structure
```
console/
├── src/                    # React frontend
│   ├── api/
│   │   ├── desktopClient.ts    # Desktop-specific API
│   │   └── unifiedClient.ts    # Unified API wrapper
│   └── hooks/
│       └── useDesktopMode.ts    # Desktop detection hook
├── src-tauri/             # Rust backend
│   ├── src/
│   │   └── main.rs       # Main Rust application
│   ├── Cargo.toml        # Rust dependencies
│   └── tauri.conf.json   # Tauri configuration
└── package.json          # Node dependencies
```

### Adding Desktop Features

1. Add Rust command in `src-tauri/src/main.rs`
2. Export in `invoke_handler!` macro
3. Add TypeScript wrapper in `desktopClient.ts`
4. Use in React components with desktop detection

### Testing

```bash
# Run frontend tests
npm test

# Run Rust tests
cd src-tauri
cargo test

# E2E tests with Tauri
npm run test:e2e
```

## Contributing

When contributing desktop-specific features:
1. Ensure web version remains functional
2. Use feature detection, not platform detection
3. Add appropriate error handling
4. Update this documentation

## License

Same as Rediacc Console - see main LICENSE file.
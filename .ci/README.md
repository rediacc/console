# Shared CI Scripts

This directory contains reusable CI scripts that work with both GitHub Actions and GitLab CI.

## Directory Structure

```
.ci/
├── config/
│   └── matrix.json         # Matrix configurations (browsers, platforms, etc.)
├── scripts/
│   ├── lib/
│   │   └── common.sh       # Shared utilities (OS detection, logging)
│   ├── ci/
│   │   └── generate-tag.sh # Generate time-based CI tag (YYYYMMDD-HHMMSS)
│   ├── version/
│   │   ├── bump.sh         # Semantic version bump (patch/minor/major)
│   │   └── commit.sh       # Commit/push version changes (CI-safe)
│   ├── setup/
│   │   ├── install-deps.sh     # npm ci with platform handling
│   │   ├── build-packages.sh   # Build shared libraries
│   │   ├── install-vscode.sh   # Cross-platform VS Code installation
│   │   └── setup-display.sh    # Xvfb setup for Linux
│   ├── tunnel/
│   │   ├── download-url.sh     # Download tunnel URL artifact
│   │   └── verify.sh           # Verify tunnel connectivity
│   ├── env/
│   │   ├── create-cli-env.sh   # Create CLI test .env
│   │   └── create-e2e-env.sh   # Create E2E test .env
│   ├── signal/
│   │   └── create-complete.sh  # Create completion signal files
│   ├── test/
│   │   ├── run-unit.sh         # Run unit tests
│   │   ├── run-e2e.sh          # Run E2E tests
│   │   └── run-cli.sh          # Run CLI tests
│   ├── docker/
│   │   ├── build-image.sh      # Build Docker images (supports --ci-tag)
│   │   └── retag-image.sh      # Re-tag CI images to semantic version
│   └── build/
│       ├── build-web.sh        # Build web application
│       ├── build-cli.sh        # Build CLI
│       └── build-desktop.sh    # Build desktop application
└── README.md
```

## Usage

All scripts are designed to be run from the repository root:

```bash
# Install dependencies
.ci/scripts/setup/install-deps.sh

# Build shared packages
.ci/scripts/setup/build-packages.sh

# Run unit tests
.ci/scripts/test/run-unit.sh

# Run E2E tests for specific browsers
.ci/scripts/test/run-e2e.sh --projects chromium firefox
```

## Versioning

Semantic versioning is managed centrally via `.ci/scripts/version/bump.sh`:

```bash
# Auto-increment patch (X.Y.Z -> X.Y.(Z+1))
.ci/scripts/version/bump.sh --auto

# Manual minor/major bump
.ci/scripts/version/bump.sh --minor
.ci/scripts/version/bump.sh --major

# Explicit version
.ci/scripts/version/bump.sh --version 1.2.3
```

For CI, write the computed version to an output file:

```bash
.ci/scripts/version/bump.sh --auto --output "$GITHUB_OUTPUT"
```

Version commits use `.ci/scripts/version/commit.sh`, which includes `[skip ci]` by default to prevent CI loops.

## Environment Variables

Scripts respect standard CI environment variables:

| Variable | Description |
|----------|-------------|
| `CI` | Set to `true` in CI environments |
| `GH_TOKEN` | GitHub token for artifact operations |
| `RUNNER_TEMP` | Temporary directory for artifacts |

## Cross-Platform Support

Scripts detect the operating system automatically and adapt:
- **Linux**: Uses apt-get, native tools
- **macOS**: Uses brew
- **Windows**: Uses choco, PowerShell where needed

Scripts work on Windows via Git Bash (MINGW/MSYS).

## Local Development

Test scripts locally before CI:

```bash
# Check if common utilities work
source .ci/scripts/lib/common.sh
detect_os  # Should print: linux, macos, or windows

# Dry-run VS Code installation check
.ci/scripts/setup/install-vscode.sh --check
```

## Adding New Scripts

1. Create script in appropriate directory
2. Source `lib/common.sh` for utilities
3. Add `set -euo pipefail` for strict mode
4. Make executable: `chmod +x script.sh`
5. Document usage in script header

Template:
```bash
#!/bin/bash
# Description of what this script does
# Usage: script.sh [options]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Script logic here
```

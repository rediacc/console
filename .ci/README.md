# Shared CI Scripts

This directory contains the reusable CI scripts driven by the workflows in
`.github/workflows/`.

## Directory Structure

Abridged — only the entry points most often edited by hand are listed. The full
set spans `build/ ci/ deploy/ docker/ docs/ env/ housekeeping/ infra/ lib/
private/ quality/ release/ security/ setup/ signal/ test/ version/`.

```
.ci/
├── config/
│   ├── constants.sh         # Pinned tool versions and shared CI constants
│   └── nfpm.yaml            # Linux package (deb/rpm/apk) build definition
├── scripts/
│   ├── lib/
│   │   └── common.sh        # Shared utilities (OS detection, logging)
│   ├── ci/
│   │   ├── generate-tag.sh  # Generate time-based CI tag (YYYYMMDD-HHMMSS)
│   │   └── derive-image-tag.sh # Derive Docker image tag from branch/tag
│   ├── version/
│   │   ├── bump.sh            # Semantic version bump (patch/minor/major)
│   │   ├── detect-bump-type.sh # Infer patch/minor/major from commits
│   │   └── resolve-version.sh  # Resolve current/next version from git tags
│   ├── setup/
│   │   ├── install-deps.sh     # npm ci with platform handling
│   │   ├── build-packages.sh   # Build shared libraries
│   │   └── install-cli-global.sh # Install the built CLI tarball globally
│   ├── env/
│   │   └── create-e2e-env.sh   # Create E2E test .env
│   ├── signal/
│   │   └── create-complete.sh  # Create completion signal files
│   ├── test/
│   │   ├── run-unit.sh         # Run unit tests
│   │   └── run-e2e.sh          # Run E2E (renet) tests
│   ├── docker/
│   │   ├── build-image.sh      # Build Docker images (supports --ci-tag)
│   │   └── retag-image.sh      # Re-tag CI images to semantic version
│   ├── housekeeping/
│   │   └── cleanup-versions.sh # Cleanup old releases, tags, and GHCR packages
│   └── build/
│       ├── build-cli.sh        # Build CLI
│       └── build-renet.sh      # Build renet binary
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

# Run E2E (renet) tests
.ci/scripts/test/run-e2e.sh
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

Note that the version source of truth is **git tags**, not a file — there are no
version bump commits. `resolve-version.sh --current` reads the latest tag and
`--bump-type` computes the next one. See the "Versioning" section of the
top-level `CLAUDE.md`.

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

# Run the shell-gate suite the way CI does
npm run test:quality-gates
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

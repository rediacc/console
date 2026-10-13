# Shared CI Scripts

This directory contains the reusable CI scripts driven by the workflows in `.github/workflows/`.

## Directory Structure

Abridged — only the entry points most often edited by hand are listed. The full set spans `build/ ci/ deploy/ docker/ docs/ env/ housekeeping/ infra/ lib/ private/ quality/ release/ security/ setup/ signal/ test/ version/`.

```
.ci/
├── breakpoint/              # On-demand CI debug box (tunnel + shell + desktop).
│   │                        # A self-contained, VENDORABLE feature package: it
│   │                        # is copied wholesale into other repos, so it has
│   │                        # its own lib and depends on nothing under scripts/.
│   ├── breakpoint.conf      # the only file a downstream repo should edit
│   ├── MANIFEST.sha256      # drift oracle; check-breakpoint-drift.sh verifies it
│   ├── lib/                 # vendored logging/parse_args + BLOCKER validation
│   ├── scripts/             # one script per step (start/stop/sweep/drift)
│   └── workflow/            # breakpoint.yml, copied to .github/workflows/
├── config/
│   ├── constants.sh         # Pinned tool versions and shared CI constants
│   └── nfpm.yaml            # Linux package (deb/rpm/apk) build definition
├── scripts/
│   ├── docker/
│   │   └── retag_image.py   # Re-tag CI images to semantic version
│   └── housekeeping/
│       └── retire-shadowed-secrets.py
├── rediacc_ci/              # Python modules that replaced the retired bash scripts (run with PYTHONPATH=.ci python3 -m)
│   ├── ci/generate_tag.py   # Generate time-based CI tag (YYYYMMDD-HHMMSS)
│   ├── version/             # resolve_version, detect_bump_type, bump
│   ├── setup/               # install_deps (npm ci with platform handling), build_packages (shared libraries)
│   ├── testrun/e2e.py       # Run E2E (renet) tests
│   ├── housekeeping/cleanup_versions.py # Cleanup old releases, tags, and GHCR packages
│   └── build/               # build_cli, build_renet, and the other build modules
└── README.md
```

## Usage

All scripts are designed to be run from the repository root:

```bash
# Install dependencies
PYTHONPATH=.ci python3 -m rediacc_ci.setup.install_deps

# Build shared packages
PYTHONPATH=.ci python3 -m rediacc_ci.setup.build_packages

# Run unit tests
PYTHONPATH=.ci python3 -m rediacc_ci.testrun.unit

# Run E2E (renet) tests
PYTHONPATH=.ci python3 -m rediacc_ci.testrun.e2e
```

## Versioning

Semantic versioning is managed centrally via `rediacc_ci.version.bump`:

```bash
# Auto-increment patch (X.Y.Z -> X.Y.(Z+1))
PYTHONPATH=.ci python3 -m rediacc_ci.version.bump --auto

# Manual minor/major bump
PYTHONPATH=.ci python3 -m rediacc_ci.version.bump --minor
PYTHONPATH=.ci python3 -m rediacc_ci.version.bump --major

# Explicit version
PYTHONPATH=.ci python3 -m rediacc_ci.version.bump --version 1.2.3
```

For CI, write the computed version to an output file:

```bash
PYTHONPATH=.ci python3 -m rediacc_ci.version.bump --auto --output "$GITHUB_OUTPUT"
```

Note that the version source of truth is **git tags**, not a file — there are no version bump commits. `rediacc_ci.version.resolve_version --current` reads the latest tag and `--bump-type` computes the next one. See the "Versioning" section of the top-level `CLAUDE.md`.

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
PYTHONPATH=.ci python3 -c "from rediacc_ci.core import common; print(common.detect_os())"  # linux, macos, or windows

# Run the gate-test suite (pytest) the way CI does
npm run check:ci-pytest
```

## Adding New Scripts

New CI logic is Python (the language policy, `check:ci-language-policy`, refuses new bash under `.ci`):

1. Create a module under `.ci/rediacc_ci/<area>/`
2. Use `rediacc_ci.core.common` (OS detection, `require_cmd`, `parse_args`) and `rediacc_ci.log` for utilities
3. Run it as `PYTHONPATH=.ci python3 -m rediacc_ci.<area>.<module>`
4. Document usage in the module docstring
5. Add a pytest under `.ci/rediacc_ci/tests/`

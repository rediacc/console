# Versioned Deployments for Console

This document explains the versioned deployment system for the Rediacc Console on GitHub Pages.

## Overview

The console uses a versioned deployment strategy that:
- Deploys each release to its own subdirectory (e.g., `/versions/v1.2.3/`)
- Always updates the root (`/`) with the latest version
- Automatically cleans up old versions to maintain a total size under 128 MB
- Keeps at least the 3 most recent versions regardless of size
- Provides a version browser at `/versions/`

## URL Structure

```
console.rediacc.com/                  → Latest version (always up-to-date)
console.rediacc.com/versions/v1.2.3/  → Specific version 1.2.3
console.rediacc.com/versions/v1.2.2/  → Specific version 1.2.2
console.rediacc.com/versions/         → Version browser (lists all versions)
console.rediacc.com/versions.json     → Machine-readable version manifest
console.rediacc.com/version.json      → Current version info
```

## How It Works

### Deployment Flow

1. **Trigger**: Push a version tag (e.g., `v1.2.3`) or manually trigger the workflow
2. **Build**: Downloads pre-built artifact from CI workflow
3. **Checkout**: Fetches existing gh-pages branch
4. **Cleanup**: Removes old versions if total size would exceed 128 MB
5. **Deploy**:
   - Copies build to `/versions/v1.2.3/`
   - Updates root `/` with latest version
   - Generates versions index page
   - Creates versions.json manifest
6. **Publish**: Uploads to GitHub Pages using native actions

### Version Cleanup Logic

The cleanup system ensures efficient storage usage:

```bash
# Size limit
MAX_SIZE: 128 MB

# Minimum versions to keep
MIN_VERSIONS: 3

# Cleanup algorithm
1. Calculate total size of existing versions
2. Add new version size to get projected total
3. If projected > 128 MB:
   - Remove oldest versions first
   - Stop when: projected size ≤ 128 MB OR remaining versions ≤ 3
   - Always preserve at least 3 most recent versions
```

**Example scenario:**
- Current versions: v1.0.0 (2 MB), v1.1.0 (2 MB), v1.2.0 (2 MB), v1.3.0 (125 MB)
- Total: 131 MB
- New version v1.4.0: 2 MB
- Projected: 133 MB (exceeds 128 MB)
- Action: Remove v1.0.0 (oldest)
- Result: v1.1.0, v1.2.0, v1.3.0, v1.4.0 = 131 MB

## Components

### 1. Version Management Script
**Location**: `.github/scripts/manage-versions.sh`

**Functions:**
- `deploy <gh-pages-dir> <build-dir> <version>` - Deploy new version with cleanup
- `cleanup <gh-pages-dir> <new-size>` - Clean old versions to fit size limit
- `list <gh-pages-dir>` - List all versions (newest first)
- `generate-index <gh-pages-dir>` - Generate versions browser page

**Usage:**
```bash
# Deploy a new version
./manage-versions.sh deploy ./gh-pages ./dist v1.2.3

# List versions
./manage-versions.sh list ./gh-pages

# Generate index only
./manage-versions.sh generate-index ./gh-pages
```

### 2. GitHub Actions Workflow
**Location**: `.github/workflows/publish.yml`

**Key steps:**
```yaml
- Download build artifact from CI workflow
- Checkout gh-pages branch
- Run version deployment script
- Upload pages artifact
- Deploy to GitHub Pages
```

**Native GitHub Tools Used:**
- `actions/checkout@v4` - Repository checkout
- `actions/configure-pages@v4` - GitHub Pages setup
- `actions/upload-pages-artifact@v3` - Upload deployment
- `actions/deploy-pages@v4` - Deploy to GitHub Pages
- `gh` CLI - Download CI artifacts (pre-installed in runners)

### 3. Version Browser
**Generated at**: `/versions/index.html`

Features:
- Beautiful gradient UI
- Lists all available versions
- Shows version metadata (date, size)
- Highlights latest version
- Responsive design

### 4. Version Manifest
**Location**: `/versions.json`

Format:
```json
{
  "latest": "v1.2.3",
  "versions": ["v1.2.3", "v1.2.2", "v1.2.1"]
}
```

## Testing Locally

### Test Versioned Deployment

```bash
cd console

# Run test with default version
./.github/scripts/test-version-deployment.sh

# Run test with specific version
./.github/scripts/test-version-deployment.sh v1.2.3

# Run test without building (use existing dist)
./.github/scripts/test-version-deployment.sh v1.2.3 true

# Inspect results
cd .test-deployment/gh-pages
python3 -m http.server 8080
# Visit http://localhost:8080
```

### Manual Testing

```bash
# 1. Build the console
npm run build

# 2. Create test gh-pages directory
mkdir -p test-gh-pages

# 3. Deploy version
.github/scripts/manage-versions.sh deploy test-gh-pages dist v1.0.0

# 4. Verify structure
ls -R test-gh-pages/

# 5. Start local server
cd test-gh-pages
python3 -m http.server 8080

# 6. Test URLs
# http://localhost:8080/               → Latest
# http://localhost:8080/versions/      → Version browser
# http://localhost:8080/versions/v1.0.0/ → Specific version
```

## Releasing a New Version

### Automatic (Recommended)

```bash
# Create and push a version tag
git tag v1.2.3
git push origin v1.2.3

# GitHub Actions will automatically:
# 1. Download the build artifact from CI
# 2. Deploy to versioned subdirectory
# 3. Update root with latest
# 4. Clean up old versions if needed
# 5. Create GitHub Release
```

### Manual

```bash
# Trigger workflow manually via GitHub UI
# Actions → Publish Console Release → Run workflow
# Enter version: v1.2.3 or 1.2.3
```

## Configuration

### Adjusting Size Limit

Edit `.github/scripts/manage-versions.sh`:

```bash
# Configuration (line 8)
MAX_SIZE_MB=128  # Change to desired size in MB
```

### Adjusting Minimum Versions

Edit `.github/scripts/manage-versions.sh`:

```bash
# Configuration (line 10)
KEEP_LATEST_COUNT=3  # Change to minimum versions to keep
```

### Version Pattern

Current pattern: `v[0-9]+.[0-9]+.[0-9]+` (semantic versioning)

To change, edit `.github/workflows/publish.yml`:

```yaml
on:
  push:
    tags:
      - 'v[0-9]+.[0-9]+.[0-9]+'  # Modify regex pattern
```

## Router Configuration

The console uses React Router with `BrowserRouter` configured to support subdirectory deployments:

```tsx
<BrowserRouter basename={import.meta.env.BASE_URL}>
```

The `BASE_URL` is set by Vite based on the deployment context:
- Development: `/console/` (for local middleware integration)
- Production: `/` (root) or `/versions/vX.Y.Z/` (versioned)

## SPA Routing Support

Each deployment includes a `404.html` file that mirrors `index.html` to support client-side routing on GitHub Pages:

```bash
cp dist/index.html dist/404.html
```

This ensures that direct navigation to routes like `/dashboard` works correctly.

## Troubleshooting

### Old versions not being cleaned

**Check:**
1. Verify size calculation: `du -sb versions/*/`
2. Check script logs in GitHub Actions
3. Ensure minimum version count isn't blocking cleanup

**Solution:**
```bash
# Manually run cleanup
.github/scripts/manage-versions.sh cleanup ./gh-pages 0
```

### Version not deploying

**Check:**
1. CI build artifact exists for the commit
2. Tag format matches: `v[0-9]+.[0-9]+.[0-9]+`
3. GitHub Pages is enabled
4. Workflow has Pages permissions

**Solution:**
```bash
# Check CI artifacts
gh run list --workflow=ci.yml --limit 5

# Check if tag exists
git tag -l "v*"
```

### Versions index not updating

**Check:**
1. Script execution logs
2. Git command permissions

**Solution:**
```bash
# Regenerate index manually
.github/scripts/manage-versions.sh generate-index ./gh-pages
```

## Architecture Decisions

### Why subdirectories?

**Pros:**
- Single domain (console.rediacc.com)
- Clean URL structure
- No CORS issues
- Easy version switching
- SEO friendly

**Cons:**
- Cumulative storage
- Need cleanup mechanism

**Alternatives considered:**
- Separate domains: Too much infrastructure
- Query parameters: Poor UX, not shareable
- Hash routing: Breaks browser history
- Artifacts only: No persistent URLs

### Why 128 MB limit?

GitHub Pages soft limit is 1 GB, but keeping deployments lean:
- Faster deployments
- Reduced bandwidth
- Encourages cleanup
- Average build ~1.5 MB → ~85 versions possible

### Why keep 3 minimum versions?

- Current stable release
- Previous stable (rollback target)
- One older version (historical reference)

## Security Considerations

### Version Enumeration

Users can discover all versions via `/versions.json`. This is intentional for:
- Transparency
- Version selection UI
- API integrations

If version privacy is needed:
- Remove versions.json generation
- Remove versions index page
- Only share version URLs privately

### Content Integrity

Each version deployment:
- Is immutable (subdirectory never overwritten)
- Includes version.json with build metadata
- Traceable to git commit

## Future Enhancements

Potential improvements:

1. **Changelog Integration**
   - Auto-generate changelog from git commits
   - Display in version browser

2. **Version Aliases**
   - `/versions/latest/` → latest version
   - `/versions/stable/` → last stable release
   - `/versions/v1/` → latest v1.x.x

3. **Download Archives**
   - Offer downloadable bundles
   - Self-hosting support

4. **Analytics**
   - Track version usage
   - Inform cleanup decisions

5. **Preview Deployments**
   - Deploy PR previews to `/preview/{pr-number}/`
   - Auto-cleanup on PR close

## Support

For issues or questions:
- Check GitHub Actions logs
- Review this documentation
- Test locally with test script
- Open issue on GitHub

## Version History

- **2025-10-11**: Initial versioned deployment system
  - 128 MB size limit
  - 3 minimum versions
  - Automatic cleanup
  - Native GitHub Actions only

# Console CI/CD Workflows

This directory contains GitHub Actions workflows for the Rediacc Console.

## Workflows

### 1. `ci.yml` - Main CI Pipeline

Runs on every pull request and push to `main`/`develop` branches.

**Jobs:**
- **PR Validation**: Title format, description, size checks, conflict detection
- **Lint**: ESLint code quality checks
- **Type Check**: TypeScript type validation
- **Build**: Production build testing (both DEBUG and RELEASE modes)
- **Security Scan**: npm audit for vulnerabilities
- **Bundle Size**: Analyzes bundle size and warns if > 10MB
- **CI Summary**: Aggregates all results

**Artifacts:**
- Build outputs for both DEBUG and RELEASE modes (retained for 90 days)
- Security audit reports (retained for 30 days)

### 2. `publish.yml` - Release Deployment

Triggered by version tags (e.g., `v1.0.0`) or manual workflow dispatch.

**Process:**
1. Detects or creates version tag
2. Finds successful CI run for the tagged commit
3. Downloads RELEASE build artifact from CI
4. Deploys to GitHub Pages with version management:
   - Updates root with latest version
   - Preserves `/versions/vX.Y.Z/` subdirectories
   - Maintains `version.json` and `versions.json`
   - Auto-cleans old versions (keeps 3 most recent, max 128MB total)
5. Creates GitHub Release with notes

**Deployment URLs:**
- **Latest**: https://console.rediacc.com
- **Specific version**: https://console.rediacc.com/versions/v0.0.6/
- **All versions**: https://console.rediacc.com/versions/

**Version Management:**
- Old versions automatically cleaned to maintain 128MB limit
- Always keeps at least 3 most recent versions
- Each version accessible via its own subdirectory

**Conventional Commit Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Test additions or changes
- `chore`: Maintenance tasks
- `ci`: CI/CD changes
- `build`: Build system changes
- `revert`: Revert previous commits

**Example PR titles:**
```
feat(ui): add dark mode toggle
fix(api): resolve token refresh race condition
docs: update deployment guide
refactor(queue): improve queue item processing
```

## Dependabot Configuration

Located at `.github/dependabot.yml`, this configures automated dependency updates:

**NPM Dependencies:**
- Runs weekly on Mondays
- Groups dev dependencies (types, eslint, vite)
- Groups production dependencies (react, antd)
- Commits prefixed with `chore(deps)`

**GitHub Actions:**
- Runs monthly
- Updates action versions
- Commits prefixed with `chore(ci)`

## Deployment Process

**Development Workflow:**
```bash
# 1. Make changes and test locally
npm run dev

# 2. Create PR (triggers ci.yml)
git checkout -b feature/my-feature
git push origin feature/my-feature

# 3. Merge to main (triggers ci.yml, creates artifact)
# CI builds and stores artifacts for 90 days

# 4. When ready to release:
git tag v0.0.7
git push origin v0.0.7

# 5. publish.yml automatically:
#    - Downloads CI artifact
#    - Deploys to console.rediacc.com
#    - Creates versioned copy at /versions/v0.0.7/
#    - Creates GitHub Release
```

**Testing Before Release:**
- Run locally: `npm run dev`
- Use Cloudflare tunnel for remote testing
- Download CI artifacts to test specific builds

## Local Testing

Before pushing, you can test CI checks locally:

```bash
# Lint check
npm run lint

# Type check
npx tsc --noEmit

# Build test
REDIACC_BUILD_TYPE=DEBUG npm run build
REDIACC_BUILD_TYPE=RELEASE npm run build

# Security audit
npm audit
```

## CI Status Badge

Add this to your README.md:

```markdown
[![Console CI](https://github.com/rediacc/console/actions/workflows/ci.yml/badge.svg)](https://github.com/rediacc/console/actions/workflows/ci.yml)
```

## Troubleshooting

### TypeScript Errors in CI

The type check job is currently set to continue on errors. If you want to enforce strict type checking:

1. Fix all TypeScript errors in the codebase
2. Update `ci.yml` to fail on type errors:
   ```yaml
   - name: Run TypeScript type check
     run: npx tsc --noEmit
     # Remove the 'continue-on-error: true' line
   ```

### Build Failures

Common issues:
- **Missing dependencies**: Run `npm ci` locally
- **Cache issues**: Clear Vite cache with `rm -rf node_modules/.vite`
- **Environment variables**: Ensure `REDIACC_BUILD_TYPE` is set

### PR Check Failures

- **Title format**: Use conventional commit format
- **Description**: Provide at least 20 characters
- **Merge conflicts**: Rebase on latest main/develop

## Workflow Permissions

Workflows require these permissions:
- `contents: read` - Read repository contents
- `pull-requests: write` - Comment on PRs (for size analysis)
- `checks: write` - Update check status

## Future Enhancements

Planned additions:
- [ ] Visual regression testing
- [ ] Performance benchmarking
- [ ] Lighthouse CI for web vitals
- [ ] Automatic deployment previews
- [ ] Code coverage reporting

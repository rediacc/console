# Console CI/CD Workflows

This directory contains GitHub Actions workflows for the Rediacc Console.

## Workflows

### 1. `ci.yml` - Main CI Pipeline

Runs on every pull request and push to `main`/`develop` branches.

**Jobs:**
- **Lint**: ESLint code quality checks
- **Type Check**: TypeScript type validation (currently informational)
- **Build**: Production build testing (both DEBUG and RELEASE modes)
- **Security Scan**: npm audit for vulnerabilities
- **Bundle Size**: Analyzes bundle size and warns if > 10MB
- **CI Summary**: Aggregates all results

**Artifacts:**
- Build outputs for both DEBUG and RELEASE modes (retained for 7 days)
- Security audit reports (retained for 30 days)

### 2. `pr-checks.yml` - PR Quality Gates

Validates pull request quality and conventions.

**Checks:**
- PR title follows Conventional Commits format
- PR description is adequate
- References issues (warning if missing)
- Labels are present (warning if missing)
- PR size analysis (warns if > 1000 lines or > 30 files)
- Merge conflict detection

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
- [ ] Playwright E2E tests in CI
- [ ] Visual regression testing
- [ ] Performance benchmarking
- [ ] Lighthouse CI for web vitals
- [ ] Automatic deployment previews
- [ ] Code coverage reporting

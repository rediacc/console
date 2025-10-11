# Contributing to Rediacc Console

Thank you for your interest in contributing to the Rediacc Console! This document provides guidelines and workflows for contributing to the project.

## 🔒 Branch Protection & Workflow

### Protected Branches

The following branches are protected and require pull requests:

- **`main`** - Production-ready code, always deployable
- **`develop`** - Integration branch (if used)

### Direct Push = Blocked ⛔

You **cannot** push directly to protected branches. All changes must go through the pull request process.

## 📝 Contribution Process

### 1. Create a Feature Branch

```bash
# Update your local main branch
git checkout main
git pull origin main

# Create a new feature branch
git checkout -b feat/your-feature-name

# Or for bug fixes
git checkout -b fix/issue-description
```

### 2. Make Your Changes

- Write clean, well-documented code
- Follow existing code style and conventions
- Add tests for new functionality
- Update documentation as needed

### 3. Commit Your Changes

Follow the [Conventional Commits](https://www.conventionalcommits.org/) format:

```bash
git add .
git commit -m "feat: add new feature description"

# Commit types:
# feat: New feature
# fix: Bug fix
# docs: Documentation changes
# style: Code style changes (formatting, etc.)
# refactor: Code refactoring
# test: Adding or updating tests
# chore: Maintenance tasks
# perf: Performance improvements
# ci: CI/CD changes
# build: Build system changes
```

### 4. Push to GitHub

```bash
git push -u origin feat/your-feature-name
```

### 5. Create a Pull Request

```bash
# Using GitHub CLI (recommended)
gh pr create --fill

# Or manually via GitHub web interface
```

### 6. Wait for CI & Reviews

Your PR must meet the following requirements before it can be merged:

#### ✅ Required Checks (All Must Pass)

- **pr-validation** - PR title and description format validation
- **pr-size-check** - Ensures PR size is manageable
- **build** - Production build must succeed
- **lint** - ESLint checks must pass
- **test** - All unit and integration tests must pass
- **type-check** - TypeScript type checking must pass

#### ✅ Required Reviews

- At least **1 approval** from a team member
- All review comments must be **resolved**

#### ✅ Branch Requirements

- Branch must be **up-to-date** with main
- **No merge conflicts**

### 7. Merge Your PR

Once all checks pass and you have approval:

1. Click **"Squash and merge"** button on GitHub
2. Edit the commit message if needed (uses PR title and description by default)
3. Confirm the merge

Your feature branch will be **automatically deleted** after merge.

## 🚫 What NOT to Do

❌ **Don't push directly to main** - All changes require PRs
❌ **Don't force push to main** - Protected and will be rejected
❌ **Don't merge without CI passing** - Merges are blocked
❌ **Don't merge without approval** - At least 1 review required
❌ **Don't leave unresolved conversations** - All must be resolved

## 🧪 Testing Locally

Before pushing your changes, test locally:

```bash
# Install dependencies
npm install

# Run all tests
npm test

# Run linting
npm run lint

# Run type checking
npm run type-check

# Build the project
npm run build

# Run development server
npm run dev
```

### Playwright E2E Tests

```bash
# Install Playwright browsers (first time only)
npx playwright install chromium

# Run E2E tests
npm run test:e2e

# Run E2E tests in UI mode
npm run test:e2e:ui

# Run specific test file
npx playwright test tests/login.spec.ts
```

## 🐛 Reporting Issues

Found a bug? Please create an issue with:

- Clear description of the problem
- Steps to reproduce
- Expected vs actual behavior
- Environment details (browser, OS, console version)
- Error messages or screenshots

## 💡 Suggesting Features

Have an idea? Create an issue with:

- Clear description of the feature
- Use case and motivation
- Proposed implementation (optional)
- Examples of similar features (if applicable)

## 📚 Code Style Guidelines

### TypeScript/React Code

- Follow [Airbnb React Style Guide](https://github.com/airbnb/javascript/tree/master/react)
- Use functional components with hooks
- Use meaningful variable and function names
- Add JSDoc comments to exported functions/components
- Keep components focused and small
- Use TypeScript types/interfaces (avoid `any`)

### Example:

```typescript
interface UserCardProps {
  user: User;
  onEdit: (userId: string) => void;
}

/**
 * Displays user information in a card format
 * @param user - The user object to display
 * @param onEdit - Callback when edit button is clicked
 */
export const UserCard: React.FC<UserCardProps> = ({ user, onEdit }) => {
  // Implementation here
};
```

### Component Organization

```
src/
├── components/         # Reusable UI components
├── pages/             # Page-level components
├── hooks/             # Custom React hooks
├── utils/             # Utility functions
├── api/               # API client and types
├── types/             # TypeScript type definitions
└── i18n/              # Internationalization files
```

### Git Commits

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Keep first line under 72 characters
- Reference issues and PRs in commit body when relevant

## 🔄 Keeping Your Branch Updated

If your branch falls behind main:

```bash
# Update main
git checkout main
git pull origin main

# Rebase your feature branch
git checkout feat/your-feature-name
git rebase main

# Force push (only to your feature branch!)
git push --force-with-lease origin feat/your-feature-name
```

## 🎨 Design Guidelines

- Follow Ant Design principles
- Maintain consistent spacing and typography
- Ensure responsive design (mobile, tablet, desktop)
- Test in multiple browsers (Chrome, Firefox, Safari, Edge)
- Ensure accessibility (ARIA labels, keyboard navigation)
- Refer to `/context/design-principles.md` for comprehensive guidelines
- Refer to `/context/style-guide.md` for brand guidelines

## ❓ FAQ

### Q: What if CI fails on my PR?

**A:** Fix the issues and push new commits. CI will automatically re-run.

### Q: Can I force push to my feature branch?

**A:** Yes! Only main/develop branches are protected. Use `--force-with-lease` for safety.

### Q: What if I need to make an urgent hotfix?

**A:** Create an emergency PR, request expedited review, and use auto-merge once approved.

### Q: How long do reviews usually take?

**A:** We aim to review PRs within 1-2 business days. Ping in the team channel if urgent.

### Q: Can I merge my own PR?

**A:** You can click merge after approval, but you cannot approve your own PR.

### Q: What happens to my branch after merge?

**A:** It's automatically deleted from GitHub. Clean up locally with `git branch -d feat/name`.

### Q: How do I run the console locally?

**A:** Run `npm install` then `npm run dev`. The console will be available at http://localhost:5173

## 🎯 Workflow Summary

```
1. Create branch     → git checkout -b feat/name
2. Make changes      → code, test, commit
3. Push branch       → git push -u origin feat/name
4. Create PR         → gh pr create --fill
5. Wait for CI       → All 6 checks must pass ✅
6. Get review        → At least 1 approval required ✅
7. Resolve comments  → All conversations resolved ✅
8. Squash & merge    → Click button, branch auto-deleted ✅
```

## 📞 Getting Help

- **Documentation**: Check `/docs` directory and project README
- **Issues**: Search existing issues first
- **Discussions**: Use GitHub Discussions for questions
- **Team Chat**: Reach out in the team communication channel

## 🌐 Internationalization

The console supports multiple languages. When adding new UI text:

1. Add the key to `src/i18n/locales/en/common.json`
2. Use the translation hook: `const { t } = useTranslation();`
3. Reference in JSX: `{t('your.key.path')}`

## 🔐 Security Considerations

- Never commit sensitive data (API keys, tokens, passwords)
- Use environment variables for configuration
- Validate all user inputs
- Follow OWASP guidelines for web security
- Report security vulnerabilities privately (see SECURITY.md)

## 📄 License

By contributing, you agree that your contributions will be licensed under the same license as the project.

---

Thank you for contributing to Rediacc Console! 🚀

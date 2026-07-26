# Contributing to Rediacc Console

Thank you for your interest in contributing to the Rediacc Console! This document provides guidelines and workflows for contributing to the project.

## 🔒 Branch Protection & Workflow

### Protected Branches

The following branch is protected and requires pull requests:

- **`main`** - Production-ready code, always deployable

### Direct Push = Blocked ⛔

You **cannot** push directly to protected branches. All changes must go through the pull request process.

### Fork PRs are not supported

CI must be run from a branch in this repository. A pull request opened from a
fork cannot access repository secrets, so the very first job (`Initialize`)
fails to mint its GitHub App token, every downstream job is skipped, and the
required `CI Complete` check reports red. There is no fork-friendly subset of
the pipeline and none is planned — the build needs private submodules
(`renet`, `account`, `elite`) that a fork cannot read anyway.

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
# Using GitHub CLI (recommended): open as a draft until CI is green
gh pr create --draft --fill

# Or manually via GitHub web interface
```

### 6. Open as a Draft, Wait for CI, then Ready + Review

Keep the PR a **draft** until CI is green. The pipeline runs on every push; the single required status check is **`CI Complete`**, an aggregator that turns green only when the whole pipeline (quality, builds, tests, install matrix, preview, review gate) has passed.

#### ✅ Required check

- **`CI Complete`** - the one required status check. There are **no required human approvals**.

#### ✅ Automated review

- When `CI Complete` is green, flip the PR ready (`gh pr ready` - allowed only once `CI Complete` is green). Marking it ready triggers an **automated Claude review**; it also re-runs after each later green push while the PR is ready.
- Claude posts inline comments as review threads. **All of its threads must be resolved (or substantively replied to)** before the PR can merge; the `Review Gate` job enforces this.

#### ✅ Branch Requirements

- Branch must be **up-to-date** with main
- **No merge conflicts**

### 7. Merge Your PR

Once `CI Complete` is green and all review threads are resolved:

1. Merge is **squash-only**. Use auto-merge so GitHub lands it the moment required checks are green: `gh pr merge --squash --auto` (or the **"Squash and merge"** button on GitHub).
2. The commit message uses the PR title and description by default; edit if needed.
3. `gh pr merge --admin` is **not** allowed - the sanctioned path is `--squash --auto`.

Your feature branch will be **automatically deleted** after merge.

## 🚫 What NOT to Do

❌ **Don't push directly to main** - All changes require PRs
❌ **Don't force push to main** - Protected and will be rejected
❌ **Don't merge with `CI Complete` red** - the required check must be green
❌ **Don't `gh pr merge --admin`** - banned; use `--squash --auto`
❌ **Don't leave unresolved review threads** - all must be resolved

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

**A:** Open a PR as usual; there is no separate approval step. Once `CI Complete` is green and the automated review's threads are resolved, `gh pr merge --squash --auto` lands it the moment checks pass.

### Q: How long do reviews usually take?

**A:** We aim to review PRs within 1-2 business days. Ping in the team channel if urgent.

### Q: Can I merge my own PR?

**A:** Yes. There are no required human approvals; once `CI Complete` is green and the automated Claude review's threads are resolved, you (or auto-merge) can squash-merge.

### Q: What happens to my branch after merge?

**A:** It's automatically deleted from GitHub. Clean up locally with `git branch -d feat/name`.

### Q: How do I run the console locally?

**A:** Run `npm install` then `npm run dev`. The console will be available at http://localhost:5173

## 🎯 Workflow Summary

```
1. Create branch     → git checkout -b feat/name
2. Make changes      → code, test, commit
3. Push branch       → git push -u origin feat/name
4. Open draft PR     → gh pr create --draft --fill
5. Wait for CI       → CI Complete must go green ✅
6. Flip ready        → gh pr ready (triggers the Claude review) ✅
7. Resolve threads   → Claude's review threads resolved ✅
8. Squash & merge    → gh pr merge --squash --auto, branch auto-deleted ✅
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

Thank you for contributing to the Rediacc Console! 🚀

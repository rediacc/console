# Rediacc Console

> React/TypeScript web UI for infrastructure management and task execution

[![GitHub Pages](https://img.shields.io/badge/demo-live-success)](https://rediacc.github.io/console/)
[![License](https://img.shields.io/github/license/rediacc/console)](./LICENSE)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-blue)](https://www.typescriptlang.org/)
[![React](https://img.shields.io/badge/React-18.x-blue)](https://reactjs.org/)
[![Ant Design](https://img.shields.io/badge/Ant%20Design-5.x-blue)](https://ant.design/)

The Rediacc Console is a modern web-based interface for managing distributed infrastructure, executing tasks, and monitoring resources. It provides an intuitive UI for interacting with the Rediacc system, including machines, bridges, repositories, and queue management.

## ✨ Features

- **Resource Management**: Manage machines, bridges, teams, and repositories
- **Queue System**: Create, monitor, and manage distributed task execution
- **File Synchronization**: Upload/download files to remote machines
- **SSH Terminal Access**: Interactive terminal sessions within repository environments
- **Real-time Monitoring**: Track task progress and system status
- **Multi-language Support**: Internationalization (i18n) with multiple language support
- **Secure Authentication**: Token-based authentication with automatic rotation
- **Vault Encryption**: Client-side encryption for sensitive data
- **Responsive Design**: Works seamlessly on desktop, tablet, and mobile devices

## 🚀 Quick Start

### Prerequisites

- Node.js 18.x or higher
- npm 9.x or higher

### Installation

```bash
# Clone the repository
git clone https://github.com/rediacc/console.git
cd console

# Install dependencies
npm install

# Start development server
npm run dev
```

The console will be available at `http://localhost:5173`

### Building for Production

```bash
# Create production build
npm run build

# Preview production build locally
npm run preview
```

## 📦 Project Structure

```
console/
├── src/
│   ├── api/              # API client and middleware
│   │   ├── client.ts     # HTTP client with token management
│   │   └── encryptionMiddleware.ts  # Vault encryption/decryption
│   ├── components/       # Reusable UI components
│   ├── pages/           # Page-level components
│   ├── hooks/           # Custom React hooks
│   ├── utils/           # Utility functions
│   ├── types/           # TypeScript type definitions
│   ├── i18n/            # Internationalization
│   │   └── locales/     # Translation files
│   ├── App.tsx          # Main application component
│   └── main.tsx         # Application entry point
├── public/              # Static assets
├── .github/
│   ├── workflows/       # CI/CD workflows
│   └── CONTRIBUTING.md  # Contribution guidelines
├── playwright/          # E2E tests
├── tests/              # Unit tests
└── vite.config.ts      # Vite configuration
```

## 🛠️ Development

### Available Scripts

```bash
npm run dev          # Start development server
npm run build        # Build for production
npm run preview      # Preview production build
npm run lint         # Run ESLint
npm run type-check   # Run TypeScript type checking
npm test             # Run unit tests
npm run test:e2e     # Run Playwright E2E tests
npm run test:e2e:ui  # Run E2E tests in UI mode
```

### Environment Variables

Create a `.env` file in the root directory:

```env
VITE_API_URL=https://api.rediacc.com
VITE_APP_VERSION=1.0.0
```

### Code Style

This project uses:

- **ESLint** for linting
- **TypeScript** for type checking
- **Prettier** for code formatting (integrated with ESLint)
- **Conventional Commits** for commit messages

## 🧪 Testing

### Unit Tests

```bash
# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage
```

### E2E Tests (Playwright)

```bash
# Install browsers (first time only)
npx playwright install chromium

# Run E2E tests
npm run test:e2e

# Run in UI mode for debugging
npm run test:e2e:ui

# Run specific test file
npx playwright test tests/login.spec.ts
```

## 🏗️ Architecture

The Console is part of the larger Rediacc system:

```
┌─────────────┐     HTTPS      ┌──────────────┐     SQL      ┌────────────┐
│   Console   │ ◄────────────► │  Middleware  │ ◄──────────► │  Database  │
│  (React)    │                 │   (.NET)     │               │ (SQL Server)│
└─────────────┘                 └──────────────┘               └────────────┘
```

### Key Technologies

- **React 18** - UI framework with hooks
- **TypeScript** - Type-safe JavaScript
- **Vite** - Fast build tool and dev server
- **Ant Design** - UI component library
- **Axios** - HTTP client
- **React Router** - Client-side routing
- **i18next** - Internationalization
- **Playwright** - E2E testing

### API Communication

The Console communicates with the Middleware API using:

- **REST API**: HTTP/HTTPS endpoints
- **Token Rotation**: Automatic security token management
- **Vault Encryption**: Client-side encryption for sensitive data
- **Error Handling**: Comprehensive error responses

## 🌐 Internationalization

The console supports multiple languages. Translation files are located in `src/i18n/locales/`:

```
src/i18n/locales/
├── en/
│   └── common.json
├── tr/
│   └── common.json
└── ...
```

To add a new translation:

1. Add the key to `en/common.json`
2. Translate to other language files
3. Use in components: `const { t } = useTranslation(); ... {t('your.key')}`

## 🔒 Security

- **Token Authentication**: Rotating tokens for API security
- **Vault Encryption**: Master password-based encryption
- **XSS Protection**: React's built-in XSS protection
- **HTTPS Only**: Enforced secure connections
- **Dependabot**: Automated security updates
- **Secret Scanning**: GitHub secret scanning enabled

See [SECURITY.md](./SECURITY.md) for reporting vulnerabilities.

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](./.github/CONTRIBUTING.md) for details.

### Quick Contribution Steps

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Make your changes
4. Commit using conventional commits (`git commit -m 'feat: add amazing feature'`)
5. Push to your branch (`git push origin feat/amazing-feature`)
6. Open a Pull Request

### Development Workflow

- All PRs must pass CI checks (build, lint, test, type-check)
- At least 1 approval required
- All conversations must be resolved
- Branch must be up-to-date with main
- Only squash merge is allowed

## 📝 Documentation

- [Contributing Guide](./.github/CONTRIBUTING.md)
- [Security Policy](./SECURITY.md)
- [Code of Conduct](./CODE_OF_CONDUCT.md)
- [Design Principles](./context/design-principles.md)
- [Style Guide](./context/style-guide.md)

## 🚢 Deployment

The console is automatically deployed to GitHub Pages when changes are merged to main:

- **Live Demo**: https://rediacc.github.io/console/
- **Deployment**: Automatic via GitHub Actions
- **Build**: Production-optimized build with Vite

## 📊 Project Status

- **Status**: Active Development
- **Version**: See [package.json](./package.json)
- **Issues**: [GitHub Issues](https://github.com/rediacc/console/issues)
- **Pull Requests**: [GitHub PRs](https://github.com/rediacc/console/pulls)

## 📄 License

This project is licensed under the terms specified in the [LICENSE](./LICENSE) file.

## 🙏 Acknowledgments

- Built with [React](https://reactjs.org/)
- UI components from [Ant Design](https://ant.design/)
- Icons from [Ant Design Icons](https://ant.design/components/icon/)
- Bundled with [Vite](https://vitejs.dev/)

## 📞 Support

- **Documentation**: Check the `/docs` directory
- **Issues**: [GitHub Issues](https://github.com/rediacc/console/issues)
- **Discussions**: [GitHub Discussions](https://github.com/rediacc/console/discussions)

---

Made with ❤️ by the Rediacc team

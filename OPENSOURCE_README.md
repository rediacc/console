# Rediacc Console - Open Source Development Guide

Welcome to the Rediacc Console open-source project! This guide will help you get started with frontend development without needing to set up a local backend.

## 🚀 Quick Start for Open-Source Contributors

### Fastest Way - Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/rediacc/console.git
cd console

# Build and run with Docker - opens browser automatically!
./go sandbox-docker
```

That's it! The console will be running at http://localhost:8080 🎉

### Alternative - Local Development

If you prefer running locally with npm:

```bash
# Clone the repository
git clone https://github.com/rediacc/console.git
cd console

# Setup for sandbox development (no backend needed)
./go setup sandbox

# Start development with sandbox backend
./go sandbox
```

The console will automatically connect to `sandbox.rediacc.com` for backend services.

## 📋 Prerequisites

### For Docker Method (Recommended)
- Docker Desktop or Docker Engine
- Git

### For Local Development
- Node.js (v18 or higher)
- npm (v9 or higher)
- Git

## 🛠️ Development Modes

### Docker Sandbox Mode (Easiest)

One command to build, run, and open the console:

```bash
./go sandbox-docker
```

Options:
```bash
./go sandbox-docker --port=3000     # Use custom port
./go sandbox-docker --no-browser    # Don't auto-open browser
```

### Local Sandbox Mode

For development with hot-reload:

```bash
./go sandbox
```

This mode:
- Connects to sandbox.rediacc.com automatically
- No backend setup required
- Ideal for UI/UX development
- Shows warning when using sandbox (⚠️ Sandbox Environment)

### Local Development Mode

For contributors with a full local setup:

```bash
# Requires .env configuration with backend details
./go dev
```

This mode:
- Attempts localhost connection first
- Falls back to sandbox if localhost unavailable
- Requires backend configuration

## 🏗️ Building for Production

```bash
# Build for production deployment
REDIACC_BUILD_TYPE=RELEASE ./go build

# Build for development/testing
REDIACC_BUILD_TYPE=DEBUG ./go build
```

## 🔧 Environment Variables

### For Sandbox Mode (Automatic)
No configuration needed! The sandbox mode sets everything up automatically.

### For Local Development
Create a `.env` file in the parent directory:

```env
SYSTEM_HTTP_PORT=7322
SYSTEM_DOMAIN=localhost
```

### Build Types

- **DEBUG**: Development mode with sandbox fallback
- **RELEASE**: Production mode (uses same-domain /api)

## 📁 Project Structure

```
console/
├── src/               # Source code
│   ├── pages/        # Page components
│   ├── components/   # Reusable components
│   ├── services/     # API and business logic
│   └── api/          # API client configuration
├── playwright/       # E2E tests
├── public/           # Static assets
├── dist/             # Build output
└── go                # Development CLI tool
```

## 🧪 Running Tests

```bash
# Run all tests
./go test

# Run specific test file
./go test --file=test_user_login.py

# Run tests in headless mode
./go test --headless
```

## 📝 Making Contributions

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Start sandbox development**
   ```bash
   ./go sandbox
   ```

4. **Make your changes**
   - The dev server will hot-reload your changes
   - Test your changes thoroughly

5. **Run linting**
   ```bash
   ./go lint
   ```

6. **Commit your changes**
   ```bash
   git commit -m "feat: add new feature"
   ```

7. **Push and create a Pull Request**

## 🎨 UI Development Tips

### Component Development
- Use TypeScript for type safety
- Follow existing component patterns
- Use Ant Design components where possible
- Maintain consistent styling with design tokens

### API Integration
- The sandbox provides a fully functional API
- Check browser console for API endpoint information
- All API calls go through `src/api/client.ts`

### Styling
- Use the existing style constants in `src/utils/styleConstants.ts`
- Follow the design principles in `/context/design-principles.md`
- Refer to the style guide in `/context/style-guide.md`

## 🔍 Debugging

### Check Active Endpoint
The login page displays which backend is being used:
- "Local Development" - Using localhost
- "Sandbox Environment (DEBUG)" - Using sandbox.rediacc.com
- "Production" - Using same-domain /api

### Console Logs
Watch the browser console for connection information:
```
[API Connection] Build type: DEBUG
[API Connection] ⚠️ NOTICE: Localhost unavailable, using sandbox environment
[API] Connected to: Sandbox Environment (DEBUG)
```

## 🤝 Community

- **Issues**: [GitHub Issues](https://github.com/rediacc/console/issues)
- **Discussions**: [GitHub Discussions](https://github.com/rediacc/console/discussions)
- **Documentation**: [docs.rediacc.com](https://docs.rediacc.com)

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Need Help?

If you encounter any issues:

1. Check the console output for error messages
2. Verify you're running Node.js v18+
3. Try clearing node_modules and reinstalling: 
   ```bash
   rm -rf node_modules
   npm install
   ```
4. Check our [troubleshooting guide](OPENSOURCE_SETUP.md#troubleshooting)
5. Open an issue on GitHub

## 🎯 Common Tasks

### Start Development
```bash
./go sandbox-docker   # Docker mode (easiest)
./go sandbox          # Local npm development
./go dev             # With local backend
```

### Build Project
```bash
./go build           # Production build
```

### Run Tests
```bash
./go test            # All tests
./go lint            # Code linting
```

### Clean Project
```bash
./go clean           # Remove build artifacts
./go clean --docker  # Also remove Docker containers/images
```

### Docker Management
```bash
# After running ./go sandbox-docker:
docker logs -f rediacc-console-sandbox     # View logs
docker stop rediacc-console-sandbox        # Stop container
docker start rediacc-console-sandbox       # Restart container
docker rm -f rediacc-console-sandbox       # Remove container
```

Happy coding! 🚀
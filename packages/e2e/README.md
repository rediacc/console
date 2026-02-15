# E2E Tests

End-to-end tests for the Console web application using [Playwright](https://playwright.dev/).

## Prerequisites

- Backend services running (`./run.sh backend start`)
- Chromium installed (`npx playwright install chromium`)

## Quick Start

```bash
# From repo root — runs setup + auth tests against local backend
./run.sh test e2e --projects chromium

# Run a specific test file
./run.sh test e2e --projects chromium --test 01-auth/01-01-registration.test.ts

# Run a specific test by line number
./run.sh test e2e --projects chromium --test 01-auth/01-01-registration.test.ts:24

# Run with visible browser
./run.sh test e2e --projects chromium --headed

# Run with Playwright UI (interactive)
./run.sh test e2e --projects chromium --ui

# Run against external backend
./run.sh test e2e --projects chromium --backend https://xxx.trycloudflare.com
```

## Running from packages/e2e/

```bash
cd packages/e2e

# Run all tests (chromium)
npx playwright test --project=chromium

# Run a single test file
npx playwright test --project=chromium tests/01-auth/01-01-registration.test.ts

# Debug mode (step through with inspector)
npx playwright test --project=chromium --debug

# Interactive UI mode
npx playwright test --project=chromium --ui

# Generate test code by recording actions
npx playwright codegen http://localhost:3000/console/

# View last test report
npx playwright show-report reports/e2e
```

## Test Suites

Predefined suites in `test-suites.json`:

| Suite | Description |
|-------|-------------|
| `ci` | Auth tests only (registration + login) |
| `auth` | Authentication tests |
| `organization` | Full organization module |
| `users` | User management |
| `teams` | Team management |
| `access` | Access control |
| `machines` | VM/machine tests |
| `settings` | Settings tests |
| `full-e2e` | Curated full flow |

```bash
npm run test:suite ci
npm run test:suite full-e2e
```

## Directory Structure

```
tests/
  setup/           Global setup (user registration)
  helpers/         Shared test helpers (user, team)
  01-auth/         Registration & login
  02-organization/ Users, teams, access
  03-machines/     Machine CRUD & connectivity
  04-repositories/ Repository operations
  05-connection/   Desktop connection tests
  06-settings/     Dashboard & vault config
  07-storage/      Storage creation
  08-credentials/  Credential operations
  09-queue/        Queue operations
  10-audit/        Audit records
  electron/        Electron app tests
pages/             Page Object Models
src/
  base/            BaseTest, BasePage (extend these)
  utils/           Constants, env, retry, VM, screenshots, reporting
  helpers/         NavigationHelper
  setup/           Global state & teardown
```

## Environment Variables

Set in `.env` (copy from `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `http://localhost:7322` | API backend URL for Vite proxy |
| `E2E_BASE_URL` | `http://localhost:3000/console/` | Application URL |
| `TEST_VERIFICATION_CODE` | `AAA111` | Activation code (CI mode only) |
| `VM_DEPLOYMENT` | `false` | Enable VM-dependent tests |
| `PWSLOWMO` | — | Slow down browser actions (ms) |
| `E2E_HIGHLIGHT` | `false` | Show click/focus indicators in video |
| `STOP_ON_FAILURE` | `false` | Stop on first test failure |

## Browser Projects

| Project | Engine |
|---------|--------|
| `chromium` | Chromium |
| `firefox` | Firefox |
| `webkit` | WebKit/Safari |
| `msedge` | Edge |
| `resolution-1920x1080` | Chromium @ 1920x1080 |
| `resolution-1366x768` | Chromium @ 1366x768 |
| `galaxy-s24` | Mobile Android |
| `iphone-15-pro-max` | Mobile iOS |
| `electron-linux-x64` | Electron (Linux) |

## Writing Tests

Tests extend `BaseTest` which provides fixtures for screenshots, test data, and reporting:

```typescript
import { baseTest } from '../../src/base/BaseTest';

baseTest.describe('Feature Name', () => {
  baseTest('should do something', async ({ page }) => {
    await page.goto('/console/login');
    await page.fill('[data-testid="email"]', 'user@example.com');
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL(/dashboard/);
  });
});
```

Page objects live in `pages/` and extend `BasePage`:

```typescript
import { BasePage } from '../../src/base/BasePage';

export class LoginPage extends BasePage {
  readonly emailInput = this.page.locator('[data-testid="email"]');

  async login(email: string, password: string) {
    await this.emailInput.fill(email);
    // ...
  }
}
```

## Artifacts

After test runs:
- **Reports**: `reports/e2e/index.html` — open with `npx playwright show-report reports/e2e`
- **Videos**: `videos/` — recorded for all tests
- **Screenshots**: captured on each test
- **Traces**: `test-results/` — open with `npx playwright show-trace <trace.zip>`

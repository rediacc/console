# CLAUDE.md - Rediacc Console Key Notes

## Project Overview
This is the Rediacc web console application built with React 18, TypeScript, and Vite. It provides a web interface for managing backup infrastructure, teams, users, and system resources.

## Architecture
```
Frontend (React) → HTTP REST API → Middleware (.NET) → SQL Server
```

## Tech Stack
- **React 18** with TypeScript
- **Redux Toolkit** for client state management
- **React Query (TanStack Query)** for server state management
- **Ant Design 5** for UI components (exclusively - no custom components)
- **React Hook Form + Zod** for form validation
- **Axios** with interceptors for API calls with token rotation
- **@ant-design/charts** for data visualization
- **Monaco Editor** for JSON vault editing
- **Vite** for build tooling

## Authentication & Security

### Password Hashing
- Uses Web Crypto API for SHA-256 hashing in the browser
- Password hash format: Base64-encoded SHA-256 hash
- Example: `PrP+ZrMeO00Q+nC1ytSccRIpSvauTkdqHEBRVdRaoSE=`

### Token Rotation
- Implements token chaining mechanism
- Each API response includes `nextRequestCredential`
- Token automatically updated in Redux store and used for next request
- Token expiration: 24 hours

### Headers
- Initial auth: `Rediacc-UserEmail` and `Rediacc-UserHash`
- Subsequent requests: `Rediacc-RequestToken`

## Development Environment

### Quick Start
```bash
# Setup environment (one-time)
./go setup

# Start development server
./go dev

# Check status
./go status
```

### Middleware API
- Default URL: `http://localhost:8080/api`
- Must be running for the console to work
- Start with: `cd ../middleware && ./go start`

### Test Credentials (Development)
- **Email**: Any email (e.g., `test@example.com`)
- **Password**: Any password (e.g., `Admin123!`)
- **Activation Code**: `111111` (hardcoded in dev mode)

## Color Theme
- Primary color: Olive drab (`#556b2f`)
- Applied consistently across buttons, icons, and accents
- Matches the offers app theme

## Key Components

### Layouts
- `AuthLayout` - For login/register pages with animated tech background
- `MainLayout` - For authenticated pages with sidebar navigation

### Common Components
- `ResourceListView` - Reusable table view for resources
- `ResourceForm` - Reusable form component with validation
- `VaultConfigModal` - JSON editor for vault configuration

### API Client
- Located in `src/api/client.ts`
- Handles token rotation automatically
- Shows toast notifications for errors
- Redirects to login on 401

## Routing Structure
```
/login          - Login page
/register       - Registration page  
/               - Dashboard
/teams          - Team management
/users          - User management
/regions        - Region management
/bridges        - Bridge management (TODO)
/machines       - Machine management (TODO)
/repositories   - Repository management (TODO)
/storage        - Storage management (TODO)
/schedules      - Schedule management (TODO)
/queue          - Queue management
/permissions    - Permissions management (TODO)
```

## State Management

### Redux Slices
- `auth` - Authentication state (user, token, company)
- More slices to be added as needed

### React Query Keys
- Teams: `['teams']`
- Users: `['users']`, `['permissionGroups']`
- Regions: `['regions']`
- Queue: `['queueItems']`, `['queueFunctions']`

## Form Validation Schemas
All validation schemas are in `src/utils/validation.ts` using Zod

## Queue Functions
Comprehensive list of queue functions with categories:
- System Functions (os_setup, os_update, etc.)
- Database Functions (db_backup, db_restore, etc.)
- Migration Functions (v2p_*, p2v_*, etc.)
- Repository Functions (repo_snapshot, repo_restore, etc.)

## Build & Deployment

### Build for Production
```bash
./go build
```

### Create Release
```bash
./go release
```

Files are output to:
- `./bin/` - Local build directory
- `../bin/console/` - Root bin directory for nginx

## Testing

### API Testing
- `test-api.mjs` - Node.js script for API testing
- `test-browser.html` - Browser-based API testing

### Run Tests
```bash
./go test
```

## Pending Implementation
The following pages show "Coming Soon":
1. Bridges Management
2. Machines Management  
3. Repositories Management
4. Storage Management
5. Schedules Management
6. Permissions Management

These need to be implemented following the same patterns as Teams and Regions pages.

## Important Files
- `PLAN.md` - Original implementation specification
- `package.json` - Dependencies (must match PLAN.md exactly)
- `src/api/client.ts` - API client with token rotation
- `src/utils/validation.ts` - Form validation schemas
- `go` - Build and development script

## Notes
- Created: 2025-06-02
- NO additional packages beyond what's in PLAN.md
- Use Ant Design components exclusively
- Follow existing patterns for new features
- Test credentials can be created on demand
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
/organization   - Organization management (comprehensive resource management)
/users          - User management (Users & Permissions tabs)
/queue          - Queue management
/settings       - Company settings
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

### Function Definition Structure
Queue functions are centralized to avoid duplication:
- **Definitions**: `src/data/functions.json` - Contains all function definitions without translations
- **Service**: `src/services/functionsService.ts` - Provides localized function data
- **Hook**: `useLocalizedFunctions()` - Returns functions with translations applied
- **Translation**: Function names and descriptions are stored in i18n files (`locales/*/functions.json`)

### Function Categories
- machine (os_setup, hello, uninstall, repo_new)
- repository (repo_mount, repo_unmount, repo_up, etc.)
- backup (repo_push, repo_pull)
- network (map_socket)

### Usage
```typescript
import { useLocalizedFunctions } from '@/services/functionsService';

const { functions, categories, getFunction, getFunctionsByCategory } = useLocalizedFunctions();
```

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

## Implemented Features

All pages and features from PLAN.md have been implemented:

### Organization Management
1. ✅ Organization Management - Comprehensive resource management in a single unified interface
   - Teams & Resources tab: 
     - Teams table: Create/delete teams, view counts, select team
     - Resources section (shows when team selected):
       - Machines: Create/delete machines, assign to bridges, vault configuration
       - Repositories: Create/delete repositories, status tracking, vault configuration  
       - Storage: Create/delete storage, usage visualization, vault configuration
       - Schedules: Create/delete schedules, cron expressions, vault configuration
   - Regions & Infrastructure tab: 
     - Regions table: Create/delete regions, configure vault, view bridge count, select region
     - Bridges table: Shows bridges for selected region, create/delete bridges, configure vault

### User & Permission Management
2. ✅ User Management - Combined Users and Permissions management in tabbed interface
   - Permissions tab: Permission groups, assign permissions to groups
   - Users tab: User list, create, activate/deactivate, assign permission groups

### Company Settings
3. ✅ Company Settings - Subscription details, resource limits, usage analytics with charts
   - Subscription tab with billing information and cost breakdown
   - Resource limits tab with usage gauges
   - Usage analytics tab with trend charts

### Dashboard
4. ✅ Dashboard - Comprehensive analytics with @ant-design/charts
   - Resource distribution (Pie chart)
   - Queue activity trends (Line chart)
   - System health (Gauge chart)
   - Team comparisons (Bar chart)
   - Recent activity timeline

### Queue Management
5. ✅ Queue Management - View queue items, add functions, status tracking

All pages follow consistent patterns:
- Resource listing with filters
- Create/Edit/Delete operations
- Vault configuration with Monaco Editor
- Proper validation with React Hook Form + Zod
- Toast notifications for user feedback
- Loading states and error handling
- Data visualization with @ant-design/charts

## Important Files
- `PLAN.md` - Original implementation specification
- `package.json` - Dependencies (must match PLAN.md exactly)
- `src/api/client.ts` - API client with token rotation
- `src/utils/validation.ts` - Form validation schemas
- `go` - Build and development script

## Pricing Configuration

The pricing is now fetched from a centralized endpoint `/config/pricing.json`:
- **Service**: `src/api/pricingService.ts`
- **Caching**: 1 hour cache to reduce requests
- **Error Handling**: Prices are hidden if the endpoint is unavailable

Dashboard pricing behavior:
- Fetches pricing on component mount
- Shows prices only when successfully loaded
- Hides price displays if pricing cannot be fetched
- Maps plan codes (COMMUNITY, ADVANCED, etc.) to pricing keys

## Notes
- Created: 2025-06-02
- Updated: 2025-06-04 - Added centralized pricing
- Updated: 2025-06-10 - Added centralized function definitions
- NO additional packages beyond what's in PLAN.md
- Use Ant Design components exclusively
- Follow existing patterns for new features
- Test credentials can be created on demand
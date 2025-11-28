# Console Monorepo Restructure - Migration Plan

**Status:** PARTIALLY IMPLEMENTED
**Created:** 2025-11-27
**Last Updated:** 2025-11-27 (Updated with queue-vault package completion)

## Executive Summary

This document outlines the detailed plan to restructure the Rediacc console repository from its current confusing structure into a proper monorepo following industry standards (Babel, Jest, TypeScript projects).

### Current State Analysis

**Repository Structure:**
```
/home/muhammed/monorepo/console/
├── src/                          # React web application (395 TS files)
├── cli/                          # CLI application (30 TS files)
│   ├── src/
│   ├── package.json              # Separate CLI dependencies
│   └── tsconfig.json             # Paths reference ../src/core
├── .github/workflows/            # Separate CI jobs for web and CLI
├── package.json                  # Web dependencies
└── tsconfig.json                 # Web TypeScript config
```

**Problems Identified:**
1. ✗ Shared utilities are duplicated (errorParser.ts, queueFormatters.ts)
2. ✗ CLI references web code via path aliases (`@/core`)
3. ✗ No clear separation of shared vs web-specific vs CLI-specific code
4. ✗ GitHub Actions has separate jobs for CLI due to different package locations
5. ✗ No workspace configuration
6. ✗ Confusing developer experience

### Target State

```
/home/muhammed/monorepo/console/
├── packages/
│   ├── web/                      # React web application
│   │   ├── src/                  # Web-specific code
│   │   ├── package.json          # Web dependencies
│   │   ├── tsconfig.json         # Extends root config
│   │   └── vite.config.ts        # Vite config
│   ├── cli/                      # CLI application
│   │   ├── src/                  # CLI-specific code
│   │   ├── bin/                  # CLI executables
│   │   ├── package.json          # CLI dependencies
│   │   └── tsconfig.json         # Extends root config
│   └── shared/                   # Shared utilities (NEW)
│       ├── src/
│       │   ├── queue/            # Queue utilities
│       │   ├── types/            # Shared type definitions
│       │   └── index.ts          # Main exports
│       ├── package.json          # Shared dependencies
│       └── tsconfig.json         # Extends root config
├── .github/workflows/            # Updated workflows
├── package.json                  # Root workspace config
└── tsconfig.json                 # Base TypeScript config
```

---

## Implementation Status Update (2025-11-27)

### ✅ Completed: Queue Vault Package Consolidation

**Package Created:** `@rediacc/queue-vault` at `/console/packages/queue-vault/`

A critical first step toward the full monorepo migration has been completed. The heavily duplicated queue vault building logic (~650 lines) has been extracted into a shared, isomorphic package.

#### What Was Done:

1. **Created Shared Package** (`packages/queue-vault/`)
   - Extracted `QueueVaultBuilder` class from web console (source of truth)
   - Created platform-agnostic implementation with dependency injection
   - Built dual CJS + ESM + TypeScript definitions
   - Auto-sync mechanism for `functions.json` via prebuild script

2. **Integrated with Web Console**
   - Removed duplicate QueueVaultBuilder class (~390 lines)
   - Updated imports to use `@rediacc/queue-vault`
   - Created WebAdapter for browser-specific operations
   - Successfully building: ✅

3. **Integrated with CLI**
   - Removed duplicate vault building logic (~260 lines)
   - Removed hardcoded function requirements (20 functions)
   - CLI now has access to all 42+ functions from functions.json
   - Created NodeAdapter for Node.js-specific operations
   - Successfully building: ✅

#### Code Reduction:
- **Web console:** 868 → 475 lines (-393 lines, -45%)
- **CLI:** 324 → 203 lines (-121 lines, -37%)
- **Total duplication eliminated:** ~514 lines
- **New shared package:** 1 package with auto-generated functions.json

#### Key Benefits Already Realized:
- ✅ Single source of truth for queue vault logic
- ✅ Guaranteed consistency between web and CLI
- ✅ CLI gains 22+ additional functions automatically
- ✅ Type safety enforced across both platforms
- ✅ Platform-specific operations cleanly abstracted

#### Files Modified:
- Created: `/console/packages/queue-vault/` (entire package)
- Modified: `/console/src/core/services/queue.ts` (removed QueueVaultBuilder)
- Modified: `/console/cli/src/services/queue.ts` (removed duplicate logic)
- Modified: `/console/src/core/types/queue.ts` (re-exports shared types)
- Updated: `/console/package.json` & `/console/cli/package.json` (added dependency)

#### Remaining Work for Full Monorepo:
This completes one major piece of shared functionality. The remaining work includes:
- [ ] Extract error parsing utilities (shared between web/CLI)
- [ ] Extract queue formatting utilities
- [ ] Extract shared type definitions
- [ ] Restructure into full packages/ layout
- [ ] Update GitHub workflows
- [ ] Update documentation

---

## Phase 1: Analysis Complete ✅

### 1.1 File Inventory

**Web Package (packages/web/)**
- 395 TypeScript files in src/
- Build output: dist/
- Dependencies: React ecosystem, Ant Design, Redux, etc.

**CLI Package (packages/cli/)**
- 30 TypeScript files in cli/src/
- Build output: cli/dist/
- Dependencies: Commander, Chalk, Inquirer, etc.
- Currently references `@/core` from ../src/core

**Identified Build Artifacts:**
- Web: `dist/` (from Vite build)
- CLI: `cli/dist/` (from TypeScript compiler)

### 1.2 Dependencies Analysis

#### Root package.json (Web dependencies)
```json
{
  "dependencies": {
    "@ant-design/charts": "^2.6.6",
    "@ant-design/icons": "^6.1.0",
    "@hookform/resolvers": "^5.2.2",
    "@opentelemetry/...": "...",
    "@reduxjs/toolkit": "^2.10.1",
    "@tanstack/react-query": "^5.90.10",
    "antd": "^5.28.0",
    "axios": "^1.13.2",
    "react": "^19.2.0",
    "react-dom": "^19.2.0",
    "react-router-dom": "^7.9.6",
    "zod": "^4.1.13",
    // ... more React-specific
  },
  "devDependencies": {
    "@types/react": "^19.2.7",
    "@vitejs/plugin-react": "^5.1.1",
    "eslint": "^9.39.1",
    "typescript": "^5.9.3",
    "vite": "^7.2.4"
  }
}
```

#### CLI package.json
```json
{
  "dependencies": {
    "axios": "^1.7.9",           // SHARED with web (different version!)
    "chalk": "^5.4.1",           // CLI-only
    "cli-table3": "^0.6.5",      // CLI-only
    "commander": "^13.0.0",      // CLI-only
    "inquirer": "^12.3.2",       // CLI-only
    "ora": "^8.1.1",             // CLI-only
    "yaml": "^2.7.0",            // CLI-only
    "zod": "^3.24.1"             // SHARED with web (different version!)
  },
  "devDependencies": {
    "@types/node": "^22.10.2",
    "tsx": "^4.19.2",
    "typescript": "^5.7.2",      // Different from web (5.9.3)
    "vitest": "^2.1.8"
  }
}
```

**Dependency Conflicts to Resolve:**
- `axios`: Web uses 1.13.2, CLI uses 1.7.9 (OLDER in CLI!)
- `zod`: Web uses 4.1.13, CLI uses 3.24.1 (major version mismatch!)
- `typescript`: Web uses 5.9.3, CLI uses 5.7.2

**Recommendation:** Use latest versions in shared package, update both packages

### 1.3 Shared Code Identified

#### Duplicated Error Parsing Logic
**File 1:** `src/core/utils/queue-status.ts` (Web)
- Lines 230-431: Error parsing functions
- `extractFirstError()`, `extractAllErrors()`, `parseFailureReason()`
- Types: `ErrorSeverity`, `ParsedError`, `ParsedErrorResult`

**File 2:** `cli/src/utils/errorParser.ts` (CLI)
- Lines 1-124: Duplicate error parsing (standalone version)
- Same types and functions with slight formatting differences

**Consolidation:** Move to `packages/shared/src/queue/error-parser.ts`

#### Queue Formatting Utilities
**File 1:** `src/core/utils/queue-status.ts` (Web)
- Lines 1-229: Queue status utilities
- `formatAge()`, status configs, priority configs
- Filter functions for queue items

**File 2:** `cli/src/utils/queueFormatters.ts` (CLI)
- Lines 1-203: CLI-specific formatters (uses Chalk for colors)
- `formatAge()` duplicated (lines 21-25)
- Status and priority formatting adapted for terminal

**Consolidation Strategy:**
- Core logic → `packages/shared/src/queue/queue-status.ts`
- CLI-specific formatting → Keep in `packages/cli/src/utils/formatters.ts`
- Web-specific formatting → Keep in `packages/web/src/utils/formatters.ts`

#### Shared Type Definitions
**From src/types/index.ts (Web):**
- `Machine`, `Repository`, `PluginContainer`
- `RediaccConfig`, `MachineAssignmentType`

**From cli/src/types/index.ts (CLI):**
- `IStorageProvider`, `ICryptoProvider` (interfaces)
- `OutputFormat`, `CliConfig` (CLI-specific)

**Consolidation:**
- Core domain types → `packages/shared/src/types/domain.ts`
- CLI-specific types → Stay in `packages/cli/src/types/`
- Web-specific types → Stay in `packages/web/src/types/`

### 1.4 Import Path Analysis

**Current CLI imports from web:**
```typescript
// cli/tsconfig.json
"paths": {
  "@/core": ["../src/core"],
  "@/core/*": ["../src/core/*"]
}
```

**Currently, CLI does NOT import from web core!**
- Error parser is duplicated (standalone version)
- Queue formatters reimplemented for CLI
- No actual cross-package imports found

**Post-migration imports:**
```typescript
// In packages/cli/src/
import { parseFailureReason } from '@rediacc/shared/queue'
import { formatAge } from '@rediacc/shared/queue'

// In packages/web/src/
import { parseFailureReason } from '@rediacc/shared/queue'
import type { Machine } from '@rediacc/shared/types'
```

### 1.5 GitHub Workflows Analysis

**Current CI Jobs (.github/workflows/ci.yml):**
1. `lint` - Runs `npm run lint` (web only)
2. `type-check` - Runs `npx tsc --noEmit` (web only)
3. `cli-check` - Separate job:
   - `working-directory: cli`
   - `cache-dependency-path: cli/package-lock.json`
   - `npm ci` in cli/
   - `npm run build` in cli/
4. `build` - Web build (DEBUG & RELEASE matrix)
5. `security-scan` - npm audit (root only)
6. `bundle-size` - Web bundle analysis
7. `ci-summary` - Depends on all jobs

**Post-migration changes:**
- Install: `npm ci` at root (installs all workspaces)
- Lint: `npm run lint --workspaces`
- Type-check: `npm run build --workspaces` (builds all packages)
- Build: Keep separate web build job
- CLI check: Integrated into workspace build
- Security scan: Run for all packages

### 1.6 Configuration Files Inventory

**Root level:**
- `package.json` → Will become workspace root config
- `tsconfig.json` → Will become base config
- `tsconfig.node.json` → Vite-specific, move to packages/web/
- `vite.config.ts` → Move to packages/web/
- `eslint.config.js` → Keep at root, configure for all packages

**CLI level:**
- `cli/package.json` → Move to packages/cli/package.json
- `cli/tsconfig.json` → Move to packages/cli/tsconfig.json (update extends)

---

## Phase 2: Detailed Migration Plan

### 2.1 File Move Mapping

#### Shared Package Creation
```
CREATE packages/shared/
├── src/
│   ├── queue/
│   │   ├── error-parser.ts          # From src/core/utils/queue-status.ts (lines 230-431)
│   │   ├── queue-status.ts          # From src/core/utils/queue-status.ts (lines 1-229)
│   │   └── index.ts                 # Exports all queue utilities
│   ├── types/
│   │   ├── domain.ts                # Machine, Repository, etc. from src/types/index.ts
│   │   └── index.ts                 # Re-exports
│   └── index.ts                     # Main entry point
├── package.json                      # New
├── tsconfig.json                     # New (extends ../../tsconfig.json)
└── README.md                         # Package documentation
```

#### Web Package Migration
```
MOVE src/ → packages/web/src/
MOVE vite.config.ts → packages/web/vite.config.ts
MOVE tsconfig.node.json → packages/web/tsconfig.node.json
MOVE index.html → packages/web/index.html
MOVE public/ → packages/web/public/
MOVE styles/ → packages/web/styles/

CREATE packages/web/package.json     # From root package.json dependencies
UPDATE packages/web/tsconfig.json    # From root tsconfig.json, update paths
UPDATE packages/web/vite.config.ts   # Update import paths, __dirname references

REMOVE from packages/web/src/core/utils/queue-status.ts:
  - Lines 230-431 (error parsing - now in shared)
  - Keep web-specific utilities
```

#### CLI Package Migration
```
MOVE cli/src/ → packages/cli/src/
MOVE cli/bin/ → packages/cli/bin/
MOVE cli/package.json → packages/cli/package.json
MOVE cli/tsconfig.json → packages/cli/tsconfig.json

UPDATE packages/cli/tsconfig.json:
  - Change "rootDir": "./src" to stay same
  - Remove "@/core" paths
  - Add shared package reference

REMOVE packages/cli/src/utils/errorParser.ts  # Replaced by shared
UPDATE packages/cli/src/utils/queueFormatters.ts:
  - Import parseFailureReason from @rediacc/shared
  - Keep CLI-specific formatting (Chalk colors)
```

### 2.2 Package.json Structure

#### Root package.json
```json
{
  "name": "rediacc-console-monorepo",
  "version": "1.0.0",
  "private": true,
  "workspaces": [
    "packages/*"
  ],
  "scripts": {
    "build": "npm run build --workspaces --if-present",
    "build:web": "npm run build -w @rediacc/web",
    "build:cli": "npm run build -w @rediacc/cli",
    "build:shared": "npm run build -w @rediacc/shared",
    "dev": "npm run dev -w @rediacc/web",
    "dev:cli": "npm run dev -w @rediacc/cli",
    "lint": "npm run lint --workspaces --if-present",
    "lint:web": "npm run lint -w @rediacc/web",
    "lint:cli": "npm run lint -w @rediacc/cli",
    "test": "npm run test --workspaces --if-present",
    "clean": "npm run clean --workspaces --if-present && rm -rf node_modules",
    "typecheck": "tsc --build"
  },
  "devDependencies": {
    "@types/node": "^22.10.2",
    "eslint": "^9.39.1",
    "typescript": "^5.9.3"
  }
}
```

#### packages/shared/package.json
```json
{
  "name": "@rediacc/shared",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "exports": {
    ".": "./dist/index.js",
    "./queue": "./dist/queue/index.js",
    "./types": "./dist/types/index.js"
  },
  "scripts": {
    "build": "tsc",
    "clean": "rm -rf dist",
    "lint": "echo 'No linting configured for shared package yet'"
  },
  "dependencies": {
    "zod": "^4.1.13"
  },
  "devDependencies": {
    "typescript": "^5.9.3"
  }
}
```

#### packages/web/package.json
```json
{
  "name": "@rediacc/web",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "lint": "eslint src --ext .js,.jsx,.ts,.tsx"
  },
  "dependencies": {
    "@rediacc/shared": "workspace:*",
    "@ant-design/charts": "^2.6.6",
    "@ant-design/icons": "^6.1.0",
    // ... all current web dependencies ...
    "axios": "^1.13.2",
    "react": "^19.2.0",
    "react-dom": "^19.2.0",
    "zod": "^4.1.13"
  },
  "devDependencies": {
    "@types/react": "^19.2.7",
    "@vitejs/plugin-react": "^5.1.1",
    "typescript": "^5.9.3",
    "vite": "^7.2.4"
  }
}
```

#### packages/cli/package.json
```json
{
  "name": "@rediacc/cli",
  "version": "0.2.93",
  "private": false,
  "type": "module",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "bin": {
    "rdc": "./bin/rdc"
  },
  "scripts": {
    "build": "tsc",
    "dev": "tsx src/index.ts",
    "start": "node dist/index.js",
    "test": "vitest",
    "lint": "eslint src --ext .ts",
    "clean": "rm -rf dist"
  },
  "dependencies": {
    "@rediacc/shared": "workspace:*",
    "axios": "^1.13.2",
    "chalk": "^5.4.1",
    "cli-table3": "^0.6.5",
    "commander": "^13.0.0",
    "inquirer": "^12.3.2",
    "ora": "^8.1.1",
    "yaml": "^2.7.0",
    "zod": "^4.1.13"
  },
  "devDependencies": {
    "@types/inquirer": "^9.0.7",
    "@types/node": "^22.10.2",
    "tsx": "^4.19.2",
    "typescript": "^5.9.3",
    "vitest": "^2.1.8"
  }
}
```

### 2.3 TypeScript Configuration

#### Root tsconfig.json (Base config)
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "lib": ["ES2020"],
    "moduleResolution": "bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "composite": true,
    "incremental": true
  },
  "references": [
    { "path": "./packages/shared" },
    { "path": "./packages/web" },
    { "path": "./packages/cli" }
  ]
}
```

#### packages/shared/tsconfig.json
```json
{
  "extends": "../../tsconfig.json",
  "compilerOptions": {
    "outDir": "./dist",
    "rootDir": "./src",
    "composite": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

#### packages/web/tsconfig.json
```json
{
  "extends": "../../tsconfig.json",
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable", "WebWorker"],
    "types": ["vite/client"],
    "jsx": "react-jsx",
    "noEmit": true,
    "isolatedModules": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"],
  "references": [
    { "path": "../shared" },
    { "path": "./tsconfig.node.json" }
  ]
}
```

#### packages/cli/tsconfig.json
```json
{
  "extends": "../../tsconfig.json",
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "lib": ["ES2022"],
    "outDir": "./dist",
    "rootDir": "./src",
    "composite": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "**/*.test.ts"],
  "references": [
    { "path": "../shared" }
  ]
}
```

### 2.4 Import Path Migration Strategy

#### Step 1: Create mapping table
```
OLD PATH (Web)                                   → NEW PATH
--------------------------------------------------------------------
src/core/utils/queue-status                      → @rediacc/shared/queue
src/types/index (Machine, Repository)           → @rediacc/shared/types

OLD PATH (CLI)                                   → NEW PATH
--------------------------------------------------------------------
./utils/errorParser                              → @rediacc/shared/queue
./utils/queueFormatters (formatAge)              → @rediacc/shared/queue
@/core/utils/queue-status (if used)              → @rediacc/shared/queue
```

#### Step 2: Files requiring import updates

**Web Package:**
```
packages/web/src/pages/queue/**/*.tsx
packages/web/src/components/**/Queue*.tsx
packages/web/src/services/queue.ts
```

Search pattern: `from ['"]@/core/utils/queue-status['"]`
Replace with: `from '@rediacc/shared/queue'`

**CLI Package:**
```
packages/cli/src/commands/queue.ts
packages/cli/src/services/queue.ts
packages/cli/src/utils/queueFormatters.ts
```

Search pattern: `from ['"]\\.\\/utils\\/errorParser['"]`
Replace with: `from '@rediacc/shared/queue'`

### 2.5 GitHub Workflows Update

**Updated .github/workflows/ci.yml:**
```yaml
jobs:
  lint:
    name: ✨ Code Quality - Lint
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v5

      - name: Setup Node.js
        uses: actions/setup-node@v6
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run ESLint (All Packages)
        run: npm run lint

  type-check:
    name: 🔍 Code Quality - TypeScript
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v5

      - name: Setup Node.js
        uses: actions/setup-node@v6
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Build all packages (type check)
        run: npm run build

  # REMOVE cli-check job - now covered by workspace build

  build:
    name: 🏗️ Build - Web (${{ matrix.build-type }})
    runs-on: ubuntu-latest
    strategy:
      matrix:
        build-type: [DEBUG, RELEASE]
    steps:
      - name: Checkout code
        uses: actions/checkout@v5

      - name: Setup Node.js
        uses: actions/setup-node@v6
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Build web application
        env:
          REDIACC_BUILD_TYPE: ${{ matrix.build-type }}
        run: npm run build:web

  ci-summary:
    name: ✅ CI Summary
    runs-on: ubuntu-latest
    needs: [lint, type-check, build, security-scan, bundle-size]
    # ... rest of summary job
```

**Key changes:**
1. Remove separate `cli-check` job
2. Update `lint` to run workspace lint
3. Update `type-check` to build all packages
4. Single `npm ci` installs all workspaces
5. Remove `working-directory` and `cache-dependency-path` for CLI

---

## Phase 3: Step-by-Step Execution Plan

### Prerequisites Checklist
- [ ] Current branch is up-to-date with main
- [ ] All tests passing
- [ ] No uncommitted changes
- [ ] PR #191 is merged (or plan to rebase)

### Step 1: Create Shared Package (DO THIS FIRST!)

```bash
# 1.1 Create directory structure
mkdir -p packages/shared/src/{queue,types}

# 1.2 Create package.json
cat > packages/shared/package.json << 'EOF'
{
  "name": "@rediacc/shared",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "exports": {
    ".": "./dist/index.js",
    "./queue": "./dist/queue/index.js",
    "./types": "./dist/types/index.js"
  },
  "scripts": {
    "build": "tsc",
    "clean": "rm -rf dist"
  },
  "dependencies": {
    "zod": "^4.1.13"
  },
  "devDependencies": {
    "typescript": "^5.9.3"
  }
}
EOF

# 1.3 Create tsconfig.json
cat > packages/shared/tsconfig.json << 'EOF'
{
  "extends": "../../tsconfig.json",
  "compilerOptions": {
    "outDir": "./dist",
    "rootDir": "./src",
    "composite": true,
    "declaration": true,
    "declarationMap": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
EOF
```

### Step 2: Extract and Move Shared Code

```bash
# 2.1 Create error parser in shared package
# Extract lines 230-431 from src/core/utils/queue-status.ts
# This includes: ErrorSeverity, ParsedError, ParsedErrorResult,
# extractFirstError, extractAllErrors, parseFailureReason, etc.

# 2.2 Create queue status utilities in shared package
# Extract lines 1-229 from src/core/utils/queue-status.ts
# This includes: status configs, formatAge, filter functions, etc.

# 2.3 Create shared type definitions
# Extract domain types from src/types/index.ts
```

**Files to create:**
- `packages/shared/src/queue/error-parser.ts`
- `packages/shared/src/queue/queue-status.ts`
- `packages/shared/src/queue/index.ts` (exports)
- `packages/shared/src/types/domain.ts`
- `packages/shared/src/types/index.ts` (exports)
- `packages/shared/src/index.ts` (main entry)

### Step 3: Update Root Configuration

```bash
# 3.1 Update root package.json
# Add workspaces configuration
# Update scripts

# 3.2 Update root tsconfig.json
# Add project references
# Make it a base config

# 3.3 Run install to set up workspaces
npm install

# 3.4 Build shared package
cd packages/shared
npm run build
cd ../..
```

### Step 4: Migrate Web Package

```bash
# 4.1 Create web package directory
mkdir -p packages/web

# 4.2 Move web files
git mv src packages/web/
git mv vite.config.ts packages/web/
git mv tsconfig.node.json packages/web/
git mv index.html packages/web/
git mv public packages/web/
git mv styles packages/web/

# 4.3 Create web package.json
# Copy dependencies from root package.json
# Add @rediacc/shared dependency

# 4.4 Create web tsconfig.json
# Copy from root, extend base config

# 4.5 Update web vite.config.ts
# Fix __dirname references
# Update paths

# 4.6 Remove duplicated code from web
# Delete error parsing from src/core/utils/queue-status.ts (lines 230-431)

# 4.7 Update imports in web
# Find all imports of queue-status utilities
# Replace with @rediacc/shared/queue
```

### Step 5: Migrate CLI Package

```bash
# 5.1 Create CLI package directory
mkdir -p packages/cli

# 5.2 Move CLI files
git mv cli/src packages/cli/
git mv cli/bin packages/cli/
git mv cli/package.json packages/cli/
git mv cli/tsconfig.json packages/cli/

# 5.3 Update CLI package.json
# Add @rediacc/shared dependency
# Update dependency versions

# 5.4 Update CLI tsconfig.json
# Remove @/core paths
# Add shared package reference

# 5.5 Remove duplicated CLI code
git rm packages/cli/src/utils/errorParser.ts

# 5.6 Update imports in CLI
# Update queueFormatters.ts to import from shared
# Update commands/queue.ts
```

### Step 6: Update All Import Statements

**Web package imports:**
```bash
# Find files importing queue-status
grep -r "from ['\""]@/core/utils/queue-status" packages/web/src/

# Update to:
# from '@rediacc/shared/queue'
```

**CLI package imports:**
```bash
# Find files importing errorParser
grep -r "from ['\""]\\.\\/utils\\/errorParser" packages/cli/src/

# Update to:
# from '@rediacc/shared/queue'
```

### Step 7: Update GitHub Workflows

```bash
# Edit .github/workflows/ci.yml
# - Remove cli-check job
# - Update install steps
# - Update lint to use workspace command
# - Update type-check to build all packages
```

### Step 8: Testing & Validation

```bash
# 8.1 Install all dependencies
npm ci

# 8.2 Build all packages
npm run build

# 8.3 Run linting
npm run lint

# 8.4 Test web development server
npm run dev:web
# Navigate to queue pages, verify error display works

# 8.5 Test CLI
npm run build:cli
cd packages/cli
node dist/index.js queue list --help
# Test queue trace command with errors

# 8.6 Verify no broken imports
# Check TypeScript compilation succeeds
# No "Cannot find module" errors
```

### Step 9: Cleanup

```bash
# 9.1 Remove old directories (after verifying migration worked)
rm -rf src/
rm -rf cli/
rm vite.config.ts
rm tsconfig.node.json
rm index.html
rm -rf public/
rm -rf styles/

# 9.2 Update .gitignore
cat >> .gitignore << 'EOF'

# Monorepo packages
packages/*/dist
packages/*/node_modules
EOF

# 9.3 Update README.md
# Document new monorepo structure
# Update build/development instructions
```

### Step 10: Final Verification

```bash
# 10.1 Clean install
rm -rf node_modules packages/*/node_modules
npm ci

# 10.2 Build from scratch
npm run build

# 10.3 Run full CI locally (if possible)
# Verify all GitHub Actions steps work

# 10.4 Create test commit
git add .
git commit -m "refactor: restructure console into monorepo packages"

# 10.5 Push to test branch
git push origin HEAD:test/monorepo-restructure
```

---

## Phase 4: Risk Assessment & Mitigation

### High-Risk Areas

**1. Import Path Breakage**
- **Risk:** Missing imports after migration
- **Mitigation:**
  - Create comprehensive search/replace mapping
  - Build all packages before committing
  - Use TypeScript compiler to catch errors
  - Test both web and CLI thoroughly

**2. Dependency Version Conflicts**
- **Risk:** axios/zod version mismatches cause runtime errors
- **Mitigation:**
  - Use latest compatible versions
  - Test both web and CLI after install
  - Check for breaking changes in release notes

**3. Build System Changes**
- **Risk:** CI fails due to workflow changes
- **Mitigation:**
  - Test CI workflow in test branch first
  - Keep old workflow as backup
  - Monitor CI run carefully

**4. CLI Binary Breakage**
- **Risk:** CLI executable path changes break user installations
- **Mitigation:**
  - Keep bin/ path structure identical
  - Test CLI installation process
  - Verify rdc command still works

### Medium-Risk Areas

**1. Vite Configuration**
- **Risk:** Build fails due to path changes
- **Mitigation:**
  - Update __dirname references carefully
  - Test dev server and production build
  - Verify asset loading

**2. ESLint Configuration**
- **Risk:** Linting fails or misses files
- **Mitigation:**
  - Keep root eslint.config.js
  - Test with --debug flag
  - Verify all packages are linted

### Low-Risk Areas

**1. Documentation**
- **Risk:** README outdated
- **Mitigation:** Update after successful migration

**2. Git History**
- **Risk:** File history lost
- **Mitigation:** Use git mv instead of rm/cp

---

## Success Criteria Checklist

### Build & Compilation
- [ ] `npm ci` succeeds at root
- [ ] `npm run build` builds all packages without errors
- [ ] `npm run build:shared` produces dist/ with .js and .d.ts files
- [ ] `npm run build:web` produces dist/index.html and assets
- [ ] `npm run build:cli` produces dist/index.js and CLI executable

### Code Quality
- [ ] `npm run lint` passes for all packages
- [ ] `npm run typecheck` passes (tsc --build)
- [ ] No TypeScript compilation errors
- [ ] No "Cannot find module" errors

### Functionality Testing
- [ ] Web dev server starts: `npm run dev:web`
- [ ] Queue page loads in browser
- [ ] Error display with severity badges works
- [ ] CLI help works: `packages/cli/bin/rdc --help`
- [ ] CLI queue list works: `packages/cli/bin/rdc queue list`
- [ ] CLI queue trace parses errors correctly

### CI/CD
- [ ] GitHub Actions CI passes on test branch
- [ ] All workflow jobs succeed
- [ ] No workflow errors or warnings
- [ ] Bundle size analysis completes

### Code Organization
- [ ] No duplicated code between web and CLI
- [ ] Shared utilities in packages/shared/
- [ ] Clear package boundaries
- [ ] Import paths use workspace references

### Git & Repository
- [ ] File history preserved (git mv used)
- [ ] .gitignore updated
- [ ] README.md updated with new structure
- [ ] Migration documented

---

## Rollback Plan

If migration fails:

```bash
# 1. Identify the issue
# 2. Document the error

# 3. Rollback to previous state
git reset --hard <commit-before-migration>

# 4. Or revert specific commit
git revert <migration-commit-hash>

# 5. Force push if needed (only on test branch!)
git push origin HEAD --force
```

**Rollback checklist:**
- [ ] Backup current state before rollback
- [ ] Document what went wrong
- [ ] Update migration plan with lessons learned
- [ ] Plan fix before retrying

---

## Post-Migration Tasks

### Documentation Updates
- [ ] Update root README.md with monorepo structure
- [ ] Create packages/shared/README.md
- [ ] Update packages/web/README.md (if exists)
- [ ] Update packages/cli/README.md
- [ ] Update CONTRIBUTING.md (if exists)

### Developer Experience
- [ ] Add workspace commands to package.json
- [ ] Create development guide for monorepo
- [ ] Update VS Code settings (if needed)
- [ ] Test workspace IntelliSense

### Future Improvements
- [ ] Consider using Turborepo or Nx for better caching
- [ ] Add changesets for version management
- [ ] Consider separate lint configs per package
- [ ] Add shared test utilities package if needed

---

## Timeline Estimate

**Phase 1: Preparation** (Already complete)
- Analysis and planning: ✅ Complete

**Phase 2: Execution**
- Shared package creation: 30 minutes
- Web package migration: 1 hour
- CLI package migration: 45 minutes
- Import path updates: 1-2 hours
- GitHub workflow updates: 30 minutes
- Testing: 1-2 hours

**Phase 3: Verification & Cleanup**
- Full testing: 1 hour
- Documentation: 1 hour
- Final review: 30 minutes

**Total estimated time:** 6-9 hours (can be done in 1-2 days)

---

## Questions & Clarifications Needed

None at this time. Plan is ready for execution.

---

## Appendix

### A. Shared Package Exports Structure

```typescript
// packages/shared/src/index.ts
export * from './queue'
export * from './types'

// packages/shared/src/queue/index.ts
export * from './error-parser'
export * from './queue-status'

// packages/shared/src/types/index.ts
export * from './domain'
```

### B. Dependency Version Resolution

**Recommended versions for shared dependencies:**
- `axios`: ^1.13.2 (use web version, update CLI)
- `zod`: ^4.1.13 (use web version, update CLI - MAJOR BUMP!)
- `typescript`: ^5.9.3 (use web version, update CLI)

**Action required:**
- Test CLI with zod 4.x (check for breaking changes from 3.x)
- Update CLI axios to 1.13.2

### C. File Count Summary

**Before migration:**
- Root package files: ~15
- Web source files: 395 .ts/.tsx
- CLI source files: 30 .ts
- Total managed files: ~440

**After migration:**
- Root config files: ~8
- packages/shared: ~10 files
- packages/web: ~400 files
- packages/cli: ~30 files
- Total managed files: ~448 (slight increase due to new package configs)

### D. Build Output Structure

```
/home/muhammed/monorepo/console/
├── packages/
│   ├── shared/
│   │   └── dist/                 # TypeScript compiled output
│   │       ├── queue/
│   │       ├── types/
│   │       └── index.js
│   ├── web/
│   │   └── dist/                 # Vite build output
│   │       ├── index.html
│   │       └── assets/
│   └── cli/
│       └── dist/                 # TypeScript compiled output
│           └── index.js
└── node_modules/                 # Shared dependencies
```

---

**End of Migration Plan**

*This plan is ready for review and execution. All analysis complete.*

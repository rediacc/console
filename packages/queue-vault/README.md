# @rediacc/queue-vault

Shared queue vault building logic for Rediacc Console Web and CLI.

## Overview

This package provides isomorphic (browser + Node.js) queue vault building functionality that was previously duplicated between the web console and CLI.

## Features

- **Platform-agnostic**: Works in both browser and Node.js environments
- **Type-safe**: Full TypeScript support with shared type definitions
- **Complete function definitions**: Includes all 42+ queue functions
- **Dependency injection**: Platform-specific operations (base64, API URL) are injected

## Installation

This is a local package in the monorepo. It's automatically linked via:

```bash
npm install
```

## Usage

### Web Console (Browser)

```typescript
import { QueueVaultBuilder, type QueueVaultBuilderConfig } from '@rediacc/queue-vault'

const builderConfig: QueueVaultBuilderConfig = {
  getApiUrl: () => `${window.location.origin}/api`,
  encodeBase64: (value: string) => btoa(value),
}

const builder = new QueueVaultBuilder(builderConfig)
const vaultJson = await builder.buildQueueVault(context)
```

### CLI (Node.js)

```typescript
import { QueueVaultBuilder, type QueueVaultBuilderConfig } from '@rediacc/queue-vault'

const builderConfig: QueueVaultBuilderConfig = {
  getApiUrl: () => apiClient.getApiUrl(),
  encodeBase64: (value: string) => Buffer.from(value, 'utf-8').toString('base64'),
}

const builder = new QueueVaultBuilder(builderConfig)
const vaultJson = await builder.buildQueueVault(context)
```

## Development

### Building

```bash
npm run build
```

This will:
1. Auto-sync `functions.json` from `/console/src/core/data/functions.json`
2. Build CommonJS output to `dist/cjs/`
3. Build ES Modules output to `dist/esm/`
4. Generate TypeScript definitions to `dist/types/`

### Syncing Function Definitions

The `functions.json` file is automatically copied from the main source during build:

```bash
npm run sync-functions  # Manual sync if needed
```

**Important**: The `src/data/functions.json` file is gitignored and auto-generated. Always update the source file at `/console/src/core/data/functions.json`.

## Package Structure

```
src/
├── types/           # Shared TypeScript type definitions
│   ├── vault.ts     # VaultData, VaultContextData, etc.
│   └── requirements.ts  # QueueRequestContext, FunctionRequirements
├── builders/        # Core vault building logic
│   └── QueueVaultBuilder.ts
├── utils/           # Utility functions
│   ├── json.ts      # minifyJSON
│   └── validation.ts  # isBase64, getParamArray, etc.
└── data/            # Function definitions
    └── functions.json  # Auto-synced from source (gitignored)
```

## Exported Types

- `QueueRequestContext` - Context for building a queue vault
- `FunctionRequirements` - Required resources for a function
- `VaultData` - Generic vault data type
- `VaultContextData` - Complete vault context structure
- `StorageSystemContextData` - Storage system configuration
- `QueueVaultBuilderConfig` - Configuration for platform adapters

## Exported Functions

- `QueueVaultBuilder` - Main vault builder class
- `minifyJSON` - JSON minification utility
- `isBase64` - Base64 validation
- `getParamArray` - Extract array parameters
- `getParamValue` - Extract string parameters
- `FUNCTION_REQUIREMENTS` - Complete function requirements data

## Version

Current version: 1.0.0
